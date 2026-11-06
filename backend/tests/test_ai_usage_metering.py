import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.services.ai_usage_service import AIUsageMeteringService
from app.models.all_models import Organization, AIUsageLedger, UsageRecord, Project, Assessment

client = TestClient(app)

def get_test_headers():
    uid = uuid.uuid4().hex[:8]
    email = f"metering_tester_{uid}@techdebt.ai"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "Metering Tester",
        "organization_name": f"Metering Org {uid}"
    })
    if reg.status_code in (200, 201):
        token = reg.json()["access_token"]
        org_id = reg.json()["user"]["org_id"]
        user_id = reg.json()["user"]["id"]
    else:
        login = client.post("/api/v1/auth/login", json={
            "email": email,
            "password": "SecurePassword123!"
        })
        token = login.json()["access_token"]
        org_id = login.json()["user"]["org_id"]
        user_id = login.json()["user"]["id"]
    return {"Authorization": f"Bearer {token}"}, org_id, user_id

def test_ai_cost_calculation():
    # Gemini 1.5 Flash: 1,000 prompt tokens ($0.000075) + 1,000 completion ($0.0003) = $0.000375
    cost_flash = AIUsageMeteringService.calculate_cost("gemini-1.5-flash", 1000, 1000)
    assert abs(cost_flash - 0.000375) < 0.00001

    # GPT-4o: 1,000 input ($0.005) + 1,000 output ($0.015) = $0.02
    cost_gpt4o = AIUsageMeteringService.calculate_cost("gpt-4o", 1000, 1000)
    assert abs(cost_gpt4o - 0.02) < 0.0001

    # Deterministic: 0.0
    cost_det = AIUsageMeteringService.calculate_cost("deterministic", 5000, 5000)
    assert cost_det == 0.0

def test_record_usage_and_aggregate_rollup():
    db = SessionLocal()
    try:
        org_id = f"test-org-{uuid.uuid4().hex[:8]}"
        org = Organization(id=org_id, name="Metered Org", slug=f"slug-{uuid.uuid4().hex[:6]}", plan="pro")
        db.add(org)
        db.commit()

        # Record 2 invocations
        entry1 = AIUsageMeteringService.record_usage(
            db=db,
            org_id=org_id,
            user_id=None,
            provider="gemini",
            model="gemini-1.5-flash",
            prompt_tokens=2000,
            completion_tokens=500,
            latency_ms=120.5,
            operation_type="code_review"
        )
        assert entry1.total_tokens == 2500
        assert entry1.cost_usd > 0

        entry2 = AIUsageMeteringService.record_usage(
            db=db,
            org_id=org_id,
            user_id=None,
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=1000,
            completion_tokens=500,
            latency_ms=95.0,
            operation_type="chat"
        )
        assert entry2.total_tokens == 1500

        # Query summary
        summary = AIUsageMeteringService.get_usage_summary(db=db, org_id=org_id)
        assert summary["total_tokens_used"] == 4000
        assert summary["total_requests_count"] == 2
        assert summary["token_limit"] == 1_000_000 # pro tier limit
        assert "gemini" in summary["providers_breakdown"]
        assert "openai" in summary["providers_breakdown"]

        # Query records
        records = AIUsageMeteringService.get_usage_records(db=db, org_id=org_id)
        assert len(records) == 2
    finally:
        db.close()

def test_ai_usage_api_endpoints():
    headers, org_id, user_id = get_test_headers()

    # 1. Create project and invoke assistant chat to trigger automatic metering
    p_name = f"Usage Proj {uuid.uuid4().hex[:6]}"
    p_res = client.post("/api/v1/projects", json={"name": p_name, "repository_url": "https://github.com/org/meter"}, headers=headers)
    assert p_res.status_code in (200, 201)
    proj_id = p_res.json()["id"]

    chat_res = client.post("/api/v1/intelligence/assistant/chat", json={
        "project_id": proj_id,
        "message": "Review my project architecture"
    }, headers=headers)
    assert chat_res.status_code == 200

    # 2. Query GET /ai-usage/summary
    sum_res = client.get("/api/v1/intelligence/ai-usage/summary", headers=headers)
    assert sum_res.status_code == 200
    s_data = sum_res.json()
    assert s_data["org_id"] == org_id
    assert s_data["total_tokens_used"] > 0
    assert s_data["total_requests_count"] >= 1

    # 3. Query GET /ai-usage/records
    rec_res = client.get("/api/v1/intelligence/ai-usage/records", headers=headers)
    assert rec_res.status_code == 200
    r_data = rec_res.json()
    assert len(r_data) >= 1
    assert r_data[0]["operation_type"] == "assistant_chat"
