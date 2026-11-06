import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.metrics_service import MetricsService

client = TestClient(app)

def test_prometheus_metrics_endpoint():
    # Make a few requests to populate metrics
    client.get("/health")
    client.get("/ready")

    # Query metrics endpoint
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    text = resp.text

    # Verify standard Prometheus structure
    assert "# HELP techdebt_uptime_seconds" in text
    assert "techdebt_uptime_seconds" in text
    assert "# HELP techdebt_http_requests_total" in text
    assert "techdebt_http_requests_total" in text
    assert 'endpoint="/health"' in text

def test_request_correlation_and_timing_headers():
    # 1. Automatic request-id generation
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert resp.headers["X-Request-ID"].startswith("req_")
    assert "X-Response-Time-Ms" in resp.headers

    # 2. Client-provided request-id preservation
    custom_id = "trace-client-abc-987"
    resp2 = client.get("/health", headers={"X-Request-ID": custom_id})
    assert resp2.status_code == 200
    assert resp2.headers["X-Request-ID"] == custom_id

def test_liveness_readiness_and_health_probes():
    # Health
    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    data_h = resp_health.json()
    assert data_h["status"] == "healthy"
    assert data_h["version"] == "3.0.0"

    # Live
    resp_live = client.get("/live")
    assert resp_live.status_code == 200
    data_l = resp_live.json()
    assert data_l["status"] == "alive"
    assert data_l["uptime_seconds"] >= 0

    # Ready
    resp_ready = client.get("/ready")
    assert resp_ready.status_code == 200
    data_r = resp_ready.json()
    assert data_r["status"] == "ready"
    assert data_r["database"] == "connected"

def test_custom_metric_counter_tracking():
    # Increment custom counter
    MetricsService.increment_counter("assessments_executed_total", {"trigger": "manual", "status": "completed"}, 3)

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert 'techdebt_assessments_executed_total{status="completed",trigger="manual"} 3' in resp.text
