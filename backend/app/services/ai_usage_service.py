from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.all_models import AIUsageLedger, UsageRecord, Organization

MODEL_PRICING_PER_1K: Dict[str, Dict[str, float]] = {
    # Rates per 1,000 tokens
    "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
    "gemini-1.5-pro": {"input": 0.0035, "output": 0.0105},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    "deterministic": {"input": 0.0, "output": 0.0},
    "deterministic-engine-v3": {"input": 0.0, "output": 0.0}
}

DEFAULT_TIER_LIMITS: Dict[str, float] = {
    # Monthly token limits
    "free": 100_000.0,
    "pro": 1_000_000.0,
    "enterprise": 10_000_000.0
}

class AIUsageMeteringService:
    @staticmethod
    def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        clean_model = model.lower()
        pricing = MODEL_PRICING_PER_1K.get(clean_model)
        if not pricing:
            # Fallback approximate matching
            if "flash" in clean_model:
                pricing = MODEL_PRICING_PER_1K["gemini-1.5-flash"]
            elif "pro" in clean_model and "gemini" in clean_model:
                pricing = MODEL_PRICING_PER_1K["gemini-1.5-pro"]
            elif "mini" in clean_model:
                pricing = MODEL_PRICING_PER_1K["gpt-4o-mini"]
            elif "gpt-4" in clean_model:
                pricing = MODEL_PRICING_PER_1K["gpt-4o"]
            elif "claude" in clean_model:
                pricing = MODEL_PRICING_PER_1K["claude-3-5-sonnet"]
            else:
                pricing = {"input": 0.0005, "output": 0.0015}

        cost_input = (prompt_tokens / 1000.0) * pricing["input"]
        cost_output = (completion_tokens / 1000.0) * pricing["output"]
        return round(cost_input + cost_output, 6)

    @classmethod
    def record_usage(
        cls,
        db: Session,
        org_id: str,
        user_id: Optional[str],
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float = 0.0,
        operation_type: str = "chat"
    ) -> AIUsageLedger:
        cost = cls.calculate_cost(model, prompt_tokens, completion_tokens)
        total_tokens = prompt_tokens + completion_tokens

        ledger_entry = AIUsageLedger(
            org_id=org_id,
            user_id=user_id,
            provider=provider,
            model=model,
            operation_type=operation_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost,
            latency_ms=round(latency_ms, 2)
        )
        db.add(ledger_entry)

        # Update or create monthly aggregate UsageRecord
        period = datetime.utcnow().strftime("%Y-%m")
        usage_rec = db.query(UsageRecord).filter(
            UsageRecord.org_id == org_id,
            UsageRecord.metric_type == "ai_tokens",
            UsageRecord.period == period
        ).first()

        org = db.query(Organization).filter(Organization.id == org_id).first()
        plan_name = (org.plan or "free").lower() if org else "free"
        plan_limit = DEFAULT_TIER_LIMITS.get(plan_name, 100_000.0)

        if usage_rec:
            usage_rec.count += float(total_tokens)
            usage_rec.limit = plan_limit
        else:
            usage_rec = UsageRecord(
                org_id=org_id,
                metric_type="ai_tokens",
                period=period,
                count=float(total_tokens),
                limit=plan_limit
            )
            db.add(usage_rec)

        db.commit()
        db.refresh(ledger_entry)
        return ledger_entry

    @classmethod
    def get_usage_summary(
        cls,
        db: Session,
        org_id: str,
        period: Optional[str] = None
    ) -> Dict[str, Any]:
        curr_period = period or datetime.utcnow().strftime("%Y-%m")
        
        # Query aggregate usage record
        usage_rec = db.query(UsageRecord).filter(
            UsageRecord.org_id == org_id,
            UsageRecord.metric_type == "ai_tokens",
            UsageRecord.period == curr_period
        ).first()

        total_tokens = usage_rec.count if usage_rec else 0.0
        token_limit = usage_rec.limit if usage_rec else 100_000.0

        # Query all ledger entries for this org
        ledgers = db.query(AIUsageLedger).filter(
            AIUsageLedger.org_id == org_id
        ).all()

        total_cost = sum(l.cost_usd for l in ledgers)
        total_prompt_tok = sum(l.prompt_tokens for l in ledgers)
        total_comp_tok = sum(l.completion_tokens for l in ledgers)

        # Provider breakdown
        provider_breakdown: Dict[str, Dict[str, Any]] = {}
        for l in ledgers:
            p = l.provider
            if p not in provider_breakdown:
                provider_breakdown[p] = {"requests_count": 0, "total_tokens": 0, "cost_usd": 0.0}
            provider_breakdown[p]["requests_count"] += 1
            provider_breakdown[p]["total_tokens"] += l.total_tokens
            provider_breakdown[p]["cost_usd"] = round(provider_breakdown[p]["cost_usd"] + l.cost_usd, 6)

        pct_used = round((total_tokens / token_limit * 100.0) if token_limit > 0 else 0.0, 1)

        return {
            "org_id": org_id,
            "period": curr_period,
            "total_tokens_used": int(total_tokens),
            "token_limit": int(token_limit),
            "percentage_quota_used": min(100.0, pct_used),
            "total_estimated_cost_usd": round(total_cost, 4),
            "prompt_tokens_count": total_prompt_tok,
            "completion_tokens_count": total_comp_tok,
            "total_requests_count": len(ledgers),
            "providers_breakdown": provider_breakdown
        }

    @classmethod
    def get_usage_records(
        cls,
        db: Session,
        org_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        ledgers = (
            db.query(AIUsageLedger)
            .filter(AIUsageLedger.org_id == org_id)
            .order_by(AIUsageLedger.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": l.id,
                "provider": l.provider,
                "model": l.model,
                "operation_type": l.operation_type,
                "prompt_tokens": l.prompt_tokens,
                "completion_tokens": l.completion_tokens,
                "total_tokens": l.total_tokens,
                "cost_usd": l.cost_usd,
                "latency_ms": l.latency_ms,
                "created_at": l.created_at
            }
            for l in ledgers
        ]
