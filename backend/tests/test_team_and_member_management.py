import uuid
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.all_models import User, OrganizationInvitation
from app.services.rate_limiter import rate_limiter

client = TestClient(app)

def test_invitation_expiration_and_revocation():
    """Verify invitation lifecycle: expiration handling and explicit revocation."""
    rate_limiter.reset()
    uid = uuid.uuid4().hex[:6]
    
    # Register org and owner
    reg = client.post("/api/v1/auth/register", json={
        "email": f"inv_lead_{uid}@teamtest.com",
        "password": "SecurePassword123!",
        "full_name": "Inv Lead",
        "organization_name": f"TeamTest Org {uid}"
    }).json()
    token = reg["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create invitation
    inv_res = client.post("/api/v1/auth/invitations", headers=headers, json={
        "email": f"candidate_{uid}@teamtest.com",
        "role": "Developer"
    })
    assert inv_res.status_code == 201
    inv_data = inv_res.json()
    inv_id = inv_data["id"]
    raw_token = inv_data["token"]

    # 2. Revoke invitation
    del_res = client.delete(f"/api/v1/auth/invitations/{inv_id}", headers=headers)
    assert del_res.status_code == 204

    # 3. Attempting to accept revoked invitation fails
    accept_revoked = client.post("/api/v1/auth/accept-invitation", json={
        "token": raw_token,
        "full_name": "Candidate User",
        "password": "CandidatePassword123!"
    })
    assert accept_revoked.status_code == 400
    assert "Invalid, expired, or already accepted" in accept_revoked.json()["detail"]

    # 4. Create second invitation and simulate expiration
    inv2 = client.post("/api/v1/auth/invitations", headers=headers, json={
        "email": f"expired_candidate_{uid}@teamtest.com",
        "role": "Developer"
    }).json()

    db = SessionLocal()
    db_invite = db.query(OrganizationInvitation).filter(OrganizationInvitation.id == inv2["id"]).first()
    db_invite.expires_at = datetime.utcnow() - timedelta(hours=1)
    db.commit()
    db.close()

    accept_expired = client.post("/api/v1/auth/accept-invitation", json={
        "token": inv2["token"],
        "full_name": "Expired User",
        "password": "ExpiredPassword123!"
    })
    assert accept_expired.status_code == 400
    assert "expired" in accept_expired.json()["detail"].lower()

def test_member_role_management_and_privilege_escalation():
    """Verify role changes, member removal, and privilege escalation prevention."""
    rate_limiter.reset()
    uid = uuid.uuid4().hex[:6]
    
    # Register org and owner
    reg = client.post("/api/v1/auth/register", json={
        "email": f"boss_{uid}@escalation.com",
        "password": "SecurePassword123!",
        "full_name": "Boss Owner",
        "organization_name": f"Escalation Org {uid}"
    }).json()
    owner_token = reg["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # Invite a developer
    inv = client.post("/api/v1/auth/invitations", headers=owner_headers, json={
        "email": f"dev_{uid}@escalation.com",
        "role": "Developer"
    }).json()
    accept = client.post("/api/v1/auth/accept-invitation", json={
        "token": inv["token"],
        "full_name": "Bob Developer",
        "password": "SecurePassword123!"
    }).json()
    dev_id = accept["user"]["id"]
    dev_headers = {"Authorization": f"Bearer {accept['access_token']}"}

    # 1. List members
    members_res = client.get("/api/v1/organizations/current/members", headers=owner_headers)
    assert members_res.status_code == 200
    assert len(members_res.json()) == 2

    # 2. Promote Developer to Engineering Manager
    promote_res = client.put(f"/api/v1/organizations/current/members/{dev_id}/role", headers=owner_headers, json={
        "role": "Engineering Manager"
    })
    assert promote_res.status_code == 200
    assert promote_res.json()["new_role"] == "Engineering Manager"

    # 3. Developer cannot promote anyone (403 Forbidden)
    dev_promote_res = client.put(f"/api/v1/organizations/current/members/{dev_id}/role", headers=dev_headers, json={
        "role": "Administrator"
    })
    assert dev_promote_res.status_code == 403

    # 4. Remove member
    remove_res = client.delete(f"/api/v1/organizations/current/members/{dev_id}", headers=owner_headers)
    assert remove_res.status_code == 200
    assert "removed" in remove_res.json()["message"]

    # 5. Member count now 1
    after_res = client.get("/api/v1/organizations/current/members", headers=owner_headers)
    assert len(after_res.json()) == 1

def test_team_activity_history():
    """Verify team activity log endpoint."""
    rate_limiter.reset()
    uid = uuid.uuid4().hex[:6]
    reg = client.post("/api/v1/auth/register", json={
        "email": f"activity_{uid}@teamactivity.com",
        "password": "SecurePassword123!",
        "full_name": "Team Activity Admin",
        "organization_name": f"TeamActivity Org {uid}"
    }).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # Create team
    team = client.post("/api/v1/teams", headers=headers, json={
        "name": f"Team Alpha {uid}",
        "description": "Alpha Activity Team"
    }).json()
    team_id = team["id"]

    # Get team activity
    activity_res = client.get(f"/api/v1/teams/{team_id}/activity", headers=headers)
    assert activity_res.status_code == 200
    assert isinstance(activity_res.json(), list)
