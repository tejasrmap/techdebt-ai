import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.rate_limiter import rate_limiter

client = TestClient(app)

def _create_org_user(prefix: str):
    rate_limiter.reset()
    uid = uuid.uuid4().hex[:6]
    res = client.post("/api/v1/auth/register", json={
        "email": f"{prefix}_{uid}@example.com",
        "password": "SecurePassword123!",
        "full_name": f"{prefix} Admin",
        "organization_name": f"{prefix} Organization {uid}"
    })
    assert res.status_code == 200
    token = res.json()["access_token"]
    org_id = res.json()["user"]["org_id"]
    return token, org_id, {"Authorization": f"Bearer {token}"}

def test_exhaustive_cross_tenant_isolation_matrix():
    """Verify that User from Org A receives 403 or 404 when targeting Org B's resources."""
    # 1. Create Org A and Org B
    token_a, org_a_id, headers_a = _create_org_user("tenant_a")
    token_b, org_b_id, headers_b = _create_org_user("tenant_b")

    # 2. Org B creates a Project
    proj_b_res = client.post("/api/v1/projects", headers=headers_b, json={
        "name": f"Project B Secret {uuid.uuid4().hex[:4]}",
        "description": "Proprietary Org B Project",
        "repository_url": "https://github.com/orgb/secret"
    })
    assert proj_b_res.status_code == 201
    proj_b_id = proj_b_res.json()["id"]

    # --- Test 1: Project Isolation ---
    # Tenant A attempts to GET Project B
    get_proj_res = client.get(f"/api/v1/projects/{proj_b_id}", headers=headers_a)
    assert get_proj_res.status_code in (403, 404)

    # Tenant A attempts to PUT Project B
    put_proj_res = client.put(f"/api/v1/projects/{proj_b_id}", headers=headers_a, json={
        "name": "Tampered Name"
    })
    assert put_proj_res.status_code in (403, 404)

    # Tenant A attempts to DELETE Project B
    del_proj_res = client.delete(f"/api/v1/projects/{proj_b_id}", headers=headers_a)
    assert del_proj_res.status_code in (403, 404)

    # --- Test 2: Repository Connection Isolation ---
    # Tenant A attempts to get repository for Project B
    repo_get_res = client.get(f"/api/v1/repositories/{proj_b_id}", headers=headers_a)
    assert repo_get_res.status_code in (403, 404)

    # Tenant A attempts to connect repo to Project B
    repo_conn_res = client.post("/api/v1/repositories/connect", headers=headers_a, json={
        "project_id": proj_b_id,
        "repo_url": "https://github.com/attacker/malicious",
        "provider": "github"
    })
    assert repo_conn_res.status_code in (403, 404)

    # --- Test 3: Assessment Isolation ---
    # Tenant A attempts to trigger assessment on Project B
    assess_run_res = client.post("/api/v1/assessments/run", headers=headers_a, json={
        "project_id": proj_b_id
    })
    assert assess_run_res.status_code in (403, 404)

    # --- Test 4: Report Isolation ---
    # Tenant A attempts to download PDF / CSV for an arbitrary assessment ID from Org B
    fake_assessment_id = str(uuid.uuid4())
    pdf_res = client.get(f"/api/v1/reports/pdf/{fake_assessment_id}", headers=headers_a)
    assert pdf_res.status_code in (403, 404)

    csv_res = client.get(f"/api/v1/reports/csv/{fake_assessment_id}", headers=headers_a)
    assert csv_res.status_code in (403, 404)

    # --- Test 5: Code Findings Isolation ---
    findings_res = client.get(f"/api/v1/code-findings/assessment/{fake_assessment_id}", headers=headers_a)
    assert findings_res.status_code in (403, 404)

    # --- Test 6: Team Management Isolation ---
    # Tenant B creates a Team
    team_b_res = client.post("/api/v1/teams", headers=headers_b, json={
        "name": f"Core Engineering {uuid.uuid4().hex[:4]}",
        "description": "Org B Private Team"
    })
    assert team_b_res.status_code == 201
    team_b_id = team_b_res.json()["id"]

    # Tenant A attempts to view Team B
    team_get_res = client.get(f"/api/v1/teams/{team_b_id}", headers=headers_a)
    assert team_get_res.status_code in (403, 404)

    # Tenant A attempts to add member to Team B
    team_add_res = client.post(f"/api/v1/teams/{team_b_id}/members", headers=headers_a, json={
        "user_id": str(uuid.uuid4()),
        "role": "member"
    })
    assert team_add_res.status_code in (403, 404)

    # --- Test 7: Billing & Invoices Isolation ---
    # Tenant A views invoices - should see only their own, never Org B
    inv_res = client.get("/api/v1/billing/invoices", headers=headers_a)
    assert inv_res.status_code == 200
    for inv in inv_res.json():
        assert inv.get("org_id") == org_a_id or "org_id" not in inv
