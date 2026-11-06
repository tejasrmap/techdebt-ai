import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.rate_limiter import rate_limiter

client = TestClient(app)

def test_project_archival_and_restoration():
    """Verify archiving hides projects by default, include_archived returns them, and restore reactivates them."""
    rate_limiter.reset()
    uid = uuid.uuid4().hex[:6]
    
    # Register org
    reg = client.post("/api/v1/auth/register", json={
        "email": f"arch_lead_{uid}@archive.com",
        "password": "SecurePassword123!",
        "full_name": "Archive Lead",
        "organization_name": f"Archive Org {uid}"
    }).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # Create project
    proj = client.post("/api/v1/projects", headers=headers, json={
        "name": f"Project Archive Test {uid}",
        "description": "Archival testing project"
    }).json()
    proj_id = proj["id"]
    assert proj["is_archived"] is False

    # 1. Archive project
    arch_res = client.post(f"/api/v1/projects/{proj_id}/archive", headers=headers)
    assert arch_res.status_code == 200
    assert arch_res.json()["is_archived"] is True

    # 2. GET projects without include_archived should not include it
    list_active = client.get("/api/v1/projects", headers=headers).json()
    assert not any(p["id"] == proj_id for p in list_active)

    # 3. GET projects with include_archived=true returns it
    list_all = client.get("/api/v1/projects?include_archived=true", headers=headers).json()
    archived_match = next((p for p in list_all if p["id"] == proj_id), None)
    assert archived_match is not None
    assert archived_match["is_archived"] is True

    # 4. Restore project
    restore_res = client.post(f"/api/v1/projects/{proj_id}/restore", headers=headers)
    assert restore_res.status_code == 200
    assert restore_res.json()["is_archived"] is False

    # 5. Visible again in standard list
    list_restored = client.get("/api/v1/projects", headers=headers).json()
    assert any(p["id"] == proj_id for p in list_restored)

def test_project_team_permissions_and_activity():
    """Verify team permission assignment, inspection, and revocation on a project."""
    rate_limiter.reset()
    uid = uuid.uuid4().hex[:6]
    reg = client.post("/api/v1/auth/register", json={
        "email": f"perm_lead_{uid}@collab.com",
        "password": "SecurePassword123!",
        "full_name": "Perm Lead",
        "organization_name": f"Collab Org {uid}"
    }).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # Create Project and Team
    proj = client.post("/api/v1/projects", headers=headers, json={
        "name": f"Collab Project {uid}"
    }).json()
    proj_id = proj["id"]

    team = client.post("/api/v1/teams", headers=headers, json={
        "name": f"Backend Guild {uid}"
    }).json()
    team_id = team["id"]

    # 1. Assign team permission
    assign_res = client.post(f"/api/v1/projects/{proj_id}/permissions", headers=headers, json={
        "team_id": team_id,
        "permission_level": "admin"
    })
    assert assign_res.status_code == 200
    assert "Assigned team" in assign_res.json()["message"]

    # 2. List permissions
    perms_res = client.get(f"/api/v1/projects/{proj_id}/permissions", headers=headers)
    assert perms_res.status_code == 200
    perms = perms_res.json()
    assert len(perms) == 1
    assert perms[0]["team_id"] == team_id
    assert perms[0]["permission_level"] == "admin"

    # 3. Project activity log
    activity_res = client.get(f"/api/v1/projects/{proj_id}/activity", headers=headers)
    assert activity_res.status_code == 200
    logs = activity_res.json()
    assert len(logs) >= 1

    # 4. Revoke team permission
    revoke_res = client.delete(f"/api/v1/projects/{proj_id}/permissions/{team_id}", headers=headers)
    assert revoke_res.status_code == 200
    assert "revoked" in revoke_res.json()["message"]

    # 5. List is now empty
    perms_empty = client.get(f"/api/v1/projects/{proj_id}/permissions", headers=headers).json()
    assert len(perms_empty) == 0
