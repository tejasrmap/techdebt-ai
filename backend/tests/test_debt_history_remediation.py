import uuid
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.all_models import Project, Technology, RiskFinding, HistoricalAssessment, Assessment, User

client = TestClient(app)

def get_test_headers():
    uid = uuid.uuid4().hex[:8]
    email = f"history_tester_{uid}@techdebt.ai"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "History Tester",
        "organization_name": f"History Org {uid}"
    })
    if reg.status_code in (200, 201):
        token = reg.json()["access_token"]
        user_id = reg.json()["user"]["id"]
    else:
        login = client.post("/api/v1/auth/login", json={
            "email": email,
            "password": "SecurePassword123!"
        })
        token = login.json()["access_token"]
        user_id = login.json()["user"]["id"]
    return {"Authorization": f"Bearer {token}"}, user_id

def test_risk_remediation_lifecycle_and_reopen():
    headers, user_id = get_test_headers()

    # 1. Create Project
    p_name = f"Remediation Proj {uuid.uuid4().hex[:6]}"
    p_res = client.post("/api/v1/projects", json={"name": p_name, "repository_url": "https://github.com/org/rem"}, headers=headers)
    assert p_res.status_code in (200, 201)
    proj_id = p_res.json()["id"]

    # 2. Insert Technology & Risk Finding
    db = SessionLocal()
    try:
        tech = Technology(name=f"test-pkg-{uuid.uuid4().hex[:6]}", ecosystem="npm")
        db.add(tech)
        db.commit()
        db.refresh(tech)

        risk = RiskFinding(
            project_id=proj_id,
            technology_id=tech.id,
            severity="High",
            title="Outdated dependency with known vulnerability",
            status="Open"
        )
        db.add(risk)
        db.commit()
        db.refresh(risk)
        risk_id = risk.id
    finally:
        db.close()

    # 3. Patch to 'In Progress' and assign user
    patch1 = client.patch(f"/api/v1/risks/{risk_id}/remediation-status", json={
        "status": "In Progress",
        "assigned_to": user_id,
        "resolution_notes": "Assigned to engineer for fix."
    }, headers=headers)
    assert patch1.status_code == 200
    p1_data = patch1.json()
    assert p1_data["status"] == "In Progress"
    assert p1_data["assigned_to"] == user_id
    assert p1_data["resolved_at"] is None

    # 4. Patch to 'Resolved'
    patch2 = client.patch(f"/api/v1/risks/{risk_id}/remediation-status", json={
        "status": "Resolved",
        "resolution_notes": "Upgraded dependency and verified tests."
    }, headers=headers)
    assert patch2.status_code == 200
    p2_data = patch2.json()
    assert p2_data["status"] == "Resolved"
    assert p2_data["resolved_at"] is not None

    # 5. Reopen finding (transition from Resolved -> Open)
    reopen_res = client.patch(f"/api/v1/risks/{risk_id}/remediation-status", json={
        "status": "Open",
        "resolution_notes": "Regression detected in downstream service. Reopening."
    }, headers=headers)
    assert reopen_res.status_code == 200
    r_data = reopen_res.json()
    assert r_data["status"] == "Open"
    assert r_data["resolved_at"] is None

def test_project_remediation_metrics_calculation():
    headers, user_id = get_test_headers()

    p_name = f"Metrics Proj {uuid.uuid4().hex[:6]}"
    p_res = client.post("/api/v1/projects", json={"name": p_name, "repository_url": "https://github.com/org/metrics"}, headers=headers)
    assert p_res.status_code in (200, 201)
    proj_id = p_res.json()["id"]

    db = SessionLocal()
    try:
        tech = Technology(name=f"metrics-pkg-{uuid.uuid4().hex[:6]}", ecosystem="pypi")
        db.add(tech)
        db.commit()
        db.refresh(tech)

        # Create one open finding and one resolved finding with known timestamps
        created_time = datetime.utcnow() - timedelta(hours=10)
        resolved_time = datetime.utcnow()

        r1 = RiskFinding(
            project_id=proj_id,
            technology_id=tech.id,
            severity="Critical",
            title="Critical remote code execution",
            status="Resolved",
            created_at=created_time,
            resolved_at=resolved_time,
            assigned_to=user_id
        )
        r2 = RiskFinding(
            project_id=proj_id,
            technology_id=tech.id,
            severity="Medium",
            title="Medium performance flaw",
            status="Open",
            created_at=created_time
        )
        db.add_all([r1, r2])
        db.commit()
    finally:
        db.close()

    metrics_res = client.get(f"/api/v1/risks/project/{proj_id}/remediation-metrics", headers=headers)
    assert metrics_res.status_code == 200
    m = metrics_res.json()
    assert m["total_findings"] == 2
    assert m["resolved_findings"] == 1
    assert m["open_findings"] == 1
    assert m["resolution_rate_pct"] == 50.0
    assert m["mean_time_to_remediate_hours"] >= 9.0
    assert m["severity_breakdown"]["Critical"]["resolved"] == 1
    assert m["severity_breakdown"]["Medium"]["open"] == 1

def test_project_debt_history_trajectory():
    headers, user_id = get_test_headers()

    p_name = f"History Trajectory Proj {uuid.uuid4().hex[:6]}"
    p_res = client.post("/api/v1/projects", json={"name": p_name, "repository_url": "https://github.com/org/traj"}, headers=headers)
    assert p_res.status_code in (200, 201)
    proj_id = p_res.json()["id"]

    db = SessionLocal()
    try:
        # Create an assessment to link historical records
        asmt = Assessment(project_id=proj_id, status="completed", overall_health_score=85.0)
        db.add(asmt)
        db.commit()
        db.refresh(asmt)

        # Create two historical snapshots simulating an improving trajectory
        t0 = datetime.utcnow() - timedelta(days=7)
        t1 = datetime.utcnow()

        h1 = HistoricalAssessment(
            project_id=proj_id,
            assessment_id=asmt.id,
            health_score=70.0,
            score_delta=0.0,
            risk_classification="Moderate Risk",
            new_risks_count=5,
            resolved_risks_count=0,
            created_at=t0
        )
        h2 = HistoricalAssessment(
            project_id=proj_id,
            assessment_id=asmt.id,
            health_score=85.0,
            score_delta=15.0,
            risk_classification="Healthy",
            new_risks_count=1,
            resolved_risks_count=4,
            created_at=t1
        )
        db.add_all([h1, h2])
        db.commit()
    finally:
        db.close()

    hist_res = client.get(f"/api/v1/projects/{proj_id}/debt-history", headers=headers)
    assert hist_res.status_code == 200
    h_data = hist_res.json()
    assert h_data["snapshots_count"] == 2
    assert h_data["overall_trend"] == "improving"
    assert h_data["cumulative_resolved_risks"] == 4
    assert len(h_data["timeline"]) == 2
    assert h_data["timeline"][0]["health_score"] == 70.0
    assert h_data["timeline"][1]["health_score"] == 85.0
