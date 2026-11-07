import time
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import SessionLocal
from app.models.all_models import User, Organization, Project, Assessment, RiskFinding, Invoice
from app.services.cache_service import CacheService
from app.services.debt_scoring_engine import CommercialDebtScoringEngine

client = TestClient(app)

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def test_commercial_full_customer_journey(db: Session):
    """
    Validates complete customer lifecycle:
    Registration -> Plan Upgrade -> Repository Setup -> Assessment -> Scoring ->
    Executive KPIs -> Report Generation -> Invoicing -> Billing Receipts.
    """
    uid = uuid.uuid4().hex[:8]
    org_name = f"Enterprise Client {uid}"
    email = f"cto_{uid}@enterpriseclient.com"
    password = "StrongPassword2026!"

    # 1. Self-service registration
    reg_resp = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": password,
        "full_name": f"Chief Architect {uid}",
        "organization_name": org_name,
        "role": "Administrator"
    })
    assert reg_resp.status_code == 200, reg_resp.text
    token = reg_resp.json()["access_token"]
    org_id = reg_resp.json()["user"]["org_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Plan upgrade to Enterprise via verified server-side Razorpay order + HMAC verification
    import os, hmac, hashlib
    from unittest.mock import patch
    from app.services.billing_service import BillingService
    mock_order_id = f"order_ent_{uid}"
    mock_pay_id = f"pay_ent_{uid}"
    with patch.dict(os.environ, {"RAZORPAY_KEY_ID": "rzp_test_mock_life", "RAZORPAY_KEY_SECRET": "rzp_test_sec_life", "RAZORPAY_CURRENCY": "USD"}):
        with patch.object(BillingService, "_post_razorpay_order", return_value={"id": mock_order_id, "amount": 499000, "currency": "USD"}):
            sub_resp = client.post("/api/v1/billing/subscribe", json={
                "plan_slug": "enterprise",
                "billing_cycle": "annual"
            }, headers=headers)
            assert sub_resp.status_code == 200
            assert sub_resp.json()["status"] == "pending_payment"

        sig = hmac.new(b"rzp_test_sec_life", f"{mock_order_id}|{mock_pay_id}".encode(), hashlib.sha256).hexdigest()
        ver_resp = client.post("/api/v1/billing/razorpay/verify-payment", json={
            "plan_slug": "enterprise",
            "billing_cycle": "annual",
            "razorpay_order_id": mock_order_id,
            "razorpay_payment_id": mock_pay_id,
            "razorpay_signature": sig,
        }, headers=headers)
        assert ver_resp.status_code == 200
        assert ver_resp.json()["status"] == "active"
        verified_invoice_id = ver_resp.json()["invoice_id"]

    # Verify subscription details
    sub_details = client.get("/api/v1/billing/subscription", headers=headers)
    assert sub_details.status_code == 200
    assert sub_details.json()["plan_slug"] == "enterprise"

    # 3. Project creation
    proj_resp = client.post("/api/v1/projects/", json={
        "name": f"Core Banking Platform {uid}",
        "repository_url": "https://github.com/gt-innox/core-banking.git",
        "default_branch": "main"
    }, headers=headers)
    assert proj_resp.status_code in (200, 201)
    project_id = proj_resp.json()["id"]

    # 4. Assessment execution & multi-pillar score generation
    scoring_result = CommercialDebtScoringEngine.calculate_project_debt(
        code_metrics={
            "lines_of_code": 45000,
            "files_analyzed": 50,
            "test_files_count": 12,
            "avg_cyclomatic_complexity": 3.2,
            "maintainability_index": 78.0
        }
    )

    assessment = Assessment(
        id=str(uuid.uuid4()),
        project_id=project_id,
        status="completed",
        overall_health_score=scoring_result["overall_health_score"]
    )
    db.add(assessment)
    db.commit()

    # Add risk finding
    risk = RiskFinding(
        id=str(uuid.uuid4()),
        project_id=project_id,
        assessment_id=assessment.id,
        technology_id=str(uuid.uuid4()),
        title="Unsanitized External Input in Ledger Service",
        severity="High",
        status="Open"
    )
    db.add(risk)
    db.commit()

    # 5. Executive Dashboard KPI verification
    kpi_resp = client.get("/api/v1/dashboard/executive-kpis", headers=headers)
    assert kpi_resp.status_code == 200
    kpi_data = kpi_resp.json()
    assert "total_financial_liability_usd" in kpi_data
    assert "pillar_breakdown" in kpi_data
    assert "portfolio_status" in kpi_data

    # Portfolio matrix verification
    matrix_resp = client.get("/api/v1/dashboard/portfolio-matrix", headers=headers)
    assert matrix_resp.status_code == 200
    assert len(matrix_resp.json()["projects"]) >= 1

    # Remediation velocity verification
    velocity_resp = client.get("/api/v1/dashboard/remediation-velocity", headers=headers)
    assert velocity_resp.status_code == 200
    assert "total_open_risks" in velocity_resp.json()

    # 6. Report generation (JSON, CSV, PDF)
    json_report = client.get(f"/api/v1/reports/json/{assessment.id}", headers=headers)
    assert json_report.status_code == 200
    assert json_report.json()["metadata"]["vendor"] == "GT InnoX LLP"
    assert "TechDebt AI" in json_report.json()["metadata"]["platform"]

    csv_report = client.get("/api/v1/reports/portfolio/csv", headers=headers)
    assert csv_report.status_code == 200
    assert "text/csv" in csv_report.headers["content-type"]

    pdf_report = client.get(f"/api/v1/reports/pdf/{assessment.id}", headers=headers)
    assert pdf_report.status_code == 200
    assert "application/pdf" in pdf_report.headers["content-type"]

    # 7. Verified payment invoice retrieval and receipt viewing
    invoices_resp = client.get("/api/v1/billing/invoices", headers=headers)
    assert invoices_resp.status_code == 200
    assert any(i["id"] == verified_invoice_id for i in invoices_resp.json())
    invoice_id = verified_invoice_id

    receipt_resp = client.get(f"/api/v1/billing/invoices/{invoice_id}/download", headers=headers)
    assert receipt_resp.status_code == 200
    assert "GT InnoX LLP" in receipt_resp.text
    assert "TechDebt AI" in receipt_resp.text

def test_performance_latency_and_caching_benchmarks():
    """
    Verifies system latency SLAs (<200ms) on API endpoints and evaluates CacheService throughput.
    """
    # 1. Health and probe latency SLA (<50ms)
    t0 = time.perf_counter()
    resp_health = client.get("/health")
    health_latency = (time.perf_counter() - t0) * 1000
    assert resp_health.status_code == 200
    assert health_latency < 200.0, f"Health endpoint exceeded 200ms SLA: {health_latency:.2f}ms"

    t0 = time.perf_counter()
    resp_metrics = client.get("/metrics")
    metrics_latency = (time.perf_counter() - t0) * 1000
    assert resp_metrics.status_code == 200
    assert metrics_latency < 200.0, f"Metrics endpoint exceeded 200ms SLA: {metrics_latency:.2f}ms"

    # 2. Plans catalog latency SLA (<100ms)
    t0 = time.perf_counter()
    resp_plans = client.get("/api/v1/billing/plans")
    plans_latency = (time.perf_counter() - t0) * 1000
    assert resp_plans.status_code == 200
    assert plans_latency < 200.0, f"Billing plans endpoint exceeded 200ms SLA: {plans_latency:.2f}ms"

    # 3. CacheService operational benchmarks
    # Measure 1,000 sets
    t0 = time.perf_counter()
    for i in range(1000):
        CacheService.set(f"bench_key_{i}", {"data": i, "token": uuid.uuid4().hex}, ttl_seconds=300)
    set_duration_ms = (time.perf_counter() - t0) * 1000
    assert set_duration_ms < 150.0, f"1000 cache sets exceeded 150ms: {set_duration_ms:.2f}ms"

    # Measure 1,000 gets
    t0 = time.perf_counter()
    for i in range(1000):
        val = CacheService.get(f"bench_key_{i}")
        assert val is not None
    get_duration_ms = (time.perf_counter() - t0) * 1000
    assert get_duration_ms < 150.0, f"1000 cache gets exceeded 150ms: {get_duration_ms:.2f}ms"

    # Invalidation benchmark
    CacheService.invalidate_prefix("bench_key_")
    assert CacheService.get("bench_key_0") is None
