import os
import html
import uuid
import time
import json
import hmac
import base64
import hashlib
import logging
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.all_models import (
    Organization,
    Subscription,
    SubscriptionPlan,
    UsageRecord,
    Invoice,
    User,
    Project,
    Notification,
    PaymentOrder,
    BillingWebhookEvent,
)

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """Raised when an organization attempts an action exceeding their subscription plan limits."""
    pass


class PaymentGatewayUnavailableError(RuntimeError):
    """Raised when a paid checkout is attempted without a configured payment gateway."""
    pass


class BillingService:
    """
    Commercial SaaS subscription management, usage metering, quota enforcement,
    and server-verified Razorpay & Stripe billing integration engine (v3.1.0).
    """

    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.getenv(
        "STRIPE_WEBHOOK_SECRET",
        "" if os.getenv("ENVIRONMENT", settings.ENVIRONMENT).lower() == "production" else "whsec_test_secret_for_hmac_sha256",
    )
    RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders"
    RAZORPAY_PAYMENTS_URL = "https://api.razorpay.com/v1/payments"
    RAZORPAY_SUBSCRIPTIONS_URL = "https://api.razorpay.com/v1/subscriptions"
    ORDER_EXPIRY_HOURS = 24

    @classmethod
    def _is_production(cls) -> bool:
        return (os.getenv("ENVIRONMENT") or settings.ENVIRONMENT or "development").strip().lower() == "production"

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
                "features": [
                    "1 repository connection",
                    "10 monthly assessments",
                    "10-dimension debt score",
                    "Basic code smell detection",
                ],
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
                "features": [
                    "Up to 5 repositories",
                    "50 monthly assessments",
                    "AI refactoring recipes",
                    "Email & webhook alerts",
                    "5 team seats",
                ],
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
                "features": [
                    "Up to 50 repositories",
                    "500 monthly assessments",
                    "30/60/90-day modernization roadmaps",
                    "Priority support",
                    "25 team seats",
                ],
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
                "features": [
                    "Unlimited repositories",
                    "Unlimited assessments",
                    "SAML SSO & custom RBAC",
                    "Dedicated SLA & architect onboarding",
                ],
            },
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
        """Retrieves active subscription or provisions default Free subscription if none exists."""
        cls._ensure_standard_plans(db)
        sub = db.query(Subscription).filter(Subscription.org_id == org_id).first()
        if sub:
            return sub

        org = db.query(Organization).filter(Organization.id == org_id).first()
        org_plan_slug = (
            org.plan.lower()
            if org and org.plan and org.plan.lower() in ("free", "starter", "professional", "enterprise")
            else "free"
        )
        sub = Subscription(
            org_id=org_id,
            plan_id=org_plan_slug,
            status="active",
            billing_cycle="monthly",
            payment_provider="none" if org_plan_slug == "free" else "manual",
            current_period_start=datetime.utcnow(),
            current_period_end=datetime.utcnow() + timedelta(days=30),
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    get_or_create_org_subscription = get_or_create_subscription

    @classmethod
    def get_active_plans(cls, db: Session) -> List[Dict[str, Any]]:
        """List active subscription plans with commercial pricing and features."""
        cls._ensure_standard_plans(db)
        plans = db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True).all()
        _, _, _, currency = cls.get_razorpay_credentials()
        return [
            {
                "id": p.id,
                "slug": p.id,
                "name": p.name,
                "description": p.description,
                "currency": currency,
                "price_monthly": p.price_monthly_cents / 100.0,
                "price_annual": p.price_yearly_cents / 100.0 if p.price_yearly_cents else 0.0,
                "max_projects": p.max_projects,
                "max_assessments_per_month": p.max_monthly_assessments,
                "max_team_members": p.max_team_members,
                "ai_recommendations_enabled": bool(p.ai_recommendations_enabled),
                "features": p.features if isinstance(p.features, list) else [],
            }
            for p in plans
        ]

    @classmethod
    def get_monthly_usage(cls, db: Session, org_id: str) -> Dict[str, Any]:
        """Calculates current period usage for an organization."""
        period = datetime.utcnow().strftime("%Y-%m")
        records = (
            db.query(UsageRecord)
            .filter(UsageRecord.org_id == org_id, UsageRecord.period == period)
            .all()
        )
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
        resource: str,
        additional_quantity: int = 1,
    ) -> Tuple[bool, int, int]:
        """
        Validates whether organization has sufficient quota under their active subscription plan.
        Returns (is_allowed, limit, current).
        """
        sub = cls.get_or_create_subscription(db, org_id)
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == sub.plan_id).first()
        if not plan:
            return False, 0, 0

        period = datetime.utcnow().strftime("%Y-%m")

        if resource == "projects":
            current_projects = db.query(Project).filter(Project.org_id == org_id, Project.is_archived == False).count()
            allowed = (current_projects + additional_quantity) <= plan.max_projects
            return allowed, plan.max_projects, current_projects

        elif resource in ("assessments", "monthly_assessments"):
            usage = (
                db.query(UsageRecord)
                .filter(
                    UsageRecord.org_id == org_id,
                    UsageRecord.metric_type == "monthly_assessments",
                    UsageRecord.period == period,
                )
                .first()
            )
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
        usage = (
            db.query(UsageRecord)
            .filter(
                UsageRecord.org_id == org_id,
                UsageRecord.metric_type == metric_type,
                UsageRecord.period == period,
            )
            .first()
        )

        if not usage:
            usage = UsageRecord(
                org_id=org_id,
                metric_type=metric_type,
                period=period,
                count=count,
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
        billing_cycle: str = "monthly",
        payment_provider: str = "manual",
        create_paid_invoice: bool = False,
        invoice_currency: str = "usd",
        invoice_amount_cents: Optional[int] = None,
        invoice_prefix: str = "INV",
    ) -> Subscription:
        """
        Switches organization plan cleanly.
        Does NOT fabricate paid invoices unless explicitly triggered by a verified provider payment.
        """
        cls._ensure_standard_plans(db)
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == target_plan_id).first()
        if not plan:
            raise ValueError(f"Subscription plan '{target_plan_id}' does not exist.")

        normalized_cycle = "yearly" if billing_cycle in ("yearly", "annual") else "monthly"
        sub = cls.get_or_create_subscription(db, org_id)
        sub.plan_id = target_plan_id
        sub.billing_cycle = normalized_cycle
        sub.status = "active"
        sub.payment_provider = "none" if target_plan_id == "free" else payment_provider
        sub.current_period_start = datetime.utcnow()
        sub.current_period_end = datetime.utcnow() + timedelta(days=365 if normalized_cycle == "yearly" else 30)
        sub.cancel_at_period_end = False

        org = db.query(Organization).filter(Organization.id == org_id).first()
        if org:
            org.plan = target_plan_id

        amount = (
            int(invoice_amount_cents)
            if invoice_amount_cents is not None
            else (plan.price_yearly_cents if normalized_cycle == "yearly" else plan.price_monthly_cents)
        )
        if create_paid_invoice and amount > 0:
            inv = Invoice(
                org_id=org_id,
                invoice_number=f"{invoice_prefix}-{datetime.utcnow().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}",
                amount_cents=amount,
                currency=(invoice_currency or "usd").lower(),
                status="paid",
                paid_at=datetime.utcnow(),
            )
            db.add(inv)
            db.flush()
            inv.hosted_invoice_url = f"/api/v1/billing/invoices/{inv.id}/download"

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
        user_id: Optional[str] = None,
        billing_cycle: str = "monthly",
        success_url: str = "",
        cancel_url: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Initiates verified payment checkout for paid plans or downgrades directly to Free.
        NEVER activates a paid subscription or creates a paid invoice without verified payment.
        """
        target_plan_id = plan_id or plan_slug or "starter"
        cls._ensure_standard_plans(db)
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == target_plan_id).first()
        if not plan:
            raise ValueError(f"Invalid plan '{target_plan_id}'.")

        normalized_cycle = "yearly" if billing_cycle in ("yearly", "annual") else "monthly"
        amount = plan.price_yearly_cents if normalized_cycle == "yearly" else plan.price_monthly_cents

        if plan.id == "free" or amount <= 0:
            updated_sub = cls.change_subscription_plan(
                db, org_id, "free", normalized_cycle, payment_provider="none", create_paid_invoice=False
            )
            return {
                "mode": "free_downgrade",
                "message": "Subscription updated to Community Free tier.",
                "subscription_id": updated_sub.id,
                "plan_id": updated_sub.plan_id,
                "status": updated_sub.status,
            }

        stripe_key = (os.getenv("STRIPE_SECRET_KEY") or cls.STRIPE_SECRET_KEY or "").strip()
        if stripe_key and not stripe_key.startswith("mock_"):
            try:
                import stripe

                stripe.api_key = stripe_key
                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    line_items=[
                        {
                            "price_data": {
                                "currency": "usd",
                                "product_data": {
                                    "name": f"TechDebt AI {plan.name}",
                                    "description": plan.description,
                                },
                                "unit_amount": amount,
                                "recurring": {"interval": "year" if normalized_cycle == "yearly" else "month"},
                            },
                            "quantity": 1,
                        }
                    ],
                    mode="subscription",
                    success_url=success_url or "http://localhost:5173/settings?tab=billing&session_id={CHECKOUT_SESSION_ID}",
                    cancel_url=cancel_url or "http://localhost:5173/settings?tab=billing",
                    client_reference_id=org_id,
                    metadata={"org_id": org_id, "plan_id": plan.id, "billing_cycle": normalized_cycle},
                )
                order_record = PaymentOrder(
                    org_id=org_id,
                    user_id=user_id,
                    provider="stripe",
                    provider_order_id=session.id,
                    plan_id=plan.id,
                    billing_cycle=normalized_cycle,
                    amount_subunits=int(amount),
                    currency="USD",
                    status="created",
                    expires_at=datetime.utcnow() + timedelta(hours=cls.ORDER_EXPIRY_HOURS),
                )
                db.add(order_record)
                db.commit()
                return {
                    "mode": "live_stripe",
                    "status": "pending_payment",
                    "checkout_url": session.url,
                    "session_id": session.id,
                }
            except Exception as e:
                logger.error(f"Stripe Checkout error: {e}")
                raise PaymentGatewayUnavailableError("Stripe checkout session initialization failed.") from e

        key_id, key_secret, _, _ = cls.get_razorpay_credentials()
        if key_id and key_secret:
            order_data = cls.create_razorpay_order(
                db=db,
                org_id=org_id,
                plan_slug=plan.id,
                billing_cycle=normalized_cycle,
                user_email=user_email,
                user_id=user_id,
            )
            order_data["status"] = "pending_payment"
            return order_data

        raise PaymentGatewayUnavailableError(
            "Payment gateway is not configured. Paid plan upgrades require verified Razorpay or Stripe payment."
        )

    @classmethod
    def create_customer_portal_session(
        cls,
        db: Session,
        org_id: str,
        return_url: str = "",
    ) -> Dict[str, Any]:
        """Generates billing portal session or returns self-service billing view URL."""
        sub = cls.get_or_create_subscription(db, org_id)
        fallback_url = return_url or "/dashboard/billing"

        stripe_key = (os.getenv("STRIPE_SECRET_KEY") or cls.STRIPE_SECRET_KEY or "").strip()
        stripe_cust = sub.provider_customer_id if sub.payment_provider == "stripe" else sub.stripe_customer_id
        if stripe_key and not stripe_key.startswith("mock_") and stripe_cust and stripe_cust.startswith("cus_"):
            try:
                import stripe

                stripe.api_key = stripe_key
                portal_session = stripe.billing_portal.Session.create(
                    customer=stripe_cust,
                    return_url=fallback_url,
                )
                return {
                    "mode": "live_stripe",
                    "portal_url": portal_session.url,
                    "customer_id": stripe_cust,
                }
            except Exception as e:
                logger.error(f"Stripe Customer Portal session creation error: {e}")

        return {
            "mode": "self_service",
            "portal_url": fallback_url,
            "payment_provider": sub.payment_provider or "none",
            "message": "Manage subscription, Razorpay orders, and invoices in the TechDebt AI Billing view.",
        }

    # ==========================================================================
    # Persistent Webhook Event Recording & Idempotency
    # ==========================================================================

    @classmethod
    def _derive_webhook_event_id(cls, provider: str, explicit_event_id: str, raw_body: Optional[bytes], payload: Dict[str, Any]) -> str:
        clean_id = (explicit_event_id or payload.get("id") or "").strip()
        if clean_id:
            return f"{provider}:{clean_id}" if not clean_id.startswith(f"{provider}:") and provider == "razorpay" else clean_id
        digest_source = raw_body if raw_body is not None else json.dumps(payload, sort_keys=True).encode("utf-8")
        return f"{provider}_sha256:{hashlib.sha256(digest_source).hexdigest()}"

    @classmethod
    def _begin_webhook_event(
        cls,
        db: Session,
        provider: str,
        event_id: str,
        event_type: str,
        payload_hash: str,
        org_id: Optional[str] = None,
    ) -> Optional[BillingWebhookEvent]:
        """
        Atomically inserts a BillingWebhookEvent row using a SAVEPOINT so duplicate/concurrent
        webhook deliveries return None cleanly without rolling back outer state.
        """
        existing = db.query(BillingWebhookEvent).filter(BillingWebhookEvent.event_id == event_id).first()
        if existing:
            return None
        record = BillingWebhookEvent(
            provider=provider,
            event_id=event_id,
            event_type=event_type or "unknown",
            org_id=org_id,
            payload_hash=payload_hash,
            status="processing",
            action_taken="none",
        )
        try:
            nested = db.begin_nested()
            db.add(record)
            db.flush()
            nested.commit()
            return record
        except IntegrityError:
            nested.rollback()
            return None

    # ==========================================================================
    # Stripe Signature & Event Engine
    # ==========================================================================

    @classmethod
    def verify_stripe_signature(
        cls,
        payload_bytes: bytes,
        sig_header: str,
        secret: Optional[str] = None,
        tolerance_sec: int = 300,
    ) -> bool:
        """Validates Stripe HMAC-SHA256 signature (t=timestamp,v1=signature) with timestamp drift protection."""
        default_secret = "" if cls._is_production() else cls.STRIPE_WEBHOOK_SECRET
        webhook_secret = (secret if secret is not None else (os.getenv("STRIPE_WEBHOOK_SECRET") or default_secret)).strip()
        if not webhook_secret or not sig_header:
            return False

        try:
            import stripe

            stripe.WebhookSignature.verify_header(
                payload=payload_bytes.decode("utf-8"),
                header=sig_header,
                secret=webhook_secret,
                tolerance=tolerance_sec,
            )
            return True
        except Exception:
            pass

        try:
            parts = dict(item.strip().split("=", 1) for item in sig_header.split(",") if "=" in item)
            t = parts.get("t")
            v1 = parts.get("v1")
            if not t or not v1:
                return False

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
    def handle_stripe_event(cls, db: Session, payload: Dict[str, Any], raw_body: Optional[bytes] = None) -> Dict[str, Any]:
        """Dispatches verified Stripe webhook events with database-backed idempotency."""
        raw_event_id = payload.get("id", "")
        event_type = payload.get("type", "")
        payload_bytes = raw_body if raw_body is not None else json.dumps(payload, sort_keys=True).encode("utf-8")
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        event_key = cls._derive_webhook_event_id("stripe", raw_event_id, payload_bytes, payload)

        data_object = payload.get("data", {}).get("object", {})
        org_id = data_object.get("client_reference_id") or data_object.get("metadata", {}).get("org_id")

        webhook_row = cls._begin_webhook_event(
            db=db,
            provider="stripe",
            event_id=event_key,
            event_type=event_type,
            payload_hash=payload_hash,
            org_id=org_id,
        )
        if webhook_row is None:
            return {"status": "ignored", "reason": "duplicate_event", "event_id": raw_event_id or event_key}

        action_taken = "none"

        if event_type == "checkout.session.completed":
            session_id = data_object.get("id", "")
            order_row = (
                db.query(PaymentOrder).filter(PaymentOrder.provider_order_id == session_id).first()
                if session_id
                else None
            )
            if order_row:
                org_id = order_row.org_id
                plan_id = order_row.plan_id
                billing_cycle = order_row.billing_cycle
                order_row.status = "paid"
                order_row.verified_at = datetime.utcnow()
            else:
                plan_id = data_object.get("metadata", {}).get("plan_id") or "starter"
                billing_cycle = data_object.get("metadata", {}).get("billing_cycle", "monthly")

            customer_id = data_object.get("customer", "")
            subscription_id = data_object.get("subscription", "")

            if org_id:
                sub = cls.change_subscription_plan(
                    db,
                    org_id,
                    plan_id,
                    billing_cycle,
                    payment_provider="stripe",
                    create_paid_invoice=True,
                    invoice_currency="usd",
                    invoice_prefix="INV-STR",
                )
                if customer_id:
                    sub.provider_customer_id = customer_id
                    sub.stripe_customer_id = customer_id
                if subscription_id:
                    sub.provider_subscription_id = subscription_id
                    sub.stripe_subscription_id = subscription_id
                webhook_row.org_id = org_id
                action_taken = "subscription_activated"

        elif event_type in ("invoice.payment_succeeded", "invoice.paid"):
            customer_id = data_object.get("customer")
            sub = (
                db.query(Subscription)
                .filter(
                    (Subscription.provider_customer_id == customer_id)
                    | (Subscription.stripe_customer_id == customer_id)
                )
                .first()
                if customer_id
                else None
            )
            if sub:
                sub.status = "active"
                amount_cents = int(data_object.get("amount_paid", data_object.get("amount_due", 0)) or 0)
                inv_num = data_object.get("number") or f"INV-STRIPE-{uuid.uuid4().hex[:6].upper()}"
                if not db.query(Invoice).filter(Invoice.invoice_number == inv_num).first():
                    inv = Invoice(
                        org_id=sub.org_id,
                        invoice_number=inv_num,
                        amount_cents=amount_cents,
                        currency=data_object.get("currency", "usd"),
                        status="paid",
                        hosted_invoice_url=data_object.get("hosted_invoice_url", ""),
                        paid_at=datetime.utcnow(),
                    )
                    db.add(inv)
                webhook_row.org_id = sub.org_id
                action_taken = "invoice_paid"

        elif event_type == "invoice.payment_failed":
            customer_id = data_object.get("customer")
            sub = (
                db.query(Subscription)
                .filter(
                    (Subscription.provider_customer_id == customer_id)
                    | (Subscription.stripe_customer_id == customer_id)
                )
                .first()
                if customer_id
                else None
            )
            if sub:
                sub.status = "past_due"
                notif = Notification(
                    org_id=sub.org_id,
                    title="Subscription Payment Failed",
                    message="Your recent subscription invoice payment failed. Please update your billing method.",
                    category="billing",
                    severity="error",
                )
                db.add(notif)
                webhook_row.org_id = sub.org_id
                action_taken = "subscription_past_due"

        elif event_type == "customer.subscription.deleted":
            customer_id = data_object.get("customer")
            sub = (
                db.query(Subscription)
                .filter(
                    (Subscription.provider_customer_id == customer_id)
                    | (Subscription.stripe_customer_id == customer_id)
                )
                .first()
                if customer_id
                else None
            )
            if sub:
                cls.change_subscription_plan(db, sub.org_id, "free", payment_provider="none", create_paid_invoice=False)
                sub.status = "canceled"
                webhook_row.org_id = sub.org_id
                action_taken = "subscription_downgraded_to_free"

        webhook_row.status = "processed"
        webhook_row.action_taken = action_taken
        webhook_row.processed_at = datetime.utcnow()
        db.commit()

        return {
            "status": "success",
            "event_type": event_type,
            "action": action_taken,
            "event_id": raw_event_id or event_key,
        }

    # ==========================================================================
    # Invoice Generation & XSS-Safe Rendering
    # ==========================================================================

    @classmethod
    def generate_invoice(
        cls,
        db: Session,
        org_id: str,
        amount_cents: int,
        description: str = "Subscription renewal",
        status: str = "paid",
        currency: str = "usd",
    ) -> Invoice:
        if amount_cents <= 0:
            raise ValueError("Invoice amount must be positive.")
        inv = Invoice(
            org_id=org_id,
            invoice_number=f"INV-{datetime.utcnow().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}",
            amount_cents=int(amount_cents),
            currency=(currency or "usd").lower(),
            status=status,
            paid_at=datetime.utcnow() if status == "paid" else None,
        )
        db.add(inv)
        db.flush()
        inv.hosted_invoice_url = f"/api/v1/billing/invoices/{inv.id}/download"
        db.commit()
        db.refresh(inv)
        return inv

    @classmethod
    def render_invoice_html(cls, invoice: Invoice, org: Optional[Organization]) -> str:
        """Renders an XSS-safe printable invoice HTML receipt for financial accounting."""
        amount_dollars = (invoice.amount_cents or 0) / 100.0
        date_str = invoice.created_at.strftime("%B %d, %Y") if invoice.created_at else "N/A"
        safe_inv_num = html.escape(str(invoice.invoice_number or "N/A"))
        safe_status = html.escape(str(invoice.status or "open"))
        safe_org_name = html.escape(str(org.name if org and org.name else "Organization"))
        safe_org_slug = html.escape(str(org.slug if org and org.slug else "N/A"))
        safe_plan = html.escape(str((org.plan.capitalize() if org and org.plan else "Subscription")))
        safe_currency = html.escape(str((invoice.currency or "usd").upper()))
        currency_symbol = "₹" if safe_currency == "INR" else "$"
        payment_method = (
            "Razorpay (Verified Order / Card / UPI)"
            if (invoice.invoice_number or "").startswith("INV-RZP") or bool(settings.RAZORPAY_KEY_ID)
            else "Verified Payment Gateway"
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Invoice {safe_inv_num} - TechDebt AI</title>
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
      <div style="color: #64748b; font-size: 14px; margin-top: 4px;">#{safe_inv_num}</div>
      <div style="margin-top: 8px;"><span class="badge badge-paid">{safe_status}</span></div>
    </div>
  </div>

  <div class="details">
    <div>
      <div style="font-size: 12px; color: #64748b; text-transform: uppercase;">Billed To:</div>
      <div style="font-size: 16px; font-weight: 600; margin-top: 4px;">{safe_org_name}</div>
      <div style="font-size: 13px; color: #64748b;">Account: {safe_org_slug}</div>
    </div>
    <div style="text-align: right;">
      <div style="font-size: 13px;"><strong>Date Issued:</strong> {date_str}</div>
      <div style="font-size: 13px; margin-top: 4px;"><strong>Payment Method:</strong> {payment_method}</div>
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
        <td>TechDebt AI SaaS Subscription ({safe_plan})</td>
        <td>1</td>
        <td>{currency_symbol}{amount_dollars:,.2f}</td>
        <td style="text-align: right;">{currency_symbol}{amount_dollars:,.2f}</td>
      </tr>
    </tbody>
  </table>

  <div class="total">
    Total Paid: {currency_symbol}{amount_dollars:,.2f} {safe_currency}
  </div>
</body>
</html>
"""

    # ==========================================================================
    # Razorpay Server-Bound Order, Payment Verification & Webhook Engine
    # ==========================================================================

    @classmethod
    def get_razorpay_credentials(cls) -> Tuple[str, str, str, str]:
        key_id = os.environ["RAZORPAY_KEY_ID"] if "RAZORPAY_KEY_ID" in os.environ else (settings.RAZORPAY_KEY_ID or "")
        key_secret = os.environ["RAZORPAY_KEY_SECRET"] if "RAZORPAY_KEY_SECRET" in os.environ else (settings.RAZORPAY_KEY_SECRET or "")
        webhook_secret = os.environ["RAZORPAY_WEBHOOK_SECRET"] if "RAZORPAY_WEBHOOK_SECRET" in os.environ else (settings.RAZORPAY_WEBHOOK_SECRET or "")
        currency = (
            os.environ["RAZORPAY_CURRENCY"] if "RAZORPAY_CURRENCY" in os.environ and os.environ["RAZORPAY_CURRENCY"].strip() else (settings.RAZORPAY_CURRENCY or "USD")
        ).upper()
        return key_id.strip(), key_secret.strip(), webhook_secret.strip(), currency

    @classmethod
    def get_razorpay_public_config(cls) -> Dict[str, Any]:
        """Returns public Razorpay Checkout config (NEVER exposes secret key)."""
        key_id, key_secret, _, currency = cls.get_razorpay_credentials()
        enabled = bool(key_id and key_secret)
        return {
            "enabled": enabled,
            "key_id": key_id if enabled else "",
            "currency": currency,
            "billing_mode": "one_time_period_order",
            "auto_renews": False,
            "vendor": "GT InnoX LLP",
        }

    @classmethod
    def _post_razorpay_order(cls, key_id: str, key_secret: str, order_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executes authenticated POST /v1/orders call to Razorpay Orders API."""
        basic_token = base64.b64encode(f"{key_id}:{key_secret}".encode("utf-8")).decode("ascii")
        req = urllib.request.Request(
            cls.RAZORPAY_ORDERS_URL,
            data=json.dumps(order_payload).encode("utf-8"),
            headers={
                "Authorization": f"Basic {basic_token}",
                "Content-Type": "application/json",
                "User-Agent": "TechDebtAI/3.1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"Razorpay order creation HTTP {e.code}: {err_body}")
            raise ValueError(f"Razorpay order creation failed ({e.code})") from e
        except Exception as e:
            logger.error(f"Razorpay order creation network error: {e}")
            raise ValueError("Razorpay order service is temporarily unavailable.") from e

    @classmethod
    def _fetch_razorpay_payment(cls, key_id: str, key_secret: str, payment_id: str) -> Dict[str, Any]:
        """Executes authenticated GET /v1/payments/{id} call to verify provider payment state."""
        basic_token = base64.b64encode(f"{key_id}:{key_secret}".encode("utf-8")).decode("ascii")
        req = urllib.request.Request(
            f"{cls.RAZORPAY_PAYMENTS_URL}/{payment_id}",
            headers={
                "Authorization": f"Basic {basic_token}",
                "Accept": "application/json",
                "User-Agent": "TechDebtAI/3.1.0",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"Razorpay payment fetch HTTP {e.code}: {err_body}")
            raise PermissionError(f"Unable to verify payment state with Razorpay ({e.code}).") from e
        except Exception as e:
            logger.error(f"Razorpay payment fetch network error: {e}")
            raise ValueError("Razorpay payment verification API is temporarily unreachable.") from e

    @classmethod
    def create_razorpay_order(
        cls,
        db: Session,
        org_id: str,
        plan_slug: str,
        billing_cycle: str = "monthly",
        user_email: str = "",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a persistent server-side PaymentOrder bound to org, plan, cycle, amount, and currency."""
        cls._ensure_standard_plans(db)
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_slug).first()
        if not plan:
            raise ValueError(f"Invalid plan '{plan_slug}'.")

        normalized_cycle = "yearly" if billing_cycle in ("yearly", "annual") else "monthly"
        amount_subunits = int(
            plan.price_yearly_cents if normalized_cycle == "yearly" else plan.price_monthly_cents
        )

        if plan.id == "free" or amount_subunits <= 0:
            sub = cls.change_subscription_plan(
                db, org_id, "free", normalized_cycle, payment_provider="none", create_paid_invoice=False
            )
            return {
                "mode": "free_downgrade",
                "status": sub.status,
                "plan_slug": sub.plan_id,
                "message": "Subscription updated to Community Free tier.",
            }

        key_id, key_secret, _, currency = cls.get_razorpay_credentials()
        if not key_id or not key_secret:
            raise ValueError("Razorpay credentials are not configured on the server.")

        receipt = f"tdai_{org_id[:8]}_{uuid.uuid4().hex[:10]}"[:40]
        order_payload = {
            "amount": amount_subunits,
            "currency": currency,
            "receipt": receipt,
            "notes": {
                "org_id": org_id,
                "plan_slug": plan.id,
                "billing_cycle": normalized_cycle,
                "user_email": user_email,
                "vendor": "GT InnoX LLP",
            },
        }
        order = cls._post_razorpay_order(key_id, key_secret, order_payload)

        provider_order_id = str(order.get("id") or "").strip()
        provider_amount = int(order.get("amount", -1))
        provider_currency = str(order.get("currency") or "").upper()
        if not provider_order_id or provider_amount != amount_subunits or provider_currency != currency:
            raise ValueError("Razorpay order response did not match requested server-side amount or currency.")

        expires_at = datetime.utcnow() + timedelta(hours=cls.ORDER_EXPIRY_HOURS)
        payment_order = PaymentOrder(
            org_id=org_id,
            user_id=user_id,
            provider="razorpay",
            provider_order_id=provider_order_id,
            plan_id=plan.id,
            billing_cycle=normalized_cycle,
            amount_subunits=amount_subunits,
            currency=currency,
            status="created",
            receipt=order.get("receipt", receipt),
            expires_at=expires_at,
        )
        db.add(payment_order)
        db.commit()
        db.refresh(payment_order)

        return {
            "mode": "live_razorpay",
            "key_id": key_id,
            "internal_order_id": payment_order.id,
            "order_id": provider_order_id,
            "amount": provider_amount,
            "currency": provider_currency,
            "receipt": payment_order.receipt,
            "plan_slug": plan.id,
            "plan_name": plan.name,
            "billing_cycle": normalized_cycle,
            "billing_type": "one_time_period_order",
            "auto_renews": False,
            "expires_at": expires_at.isoformat(),
            "vendor": "GT InnoX LLP",
        }

    @classmethod
    def verify_razorpay_payment_signature(
        cls,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
        secret: Optional[str] = None,
    ) -> bool:
        """
        Cryptographically verifies Razorpay Checkout signature:
        HMAC-SHA256(order_id + "|" + payment_id, key_secret).
        """
        _, default_secret, _, _ = cls.get_razorpay_credentials()
        key_secret = (secret if secret is not None else default_secret).strip()
        if not key_secret or not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
            return False
        msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        expected = hmac.new(key_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, razorpay_signature.strip())

    @classmethod
    def complete_razorpay_payment(
        cls,
        db: Session,
        org_id: str,
        plan_slug: str,
        billing_cycle: str,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
        verify_provider_api: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Verifies Razorpay signature AND binds activation strictly to the persisted server-side
        PaymentOrder (org, plan, cycle, amount, currency, expiry, and provider payment state).
        """
        order_id_clean = (razorpay_order_id or "").strip()
        payment_id_clean = (razorpay_payment_id or "").strip()
        if not order_id_clean or not payment_id_clean:
            raise PermissionError("Missing Razorpay order ID or payment ID.")

        # 1. Verify cryptographic HMAC signature
        if not cls.verify_razorpay_payment_signature(
            razorpay_order_id=order_id_clean,
            razorpay_payment_id=payment_id_clean,
            razorpay_signature=razorpay_signature,
        ):
            raise PermissionError("Invalid Razorpay cryptographic payment signature.")

        # 2. Fetch previously created server-side order
        payment_order = (
            db.query(PaymentOrder)
            .filter(PaymentOrder.provider_order_id == order_id_clean, PaymentOrder.provider == "razorpay")
            .first()
        )
        if not payment_order:
            raise PermissionError("Unknown or unverified Razorpay order ID.")

        # 3. Verify organisation ownership
        if payment_order.org_id != org_id:
            raise PermissionError("Order does not belong to the authenticated organization.")

        # 4. Database-backed payment replay & idempotency check
        existing_payment_owner = (
            db.query(PaymentOrder)
            .filter(PaymentOrder.provider_payment_id == payment_id_clean)
            .first()
        )
        if existing_payment_owner and existing_payment_owner.id != payment_order.id:
            raise PermissionError("Payment ID has already been linked to another order.")

        if payment_order.status == "paid":
            if payment_order.provider_payment_id == payment_id_clean:
                sub = cls.get_or_create_subscription(db, org_id)
                return {
                    "status": "already_processed",
                    "subscription_id": sub.id,
                    "plan_slug": sub.plan_id,
                    "payment_id": payment_id_clean,
                    "order_id": order_id_clean,
                }
            raise PermissionError("Order has already been fulfilled with a different payment ID.")

        if payment_order.status in ("failed", "expired", "refunded"):
            raise PermissionError(f"Payment order cannot be completed from state '{payment_order.status}'.")

        # 5. Check order expiration
        if payment_order.expires_at and payment_order.expires_at < datetime.utcnow():
            payment_order.status = "expired"
            db.commit()
            raise PermissionError("Payment order has expired. Please initiate a new checkout.")

        # 6. Verify selected plan and billing cycle against server-side order (never trust client!)
        normalized_cycle = "yearly" if billing_cycle in ("yearly", "annual") else "monthly"
        if plan_slug != payment_order.plan_id or normalized_cycle != payment_order.billing_cycle:
            raise PermissionError(
                "Tampered plan or billing cycle detected: does not match server-side payment order."
            )

        cls._ensure_standard_plans(db)
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == payment_order.plan_id).first()
        if not plan:
            raise ValueError(f"Subscription plan '{payment_order.plan_id}' does not exist.")

        # 7. Verify amount and currency integrity against server plan pricing
        key_id, key_secret, _, configured_currency = cls.get_razorpay_credentials()
        expected_amount = int(
            plan.price_yearly_cents if payment_order.billing_cycle == "yearly" else plan.price_monthly_cents
        )
        if int(payment_order.amount_subunits) != expected_amount:
            raise PermissionError("Order amount does not match canonical plan price.")
        if payment_order.currency.upper() != configured_currency.upper():
            raise PermissionError("Order currency mismatch against configured merchant currency.")

        # 8. Server-side provider payment verification when live keys or explicit check enabled
        should_verify_api = (
            verify_provider_api
            if verify_provider_api is not None
            else (key_id.startswith("rzp_live_") or os.getenv("RAZORPAY_VERIFY_PAYMENT_API", "").lower() == "true")
        )
        if should_verify_api:
            provider_payment = cls._fetch_razorpay_payment(key_id, key_secret, payment_id_clean)
            prov_status = str(provider_payment.get("status") or "").lower()
            prov_order_id = str(provider_payment.get("order_id") or "")
            prov_amount = int(provider_payment.get("amount", -1))
            prov_currency = str(provider_payment.get("currency") or "").upper()

            if prov_order_id != order_id_clean:
                raise PermissionError("Provider payment record does not belong to this Razorpay order.")
            if prov_amount != int(payment_order.amount_subunits):
                raise PermissionError("Provider payment amount does not match server-side order amount.")
            if prov_currency != payment_order.currency.upper():
                raise PermissionError("Provider payment currency does not match server-side order currency.")
            if prov_status not in ("captured", "authorized"):
                payment_order.status = "failed"
                payment_order.error_message = f"Provider status: {prov_status}"
                db.commit()
                raise PermissionError(f"Payment is not captured/authorized by Razorpay (status: {prov_status}).")

        # 9. Activate subscription & record verified invoice transactionally
        payment_order.status = "paid"
        payment_order.provider_payment_id = payment_id_clean
        payment_order.verified_at = datetime.utcnow()

        sub = cls.get_or_create_subscription(db, org_id)
        sub.plan_id = plan.id
        sub.billing_cycle = payment_order.billing_cycle
        sub.status = "active"
        sub.payment_provider = "razorpay"
        sub.provider_order_id = order_id_clean
        sub.provider_payment_id = payment_id_clean
        sub.provider_subscription_id = ""  # One-time order — do not claim auto-renewal
        sub.stripe_customer_id = f"rzp_order:{order_id_clean}"
        sub.stripe_subscription_id = f"rzp_pay:{payment_id_clean}"
        sub.current_period_start = datetime.utcnow()
        sub.current_period_end = datetime.utcnow() + timedelta(
            days=365 if payment_order.billing_cycle == "yearly" else 30
        )
        sub.cancel_at_period_end = False

        org = db.query(Organization).filter(Organization.id == org_id).first()
        if org:
            org.plan = plan.id

        inv_suffix = f"{payment_id_clean[-6:].upper()}-{uuid.uuid4().hex[:4].upper()}"
        inv = Invoice(
            org_id=org_id,
            invoice_number=f"INV-RZP-{datetime.utcnow().strftime('%Y%m')}-{inv_suffix}",
            amount_cents=int(payment_order.amount_subunits),
            currency=payment_order.currency.lower(),
            status="paid",
            paid_at=datetime.utcnow(),
        )
        db.add(inv)
        db.flush()
        inv.hosted_invoice_url = f"/api/v1/billing/invoices/{inv.id}/download"
        db.commit()
        db.refresh(sub)

        return {
            "status": "active",
            "message": f"Payment verified! Upgraded to {plan.name} ({payment_order.billing_cycle}).",
            "subscription_id": sub.id,
            "plan_slug": sub.plan_id,
            "billing_type": "one_time_period_order",
            "auto_renews": False,
            "invoice_id": inv.id,
            "invoice_number": inv.invoice_number,
            "payment_id": payment_id_clean,
            "order_id": order_id_clean,
        }

    @classmethod
    def verify_razorpay_webhook_signature(
        cls,
        payload_bytes: bytes,
        sig_header: str,
        secret: Optional[str] = None,
    ) -> bool:
        """
        Verifies X-Razorpay-Signature webhook HMAC-SHA256 header over raw request bytes.
        In production, strictly requires dedicated RAZORPAY_WEBHOOK_SECRET.
        """
        _, key_secret, webhook_secret, _ = cls.get_razorpay_credentials()
        if secret is not None:
            signing_secret = secret.strip()
        elif cls._is_production():
            signing_secret = webhook_secret
        else:
            signing_secret = webhook_secret or key_secret
        if not signing_secret or not sig_header:
            return False
        expected = hmac.new(signing_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig_header.strip())

    @classmethod
    def handle_razorpay_event(
        cls,
        db: Session,
        payload: Dict[str, Any],
        event_id: str = "",
        raw_body: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """Processes verified Razorpay webhook events with persistent DB idempotency and order reconciliation."""
        event_type = str(payload.get("event") or "")
        payload_bytes = raw_body if raw_body is not None else json.dumps(payload, sort_keys=True).encode("utf-8")
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        event_key = cls._derive_webhook_event_id("razorpay", event_id, payload_bytes, payload)

        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {}) or {}
        order_entity = payload.get("payload", {}).get("order", {}).get("entity", {}) or {}
        sub_entity = payload.get("payload", {}).get("subscription", {}).get("entity", {}) or {}
        refund_entity = payload.get("payload", {}).get("refund", {}).get("entity", {}) or {}

        notes = (
            payment_entity.get("notes")
            or order_entity.get("notes")
            or sub_entity.get("notes")
            or {}
        )
        if not isinstance(notes, dict):
            notes = {}

        payment_id = str(payment_entity.get("id") or refund_entity.get("payment_id") or "").strip()
        order_id = str(payment_entity.get("order_id") or order_entity.get("id") or "").strip()
        rzp_sub_id = str(sub_entity.get("id") or "").strip()

        payment_order = (
            db.query(PaymentOrder).filter(PaymentOrder.provider_order_id == order_id).first()
            if order_id
            else None
        )
        if not payment_order and payment_id:
            payment_order = (
                db.query(PaymentOrder).filter(PaymentOrder.provider_payment_id == payment_id).first()
            )

        if not payment_order and (event_type in ("payment.captured", "order.paid") or order_id):
            webhook_row = cls._begin_webhook_event(
                db=db,
                provider="razorpay",
                event_id=event_key,
                event_type=event_type,
                payload_hash=payload_hash,
                org_id=notes.get("org_id"),
            )
            if webhook_row:
                webhook_row.status = "rejected"
                webhook_row.error_message = f"Rejected unrecognised internal payment order: {order_id or payment_id}"
                db.commit()
            raise PermissionError("Unrecognised payment order: cannot activate plan without valid server-persisted PaymentOrder.")

        org_id = payment_order.org_id if payment_order else notes.get("org_id")
        plan_slug = payment_order.plan_id if payment_order else (notes.get("plan_slug") or "starter")
        billing_cycle = payment_order.billing_cycle if payment_order else (notes.get("billing_cycle") or "monthly")

        webhook_row = cls._begin_webhook_event(
            db=db,
            provider="razorpay",
            event_id=event_key,
            event_type=event_type,
            payload_hash=payload_hash,
            org_id=org_id,
        )
        if webhook_row is None:
            return {"status": "ignored", "reason": "duplicate_event", "event_id": event_id or event_key}

        action_taken = "none"

        if event_type in ("payment.captured", "order.paid") and org_id:
            # Validate amount & currency against persisted PaymentOrder when present
            if payment_order:
                entity_amount = payment_entity.get("amount") or order_entity.get("amount_paid") or order_entity.get("amount")
                entity_currency = (payment_entity.get("currency") or order_entity.get("currency") or "").upper()
                if entity_amount is not None and int(entity_amount) != int(payment_order.amount_subunits):
                    webhook_row.status = "rejected"
                    webhook_row.error_message = "Webhook amount mismatch against server-side PaymentOrder"
                    db.commit()
                    raise PermissionError("Webhook payment amount does not match server-side order.")
                if entity_currency and entity_currency != payment_order.currency.upper():
                    webhook_row.status = "rejected"
                    webhook_row.error_message = "Webhook currency mismatch against server-side PaymentOrder"
                    db.commit()
                    raise PermissionError("Webhook payment currency does not match server-side order.")

            already_paid = (
                (payment_order and payment_order.status == "paid")
                or (
                    payment_id
                    and db.query(Subscription)
                    .filter(
                        (Subscription.provider_payment_id == payment_id)
                        | (Subscription.stripe_subscription_id == f"rzp_pay:{payment_id}")
                    )
                    .first()
                    is not None
                )
            )
            if already_paid:
                action_taken = "already_activated"
            else:
                cls._ensure_standard_plans(db)
                inv_currency = payment_order.currency.lower() if payment_order else (payment_entity.get("currency") or "usd")
                inv_amount = payment_order.amount_subunits if payment_order else payment_entity.get("amount")
                sub = cls.change_subscription_plan(
                    db,
                    org_id,
                    plan_slug,
                    billing_cycle,
                    payment_provider="razorpay",
                    create_paid_invoice=True,
                    invoice_currency=inv_currency,
                    invoice_amount_cents=inv_amount,
                    invoice_prefix="INV-RZP",
                )
                if order_id:
                    sub.provider_order_id = order_id
                    sub.stripe_customer_id = f"rzp_order:{order_id}"
                if payment_id:
                    sub.provider_payment_id = payment_id
                    sub.stripe_subscription_id = f"rzp_pay:{payment_id}"
                if payment_order:
                    payment_order.status = "paid"
                    if payment_id:
                        payment_order.provider_payment_id = payment_id
                    payment_order.verified_at = datetime.utcnow()
                action_taken = "subscription_activated"

        elif event_type in ("subscription.activated", "subscription.charged") and org_id:
            cls._ensure_standard_plans(db)
            sub = cls.change_subscription_plan(
                db,
                org_id,
                plan_slug,
                billing_cycle,
                payment_provider="razorpay",
                create_paid_invoice=(event_type == "subscription.charged"),
                invoice_currency=(payment_entity.get("currency") or "usd"),
                invoice_amount_cents=payment_entity.get("amount"),
                invoice_prefix="INV-RZPSUB",
            )
            if rzp_sub_id:
                sub.provider_subscription_id = rzp_sub_id
            if payment_id:
                sub.provider_payment_id = payment_id
            action_taken = "recurring_subscription_active"

        elif event_type in ("payment.failed", "subscription.halted") and org_id:
            # Out-of-order guard: never mark subscription past_due if this order was already paid!
            if payment_order and payment_order.status == "paid":
                action_taken = "ignored_out_of_order_failure"
            else:
                if payment_order:
                    payment_order.status = "failed"
                sub = db.query(Subscription).filter(Subscription.org_id == org_id).first()
                if sub:
                    sub.status = "past_due"
                    notif = Notification(
                        org_id=org_id,
                        title="Razorpay Subscription Payment Failed",
                        message="Your recent Razorpay payment attempt failed. Please retry or update your payment method.",
                        category="billing",
                        severity="error",
                    )
                    db.add(notif)
                    action_taken = "subscription_past_due"

        elif event_type in ("subscription.cancelled", "subscription.completed") and org_id:
            sub = db.query(Subscription).filter(Subscription.org_id == org_id).first()
            if sub:
                cls.change_subscription_plan(db, org_id, "free", payment_provider="none", create_paid_invoice=False)
                sub.status = "canceled"
                sub.provider_subscription_id = ""
                action_taken = "subscription_cancelled"

        elif event_type in ("payment.refunded", "refund.processed") and (org_id or payment_order):
            target_org_id = org_id or payment_order.org_id
            if payment_order:
                payment_order.status = "refunded"
            sub = db.query(Subscription).filter(Subscription.org_id == target_org_id).first()
            if sub:
                cls.change_subscription_plan(db, target_org_id, "free", payment_provider="none", create_paid_invoice=False)
                sub.status = "canceled"
            action_taken = "payment_refunded_downgraded"

        webhook_row.org_id = org_id
        webhook_row.status = "processed"
        webhook_row.action_taken = action_taken
        webhook_row.processed_at = datetime.utcnow()
        db.commit()

        return {
            "status": "success",
            "event_type": event_type,
            "action": action_taken,
            "event_id": event_id or event_key,
        }
