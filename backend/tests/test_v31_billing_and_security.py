import hmac
import json
import time
import uuid
import hashlib
from datetime import datetime, timedelta
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.all_models import (
    User,
    Organization,
    Subscription,
    PaymentOrder,
    BillingWebhookEvent,
    Invoice,
    AuditLog,
)
from app.services.auth_service import generate_totp_code
from app.services.billing_service import BillingService
from app.services.disaster_recovery_service import DisasterRecoveryService

client = TestClient(app)


def _register_tenant(org_prefix: str = "SecOrg", org_Display: str = "") -> tuple[dict, str, str, str]:
    uid = uuid.uuid4().hex[:8]
    email = f"admin_{uid}@techdebt.ai"
    password = "StrongPassword123!"
    org_name = org_Display or f"{org_prefix} {uid}"
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Tenant Creator",
            "organization_name": org_name,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    return headers, body["user"]["org_id"], body["user"]["id"], email


def _sign_rzp(order_id: str, payment_id: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), f"{order_id}|{payment_id}".encode("utf-8"), hashlib.sha256).hexdigest()


def test_new_registration_defaults_to_free_tier_and_enforces_quotas():
    headers, org_id, _, _ = _register_tenant("FreeDefault")

    sub_res = client.get("/api/v1/billing/subscription", headers=headers)
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["plan_slug"] == "free"
    assert sub_data["billing_mode"] == "free"
    assert sub_data["auto_renews"] is False
    assert sub_data["limits"]["max_projects"] == 1
    assert sub_data["limits"]["max_team_members"] == 1

    # 1st project succeeds
    p1 = client.post("/api/v1/projects", json={"name": f"Proj1-{uuid.uuid4().hex[:6]}"}, headers=headers)
    assert p1.status_code in (200, 201)

    # 2nd project blocked by Free tier entitlement
    p2 = client.post("/api/v1/projects", json={"name": f"Proj2-{uuid.uuid4().hex[:6]}"}, headers=headers)
    assert p2.status_code in (402, 403)

    # Team invitation blocked on 1-seat Free tier
    inv = client.post(
        "/api/v1/auth/invitations",
        json={"email": f"extra_{uuid.uuid4().hex[:6]}@techdebt.ai", "role": "Developer"},
        headers=headers,
    )
    assert inv.status_code in (402, 403)


def test_unconfigured_payment_gateway_never_grants_free_paid_upgrade(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "")
    monkeypatch.setattr(BillingService, "STRIPE_SECRET_KEY", "")

    headers, org_id, _, _ = _register_tenant("NoGateway")
    res = client.post(
        "/api/v1/billing/subscribe",
        json={"plan_slug": "enterprise", "billing_cycle": "yearly"},
        headers=headers,
    )
    assert res.status_code == 503

    sub = client.get("/api/v1/billing/subscription", headers=headers).json()
    assert sub["plan_slug"] == "free"


def test_order_bound_razorpay_verification_blocks_tampering_cross_org_expiry_and_replay(monkeypatch):
    test_key = "rzp_test_mock_v31_key"
    test_secret = "rzp_test_mock_v31_secret"
    monkeypatch.setenv("RAZORPAY_KEY_ID", test_key)
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", test_secret)
    monkeypatch.setenv("RAZORPAY_CURRENCY", "USD")

    headers_a, org_a, _, _ = _register_tenant("BuyerOrgA", f"Buyer <script>alert(1)</script> {uuid.uuid4().hex[:5]}")
    headers_b, org_b, _, _ = _register_tenant("AttackerOrgB")

    starter_order_id = f"order_{uuid.uuid4().hex[:12]}"
    with patch.object(
        BillingService,
        "_post_razorpay_order",
        return_value={"id": starter_order_id, "amount": 4900, "currency": "USD", "status": "created"},
    ):
        order_res = client.post(
            "/api/v1/billing/razorpay/create-order",
            json={"plan_slug": "starter", "billing_cycle": "monthly"},
            headers=headers_a,
        )
    assert order_res.status_code == 200
    odata = order_res.json()
    assert odata["order_id"] == starter_order_id
    assert odata["billing_type"] == "one_time_period_order"
    assert odata["auto_renews"] is False

    payment_id = f"pay_{uuid.uuid4().hex[:12]}"
    valid_sig = _sign_rzp(starter_order_id, payment_id, test_secret)

    # 1. Invalid signature -> 400
    bad_sig_res = client.post(
        "/api/v1/billing/razorpay/verify-payment",
        json={
            "plan_slug": "starter",
            "billing_cycle": "monthly",
            "razorpay_order_id": starter_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": "deadbeef" * 8,
        },
        headers=headers_a,
    )
    assert bad_sig_res.status_code == 400

    # 2. Unknown order_id with valid HMAC -> 400!
    forged_order = f"order_forged_{uuid.uuid4().hex[:8]}"
    forged_sig = _sign_rzp(forged_order, payment_id, test_secret)
    uncreated_res = client.post(
        "/api/v1/billing/razorpay/verify-payment",
        json={
            "plan_slug": "enterprise",
            "billing_cycle": "yearly",
            "razorpay_order_id": forged_order,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": forged_sig,
        },
        headers=headers_a,
    )
    assert uncreated_res.status_code == 400

    # 3. Altered plan_slug ($49 starter order trying to activate $499 enterprise!) -> 400!
    tampered_plan_res = client.post(
        "/api/v1/billing/razorpay/verify-payment",
        json={
            "plan_slug": "enterprise",
            "billing_cycle": "monthly",
            "razorpay_order_id": starter_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_sig,
        },
        headers=headers_a,
    )
    assert tampered_plan_res.status_code == 400
    assert "tampered" in tampered_plan_res.json()["detail"].lower()

    # 4. Altered billing_cycle (monthly order trying to activate yearly!) -> 400!
    tampered_cycle_res = client.post(
        "/api/v1/billing/razorpay/verify-payment",
        json={
            "plan_slug": "starter",
            "billing_cycle": "yearly",
            "razorpay_order_id": starter_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_sig,
        },
        headers=headers_a,
    )
    assert tampered_cycle_res.status_code == 400

    # 5. Cross-organisation hijack (Org B submitting Org A's order & signature) -> 400!
    hijack_res = client.post(
        "/api/v1/billing/razorpay/verify-payment",
        json={
            "plan_slug": "starter",
            "billing_cycle": "monthly",
            "razorpay_order_id": starter_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_sig,
        },
        headers=headers_b,
    )
    assert hijack_res.status_code == 400

    # 6. Provider API verification: tampered amount / currency / outage
    monkeypatch.setenv("RAZORPAY_VERIFY_PAYMENT_API", "true")
    with patch.object(
        BillingService,
        "_fetch_razorpay_payment",
        return_value={"id": payment_id, "order_id": starter_order_id, "amount": 100, "currency": "USD", "status": "captured"},
    ):
        bad_amt_res = client.post(
            "/api/v1/billing/razorpay/verify-payment",
            json={
                "plan_slug": "starter",
                "billing_cycle": "monthly",
                "razorpay_order_id": starter_order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": valid_sig,
            },
            headers=headers_a,
        )
        assert bad_amt_res.status_code == 400

    with patch.object(
        BillingService,
        "_fetch_razorpay_payment",
        side_effect=ValueError("Razorpay payment verification API is temporarily unreachable."),
    ):
        outage_res = client.post(
            "/api/v1/billing/razorpay/verify-payment",
            json={
                "plan_slug": "starter",
                "billing_cycle": "monthly",
                "razorpay_order_id": starter_order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": valid_sig,
            },
            headers=headers_a,
        )
        assert outage_res.status_code == 503

    # Verify Org A is STILL on free after all failed/tampered attempts!
    assert client.get("/api/v1/billing/subscription", headers=headers_a).json()["plan_slug"] == "free"

    # 7. Genuine verified payment succeeds!
    with patch.object(
        BillingService,
        "_fetch_razorpay_payment",
        return_value={"id": payment_id, "order_id": starter_order_id, "amount": 4900, "currency": "USD", "status": "captured"},
    ):
        ok_res = client.post(
            "/api/v1/billing/razorpay/verify-payment",
            json={
                "plan_slug": "starter",
                "billing_cycle": "monthly",
                "razorpay_order_id": starter_order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": valid_sig,
            },
            headers=headers_a,
        )
    assert ok_res.status_code == 200, ok_res.text
    ok_data = ok_res.json()
    assert ok_data["status"] == "active"
    assert ok_data["plan_slug"] == "starter"
    assert ok_data["auto_renews"] is False

    # 8. Replay of identical payment returns already_processed without creating a 2nd invoice
    replay_res = client.post(
        "/api/v1/billing/razorpay/verify-payment",
        json={
            "plan_slug": "starter",
            "billing_cycle": "monthly",
            "razorpay_order_id": starter_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_sig,
        },
        headers=headers_a,
    )
    assert replay_res.status_code == 200
    assert replay_res.json()["status"] == "already_processed"
    invoices = client.get("/api/v1/billing/invoices", headers=headers_a).json()
    assert len(invoices) == 1

    # 9. Invoice HTML escapes XSS in organization name
    html_dl = client.get(f"/api/v1/billing/invoices/{invoices[0]['id']}/download", headers=headers_a)
    assert html_dl.status_code == 200
    assert "<script>alert(1)</script>" not in html_dl.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_dl.text

    # 10. Expired order is rejected
    expired_order_id = f"order_exp_{uuid.uuid4().hex[:10]}"
    with patch.object(
        BillingService,
        "_post_razorpay_order",
        return_value={"id": expired_order_id, "amount": 19900, "currency": "USD", "status": "created"},
    ):
        client.post(
            "/api/v1/billing/razorpay/create-order",
            json={"plan_slug": "professional", "billing_cycle": "monthly"},
            headers=headers_a,
        )
    db = SessionLocal()
    try:
        po = db.query(PaymentOrder).filter(PaymentOrder.provider_order_id == expired_order_id).first()
        po.expires_at = datetime.utcnow() - timedelta(minutes=5)
        db.commit()
    finally:
        db.close()

    exp_pay = f"pay_exp_{uuid.uuid4().hex[:8]}"
    exp_res = client.post(
        "/api/v1/billing/razorpay/verify-payment",
        json={
            "plan_slug": "professional",
            "billing_cycle": "monthly",
            "razorpay_order_id": expired_order_id,
            "razorpay_payment_id": exp_pay,
            "razorpay_signature": _sign_rzp(expired_order_id, exp_pay, test_secret),
        },
        headers=headers_a,
    )
    assert exp_res.status_code == 400
    assert "expired" in exp_res.json()["detail"].lower()


def test_webhook_persistent_idempotency_out_of_order_and_refund_reconciliation(monkeypatch):
    wh_secret = "whsec_rzp_dedicated_v31"
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_mock_wh")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_test_mock_secret_wh")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", wh_secret)
    monkeypatch.setenv("RAZORPAY_CURRENCY", "USD")

    headers, org_id, _, _ = _register_tenant("WebhookOrg")
    order_id = f"order_wh_{uuid.uuid4().hex[:10]}"
    payment_id = f"pay_wh_{uuid.uuid4().hex[:10]}"

    with patch.object(
        BillingService,
        "_post_razorpay_order",
        return_value={"id": order_id, "amount": 19900, "currency": "USD", "status": "created"},
    ):
        client.post(
            "/api/v1/billing/razorpay/create-order",
            json={"plan_slug": "professional", "billing_cycle": "monthly"},
            headers=headers,
        )

    # 1. Tampered webhook amount (order is 19900, webhook claims 100) -> rejected 400
    bad_payload = json.dumps(
        {
            "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": payment_id, "order_id": order_id, "amount": 100, "currency": "USD"}}},
        }
    ).encode("utf-8")
    bad_sig = hmac.new(wh_secret.encode("utf-8"), bad_payload, hashlib.sha256).hexdigest()
    bad_wh = client.post(
        "/api/v1/billing/razorpay/webhook",
        content=bad_payload,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": bad_sig, "X-Razorpay-Event-Id": f"evt_bad_{uuid.uuid4().hex[:8]}"},
    )
    assert bad_wh.status_code == 400

    # 2. Valid webhook activates subscription and persists BillingWebhookEvent
    evt_id = f"evt_ok_{uuid.uuid4().hex[:8]}"
    ok_payload = json.dumps(
        {
            "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": payment_id, "order_id": order_id, "amount": 19900, "currency": "USD"}}},
        }
    ).encode("utf-8")
    ok_sig = hmac.new(wh_secret.encode("utf-8"), ok_payload, hashlib.sha256).hexdigest()
    wh1 = client.post(
        "/api/v1/billing/razorpay/webhook",
        content=ok_payload,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": ok_sig, "X-Razorpay-Event-Id": evt_id},
    )
    assert wh1.status_code == 200
    assert wh1.json()["action"] == "subscription_activated"

    # Duplicate delivery is ignored via DB table
    wh2 = client.post(
        "/api/v1/billing/razorpay/webhook",
        content=ok_payload,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": ok_sig, "X-Razorpay-Event-Id": evt_id},
    )
    assert wh2.status_code == 200
    assert wh2.json()["status"] == "ignored"

    db = SessionLocal()
    try:
        assert db.query(BillingWebhookEvent).filter(BillingWebhookEvent.event_id == f"razorpay:{evt_id}").count() == 1
    finally:
        db.close()

    # 3. Out-of-order payment.failed for already-paid order does NOT mark subscription past_due
    ooo_payload = json.dumps(
        {
            "event": "payment.failed",
            "payload": {"payment": {"entity": {"id": payment_id, "order_id": order_id}}},
        }
    ).encode("utf-8")
    ooo_sig = hmac.new(wh_secret.encode("utf-8"), ooo_payload, hashlib.sha256).hexdigest()
    ooo_res = client.post(
        "/api/v1/billing/razorpay/webhook",
        content=ooo_payload,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": ooo_sig, "X-Razorpay-Event-Id": f"evt_ooo_{uuid.uuid4().hex[:8]}"},
    )
    assert ooo_res.status_code == 200
    assert ooo_res.json()["action"] == "ignored_out_of_order_failure"
    assert client.get("/api/v1/billing/subscription", headers=headers).json()["status"] == "active"

    # 4. Refund event downgrades subscription cleanly to free/canceled
    ref_payload = json.dumps(
        {
            "event": "refund.processed",
            "payload": {"refund": {"entity": {"id": f"rfnd_{uuid.uuid4().hex[:8]}", "payment_id": payment_id}}},
        }
    ).encode("utf-8")
    ref_sig = hmac.new(wh_secret.encode("utf-8"), ref_payload, hashlib.sha256).hexdigest()
    ref_res = client.post(
        "/api/v1/billing/razorpay/webhook",
        content=ref_payload,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": ref_sig, "X-Razorpay-Event-Id": f"evt_ref_{uuid.uuid4().hex[:8]}"},
    )
    assert ref_res.status_code == 200
    sub_after = client.get("/api/v1/billing/subscription", headers=headers).json()
    assert sub_after["plan_slug"] == "free"
    assert sub_after["status"] == "canceled"


def test_real_totp_mfa_login_enforcement_and_password_change_invalidation():
    headers, org_id, user_id, email = _register_tenant("MfaOrg")

    # 1. Initiate MFA setup -> secret encrypted in DB
    setup_res = client.post("/api/v1/auth/mfa/setup", headers=headers)
    assert setup_res.status_code == 200
    secret_b32 = setup_res.json()["mfa_secret"]

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == user_id).first()
        assert u.mfa_secret != secret_b32  # Ciphertext stored, never plaintext
        assert u.mfa_enabled is False
    finally:
        db.close()

    # 2. Arbitrary 6 digits rejected (no sham MFA!)
    wrong_code = "000000" if generate_totp_code(secret_b32) != "000000" else "999999"
    bad_verif = client.post("/api/v1/auth/mfa/verify", json={"code": wrong_code}, headers=headers)
    assert bad_verif.status_code == 400

    # 3. Real RFC 6238 TOTP code activates MFA
    real_code = generate_totp_code(secret_b32)
    ok_verif = client.post("/api/v1/auth/mfa/verify", json={"code": real_code}, headers=headers)
    assert ok_verif.status_code == 200
    assert ok_verif.json()["mfa_enabled"] is True

    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["mfa_enabled"] is True

    # 4. Login without mfa_code -> 401 MFA_REQUIRED
    login_no_mfa = client.post("/api/v1/auth/login", json={"email": email, "password": "StrongPassword123!"})
    assert login_no_mfa.status_code == 401
    assert "MFA_REQUIRED" in login_no_mfa.json()["detail"]

    # 5. Login with wrong mfa_code -> 401
    login_bad_mfa = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPassword123!", "mfa_code": wrong_code},
    )
    assert login_bad_mfa.status_code == 401

    # 6. Login with valid TOTP -> 200
    login_ok = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPassword123!", "mfa_code": generate_totp_code(secret_b32)},
    )
    assert login_ok.status_code == 200
    old_token_headers = {"Authorization": f"Bearer {login_ok.json()['access_token']}"}

    # 7. Password change invalidates prior tokens!
    time.sleep(1.1)
    chg = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "StrongPassword123!", "new_password": "UpdatedPassword456!"},
        headers=old_token_headers,
    )
    assert chg.status_code == 200

    stale_me = client.get("/api/v1/auth/me", headers=old_token_headers)
    assert stale_me.status_code == 401


def test_system_disaster_recovery_isolation_teams_fix_and_viewer_rbac():
    headers_a, org_a, user_a_id, _ = _register_tenant("TenantAlpha")
    headers_b, org_b, user_b_id, _ = _register_tenant("TenantBeta")

    # Tenant Administrator & Owner CANNOT trigger system-wide DB backup/restore or manual invoice forgery
    assert client.post("/api/v1/system/disaster-recovery/backup", headers=headers_a).status_code == 403
    assert client.post(
        "/api/v1/system/disaster-recovery/restore",
        json={"backup_id": "backup_20261107_000000"},
        headers=headers_a,
    ).status_code == 403
    assert client.post(
        "/api/v1/billing/invoices/generate-manual",
        json={"amount_dollars": 999.0},
        headers=headers_a,
    ).status_code == 403

    # Path traversal in backup_id is strictly rejected at service layer
    with pytest.raises(ValueError, match="Invalid backup_id"):
        DisasterRecoveryService.restore_backup("../../etc/passwd")

    # Teams detail + project assignment + activity log work without 500 and respect org boundaries
    proj_a = client.post("/api/v1/projects", json={"name": f"TeamProj-{uuid.uuid4().hex[:6]}"}, headers=headers_a).json()
    team_a = client.post("/api/v1/teams", json={"name": f"PlatformEng-{uuid.uuid4().hex[:5]}"}, headers=headers_a)
    assert team_a.status_code == 201
    team_id = team_a.json()["id"]

    assign = client.post(
        f"/api/v1/teams/{team_id}/projects/{proj_a['id']}",
        json={"permission_level": "admin"},
        headers=headers_a,
    )
    assert assign.status_code == 200

    detail = client.get(f"/api/v1/teams/{team_id}", headers=headers_a)
    assert detail.status_code == 200
    assert detail.json()["assigned_projects"][0]["permission_level"] == "admin"
    assert detail.json()["members"][0]["joined_at"] is not None

    # Org B cannot access Org A's team
    assert client.get(f"/api/v1/teams/{team_id}", headers=headers_b).status_code == 404

    # Viewer role is strictly blocked from mutating endpoints
    db = SessionLocal()
    try:
        BillingService.change_subscription_plan(db, org_b, "starter")
        u_b = db.query(User).filter(User.id == user_b_id).first()
        u_b.role = "Viewer"
        db.commit()
    finally:
        db.close()

    assert client.post("/api/v1/assessments/run", json={"project_id": proj_a["id"]}, headers=headers_b).status_code == 403
    assert client.post("/api/v1/technologies", json={"name": "react"}, headers=headers_b).status_code == 403
    assert client.post(
        "/api/v1/technologies/import",
        json={"project_id": proj_a["id"], "file_name": "package.json", "content": "{}"},
        headers=headers_b,
    ).status_code == 403

