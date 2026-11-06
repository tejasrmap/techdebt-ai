import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.rate_limiter import rate_limiter

client = TestClient(app)

def test_organization_crud_and_lifecycle():
    """Verify organization metadata retrieval, update, ownership transfer, export, and deletion."""
    rate_limiter.reset()
    uid = uuid.uuid4().hex[:6]
    
    # 1. Register Org and Owner
    reg = client.post("/api/v1/auth/register", json={
        "email": f"org_owner_{uid}@orgcorp.com",
        "password": "SecurePassword123!",
        "full_name": "Org Owner",
        "organization_name": f"OrgCorp {uid}"
    }).json()
    token = reg["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Set user role to Owner in DB
    from app.database import SessionLocal
    from app.models.all_models import User
    db = SessionLocal()
    owner_user = db.query(User).filter(User.email == f"org_owner_{uid}@orgcorp.com").first()
    owner_user.role = "Owner"
    db.commit()
    db.close()

    # 2. GET current organization
    get_res = client.get("/api/v1/organizations/current", headers=headers)
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["name"] == f"OrgCorp {uid}"
    assert data["member_count"] == 1

    # 3. PUT update organization
    update_res = client.put("/api/v1/organizations/current", headers=headers, json={
        "name": f"OrgCorp Renamed {uid}",
        "slug": f"orgcorp-renamed-{uid}"
    })
    assert update_res.status_code == 200
    assert update_res.json()["name"] == f"OrgCorp Renamed {uid}"

    # 4. GET audit logs
    audit_res = client.get("/api/v1/organizations/current/audit-logs", headers=headers)
    assert audit_res.status_code == 200
    assert audit_res.json()["total"] >= 1

    # 5. GET export organization data
    export_res = client.get("/api/v1/organizations/current/export", headers=headers)
    assert export_res.status_code == 200
    export_data = export_res.json()
    assert "export_timestamp" in export_data
    assert export_data["organization"]["name"] == f"OrgCorp Renamed {uid}"
    assert len(export_data["members"]) == 1

    # 6. Create another member and transfer ownership
    invite = client.post("/api/v1/auth/invitations", headers=headers, json={
        "email": f"successor_{uid}@orgcorp.com",
        "role": "Administrator"
    }).json()
    accept = client.post("/api/v1/auth/accept-invitation", json={
        "token": invite["token"],
        "full_name": "Successor User",
        "password": "SecurePassword123!"
    }).json()
    successor_id = accept["user"]["id"]

    transfer_res = client.post("/api/v1/organizations/current/transfer-ownership", headers=headers, json={
        "new_owner_user_id": successor_id
    })
    assert transfer_res.status_code == 200
    assert "transferred" in transfer_res.json()["message"]

    # 7. Demoted previous owner cannot delete organization (403 Forbidden)
    del_demoted = client.delete("/api/v1/organizations/current?confirm=true", headers=headers)
    assert del_demoted.status_code == 403
    assert "Operation not permitted" in del_demoted.json()["detail"]

    # 8. Successor as Owner without confirm query param fails with 400 Bad Request
    successor_headers = {"Authorization": f"Bearer {accept['access_token']}"}
    del_unconfirmed = client.delete("/api/v1/organizations/current", headers=successor_headers)
    assert del_unconfirmed.status_code == 400
    assert "Confirmation required" in del_unconfirmed.json()["detail"]

    # 9. Successor as Owner can delete organization with confirm=true (200 OK)
    del_res = client.delete("/api/v1/organizations/current?confirm=true", headers=successor_headers)
    assert del_res.status_code == 200
    assert "deleted successfully" in del_res.json()["message"]
