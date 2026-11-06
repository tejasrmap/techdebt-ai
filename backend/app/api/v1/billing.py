import os
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import User, Organization, SubscriptionPlan, Subscription, Invoice, UsageRecord
from app.services.auth_service import get_current_user, require_roles
from app.services.billing_service import BillingService

router = APIRouter(prefix="/billing", tags=["Billing & Subscriptions"])

class SubscribeRequest(BaseModel):
    plan_slug: str # starter, professional, enterprise
    billing_cycle: str = "monthly" # monthly or annual
    success_url: Optional[str] = "/dashboard/billing?status=success"
    cancel_url: Optional[str] = "/dashboard/billing?status=cancelled"

@router.get("/plans")
def list_plans(db: Session = Depends(get_db)):
    """List all available commercial subscription plans."""
    return BillingService.get_active_plans(db)

@router.get("/subscription")
def get_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve the current organization's subscription details and entitlements."""
    sub = BillingService.get_or_create_org_subscription(db, current_user.org_id)
    usage = BillingService.get_monthly_usage(db, current_user.org_id)

    plan = sub.plan
    features = plan.features if isinstance(plan.features, dict) else {}

    return {
        "subscription_id": sub.id,
        "org_id": sub.org_id,
        "plan_name": plan.name,
        "plan_slug": plan.slug,
        "status": sub.status,
        "billing_cycle": sub.billing_cycle,
        "current_period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "cancel_at_period_end": sub.cancel_at_period_end,
        "price_monthly": plan.price_monthly,
        "price_annual": plan.price_annual,
        "limits": {
            "max_projects": plan.max_projects,
            "max_assessments_per_month": plan.max_assessments_per_month,
            "max_team_members": plan.max_team_members,
        },
        "features": features,
        "current_usage": usage
    }

@router.post("/subscribe")
def subscribe_or_upgrade(
    req: SubscribeRequest,
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator"])),
    db: Session = Depends(get_db)
):
    """Initiates checkout or upgrades subscription."""
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == req.plan_slug).first()
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan '{req.plan_slug}' not found")

    result = BillingService.create_checkout_session(
        db=db,
        org_id=current_user.org_id,
        user_email=current_user.email,
        plan_slug=req.plan_slug,
        billing_cycle=req.billing_cycle,
        success_url=req.success_url or "/dashboard/billing?status=success",
        cancel_url=req.cancel_url or "/dashboard/billing?status=cancelled"
    )

    return result

@router.post("/checkout")
def create_checkout(
    req: SubscribeRequest,
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator"])),
    db: Session = Depends(get_db)
):
    """Initiates Stripe Checkout session for subscription creation or upgrade."""
    return subscribe_or_upgrade(req=req, current_user=current_user, db=db)

class CustomerPortalRequest(BaseModel):
    return_url: Optional[str] = None

@router.post("/portal")
def create_portal_session(
    req: Optional[CustomerPortalRequest] = None,
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator"])),
    db: Session = Depends(get_db)
):
    """Generates customer portal session to manage subscription and payments."""
    return_url = req.return_url if req and req.return_url else ""
    return BillingService.create_customer_portal_session(
        db=db,
        org_id=current_user.org_id,
        return_url=return_url
    )

@router.get("/portal/session")
def get_portal_session(
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator"])),
    db: Session = Depends(get_db)
):
    """Retrieves customer portal URL for self-service billing management."""
    return BillingService.create_customer_portal_session(
        db=db,
        org_id=current_user.org_id
    )


@router.post("/cancel")
def cancel_subscription(
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator"])),
    db: Session = Depends(get_db)
):
    """Cancels subscription at the end of the current billing cycle."""
    sub = BillingService.get_or_create_org_subscription(db, current_user.org_id)
    if sub.plan.slug == "free":
        raise HTTPException(status_code=400, detail="Cannot cancel free tier")

    sub.cancel_at_period_end = True
    db.commit()
    return {"message": "Subscription set to cancel at end of current period"}

@router.get("/invoices")
def get_invoices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List billing invoices for the current organization."""
    invoices = db.query(Invoice).filter(Invoice.org_id == current_user.org_id).order_by(Invoice.created_at.desc()).all()
    return [
        {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "amount_due": inv.amount_due,
            "amount_paid": inv.amount_paid,
            "currency": inv.currency,
            "status": inv.status,
            "period_start": inv.period_start.isoformat() if inv.period_start else None,
            "period_end": inv.period_end.isoformat() if inv.period_end else None,
            "hosted_invoice_url": inv.hosted_invoice_url,
            "invoice_pdf": inv.invoice_pdf,
            "created_at": inv.created_at.isoformat()
        }
        for inv in invoices
    ]

@router.get("/usage")
def get_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get real-time usage metrics and entitlement status."""
    sub = BillingService.get_or_create_org_subscription(db, current_user.org_id)
    usage = BillingService.get_monthly_usage(db, current_user.org_id)

    return {
        "org_id": current_user.org_id,
        "plan": sub.plan.name,
        "usage": usage,
        "limits": {
            "projects": sub.plan.max_projects,
            "monthly_assessments": sub.plan.max_assessments_per_month,
            "team_members": sub.plan.max_team_members,
        }
    }

@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receives and cryptographically verifies Stripe webhook events using HMAC-SHA256.
    Protects against timestamp drift replay attacks and processes subscription lifecycle events.
    """
    try:
        body = await request.body()
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    sig_header = request.headers.get("stripe-signature", "")
    
    # If a webhook secret is configured, require and verify the cryptographic signature
    if BillingService.STRIPE_WEBHOOK_SECRET:
        if not sig_header:
            raise HTTPException(status_code=400, detail="Missing required Stripe-Signature header")

        is_valid = BillingService.verify_stripe_signature(
            payload_bytes=body,
            sig_header=sig_header,
            secret=BillingService.STRIPE_WEBHOOK_SECRET
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail="Invalid Stripe webhook cryptographic signature")

    result = BillingService.handle_stripe_event(db=db, payload=payload)
    return result


