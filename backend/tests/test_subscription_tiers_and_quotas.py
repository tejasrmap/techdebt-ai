import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.services.billing_service import BillingService
from app.models.all_models import Organization, SubscriptionPlan, Subscription, User, Project

client = TestClient(app)

def get_test_headers(plan: str = "free"):
    uid = uuid.uuid4().hex[:8]
    email = f"tier_tester_{uid}@techdebt.ai"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Tier Tester",
        "organization_name": f"Tier Org {uid}"
    })
    if reg.status_code in (200, 201):
        token = reg.json()["access_token"]
        org_id = reg.json()["user"]["org_id"]
    else:
        login = client.post("/api/v1/auth/login", json={
            "email": email,
            "password": "SecurePassword123!"
        })
        token = login.json()["access_token"]
        org_id = login.json()["user"]["org_id"]

    db = SessionLocal()
    try:
        BillingService.change_subscription_plan(db, org_id, plan)
    finally:
        db.close()

    return {"Authorization": f"Bearer {token}"}, org_id

def test_list_subscription_plans():
    resp = client.get("/api/v1/billing/plans")
    assert resp.status_code == 200
    plans = resp.json()
    assert len(plans) >= 4

    plan_ids = {p["id"] for p in plans}
    assert "free" in plan_ids
    assert "starter" in plan_ids
    assert "professional" in plan_ids
    assert "enterprise" in plan_ids

    free_plan = next(p for p in plans if p["id"] == "free")
    assert free_plan["max_projects"] == 1
    assert free_plan["max_assessments_per_month"] == 10
    assert free_plan["price_monthly"] == 0.0

    pro_plan = next(p for p in plans if p["id"] == "professional")
    assert pro_plan["max_projects"] == 50
    assert pro_plan["max_assessments_per_month"] == 500
    assert pro_plan["price_monthly"] == 199.0

def test_entitlement_limits_and_checks():
    db = SessionLocal()
    try:
        org_id = f"entitlement-org-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name=f"Entitled Org {uuid.uuid4().hex[:6]}", slug=f"slug-{uuid.uuid4().hex[:6]}", plan="free")
        db.add(org)
        db.commit()

        # Free tier: 1 project limit
        allowed, limit, current = BillingService.check_entitlement(db, org_id, "projects", additional_quantity=1)
        assert allowed is True
        assert limit == 1
        assert current == 0

        # Simulate existing project
        proj = Project(org_id=org_id, name="Sample Project")
        db.add(proj)
        db.commit()

        # Check entitlement for a 2nd project on Free tier -> should be False
        allowed2, limit2, current2 = BillingService.check_entitlement(db, org_id, "projects", additional_quantity=1)
        assert allowed2 is False
        assert limit2 == 1
        assert current2 == 1

        # Check AI recommendations on Free tier -> False
        allowed_ai, _, _ = BillingService.check_entitlement(db, org_id, "ai_recommendations")
        assert allowed_ai is False

        # Upgrade to starter -> AI recommendations allowed, 5 projects allowed
        BillingService.change_subscription_plan(db, org_id, "starter")
        allowed_upgrade, limit_up, _ = BillingService.check_entitlement(db, org_id, "projects", additional_quantity=1)
        assert allowed_upgrade is True
        assert limit_up == 5

        allowed_ai_up, _, _ = BillingService.check_entitlement(db, org_id, "ai_recommendations")
        assert allowed_ai_up is True
    finally:
        db.close()

def test_subscription_upgrade_api_workflow():
    headers, org_id = get_test_headers(plan="free")

    # 1. Check current subscription
    sub_res = client.get("/api/v1/billing/subscription", headers=headers)
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["plan_slug"] == "free"
    assert sub_data["limits"]["max_projects"] == 1

    # 2. Upgrade to starter tier via /subscribe endpoint
    up_res = client.post("/api/v1/billing/subscribe", json={
        "plan_slug": "starter",
        "billing_cycle": "monthly"
    }, headers=headers)
    assert up_res.status_code == 200
    up_data = up_res.json()
    assert up_data["status"] in ("active", "success")

    # 3. Check updated subscription
    updated_sub = client.get("/api/v1/billing/subscription", headers=headers).json()
    assert updated_sub["plan_slug"] == "starter"
    assert updated_sub["limits"]["max_projects"] == 5
    assert updated_sub["limits"]["max_assessments_per_month"] == 50
