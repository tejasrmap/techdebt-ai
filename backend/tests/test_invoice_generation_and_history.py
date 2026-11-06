import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.all_models import Organization, Invoice

client = TestClient(app)

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

    # 1. Manually generate an invoice
    gen_res = client.post("/api/v1/billing/invoices/generate-manual", json={
        "amount_dollars": 149.00,
        "description": "Annual Professional Plan Renewal"
    }, headers=headers)
    assert gen_res.status_code == 200
    inv_data = gen_res.json()
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
    assert d["amount_dollars"] == 149.00
    assert d["status"] == "paid"

    # 4. Download printable HTML invoice
    dl_res = client.get(f"/api/v1/billing/invoices/{inv_id}/download", headers=headers)
    assert dl_res.status_code == 200
    assert "text/html" in dl_res.headers.get("content-type", "")
    html = dl_res.text
    assert inv_num in html
    assert "TechDebt AI" in html
    assert "149.00" in html

def test_cross_tenant_invoice_isolation():
    headers_a, org_a = get_test_headers()
    headers_b, org_b = get_test_headers()

    # Generate invoice for Org A
    gen_res = client.post("/api/v1/billing/invoices/generate-manual", json={
        "amount_dollars": 299.00
    }, headers=headers_a)
    assert gen_res.status_code == 200
    inv_a_id = gen_res.json()["invoice_id"]

    # Org B attempts to read Org A's invoice -> 404
    steal_res = client.get(f"/api/v1/billing/invoices/{inv_a_id}", headers=headers_b)
    assert steal_res.status_code == 404

    # Org B attempts to download Org A's invoice -> 404
    dl_steal_res = client.get(f"/api/v1/billing/invoices/{inv_a_id}/download", headers=headers_b)
    assert dl_steal_res.status_code == 404
