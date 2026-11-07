import uuid
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import SessionLocal
from app.models.all_models import (
    User, Organization, Project, Assessment, RiskFinding, TechnologyScore, Technology
)

client = TestClient(app)

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def get_test_auth(db: Session):
    uid = uuid.uuid4().hex[:8]
    email = f"rep_{uid}@example.com"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": f"Report User {uid}",
        "organization_name": f"Report Org {uid}"
    })
    token = reg.json()["access_token"]
    org_id = reg.json()["user"]["org_id"]
    return {"Authorization": f"Bearer {token}"}, org_id

def test_assessment_reports_pdf_csv_json(db: Session):
    headers, org_id = get_test_auth(db)

    project = Project(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name="Billing Engine Core"
    )
    db.add(project)
    db.commit()

    assessment = Assessment(
        id=str(uuid.uuid4()),
        project_id=project.id,
        status="completed",
        overall_health_score=88.0,
        technical_debt_ratio=11.5,
        estimated_remediation_hours=18.0,
        lines_of_code=8500,
        files_analyzed=42
    )
    db.add(assessment)
    db.commit()

    tech = Technology(
        id=str(uuid.uuid4()),
        name=f"FastAPI-{uuid.uuid4().hex[:4]}",
        category="Framework",
        latest_stable_version="0.110.0"
    )
    db.add(tech)
    db.commit()

    score = TechnologyScore(
        id=str(uuid.uuid4()),
        assessment_id=assessment.id,
        technology_id=tech.id,
        overall_score=92.0,
        risk_classification="Healthy",
        maintenance_health=95.0,
        security_exposure=90.0,
        version_currency=90.0,
        community_activity=85.0,
        documentation_quality=90.0,
        ecosystem_compatibility=90.0,
        sustainability=90.0,
        upgrade_complexity=10.0
    )
    risk = RiskFinding(
        id=str(uuid.uuid4()),
        project_id=project.id,
        assessment_id=assessment.id,
        technology_id=tech.id,
        title="Unpinned Sub-dependency Version",
        severity="Medium",
        status="Open",
        business_impact="May cause build inconsistency"
    )
    db.add_all([score, risk])
    db.commit()

    # 1. PDF Report Download
    resp_pdf = client.get(f"/api/v1/reports/pdf/{assessment.id}", headers=headers)
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["content-type"] == "application/pdf"
    assert resp_pdf.content.startswith(b"%PDF")

    # 2. CSV Report Download
    resp_csv = client.get(f"/api/v1/reports/csv/{assessment.id}", headers=headers)
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers["content-type"]
    csv_text = resp_csv.text
    assert "Technical Debt Audit Report" in csv_text
    assert "Billing Engine Core" in csv_text
    assert "FastAPI" in csv_text

    # 3. JSON Report Export
    resp_json = client.get(f"/api/v1/reports/json/{assessment.id}", headers=headers)
    assert resp_json.status_code == 200
    json_data = resp_json.json()
    assert json_data["metadata"]["vendor"] == "GT InnoX LLP"
    assert "TechDebt AI" in json_data["metadata"]["platform"]
    assert json_data["executive_summary"]["overall_health_score"] == 88.0
    assert json_data["executive_summary"]["technical_debt_ratio"] == 11.5
    assert json_data["executive_summary"]["financial_liability_usd"] == 18.0 * 120.0
    assert len(json_data["technologies"]) == 1
    assert len(json_data["risks"]) == 1

def test_portfolio_reports_pdf_csv_json(db: Session):
    headers, org_id = get_test_auth(db)

    # 1. Portfolio PDF
    resp_pdf = client.get("/api/v1/reports/portfolio/pdf", headers=headers)
    assert resp_pdf.status_code == 200
    assert resp_pdf.headers["content-type"] == "application/pdf"
    assert resp_pdf.content.startswith(b"%PDF")

    # 2. Portfolio CSV
    resp_csv = client.get("/api/v1/reports/portfolio/csv", headers=headers)
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers["content-type"]
    assert "Enterprise Portfolio Report" in resp_csv.text

    # 3. Portfolio JSON
    resp_json = client.get("/api/v1/reports/portfolio/json", headers=headers)
    assert resp_json.status_code == 200
    p_data = resp_json.json()
    assert p_data["metadata"]["vendor"] == "GT InnoX LLP"
    assert "portfolio" in p_data

def test_report_tenant_isolation(db: Session):
    headers_a, org_id_a = get_test_auth(db)
    headers_b, org_id_b = get_test_auth(db)

    # Create project & assessment for Org A
    project_a = Project(id=str(uuid.uuid4()), org_id=org_id_a, name="Org A Secret Project")
    db.add(project_a)
    db.commit()

    a_a = Assessment(id=str(uuid.uuid4()), project_id=project_a.id, status="completed", overall_health_score=95.0)
    db.add(a_a)
    db.commit()

    # Org B trying to download Org A's report gets 404
    resp_pdf_b = client.get(f"/api/v1/reports/pdf/{a_a.id}", headers=headers_b)
    assert resp_pdf_b.status_code == 404

    resp_json_b = client.get(f"/api/v1/reports/json/{a_a.id}", headers=headers_b)
    assert resp_json_b.status_code == 404
