import uuid
from datetime import datetime, timedelta
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

def get_test_auth(db: Session, plan: str = "enterprise"):
    uid = uuid.uuid4().hex[:8]
    email = f"dash_{uid}@example.com"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": f"Dash User {uid}",
        "organization_name": f"Dash Org {uid}"
    })
    token = reg.json()["access_token"]
    org_id = reg.json()["user"]["org_id"]
    user_id = reg.json()["user"]["id"]

    if plan != "enterprise":
        org = db.query(Organization).filter(Organization.id == org_id).first()
        org.plan = plan
        db.commit()

    return {"Authorization": f"Bearer {token}"}, org_id, user_id

def test_empty_dashboard_overview(db: Session):
    headers, org_id, _ = get_test_auth(db)
    response = client.get("/api/v1/dashboard/overview", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_projects"] == 0
    assert data["total_financial_liability_usd"] == 0.0
    assert data["average_technical_debt_ratio"] == 0.0

def test_populated_dashboard_kpis_and_velocity(db: Session):
    headers, org_id, _ = get_test_auth(db)

    # Create project
    project = Project(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name="Backend Core Service",
        description="Core financial service"
    )
    db.add(project)
    db.commit()

    # Create assessment
    assessment = Assessment(
        id=str(uuid.uuid4()),
        project_id=project.id,
        status="completed",
        overall_health_score=82.5,
        technical_debt_ratio=14.2,
        estimated_remediation_hours=25.0,
        lines_of_code=12500,
        code_maintainability_score=85.0,
        architecture_score=80.0,
        security_score=88.0,
        dependency_score=78.0,
        reliability_score=82.0
    )
    db.add(assessment)
    db.commit()

    # Create technology for risk finding foreign key
    tech = Technology(
        id=str(uuid.uuid4()),
        name=f"Python-{uuid.uuid4().hex[:4]}",
        category="Language",
        latest_stable_version="3.10"
    )
    db.add(tech)
    db.commit()

    # Create open risk
    r1 = RiskFinding(
        id=str(uuid.uuid4()),
        project_id=project.id,
        assessment_id=assessment.id,
        technology_id=tech.id,
        title="Outdated Crypto Cipher Suite",
        severity="Critical",
        status="Open",
        created_at=datetime.utcnow() - timedelta(days=2)
    )
    # Create resolved risk
    r2 = RiskFinding(
        id=str(uuid.uuid4()),
        project_id=project.id,
        assessment_id=assessment.id,
        technology_id=tech.id,
        title="Permissive CORS Configuration",
        severity="High",
        status="Resolved",
        created_at=datetime.utcnow() - timedelta(days=10),
        resolved_at=datetime.utcnow() - timedelta(days=4)
    )
    db.add_all([r1, r2])
    db.commit()

    # 1. Test Overview
    resp_overview = client.get("/api/v1/dashboard/overview", headers=headers)
    assert resp_overview.status_code == 200
    d_ov = resp_overview.json()
    assert d_ov["total_projects"] == 1
    assert d_ov["total_lines_of_code"] == 12500
    assert d_ov["average_technical_debt_ratio"] == 14.2
    assert d_ov["total_financial_liability_usd"] == 25.0 * 120.0
    assert d_ov["remediation_mttr_days"] == 6.0

    # 2. Test Executive KPIs
    resp_kpis = client.get("/api/v1/dashboard/executive-kpis", headers=headers)
    assert resp_kpis.status_code == 200
    d_kpi = resp_kpis.json()
    assert d_kpi["critical_vulnerabilities"] == 1
    assert d_kpi["sla_compliance_rate"] == 100.0
    assert d_kpi["pillar_breakdown"]["security"] == 88.0
    assert len(d_kpi["top_hotspots"]) >= 1

    # 3. Test Remediation Velocity
    resp_vel = client.get("/api/v1/dashboard/remediation-velocity", headers=headers)
    assert resp_vel.status_code == 200
    d_vel = resp_vel.json()
    assert d_vel["total_open_risks"] == 1
    assert d_vel["total_resolved_risks"] == 1
    assert d_vel["overall_mttr_days"] == 6.0
    assert "High" in d_vel["mttr_by_severity"]

    # 4. Test Portfolio Matrix
    resp_matrix = client.get("/api/v1/dashboard/portfolio-matrix", headers=headers)
    assert resp_matrix.status_code == 200
    d_matrix = resp_matrix.json()
    assert d_matrix["total_projects"] == 1
    assert d_matrix["projects"][0]["project_name"] == "Backend Core Service"
    assert d_matrix["projects"][0]["health_score"] == 82.5

def test_tenant_isolation_dashboard(db: Session):
    headers_a, org_id_a, _ = get_test_auth(db)
    headers_b, org_id_b, _ = get_test_auth(db)

    # Org B should see 0 projects and 0 liability
    resp_b = client.get("/api/v1/dashboard/overview", headers=headers_b)
    assert resp_b.status_code == 200
    assert resp_b.json()["total_projects"] == 0
    assert resp_b.json()["total_financial_liability_usd"] == 0.0
