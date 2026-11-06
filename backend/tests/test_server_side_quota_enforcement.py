import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.services.billing_service import BillingService
from app.models.all_models import Organization, Subscription, UsageRecord, Project, Assessment

client = TestClient(app)

def get_test_headers(plan: str = "free"):
    uid = uuid.uuid4().hex[:8]
    email = f"quota_tester_{uid}@techdebt.ai"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Quota Tester",
        "organization_name": f"Quota Org {uid}"
    })
    token = reg.json()["access_token"]
    org_id = reg.json()["user"]["org_id"]

    db = SessionLocal()
    try:
        BillingService.change_subscription_plan(db, org_id, plan)
    finally:
        db.close()

    return {"Authorization": f"Bearer {token}"}, org_id

def test_project_creation_quota_enforcement():
    headers, org_id = get_test_headers(plan="free")

    # 1st project on Free tier (limit 1) succeeds
    p1 = client.post("/api/v1/projects", json={
        "name": f"Free Proj 1 {uuid.uuid4().hex[:6]}",
        "repository_url": "https://github.com/org/free1"
    }, headers=headers)
    assert p1.status_code in (200, 201)

    # 2nd project on Free tier fails with quota exceeded error
    p2 = client.post("/api/v1/projects", json={
        "name": f"Free Proj 2 {uuid.uuid4().hex[:6]}",
        "repository_url": "https://github.com/org/free2"
    }, headers=headers)
    assert p2.status_code in (402, 403)
    assert "limit reached" in p2.json()["detail"].lower()

def test_assessment_quota_enforcement():
    headers, org_id = get_test_headers(plan="free")

    # Create 1 allowed project
    p = client.post("/api/v1/projects", json={
        "name": f"Asmt Proj {uuid.uuid4().hex[:6]}",
        "repository_url": "https://github.com/org/asmt"
    }, headers=headers).json()
    proj_id = p["id"]

    # Artificially set usage record to 10 assessments (the limit for free tier)
    db = SessionLocal()
    try:
        BillingService.record_usage(db, org_id, "monthly_assessments", 10.0)
    finally:
        db.close()

    # Attempt running an assessment when quota is exhausted
    asmt_res = client.post("/api/v1/assessments/run", json={
        "project_id": proj_id
    }, headers=headers)
    assert asmt_res.status_code in (402, 403)
    assert "monthly assessment limit reached" in asmt_res.json()["detail"].lower()

def test_team_member_quota_enforcement():
    headers, org_id = get_test_headers(plan="free")

    # Free tier has max_team_members = 1 (the registered admin user already occupies it)
    invite_res = client.post("/api/v1/auth/invitations", json={
        "email": f"newbie_{uuid.uuid4().hex[:6]}@techdebt.ai",
        "role": "Developer"
    }, headers=headers)
    assert invite_res.status_code in (402, 403)
    assert "limit reached" in invite_res.json()["detail"].lower()

def test_ai_feature_gating_and_upgrade():
    headers, org_id = get_test_headers(plan="free")

    p = client.post("/api/v1/projects", json={
        "name": f"AI Gate Proj {uuid.uuid4().hex[:6]}",
        "repository_url": "https://github.com/org/aigate"
    }, headers=headers).json()
    proj_id = p["id"]

    # 1. Attempt AI assistant on Free plan -> Rejected with 402
    ai_res = client.post("/api/v1/intelligence/assistant/chat", json={
        "project_id": proj_id,
        "message": "Give me refactoring advice"
    }, headers=headers)
    assert ai_res.status_code in (402, 403)
    assert "subscription plan" in ai_res.json()["detail"].lower()

    # 2. Upgrade to Starter tier via verified Razorpay order + HMAC verification
    import os, hmac, hashlib
    from unittest.mock import patch
    mock_order_id = f"order_q_{uuid.uuid4().hex[:10]}"
    mock_pay_id = f"pay_q_{uuid.uuid4().hex[:10]}"
    with patch.dict(os.environ, {"RAZORPAY_KEY_ID": "rzp_test_mock_q", "RAZORPAY_KEY_SECRET": "rzp_test_sec_q", "RAZORPAY_CURRENCY": "USD"}):
        with patch.object(BillingService, "_post_razorpay_order", return_value={"id": mock_order_id, "amount": 4900, "currency": "USD"}):
            up_res = client.post("/api/v1/billing/subscribe", json={
                "plan_slug": "starter",
                "billing_cycle": "monthly"
            }, headers=headers)
            assert up_res.status_code == 200
        sig = hmac.new(b"rzp_test_sec_q", f"{mock_order_id}|{mock_pay_id}".encode(), hashlib.sha256).hexdigest()
        ver_res = client.post("/api/v1/billing/razorpay/verify-payment", json={
            "plan_slug": "starter",
            "billing_cycle": "monthly",
            "razorpay_order_id": mock_order_id,
            "razorpay_payment_id": mock_pay_id,
            "razorpay_signature": sig,
        }, headers=headers)
        assert ver_res.status_code == 200

    # 3. Attempt AI assistant again -> Succeeded (200)
    ai_res_success = client.post("/api/v1/intelligence/assistant/chat", json={
        "project_id": proj_id,
        "message": "Give me refactoring advice"
    }, headers=headers)
    assert ai_res_success.status_code == 200
