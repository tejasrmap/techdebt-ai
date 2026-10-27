import uuid
import pytest
from app.database import SessionLocal
from app.models.all_models import Organization, SubscriptionPlan, Subscription
from app.services.billing_service import BillingService

def test_subscription_plans_seeded():
    """Verify standard commercial tiers (Free, Starter, Pro, Enterprise) exist."""
    db = SessionLocal()
    try:
        plans = BillingService.get_active_plans(db)
        slugs = [p["slug"] for p in plans]
        assert "free" in slugs
        assert "starter" in slugs
        assert "professional" in slugs
        assert "enterprise" in slugs
    finally:
        db.close()

def test_entitlement_enforcement_and_metering():
    """Verify tier limit checks and usage record increments."""
    db = SessionLocal()
    try:
        org = Organization(name=f"Entitlement Org {uuid.uuid4().hex[:6]}", slug=f"ent-{uuid.uuid4().hex[:6]}", plan="free")
        db.add(org)
        db.commit()

        # Free tier default has max_projects=1
        sub = BillingService.get_or_create_org_subscription(db, org.id)
        assert sub.plan.slug == "free"

        # Check entitlement for projects
        allowed, limit, current = BillingService.check_entitlement(db, org.id, "projects")
        assert allowed is True
        assert limit == 1
        assert current == 0

        # Record usage
        BillingService.record_usage(db, org.id, "monthly_assessments", 1)
        BillingService.record_usage(db, org.id, "monthly_assessments", 2)

        usage = BillingService.get_monthly_usage(db, org.id)
        assert usage.get("monthly_assessments", 0) == 3

        # Upgrade to Professional
        upgrade_res = BillingService.create_checkout_session(
            db=db,
            org_id=org.id,
            user_email="admin@example.com",
            plan_slug="professional",
            billing_cycle="annual"
        )
        assert upgrade_res["status"] in ("active", "checkout_ready")

        # Refresh subscription
        db.refresh(sub)
        assert sub.plan.slug == "professional"
        assert sub.plan.max_projects >= 50
    finally:
        db.close()
