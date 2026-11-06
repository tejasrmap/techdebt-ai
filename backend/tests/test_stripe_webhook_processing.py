import time
import json
import uuid
import hmac
import hashlib
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.services.billing_service import BillingService
from app.models.all_models import Organization, Subscription, Invoice, Notification

client = TestClient(app)

SECRET = BillingService.STRIPE_WEBHOOK_SECRET

def generate_stripe_header(payload_str: str, timestamp: int, secret: str = SECRET) -> str:
    signed_payload = f"{timestamp}.{payload_str}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"

def test_stripe_signature_verification_and_tamper_rejection():
    payload = json.dumps({"id": f"evt_{uuid.uuid4().hex[:8]}", "type": "ping", "data": {}})
    now = int(time.time())

    # 1. Valid signature
    valid_header = generate_stripe_header(payload, now)
    assert BillingService.verify_stripe_signature(payload.encode("utf-8"), valid_header, secret=SECRET) is True

    # 2. Tampered payload
    tampered_payload = json.dumps({"id": "evt_tampered", "type": "ping", "data": {}})
    assert BillingService.verify_stripe_signature(tampered_payload.encode("utf-8"), valid_header, secret=SECRET) is False

    # 3. Timestamp replay drift (> 300 seconds old)
    old_header = generate_stripe_header(payload, now - 600)
    assert BillingService.verify_stripe_signature(payload.encode("utf-8"), old_header, secret=SECRET) is False

def test_webhook_endpoint_signature_rejection():
    payload = {"id": f"evt_{uuid.uuid4().hex[:8]}", "type": "ping", "data": {}}

    # Missing signature header -> 400
    res_missing = client.post("/api/v1/billing/webhook", json=payload)
    assert res_missing.status_code == 400

    # Invalid signature -> 400
    res_bad = client.post(
        "/api/v1/billing/webhook",
        json=payload,
        headers={"stripe-signature": "t=123456,v1=bad_mac"}
    )
    assert res_bad.status_code == 400

def test_webhook_checkout_session_completed():
    db = SessionLocal()
    try:
        org_id = f"stripe-org-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name=f"Stripe Org {uuid.uuid4().hex[:6]}", slug=f"slug-{uuid.uuid4().hex[:6]}", plan="free")
        db.add(org)
        db.commit()

        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        payload = {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": org_id,
                    "customer": "cus_test_123456",
                    "subscription": "sub_test_654321",
                    "metadata": {"org_id": org_id, "plan_id": "professional", "billing_cycle": "monthly"}
                }
            }
        }
        payload_str = json.dumps(payload)
        now = int(time.time())
        header = generate_stripe_header(payload_str, now)

        resp = client.post(
            "/api/v1/billing/webhook",
            data=payload_str,
            headers={"Content-Type": "application/json", "stripe-signature": header}
        )
        assert resp.status_code == 200
        r_data = resp.json()
        assert r_data["status"] == "success"
        assert r_data["action"] == "subscription_activated"

        # Verify subscription was updated in database
        sub = db.query(Subscription).filter(Subscription.org_id == org_id).first()
        assert sub.plan_id == "professional"
        assert sub.stripe_customer_id == "cus_test_123456"
        assert sub.stripe_subscription_id == "sub_test_654321"

        # 2. Idempotency test: repeating the same event ID returns 'ignored'
        dup_resp = client.post(
            "/api/v1/billing/webhook",
            data=payload_str,
            headers={"Content-Type": "application/json", "stripe-signature": header}
        )
        assert dup_resp.status_code == 200
        assert dup_resp.json()["status"] == "ignored"
    finally:
        db.close()

def test_webhook_invoice_failed_and_subscription_deleted():
    db = SessionLocal()
    try:
        org_id = f"stripe-fail-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name=f"Fail Org {uuid.uuid4().hex[:6]}", slug=f"slug-{uuid.uuid4().hex[:6]}", plan="starter")
        db.add(org)
        db.commit()

        sub = BillingService.get_or_create_subscription(db, org_id)
        sub.stripe_customer_id = "cus_fail_user_789"
        sub.plan_id = "starter"
        db.commit()

        # 1. invoice.payment_failed
        fail_event = {
            "id": f"evt_{uuid.uuid4().hex[:12]}",
            "type": "invoice.payment_failed",
            "data": {"object": {"customer": "cus_fail_user_789"}}
        }
        fail_str = json.dumps(fail_event)
        now = int(time.time())
        fail_hdr = generate_stripe_header(fail_str, now)

        res_fail = client.post(
            "/api/v1/billing/webhook",
            data=fail_str,
            headers={"Content-Type": "application/json", "stripe-signature": fail_hdr}
        )
        assert res_fail.status_code == 200
        db.refresh(sub)
        assert sub.status == "past_due"

        # 2. customer.subscription.deleted
        del_event = {
            "id": f"evt_{uuid.uuid4().hex[:12]}",
            "type": "customer.subscription.deleted",
            "data": {"object": {"customer": "cus_fail_user_789"}}
        }
        del_str = json.dumps(del_event)
        del_hdr = generate_stripe_header(del_str, now)

        res_del = client.post(
            "/api/v1/billing/webhook",
            data=del_str,
            headers={"Content-Type": "application/json", "stripe-signature": del_hdr}
        )
        assert res_del.status_code == 200
        db.refresh(sub)
        assert sub.plan_id == "free"
        assert sub.status == "canceled"
    finally:
        db.close()
