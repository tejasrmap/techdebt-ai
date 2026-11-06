import uuid
import asyncio
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.modular_ai_engine import (
    ModularAIEngine,
    DeterministicFallbackProvider,
    GeminiProvider,
    OpenAIProvider,
    AnthropicProvider
)

client = TestClient(app)

def get_test_headers():
    uid = uuid.uuid4().hex[:8]
    email = f"ai_tester_{uid}@techdebt.ai"
    reg = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "SecurePassword123!",
        "full_name": "AI Tester",
        "organization_name": f"AI Org {uid}"
    })
    if reg.status_code in (200, 201):
        token = reg.json()["access_token"]
    else:
        login = client.post("/api/v1/auth/login", json={
            "email": email,
            "password": "SecurePassword123!"
        })
        token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_deterministic_fallback_provider():
    async def _run():
        provider = DeterministicFallbackProvider()
        assert provider.is_configured() is True
        
        # Text generation
        resp = await provider.generate_text("Analyze architecture risks")
        assert resp.provider == "deterministic"
        assert "Deterministic AI Engine" in resp.content
        assert resp.latency_ms >= 0

        # JSON generation
        resp_json = await provider.generate_text("Provide technical debt metrics in JSON format")
        assert "deterministic_analysis_completed" in resp_json.content

        # Health check
        health = await provider.health_check()
        assert health["status"] == "healthy"
    
    asyncio.run(_run())

def test_modular_engine_automatic_fallback_cascade():
    async def _run():
        engine = ModularAIEngine()
        
        # Requesting an unconfigured provider triggers fallback to deterministic
        resp = await engine.generate_completion(
            prompt="Review database performance",
            preferred_provider="gemini"
        )
        assert resp.provider in ("gemini", "deterministic")
        if resp.provider == "deterministic":
            assert resp.fallback_used is True
        assert len(resp.content) > 0

        # Explicit deterministic generation
        forced_resp = await engine.generate_completion(
            prompt="Summarize technical debt",
            preferred_provider="deterministic"
        )
        assert forced_resp.provider == "deterministic"
    
    asyncio.run(_run())

def test_providers_status_reporting():
    async def _run():
        engine = ModularAIEngine()
        status = await engine.get_providers_status()
        assert "providers" in status
        assert "gemini" in status["providers"]
        assert "openai" in status["providers"]
        assert "anthropic" in status["providers"]
        assert "deterministic" in status["providers"]
        assert status["providers"]["deterministic"]["is_configured"] is True

    asyncio.run(_run())


def test_ai_providers_api_endpoints():
    headers = get_test_headers()

    # 1. GET /api/v1/intelligence/ai-providers
    prov_res = client.get("/api/v1/intelligence/ai-providers", headers=headers)
    assert prov_res.status_code == 200
    p_data = prov_res.json()
    assert "providers" in p_data
    assert "deterministic" in p_data["providers"]

    # 2. POST /api/v1/intelligence/ai-providers/test with fallback
    test_res = client.post("/api/v1/intelligence/ai-providers/test", json={
        "force_fallback": True,
        "prompt": "Test AI engine resilience"
    }, headers=headers)
    assert test_res.status_code == 200
    t_data = test_res.json()
    assert t_data["status"] == "success"
    assert t_data["provider"] == "deterministic"
    assert t_data["content_length"] > 0
