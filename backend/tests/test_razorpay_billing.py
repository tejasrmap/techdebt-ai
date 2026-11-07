import json
import uuid
import hmac
import hashlib
from datetime import datetime, timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.all_models import Organization, Subscription, Invoice, PaymentOrder
from app.services.billing_service import BillingService

client = TestClient(app)

TEST_RZP_KEY_ID = "rzp_test_mock_key_id"
TEST_RZP_SECRET = "mock_razorpay_secret_for_ci_tests_2026"


def _register_admin():
    uid = uuid.uuid4().hex[:8]
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"rzp_admin_{uid}@example.com",
            "password": "StrongPassword2026!",
            "full_name": f"Billing Admin {uid}",
            "organization_name": f"Razorpay Org {uid}",
            "role": "Administrator",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data["access_token"], data["user"]["org_id"]


def test_razorpay_public_config_never_exposes_secret(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", TEST_RZP_KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", TEST_RZP_SECRET)
    monkeypatch.setenv("RAZORPAY_CURRENCY", "USD")

    resp = client.get("/api/v1/billing/razorpay/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["key_id"] == TEST_RZP_KEY_ID
    assert body["currency"] == "USD"
    assert "key_secret" not in body
    assert TEST_RZP_SECRET not in json.dumps(body)


def test_razorpay_order_creation_and_signature_verification(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", TEST_RZP_KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", TEST_RZP_SECRET)
    monkeypatch.setenv("RAZORPAY_CURRENCY", "USD")

    token, org_id = _register_admin()
    headers = {"Authorization": f"Bearer {token}"}

    mock_order_id = f"order_{uuid.uuid4().hex[:14]}"
    mock_payment_id = f"pay_{uuid.uuid4().hex[:14]}"

    with patch.object(
        BillingService,
        "_post_razorpay_order",
        return_value={
            "id": mock_order_id,
            "amount": 19900,
            "currency": "USD",
            "receipt": "tdai_test_rcpt",
            "status": "created",
        },
    ):
        order_resp = client.post(
            "/api/v1/billing/razorpay/create-order",
            json={"plan_slug": "professional", "billing_cycle": "monthly"},
            headers=headers,
        )
        assert order_resp.status_code == 200, order_resp.text
        order_data = order_resp.json()
        assert order_data["mode"] == "live_razorpay"
        assert order_data["order_id"] == mock_order_id
        assert order_data["amount"] == 19900

    # 1. Forged signature must be rejected with 400
    bad_verify = client.post(
        "/api/v1/billing/razorpay/verify-payment",
        json={
            "plan_slug": "professional",
            "billing_cycle": "monthly",
            "razorpay_order_id": mock_order_id,
            "razorpay_payment_id": mock_payment_id,
            "razorpay_signature": "forged_invalid_signature_hex",
        },
        headers=headers,
    )
    assert bad_verify.status_code == 400

    # 2. Valid HMAC-SHA256(order_id|payment_id) activates plan & generates INV-RZP invoice
    valid_sig = hmac.new(
        TEST_RZP_SECRET.encode("utf-8"),
        f"{mock_order_id}|{mock_payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    ok_verify = client.post(
        "/api/v1/billing/razorpay/verify-payment",
        json={
            "plan_slug": "professional",
            "billing_cycle": "monthly",
            "razorpay_order_id": mock_order_id,
            "razorpay_payment_id": mock_payment_id,
            "razorpay_signature": valid_sig,
        },
        headers=headers,
    )
    assert ok_verify.status_code == 200, ok_verify.text
    v_data = ok_verify.json()
    assert v_data["status"] == "active"
    assert v_data["plan_slug"] == "professional"
    assert v_data["invoice_number"].startswith("INV-RZP-")

    # 3. Replay of same payment_id is idempotent
    dup_verify = client.post(
        "/api/v1/billing/razorpay/verify-payment",
        json={
            "plan_slug": "professional",
            "billing_cycle": "monthly",
            "razorpay_order_id": mock_order_id,
            "razorpay_payment_id": mock_payment_id,
            "razorpay_signature": valid_sig,
        },
        headers=headers,
    )
    assert dup_verify.status_code == 200
    assert dup_verify.json()["status"] == "already_processed"


def test_razorpay_webhook_signature_and_lifecycle(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", TEST_RZP_KEY_ID)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", TEST_RZP_SECRET)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", TEST_RZP_SECRET)

    db = SessionLocal()
    try:
        org_id = f"rzp-wh-{uuid.uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name=f"RZP Webhook Org {uuid.uuid4().hex[:6]}",
            slug=f"rzp-wh-{uuid.uuid4().hex[:6]}",
            plan="free",
        )
        db.add(org)
        db.commit()

        order_ref = f"order_{uuid.uuid4().hex[:12]}"
        pay_order = PaymentOrder(
            org_id=org_id,
            provider="razorpay",
            provider_order_id=order_ref,
            plan_id="enterprise",
            billing_cycle="yearly",
            amount_subunits=299000,
            currency="USD",
            status="created",
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        db.add(pay_order)
        db.commit()

        event_id = f"rzp_evt_{uuid.uuid4().hex[:10]}"
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": f"pay_{uuid.uuid4().hex[:12]}",
                        "order_id": order_ref,
                        "amount": 299000,
                        "currency": "USD",
                        "notes": {
                            "org_id": org_id,
                            "plan_slug": "enterprise",
                            "billing_cycle": "yearly",
                        },
                    }
                }
            },
        }
        raw_body = json.dumps(payload)

        # Missing signature -> 400
        missing_res = client.post(
            "/api/v1/billing/razorpay/webhook",
            data=raw_body,
            headers={"Content-Type": "application/json"},
        )
        assert missing_res.status_code == 400

        # Valid X-Razorpay-Signature -> activates subscription
        sig = hmac.new(TEST_RZP_SECRET.encode("utf-8"), raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
        ok_res = client.post(
            "/api/v1/billing/razorpay/webhook",
            data=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
                "X-Razorpay-Event-Id": event_id,
            },
        )
        assert ok_res.status_code == 200, ok_res.text
        assert ok_res.json()["action"] == "subscription_activated"

        db.expire_all()
        sub = db.query(Subscription).filter(Subscription.org_id == org_id).first()
        assert sub is not None
        assert sub.plan_id == "enterprise"

        # Duplicate event ID -> ignored
        dup_res = client.post(
            "/api/v1/billing/razorpay/webhook",
            data=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
                "X-Razorpay-Event-Id": event_id,
            },
        )
        assert dup_res.status_code == 200
        assert dup_res.json()["status"] == "ignored"
    finally:
        db.close()

