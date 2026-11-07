"""
TechDebt AI v3.1.0 — Test Suite for AI Provider Abstraction,
Secret Redaction, Schema Validation, and Finding Traceability (GAP-AI-01).
"""

import asyncio
import pytest
import json
from unittest.mock import patch, MagicMock
from pydantic import BaseModel

from app.services.modular_ai_engine import (
    ModularAIEngine,
    GeminiProvider,
    OpenAIProvider,
    DeterministicFallbackProvider,
    LLMResponse
)
from app.services.prompt_defense_service import PromptDefenseService
from app.services.ai_engineering_assistant import (
    AIEngineeringAssistant,
    RecommendationsSchema
)


def test_outbound_secret_redaction():
    leak_sample = (
        "Project config: sk-abcdef1234567890abcdef1234567890\n"
        "AWS: AKIAIOSFODNN7EXAMPLE\n"
        "Razorpay: rzp_test_1234567890abcd\n"
        "Password: password='super_secret_pass'\n"
        "Database: postgresql://admin:secret123@db.example.com/production"
    )
    redacted = PromptDefenseService.redact_secrets(leak_sample)
    assert "sk-" not in redacted
    assert "AKIA" not in redacted
    assert "rzp_test_" not in redacted
    assert "super_secret_pass" not in redacted
    assert "secret123" not in redacted
    assert "[REDACTED_" in redacted


def test_gemini_provider_uses_header_auth():
    async def _test():
        provider = GeminiProvider(api_key="test-gemini-key")
        captured_request = {}

        async def mock_post(url, headers=None, json=None):
            captured_request["url"] = str(url)
            captured_request["headers"] = headers
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "candidates": [{"content": {"parts": [{"text": "Hello Gemini"}]}}],
                "usageMetadata": {"promptTokenCount": 15, "candidatesTokenCount": 5}
            }
            return mock_resp

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            res = await provider.generate_text("test prompt")
            assert res.content == "Hello Gemini"
            assert res.provider == "gemini"
            # API key MUST be in header, not in query string URL
            assert captured_request["headers"].get("x-goog-api-key") == "test-gemini-key"
            assert "?key=" not in captured_request["url"]

    asyncio.run(_test())


def test_openai_provider_uses_bearer_header():
    async def _test():
        provider = OpenAIProvider(api_key="test-openai-key")
        captured_request = {}

        async def mock_post(url, headers=None, json=None):
            captured_request["url"] = str(url)
            captured_request["headers"] = headers
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "Hello OpenAI"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 8}
            }
            return mock_resp

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            res = await provider.generate_text("test prompt")
            assert res.content == "Hello OpenAI"
            assert res.provider == "openai"
            assert captured_request["headers"].get("Authorization") == "Bearer test-openai-key"

    asyncio.run(_test())


def test_schema_validation_and_deterministic_fallback():
    async def _test():
        engine = ModularAIEngine()

        class StrictSchema(BaseModel):
            summary: str
            action_items: list[str]

        # Without cloud keys, engine falls back to deterministic provider
        res = await engine.generate_completion(
            prompt="Analyze repository architecture",
            output_schema=StrictSchema
        )
        assert res.fallback_used is True
        assert res.provider == "deterministic"

    asyncio.run(_test())


def test_ai_engineering_assistant_recommendation_provenance_and_traceability():
    async def _test():
        assistant = AIEngineeringAssistant()
        
        code_findings = [
            {"id": "FINDING-101", "file_path": "services/auth.py", "title": "Weak salt", "severity": "High"},
            {"id": "FINDING-202", "file_path": "core/db.py", "title": "Connection leak", "severity": "Medium"}
        ]
        hotspots = [
            {"file_path": "services/auth.py", "complexity": 18, "loc": 450}
        ]
        dependencies = [
            {"name": "fastapi", "version": "0.100.0"}
        ]

        recs = await assistant.generate_engineering_recommendations(
            project_name="TestApp",
            overall_score=75.0,
            risk_classification="Moderate",
            hotspots=hotspots,
            code_findings=code_findings,
            dependencies=dependencies,
            total_remediation_hours=12.5
        )

        assert recs["origin"] == "rule_based"
        assert recs["provider"] == "deterministic"
        assert recs["model"] == "deterministic-engine-v3"
        assert recs["cost_usd"] == 0.0
        assert "FINDING-101" in recs["finding_traceability"]
        assert len(recs["refactoring_recipes"]) > 0
        assert len(recs["modernization_roadmap"]["immediate_30_days"]) > 0

    asyncio.run(_test())
