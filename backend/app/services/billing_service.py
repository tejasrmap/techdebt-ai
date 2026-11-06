import os
import uuid
import time
import hmac
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set
from sqlalchemy.orm import Session

from app.models.all_models import (
    Organization, Subscription, SubscriptionPlan, UsageRecord, Invoice, User, Project, Notification
)

logger = logging.getLogger(__name__)

class QuotaExceededError(Exception):
    """Raised when an organization attempts an action exceeding their subscription plan limits."""
    pass

class BillingService:
    """
    Commercial SaaS subscription management, usage metering, quota enforcement,
    and Stripe billing integration engine.
    """

    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret_for_hmac_sha256")
    _processed_events: Set[str] = set()

    @classmethod
    def _ensure_standard_plans(cls, db: Session):
        """Ensures standard SaaS tiers exist in the database."""
        standard_plans = [
            {
                "id": "free",
                "name": "Community Free",
                "description": "Essential code quality and dependency health for solo developers",
                "price_monthly_cents": 0,
                "price_yearly_cents": 0,
                "max_projects": 1,
                "max_monthly_assessments": 10,
                "max_repo_size_mb": 25,
                "max_team_members": 1,
                "ai_recommendations_enabled": False,
                "advanced_code_analysis_enabled": True,
                "features": ["1 repository connection", "10 monthly assessments", "10-dimension debt score", "Basic code smell detection"]
            },
            {
                "id": "starter",
                "name": "Team Starter",
                "description": "Collaborative intelligence and dependency remediation for growing teams",
                "price_monthly_cents": 4900,
                "price_yearly_cents": 49000,
                "max_projects": 5,
                "max_monthly_assessments": 50,
                "max_repo_size_mb": 100,
                "max_team_members": 5,
                "ai_recommendations_enabled": True,
                "advanced_code_analysis_enabled": True,
                "features": ["Up to 5 repositories", "50 monthly assessments", "AI refactoring recipes", "Email & webhook alerts", "5 team seats"]
            },
            {
                "id": "professional",
                "name": "Professional",
                "description": "Complete architecture intelligence and automated governance for engineering organizations",
                "price_monthly_cents": 19900,
                "price_yearly_cents": 199000,
                "max_projects": 50,
                "max_monthly_assessments": 500,
                "max_repo_size_mb": 500,
                "max_team_members": 25,
                "ai_recommendations_enabled": True,
                "advanced_code_analysis_enabled": True,
                "features": ["Up to 50 repositories", "500 monthly assessments", "30/60/90-day modernization roadmaps", "Priority support", "25 team seats"]
            },
            {
                "id": "enterprise",
                "name": "Enterprise",
                "description": "Custom scale, unlimited repositories, dedicated VPC and SSO governance",
                "price_monthly_cents": 49900,
                "price_yearly_cents": 499000,
                "max_projects": 1000,
                "max_monthly_assessments": 10000,
                "max_repo_size_mb": 2048,
                "max_team_members": 1000,
                "ai_recommendations_enabled": True,
                "advanced_code_analysis_enabled": True,
                "features": ["Unlimited repositories", "Unlimited assessments", "SAML SSO & custom RBAC", "Dedicated SLA & architect onboarding"]
            }
        ]
        for p_data in standard_plans:
            existing = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == p_data["id"]).first()
            if not existing:
                plan = SubscriptionPlan(**p_data)
                db.add(plan)
            else:
                for k, v in p_data.items():
                    setattr(existing, k, v)
        db.commit()

    @classmethod
    def get_or_create_subscription(cls, db: Session, org_id: str) -> Subscription:
        """Retrieves active subscription or provisions default subscription according to org plan."""
        cls._ensure_standard_plans(db)
        sub = db.query(Subscription).filter(Subscription.org_id == org_id).first()
        org = db.query(Organization).filter(Organization.id == org_id).first()
        org_plan_slug = org.plan.lower() if org and org.plan and org.plan.lower() in ("free", "starter", "professional", "enterprise") else "free"

        if not sub:
            sub = Subscription(
                org_id=org_id,
                plan_id=org_plan_slug,
                status="active",
                billing_cycle="monthly",
                current_period_start=datetime.utcnow(),
                current_period_end=datetime.utcnow() + timedelta(days=30)
            )
            db.add(sub)
            db.commit()
            db.refresh(sub)
        elif org and org.plan and org.plan.lower() in ("professional", "enterprise") and sub.plan_id == "free":
            # Upgrade existing subscription if org was designated enterprise/professional
            sub.plan_id = org_plan_slug
            db.commit()
            db.refresh(sub)

        return sub

    get_or_create_org_subscription = get_or_create_subscription

    @classmethod
    def get_active_plans(cls, db: Session) -> List[Dict[str, Any]]:
        """List active subscription plans with commercial pricing and features."""
        cls._ensure_standard_plans(db)
        plans = db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True).all()
        return [
            {
                "id": p.id,
                "slug": p.id,
                "name": p.name,
                "description": p.description,
                "price_monthly": p.price_monthly_cents / 100.0,
                "price_annual": p.price_yearly_cents / 100.0 if p.price_yearly_cents else 0.0,
                "max_projects": p.max_projects,
                "max_assessments_per_month": p.max_monthly_assessments,
                "max_team_members": p.max_team_members,
                "features": p.features if isinstance(p.features, list) else []
            }
            for p in plans
        ]

    @classmethod
    def get_monthly_usage(cls, db: Session, org_id: str) -> Dict[str, Any]:
        """Calculates current period usage for an organization."""
        period = datetime.utcnow().strftime("%Y-%m")
        records = db.query(UsageRecord).filter(
            UsageRecord.org_id == org_id,
            UsageRecord.period == period
        ).all()
        usage = {r.metric_type: int(r.count) for r in records}
        usage.setdefault("projects", db.query(Project).filter(Project.org_id == org_id).count())
        usage.setdefault("team_members", db.query(User).filter(User.org_id == org_id).count())
        usage.setdefault("monthly_assessments", usage.get("monthly_assessments", 0))
        return usage

    @classmethod
    def check_entitlement(
        cls,
        db: Session,
        org_id: str,
        resource: str,  # 'projects', 'assessments', 'team_members', 'ai_recommendations', 'code_analysis'
        additional_quantity: int = 1
    ) -> Tuple[bool, int, int]:
        """
        Validates whether organization has sufficient quota under their active subscription plan.
        Returns (is_allowed, limit, current).
        """
        sub = cls.get_or_create_subscription(db, org_id)
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == sub.plan_id).first()
        if not plan:
            return True, 9999, 0

        period = datetime.utcnow().strftime("%Y-%m")

        if resource == "projects":
            current_projects = db.query(Project).filter(Project.org_id == org_id).count()
            allowed = (current_projects + additional_quantity) <= plan.max_projects
            return allowed, plan.max_projects, current_projects

        elif resource in ("assessments", "monthly_assessments"):
            usage = db.query(UsageRecord).filter(
                UsageRecord.org_id == org_id,
                UsageRecord.metric_type == "monthly_assessments",
                UsageRecord.period == period
            ).first()
            current_assessments = int(usage.count) if usage else 0
            allowed = (current_assessments + additional_quantity) <= plan.max_monthly_assessments
            return allowed, plan.max_monthly_assessments, current_assessments

        elif resource == "team_members":
            current_members = db.query(User).filter(User.org_id == org_id).count()
            allowed = (current_members + additional_quantity) <= plan.max_team_members
            return allowed, plan.max_team_members, current_members

        elif resource == "ai_recommendations":
            allowed = bool(plan.ai_recommendations_enabled)
            return allowed, 1 if allowed else 0, 0

        elif resource == "code_analysis":
            allowed = bool(plan.advanced_code_analysis_enabled)
            return allowed, 1 if allowed else 0, 0

        return True, 9999, 0

    @classmethod
    def record_usage(cls, db: Session, org_id: str, metric_type: str, count: float = 1.0):
        """Atomically increments monthly usage metric for tenant."""
        period = datetime.utcnow().strftime("%Y-%m")
        usage = db.query(UsageRecord).filter(
            UsageRecord.org_id == org_id,
            UsageRecord.metric_type == metric_type,
            UsageRecord.period == period
        ).first()

        if not usage:
            usage = UsageRecord(
                org_id=org_id,
                metric_type=metric_type,
                period=period,
                count=count
            )
            db.add(usage)
        else:
            usage.count += count
            usage.updated_at = datetime.utcnow()
        db.commit()

    @classmethod
    def change_subscription_plan(
        cls,
        db: Session,
        org_id: str,
        target_plan_id: str,
        billing_cycle: str = "monthly"
    ) -> Subscription:
        """
        Switches organization plan (used in direct upgrade/downgrade and webhook processing).
        Generates corresponding Invoice record.
        """
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == target_plan_id).first()
        if not plan:
            raise ValueError(f"Subscription plan '{target_plan_id}' does not exist.")

        sub = cls.get_or_create_subscription(db, org_id)
        sub.plan_id = target_plan_id
        sub.billing_cycle = billing_cycle
        sub.status = "active"
        sub.current_period_start = datetime.utcnow()
        sub.current_period_end = datetime.utcnow() + timedelta(days=365 if billing_cycle == "yearly" else 30)
        sub.cancel_at_period_end = False

        # Update organization plan string for backward compatibility
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if org:
            org.plan = target_plan_id

        # Generate invoice record
        amount = plan.price_yearly_cents if billing_cycle == "yearly" else plan.price_monthly_cents
        if amount > 0:
            inv = Invoice(
                org_id=org_id,
                invoice_number=f"INV-{datetime.utcnow().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}",
                amount_cents=amount,
                currency="usd",
                status="paid",
                hosted_invoice_url=f"/billing/invoices/download?id={uuid.uuid4().hex[:8]}",
                paid_at=datetime.utcnow()
            )
            db.add(inv)

        db.commit()
        db.refresh(sub)
        return sub

    @classmethod
    def create_checkout_session(
        cls,
        db: Session,
        org_id: str,
        plan_id: Optional[str] = None,
        plan_slug: Optional[str] = None,
        user_email: str = "",
        billing_cycle: str = "monthly",
        success_url: str = "",
        cancel_url: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generates Stripe Checkout Session if STRIPE_SECRET_KEY is configured.
        Otherwise provides immediate sandbox upgrade for seamless development & staging evaluation.
        """
        target_plan_id = plan_id or plan_slug or "starter"
        cls._ensure_standard_plans(db)
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == target_plan_id).first()
        if not plan:
            raise ValueError(f"Invalid plan '{target_plan_id}'.")

        if cls.STRIPE_SECRET_KEY and not cls.STRIPE_SECRET_KEY.startswith("mock_"):
            try:
                import stripe
                stripe.api_key = cls.STRIPE_SECRET_KEY
                amount = plan.price_yearly_cents if billing_cycle == "yearly" else plan.price_monthly_cents
                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    line_items=[{
                        "price_data": {
                            "currency": "usd",
                            "product_data": {
                                "name": f"TechDebt AI {plan.name}",
                                "description": plan.description,
                            },
                            "unit_amount": amount,
                            "recurring": {"interval": "year" if billing_cycle == "yearly" else "month"}
                        },
                        "quantity": 1,
                    }],
                    mode="subscription",
                    success_url=success_url or "http://localhost:5173/settings?tab=billing&session_id={CHECKOUT_SESSION_ID}",
                    cancel_url=cancel_url or "http://localhost:5173/settings?tab=billing",
                    client_reference_id=org_id,
                    metadata={"org_id": org_id, "plan_id": plan_id, "billing_cycle": billing_cycle}
                )
                return {
                    "mode": "live_stripe",
                    "checkout_url": session.url,
                    "session_id": session.id
                }
            except Exception as e:
                logger.error(f"Stripe Checkout error: {e}")
                # Fall through to sandbox activation

        # Sandbox activation when Stripe key is not configured or offline
        updated_sub = cls.change_subscription_plan(db, org_id, target_plan_id, billing_cycle)
        return {
            "mode": "sandbox",
            "message": f"Sandbox subscription to plan '{plan.name}' ({billing_cycle}) activated successfully.",
            "subscription_id": updated_sub.id,
            "plan_id": updated_sub.plan_id,
            "status": updated_sub.status
        }

    @classmethod
    def create_customer_portal_session(
        cls,
        db: Session,
        org_id: str,
        return_url: str = ""
    ) -> Dict[str, Any]:
        """
        Generates a Stripe Billing Customer Portal session to manage payment methods,
        invoices, and subscriptions. Falls back to internal settings portal when offline or in sandbox mode.
        """
        sub = cls.get_or_create_subscription(db, org_id)
        fallback_url = return_url or "http://localhost:5173/settings?tab=billing"

        if cls.STRIPE_SECRET_KEY and not cls.STRIPE_SECRET_KEY.startswith("mock_") and sub.stripe_customer_id:
            try:
                import stripe
                stripe.api_key = cls.STRIPE_SECRET_KEY
                portal_session = stripe.billing_portal.Session.create(
                    customer=sub.stripe_customer_id,
                    return_url=fallback_url
                )
                return {
                    "mode": "live_stripe",
                    "portal_url": portal_session.url,
                    "customer_id": sub.stripe_customer_id
                }
            except Exception as e:
                logger.error(f"Stripe Customer Portal session creation error: {e}")

        return {
            "mode": "sandbox",
            "portal_url": fallback_url,
            "message": "Customer portal active in local sandbox mode."
        }

    @classmethod
    def verify_stripe_signature(
        cls,
        payload_bytes: bytes,
        sig_header: str,
        secret: Optional[str] = None,
        tolerance_sec: int = 300
    ) -> bool:
        """
        Validates Stripe HMAC-SHA256 signature (t=timestamp,v1=signature) with timestamp drift protection.
        """
        webhook_secret = secret or cls.STRIPE_WEBHOOK_SECRET
        if not webhook_secret or not sig_header:
            return False

        # Try official stripe library if available
        try:
            import stripe
            stripe.WebhookSignature.verify_header(
                payload=payload_bytes.decode("utf-8"),
                header=sig_header,
                secret=webhook_secret,
                tolerance=tolerance_sec
            )
            return True
        except Exception:
            pass

        # Fallback manual HMAC-SHA256 verification
        try:
            parts = dict(item.strip().split("=", 1) for item in sig_header.split(","))
            t = parts.get("t")
            v1 = parts.get("v1")
            if not t or not v1:
                return False

            # Check timestamp drift
            timestamp = int(t)
            if abs(time.time() - timestamp) > tolerance_sec:
                logger.warning(f"Stripe signature timestamp drift exceeds {tolerance_sec}s")
                return False

            signed_payload = f"{t}.".encode("utf-8") + payload_bytes
            expected_mac = hmac.new(webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
            return hmac.compare_digest(v1, expected_mac)
        except Exception as e:
            logger.error(f"Stripe signature verification exception: {e}")
            return False

    @classmethod
    def handle_stripe_event(cls, db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatches verified Stripe webhook events. Guarantees idempotent execution.
        """
        event_id = payload.get("id")
        if event_id and event_id in cls._processed_events:
            return {"status": "ignored", "reason": "duplicate_event", "event_id": event_id}

        event_type = payload.get("type", "")
        data_object = payload.get("data", {}).get("object", {})

        action_taken = "none"

        # 1. Checkout session completed
        if event_type == "checkout.session.completed":
            org_id = data_object.get("client_reference_id") or data_object.get("metadata", {}).get("org_id")
            plan_id = data_object.get("metadata", {}).get("plan_id") or "starter"
            billing_cycle = data_object.get("metadata", {}).get("billing_cycle", "monthly")
            customer_id = data_object.get("customer", "")
            subscription_id = data_object.get("subscription", "")

            if org_id:
                sub = cls.change_subscription_plan(db, org_id, plan_id, billing_cycle)
                if customer_id:
                    sub.stripe_customer_id = customer_id
                if subscription_id:
                    sub.stripe_subscription_id = subscription_id
                db.commit()
                action_taken = "subscription_activated"

        # 2. Invoice payment succeeded
        elif event_type in ("invoice.payment_succeeded", "invoice.paid"):
            customer_id = data_object.get("customer")
            sub = db.query(Subscription).filter(Subscription.stripe_customer_id == customer_id).first() if customer_id else None
            if sub:
                sub.status = "active"
                amount_cents = data_object.get("amount_paid", data_object.get("amount_due", 0))
                inv_num = data_object.get("number") or f"INV-STRIPE-{uuid.uuid4().hex[:6].upper()}"
                
                inv = Invoice(
                    org_id=sub.org_id,
                    invoice_number=inv_num,
                    amount_cents=amount_cents,
                    currency=data_object.get("currency", "usd"),
                    status="paid",
                    hosted_invoice_url=data_object.get("hosted_invoice_url", ""),
                    paid_at=datetime.utcnow()
                )
                db.add(inv)
                db.commit()
                action_taken = "invoice_paid"

        # 3. Invoice payment failed
        elif event_type == "invoice.payment_failed":
            customer_id = data_object.get("customer")
            sub = db.query(Subscription).filter(Subscription.stripe_customer_id == customer_id).first() if customer_id else None
            if sub:
                sub.status = "past_due"
                # Emit warning notification
                notif = Notification(
                    org_id=sub.org_id,
                    title="Subscription Payment Failed",
                    message="Your recent subscription invoice payment failed. Please update your billing method.",
                    category="billing",
                    severity="error"
                )
                db.add(notif)
                db.commit()
                action_taken = "subscription_past_due"

        # 4. Subscription canceled / deleted
        elif event_type == "customer.subscription.deleted":
            customer_id = data_object.get("customer")
            sub = db.query(Subscription).filter(Subscription.stripe_customer_id == customer_id).first() if customer_id else None
            if sub:
                cls.change_subscription_plan(db, sub.org_id, "free")
                sub.status = "canceled"
                db.commit()
                action_taken = "subscription_downgraded_to_free"

        if event_id:
            cls._processed_events.add(event_id)

        return {
            "status": "success",
            "event_type": event_type,
            "action": action_taken,
            "event_id": event_id
        }

    @classmethod
    def generate_invoice(
        cls,
        db: Session,
        org_id: str,
        amount_cents: int,
        description: str = "Subscription renewal",
        status: str = "paid"
    ) -> Invoice:
        inv = Invoice(
            org_id=org_id,
            invoice_number=f"INV-{datetime.utcnow().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}",
            amount_cents=amount_cents,
            currency="usd",
            status=status,
            hosted_invoice_url=f"/api/v1/billing/invoices/download?id={uuid.uuid4().hex[:8]}",
            paid_at=datetime.utcnow() if status == "paid" else None
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)
        return inv

    @classmethod
    def render_invoice_html(cls, invoice: Invoice, org: Organization) -> str:
        """
        Renders a commercial, printable invoice HTML receipt for financial accounting.
        """
        amount_dollars = (invoice.amount_cents or 0) / 100.0
        date_str = invoice.created_at.strftime("%B %d, %Y") if invoice.created_at else "N/A"
        
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Invoice {invoice.invoice_number} - TechDebt AI</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1e293b; padding: 40px; max-width: 800px; margin: auto; }}
  .header {{ display: flex; justify-content: space-between; border-bottom: 2px solid #e2e8f0; padding-bottom: 20px; }}
  .brand {{ font-size: 24px; font-weight: 700; color: #4338ca; }}
  .vendor {{ font-size: 13px; color: #64748b; margin-top: 6px; }}
  .details {{ display: flex; justify-content: space-between; margin-top: 30px; }}
  .badge {{ display: inline-block; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 600; text-transform: uppercase; }}
  .badge-paid {{ background: #dcfce7; color: #15803d; }}
  .table {{ width: 100%; border-collapse: collapse; margin-top: 30px; }}
  .table th {{ background: #f8fafc; text-align: left; padding: 12px; font-size: 13px; border-bottom: 1px solid #cbd5e1; }}
  .table td {{ padding: 14px 12px; border-bottom: 1px solid #e2e8f0; font-size: 14px; }}
  .total {{ text-align: right; margin-top: 25px; font-size: 18px; font-weight: 700; }}
  @media print {{ body {{ padding: 0; }} }}
</style>
</head>
<body>
  <div class="header">
    <div>
      <div class="brand">TechDebt AI</div>
      <div class="vendor">GT InnoX LLP &bull; Software Engineering Intelligence Platform</div>
    </div>
    <div style="text-align: right;">
      <h2 style="margin: 0; color: #0f172a;">INVOICE</h2>
      <div style="color: #64748b; font-size: 14px; margin-top: 4px;">#{invoice.invoice_number}</div>
      <div style="margin-top: 8px;"><span class="badge badge-paid">{invoice.status}</span></div>
    </div>
  </div>

  <div class="details">
    <div>
      <div style="font-size: 12px; color: #64748b; text-transform: uppercase;">Billed To:</div>
      <div style="font-size: 16px; font-weight: 600; margin-top: 4px;">{org.name}</div>
      <div style="font-size: 13px; color: #64748b;">Account: {org.slug}</div>
    </div>
    <div style="text-align: right;">
      <div style="font-size: 13px;"><strong>Date Issued:</strong> {date_str}</div>
      <div style="font-size: 13px; margin-top: 4px;"><strong>Payment Method:</strong> Credit Card (Stripe)</div>
    </div>
  </div>

  <table class="table">
    <thead>
      <tr>
        <th>Description</th>
        <th>Qty</th>
        <th>Unit Price</th>
        <th style="text-align: right;">Amount</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>TechDebt AI SaaS Subscription ({org.plan.capitalize() if org.plan else 'Pro'})</td>
        <td>1</td>
        <td>${amount_dollars:,.2f}</td>
        <td style="text-align: right;">${amount_dollars:,.2f}</td>
      </tr>
    </tbody>
  </table>

  <div class="total">
    Total Paid: ${amount_dollars:,.2f} USD
  </div>
</body>
</html>
"""



