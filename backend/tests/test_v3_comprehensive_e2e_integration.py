import uuid
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import SessionLocal
from app.models.all_models import (
    User, Organization, Project, Assessment, Technology, ProjectTechnology,
    TechnologyScore, RiskFinding, RepositoryConnection, Invoice, Notification
)
from app.services.billing_service import BillingService
from app.services.debt_scoring_engine import CommercialDebtScoringEngine
from app.services.report_generator import ReportGenerator

client = TestClient(app)

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def test_v3_complete_e2e_customer_and_platform_lifecycle(db: Session):
    """
    Comprehensive End-to-End Test exercising complete TechDebt AI v3.0.0 platform capabilities:
    1. Tenant & User onboarding.
    2. Project registration & repository configuration.
    3. Multi-pillar technical debt assessment & TDR calculation.
    4. Financial liability calculation in USD ($120/hr dev rate).
    5. Multi-channel reporting (PDF, CSV, JSON).
    6. Automated notification generation.
    7. Quota enforcement on subscription tier.
    8. Invoice generation & billing history.
    """
    uid = uuid.uuid4().hex[:8]
    email = f"e2e_enterprise_{uid}@techdebt.ai"

    # Step 1: Tenant & User Onboarding
    reg_res = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "EnterprisePassword123!",
        "full_name": "VP of Engineering",
        "organization_name": f"Acme Global {uid}"
    })
    assert reg_res.status_code == 200, f"Registration failed: {reg_res.text}"
    token = reg_res.json()["access_token"]
    org_id = reg_res.json()["user"]["org_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Step 2: Project Creation
    proj_res = client.post("/api/v1/projects", json={
        "name": "Payments Microservice",
        "description": "High-throughput core settlement engine",
        "primary_language": "Python"
    }, headers=headers)
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # Step 3: Repository Connection Configuration
    repo_conn = RepositoryConnection(
        id=str(uuid.uuid4()),
        org_id=org_id,
        project_id=project_id,
        provider="github",
        repo_name="payments-settlement-engine",
        repo_url="https://github.com/acme-global/payments-settlement-engine.git",
        selected_branch="main",
        status="connected"
    )
    db.add(repo_conn)
    db.commit()

    repo_settings_res = client.put(f"/api/v1/repositories/{project_id}/settings", json={
        "selected_branch": "release/v3.0.0",
        "review_frequency": "daily",
        "excluded_paths": ["tests/**", "dist/**"],
        "auto_assess_on_push": True
    }, headers=headers)
    assert repo_settings_res.status_code == 200
    assert repo_settings_res.json()["selected_branch"] == "release/v3.0.0"

    # Step 4: Assessment & Multi-Pillar Technical Debt Scoring
    assessment = Assessment(
        id=str(uuid.uuid4()),
        project_id=project_id,
        status="completed",
        overall_health_score=84.5,
        technical_debt_ratio=12.8,
        estimated_remediation_hours=32.0,
        lines_of_code=28500,
        files_analyzed=96,
        code_maintainability_score=86.0,
        architecture_score=82.0,
        security_score=88.0,
        dependency_score=80.0,
        reliability_score=86.0
    )
    db.add(assessment)
    db.commit()

    tech = Technology(
        id=str(uuid.uuid4()),
        name=f"fastapi-core-{uid}",
        category="Framework",
        latest_stable_version="0.110.0"
    )
    db.add(tech)
    db.commit()

    score = TechnologyScore(
        id=str(uuid.uuid4()),
        assessment_id=assessment.id,
        technology_id=tech.id,
        overall_score=88.0,
        risk_classification="Healthy",
        maintenance_health=90.0,
        security_exposure=85.0,
        version_currency=90.0,
        community_activity=85.0,
        documentation_quality=85.0,
        ecosystem_compatibility=90.0,
        sustainability=90.0,
        upgrade_complexity=10.0
    )
    risk = RiskFinding(
        id=str(uuid.uuid4()),
        project_id=project_id,
        assessment_id=assessment.id,
        technology_id=tech.id,
        title="TLS 1.1 Insecure Cipher Configuration",
        severity="Critical",
        status="Open",
        business_impact="PCI-DSS Non-compliance",
        technical_impact="Weak transport layer cipher"
    )
    db.add_all([score, risk])
    db.commit()

    # Step 5: Verify Explainable Debt Scoring
    explained = CommercialDebtScoringEngine.explain_debt_score(
        code_metrics={"lines_of_code": 28500, "files_analyzed": 96, "duplicated_blocks_ratio": 2.5},
        tech_scores=[{"maintenance_health": 90, "version_currency": 90, "security_exposure": 85}],
        risk_findings=[{"severity": "Critical", "title": "TLS 1.1 Insecure Cipher Configuration"}]
    )
    assert explained["technical_debt_ratio"] > 0.0
    assert explained["total_financial_cost_usd"] > 0.0
    assert "pillars" in explained
    assert len(explained["pillars"]) == 5
    assert "security_debt" in explained["pillars"]

    # Step 6: Verify Dashboard Executive KPIs
    dash_kpi_res = client.get("/api/v1/dashboard/executive-kpis", headers=headers)
    assert dash_kpi_res.status_code == 200
    kpi_data = dash_kpi_res.json()
    assert kpi_data["critical_vulnerabilities"] >= 1
    assert kpi_data["total_lines_of_code"] >= 28500

    # Step 7: Verify Multi-Channel Reporting (PDF, CSV, JSON)
    pdf_res = client.get(f"/api/v1/reports/pdf/{assessment.id}", headers=headers)
    assert pdf_res.status_code == 200
    assert pdf_res.content.startswith(b"%PDF")

    csv_res = client.get(f"/api/v1/reports/csv/{assessment.id}", headers=headers)
    assert csv_res.status_code == 200
    assert "Payments Microservice" in csv_res.text

    json_res = client.get(f"/api/v1/reports/json/{assessment.id}", headers=headers)
    assert json_res.status_code == 200
    j_data = json_res.json()
    assert j_data["metadata"]["vendor"] == "GT InnoX LLP"
    assert j_data["executive_summary"]["overall_health_score"] == 84.5

    # Step 8: Commercial Invoice Generation via Verified Payment Order
    import os, hmac, hashlib
    from unittest.mock import patch
    mock_order_id = f"order_v3e2e_{uid}"
    mock_pay_id = f"pay_v3e2e_{uid}"
    with patch.dict(os.environ, {"RAZORPAY_KEY_ID": "rzp_test_mock_v3", "RAZORPAY_KEY_SECRET": "rzp_test_sec_v3", "RAZORPAY_CURRENCY": "USD"}):
        with patch.object(BillingService, "_post_razorpay_order", return_value={"id": mock_order_id, "amount": 49900, "currency": "USD"}):
            ord_res = client.post("/api/v1/billing/razorpay/create-order", json={"plan_slug": "enterprise", "billing_cycle": "monthly"}, headers=headers)
            assert ord_res.status_code == 200
        sig = hmac.new(b"rzp_test_sec_v3", f"{mock_order_id}|{mock_pay_id}".encode(), hashlib.sha256).hexdigest()
        inv_res = client.post("/api/v1/billing/razorpay/verify-payment", json={
            "plan_slug": "enterprise",
            "billing_cycle": "monthly",
            "razorpay_order_id": mock_order_id,
            "razorpay_payment_id": mock_pay_id,
            "razorpay_signature": sig,
        }, headers=headers)
    assert inv_res.status_code == 200
    inv_id = inv_res.json()["invoice_id"]

    inv_html = client.get(f"/api/v1/billing/invoices/{inv_id}/download", headers=headers)
    assert inv_html.status_code == 200
    assert "GT InnoX LLP" in inv_html.text

    # Step 9: In-app Notification Verification
    notif_res = client.get("/api/v1/notifications/unread-count", headers=headers)
    assert notif_res.status_code == 200

    # Step 10: Quota Checking
    BillingService.change_subscription_plan(db, org_id, "starter")
    allowed, limit, current = BillingService.check_entitlement(db, org_id, "team_members")
    assert limit == 5
