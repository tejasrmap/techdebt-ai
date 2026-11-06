import os
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
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

@router.get("/invoices/{invoice_id}")
def get_invoice_detail(
    invoice_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve detailed invoice record for caller's organization."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.org_id == current_user.org_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found or unauthorized")

    org = db.query(Organization).filter(Organization.id == inv.org_id).first()
    return {
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "org_id": inv.org_id,
        "organization_name": org.name if org else "",
        "amount_cents": inv.amount_cents,
        "amount_dollars": inv.amount_due,
        "currency": inv.currency,
        "status": inv.status,
        "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "download_url": f"/api/v1/billing/invoices/{inv.id}/download"
    }

@router.get("/invoices/{invoice_id}/download", response_class=HTMLResponse)
def download_invoice(
    invoice_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Downloads printable HTML invoice receipt."""
    inv = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.org_id == current_user.org_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found or unauthorized")

    org = db.query(Organization).filter(Organization.id == inv.org_id).first()
    html_content = BillingService.render_invoice_html(inv, org)
    return HTMLResponse(
        content=html_content,
        headers={"Content-Disposition": f'inline; filename="{inv.invoice_number}.html"'}
    )

class GenerateManualInvoiceRequest(BaseModel):
    amount_dollars: float
    description: Optional[str] = "Manual subscription credit"

@router.post("/invoices/generate-manual")
def generate_manual_invoice(
    req: GenerateManualInvoiceRequest,
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator"])),
    db: Session = Depends(get_db)
):
    """Manually creates an invoice record for the organization."""
    cents = int(req.amount_dollars * 100)
    inv = BillingService.generate_invoice(
        db=db,
        org_id=current_user.org_id,
        amount_cents=cents,
        description=req.description or "Manual subscription invoice"
    )
    return {
        "message": "Invoice generated successfully",
        "invoice_id": inv.id,
        "invoice_number": inv.invoice_number,
        "amount_dollars": req.amount_dollars
    }


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


class RazorpayOrderRequest(BaseModel):
    plan_slug: str
    billing_cycle: str = "monthly"


class RazorpayVerifyRequest(BaseModel):
    plan_slug: str
    billing_cycle: str = "monthly"
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.get("/razorpay/config")
def get_razorpay_config():
    """Returns public Razorpay Checkout configuration (key_id & enabled state only)."""
    return BillingService.get_razorpay_public_config()


@router.post("/razorpay/create-order")
def create_razorpay_order(
    req: RazorpayOrderRequest,
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator"])),
    db: Session = Depends(get_db),
):
    """Creates a live Razorpay Order for plan upgrade or downgrades directly if free."""
    try:
        return BillingService.create_razorpay_order(
            db=db,
            org_id=current_user.org_id,
            plan_slug=req.plan_slug,
            billing_cycle=req.billing_cycle,
            user_email=current_user.email,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/razorpay/verify-payment")
def verify_razorpay_payment(
    req: RazorpayVerifyRequest,
    current_user: User = Depends(require_roles(["SuperAdmin", "Owner", "Administrator"])),
    db: Session = Depends(get_db),
):
    """Cryptographically verifies Razorpay Checkout signature and activates the subscription."""
    try:
        return BillingService.complete_razorpay_payment(
            db=db,
            org_id=current_user.org_id,
            plan_slug=req.plan_slug,
            billing_cycle=req.billing_cycle,
            razorpay_order_id=req.razorpay_order_id,
            razorpay_payment_id=req.razorpay_payment_id,
            razorpay_signature=req.razorpay_signature,
        )
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Receives and verifies Razorpay webhook events using X-Razorpay-Signature HMAC-SHA256."""
    try:
        body = await request.body()
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    sig_header = request.headers.get("x-razorpay-signature", "")
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing required X-Razorpay-Signature header")

    if not BillingService.verify_razorpay_webhook_signature(payload_bytes=body, sig_header=sig_header):
        raise HTTPException(status_code=400, detail="Invalid Razorpay webhook cryptographic signature")

    event_id = request.headers.get("x-razorpay-event-id", "")
    return BillingService.handle_razorpay_event(db=db, payload=payload, event_id=event_id)



