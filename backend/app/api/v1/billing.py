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
    """Receives Stripe webhook events for automated recurring billing."""
    try:
        body = await request.body()
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    event_type = payload.get("type", "")
    data_object = payload.get("data", {}).get("object", {})

    # Process events like invoice.paid, customer.subscription.updated, customer.subscription.deleted
    if event_type == "invoice.payment_succeeded":
        customer_id = data_object.get("customer")
        amount_paid = data_object.get("amount_paid", 0) / 100.0
        # Update matching invoice if present
        inv_id = data_object.get("id")
        inv = db.query(Invoice).filter(Invoice.stripe_invoice_id == inv_id).first()
        if inv:
            inv.status = "paid"
            inv.amount_paid = amount_paid
            db.commit()

    return {"status": "success"}

