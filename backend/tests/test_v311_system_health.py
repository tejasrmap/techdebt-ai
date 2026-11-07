import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.historical_memory_adapter import HistoricalAssessmentMemoryAdapter
from app.database import SessionLocal

client = TestClient(app)

def test_system_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["version"] == "3.1.1"
    assert "components" in data
    components = data["components"]
    assert "database" in components
    assert components["database"]["status"] == "connected"
    assert components["database"]["healthy"] is True
    assert "storage" in components
    assert components["storage"]["status"] == "writable"
    assert "redis" in components
    assert "ai_providers" in components
    assert "vulnerability_intelligence" in components

def test_liveness_and_readiness_probes():
    live_resp = client.get("/live")
    assert live_resp.status_code == 200
    live_data = live_resp.json()
    assert live_data["status"] == "alive"
    assert live_data["version"] == "3.1.1"
    assert "uptime_seconds" in live_data

    ready_resp = client.get("/ready")
    assert ready_resp.status_code == 200
    ready_data = ready_resp.json()
    assert ready_data["status"] == "ready"
    assert ready_data["database"] == "connected"
    assert ready_data["version"] == "3.1.1"

def test_historical_adapter_live_connectivity_check():
    adapter = HistoricalAssessmentMemoryAdapter()
    db = SessionLocal()
    try:
        import asyncio
        res = asyncio.run(adapter.verify_connectivity(db=db))
        assert res["connected"] is True
        assert res["status"] == "healthy"
        assert res["mode"] == "postgresql"
        assert "verified" in res["message"].lower() or "operational" in res["message"].lower()
    finally:
        db.close()

