import uuid
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import SessionLocal
from app.models.all_models import (
    User, Organization, Project, Assessment, RiskFinding, RepositoryConnection, Technology
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
    email = f"ux_{uid}@example.com"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": f"UX User {uid}",
        "organization_name": f"UX Org {uid}"
    })
    token = reg.json()["access_token"]
    org_id = reg.json()["user"]["org_id"]
    user_id = reg.json()["user"]["id"]
    return {"Authorization": f"Bearer {token}"}, org_id, user_id

def test_repository_settings_and_disconnect(db: Session):
    headers, org_id, _ = get_test_auth(db)

    # Create project
    project = Project(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name="UX Test Repository",
        description="Testing repo settings"
    )
    db.add(project)
    db.commit()

    # Create connected repo
    conn = RepositoryConnection(
        id=str(uuid.uuid4()),
        org_id=org_id,
        project_id=project.id,
        provider="github",
        repo_name="ux-test-repo",
        repo_url="https://github.com/gt-innox/ux-test-repo.git",
        selected_branch="main",
        status="connected"
    )
    db.add(conn)
    db.commit()

    # 1. Get settings
    resp_get = client.get(f"/api/v1/repositories/{project.id}/settings", headers=headers)
    assert resp_get.status_code == 200
    data_get = resp_get.json()
    assert data_get["selected_branch"] == "main"
    assert data_get["review_frequency"] == "weekly"

    # 2. Update settings
    resp_put = client.put(f"/api/v1/repositories/{project.id}/settings", json={
        "selected_branch": "develop",
        "review_frequency": "daily",
        "excluded_paths": ["tests/**", "build/**"],
        "auto_assess_on_push": False
    }, headers=headers)
    assert resp_put.status_code == 200
    assert resp_put.json()["selected_branch"] == "develop"
    assert resp_put.json()["settings"]["review_frequency"] == "daily"
    assert resp_put.json()["settings"]["auto_assess_on_push"] is False

    # 3. Disconnect repository
    resp_del = client.delete(f"/api/v1/repositories/{project.id}/connection", headers=headers)
    assert resp_del.status_code == 200
    assert "disconnected successfully" in resp_del.json()["message"]

    # Verify 404 after disconnection
    resp_post_del = client.get(f"/api/v1/repositories/{project.id}/settings", headers=headers)
    assert resp_post_del.status_code == 404

def test_assessment_status_findings_and_compare(db: Session):
    headers, org_id, _ = get_test_auth(db)

    project = Project(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name="Assessment Comparison Project"
    )
    db.add(project)
    db.commit()

    # Assessment 1 (Base)
    a1 = Assessment(
        id=str(uuid.uuid4()),
        project_id=project.id,
        status="completed",
        overall_health_score=70.0,
        technical_debt_ratio=20.0
    )
    # Assessment 2 (Target - Improved)
    a2 = Assessment(
        id=str(uuid.uuid4()),
        project_id=project.id,
        status="completed",
        overall_health_score=85.0,
        technical_debt_ratio=12.0
    )
    db.add_all([a1, a2])
    db.commit()

    tech = Technology(
        id=str(uuid.uuid4()),
        name=f"Tech-{uuid.uuid4().hex[:4]}",
        category="Framework",
        latest_stable_version="2.0"
    )
    db.add(tech)
    db.commit()

    # Risk 1 in a1 (will be resolved in a2)
    r1 = RiskFinding(
        id=str(uuid.uuid4()),
        project_id=project.id,
        assessment_id=a1.id,
        technology_id=tech.id,
        title="SQL Injection Vulnerability",
        severity="Critical",
        status="Open"
    )
    # Risk 2 in a2 (new risk)
    r2 = RiskFinding(
        id=str(uuid.uuid4()),
        project_id=project.id,
        assessment_id=a2.id,
        technology_id=tech.id,
        title="Missing Rate Limiting Header",
        severity="Low",
        status="Open"
    )
    db.add_all([r1, r2])
    db.commit()

    # 1. Test status endpoint
    resp_status = client.get(f"/api/v1/assessments/{a2.id}/status", headers=headers)
    assert resp_status.status_code == 200
    st_data = resp_status.json()
    assert st_data["status"] == "completed"
    assert st_data["progress_percent"] == 100
    assert st_data["stage"] == "completed"

    # 2. Test findings endpoint with severity filter
    resp_findings = client.get(f"/api/v1/assessments/{a1.id}/findings?severity=Critical", headers=headers)
    assert resp_findings.status_code == 200
    f_data = resp_findings.json()
    assert f_data["total"] == 1
    assert f_data["items"][0]["title"] == "SQL Injection Vulnerability"

    # 3. Test comparison endpoint
    resp_comp = client.get(f"/api/v1/assessments/compare/two?base_id={a1.id}&target_id={a2.id}", headers=headers)
    assert resp_comp.status_code == 200
    comp_data = resp_comp.json()
    assert comp_data["score_delta"] == 15.0
    assert comp_data["tdr_delta"] == -8.0
    assert comp_data["trend"] == "improved"
    assert "Missing Rate Limiting Header" in comp_data["new_risks"]
    assert "SQL Injection Vulnerability" in comp_data["resolved_risks"]
