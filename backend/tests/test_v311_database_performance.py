import uuid
import pytest
from app.database import SessionLocal
from app.models.all_models import Organization, AIUsageLedger
from app.services.ai_usage_service import AIUsageMeteringService

def test_sql_aggregation_ai_usage_summary():
    db = SessionLocal()
    org_id = str(uuid.uuid4())
    org = Organization(id=org_id, name=f"Perf Test Org {uuid.uuid4().hex[:6]}", slug=f"perf-org-{uuid.uuid4().hex[:6]}", plan="pro")
    db.add(org)
    db.commit()

    try:
        # Seed several usage records across different providers
        entry1 = AIUsageLedger(
            org_id=org_id,
            user_id=None,
            provider="gemini",
            model="gemini-1.5-flash",
            operation_type="chat",
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            cost_usd=0.000225,
            latency_ms=120.0
        )
        entry2 = AIUsageLedger(
            org_id=org_id,
            user_id=None,
            provider="gemini",
            model="gemini-1.5-pro",
            operation_type="recommendation",
            prompt_tokens=2000,
            completion_tokens=1000,
            total_tokens=3000,
            cost_usd=0.0175,
            latency_ms=350.0
        )
        entry3 = AIUsageLedger(
            org_id=org_id,
            user_id=None,
            provider="openai",
            model="gpt-4o",
            operation_type="chat",
            prompt_tokens=500,
            completion_tokens=250,
            total_tokens=750,
            cost_usd=0.00625,
            latency_ms=210.0
        )
        db.add_all([entry1, entry2, entry3])
        db.commit()

        # Run SQL aggregate summary
        summary = AIUsageMeteringService.get_usage_summary(db=db, org_id=org_id)
        assert summary["org_id"] == org_id
        assert summary["total_requests_count"] == 3
        assert summary["prompt_tokens_count"] == 3500
        assert summary["completion_tokens_count"] == 1750
        assert summary["total_estimated_cost_usd"] > 0.02
        assert "gemini" in summary["providers_breakdown"]
        assert "openai" in summary["providers_breakdown"]
        assert summary["providers_breakdown"]["gemini"]["requests_count"] == 2
        assert summary["providers_breakdown"]["openai"]["requests_count"] == 1
    finally:
        db.close()

