import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.services.billing_service import BillingService
from app.models.all_models import User, Organization

client = TestClient(app)

def get_test_headers(role: str = "Administrator"):
    uid = uuid.uuid4().hex[:8]
    email = f"portal_tester_{uid}@techdebt.ai"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Portal Tester",
        "organization_name": f"Portal Org {uid}"
    })
    token = reg.json()["access_token"]
    org_id = reg.json()["user"]["org_id"]
    user_id = reg.json()["user"]["id"]

    if role != "Administrator":
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.id == user_id).first()
            if u:
                u.role = role
                db.commit()
        finally:
            db.close()

    return {"Authorization": f"Bearer {token}"}, org_id

def test_stripe_checkout_endpoint():
    headers, org_id = get_test_headers(role="Administrator")

    # 1. Successful checkout initiation
    checkout_res = client.post("/api/v1/billing/checkout", json={
        "plan_slug": "professional",
        "billing_cycle": "yearly"
    }, headers=headers)
    assert checkout_res.status_code == 200
    c_data = checkout_res.json()
    assert c_data["mode"] in ("live_stripe", "sandbox")
    if c_data["mode"] == "sandbox":
        assert c_data["plan_id"] == "professional"
        assert c_data["status"] == "active"

    # 2. Non-existent plan returns 404
    bad_res = client.post("/api/v1/billing/checkout", json={
        "plan_slug": "non_existent_plan",
        "billing_cycle": "monthly"
    }, headers=headers)
    assert bad_res.status_code == 404

def test_customer_portal_endpoints():
    headers, org_id = get_test_headers(role="Administrator")

    # 1. POST /billing/portal
    portal_res = client.post("/api/v1/billing/portal", json={
        "return_url": "http://localhost:5173/dashboard/billing"
    }, headers=headers)
    assert portal_res.status_code == 200
    p_data = portal_res.json()
    assert "portal_url" in p_data
    assert p_data["mode"] in ("live_stripe", "sandbox")

    # 2. GET /billing/portal/session
    session_res = client.get("/api/v1/billing/portal/session", headers=headers)
    assert session_res.status_code == 200
    s_data = session_res.json()
    assert "portal_url" in s_data

def test_billing_rbac_authorization():
    # Regular developer should be forbidden from purchasing or managing billing
    dev_headers, _ = get_test_headers(role="Developer")

    checkout_res = client.post("/api/v1/billing/checkout", json={
        "plan_slug": "starter",
        "billing_cycle": "monthly"
    }, headers=dev_headers)
    assert checkout_res.status_code == 403

    portal_res = client.post("/api/v1/billing/portal", json={}, headers=dev_headers)
    assert portal_res.status_code == 403
