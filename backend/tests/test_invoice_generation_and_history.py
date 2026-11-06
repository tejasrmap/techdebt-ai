import os
import hmac
import hashlib
import uuid
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.all_models import Organization, Invoice
from app.services.billing_service import BillingService

client = TestClient(app)

def _purchase_verified_plan(headers: dict, plan_slug: str = "professional", cycle: str = "monthly", amount: int = 19900) -> dict:
    order_id = f"order_inv_{uuid.uuid4().hex[:10]}"
    pay_id = f"pay_inv_{uuid.uuid4().hex[:10]}"
    with patch.dict(os.environ, {"RAZORPAY_KEY_ID": "rzp_test_mock_inv", "RAZORPAY_KEY_SECRET": "rzp_test_sec_inv", "RAZORPAY_CURRENCY": "USD"}):
        with patch.object(BillingService, "_post_razorpay_order", return_value={"id": order_id, "amount": amount, "currency": "USD"}):
            c_res = client.post("/api/v1/billing/razorpay/create-order", json={"plan_slug": plan_slug, "billing_cycle": cycle}, headers=headers)
            assert c_res.status_code == 200
        sig = hmac.new(b"rzp_test_sec_inv", f"{order_id}|{pay_id}".encode(), hashlib.sha256).hexdigest()
        v_res = client.post("/api/v1/billing/razorpay/verify-payment", json={
            "plan_slug": plan_slug,
            "billing_cycle": cycle,
            "razorpay_order_id": order_id,
            "razorpay_payment_id": pay_id,
            "razorpay_signature": sig,
        }, headers=headers)
        assert v_res.status_code == 200, v_res.text
        return v_res.json()

def get_test_headers():
    uid = uuid.uuid4().hex[:8]
    email = f"invoice_tester_{uid}@techdebt.ai"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Invoice Tester",
        "organization_name": f"Invoice Org {uid}"
    })
    token = reg.json()["access_token"]
    org_id = reg.json()["user"]["org_id"]
    return {"Authorization": f"Bearer {token}"}, org_id

def test_invoice_creation_retrieval_and_download():
    headers, org_id = get_test_headers()

    # 1. Generate a verified invoice via order-bound payment verification
    inv_data = _purchase_verified_plan(headers, plan_slug="professional", cycle="monthly", amount=19900)
    inv_id = inv_data["invoice_id"]
    inv_num = inv_data["invoice_number"]

    # 2. List invoices
    list_res = client.get("/api/v1/billing/invoices", headers=headers)
    assert list_res.status_code == 200
    invoices = list_res.json()
    assert len(invoices) >= 1
    assert any(i["id"] == inv_id for i in invoices)

    # 3. Retrieve invoice detail
    detail_res = client.get(f"/api/v1/billing/invoices/{inv_id}", headers=headers)
    assert detail_res.status_code == 200
    d = detail_res.json()
    assert d["id"] == inv_id
    assert d["invoice_number"] == inv_num
    assert d["amount_dollars"] == 199.00
    assert d["status"] == "paid"

    # 4. Download printable HTML invoice
    dl_res = client.get(f"/api/v1/billing/invoices/{inv_id}/download", headers=headers)
    assert dl_res.status_code == 200
    assert "text/html" in dl_res.headers.get("content-type", "")
    html = dl_res.text
    assert inv_num in html
    assert "TechDebt AI" in html
    assert "199.00" in html

def test_cross_tenant_invoice_isolation():
    headers_a, org_a = get_test_headers()
    headers_b, org_b = get_test_headers()

    # Generate verified invoice for Org A
    inv_a_id = _purchase_verified_plan(headers_a, plan_slug="starter", cycle="monthly", amount=4900)["invoice_id"]

    # Org B attempts to read Org A's invoice -> 404
    steal_res = client.get(f"/api/v1/billing/invoices/{inv_a_id}", headers=headers_b)
    assert steal_res.status_code == 404

    # Org B attempts to download Org A's invoice -> 404
    dl_steal_res = client.get(f"/api/v1/billing/invoices/{inv_a_id}/download", headers=headers_b)
    assert dl_steal_res.status_code == 404
