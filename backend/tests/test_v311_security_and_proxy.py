import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from app.services.rate_limiter import get_client_ip, is_trusted_proxy, rate_limiter

def test_is_trusted_proxy_recognition():
    assert is_trusted_proxy("127.0.0.1") is True
    assert is_trusted_proxy("::1") is True
    assert is_trusted_proxy("10.0.1.5") is True
    assert is_trusted_proxy("172.18.0.2") is True
    assert is_trusted_proxy("192.168.1.100") is True
    # Public Internet IPs must NOT be trusted proxies
    assert is_trusted_proxy("203.0.113.195") is False
    assert is_trusted_proxy("8.8.8.8") is False

def test_client_ip_trusted_proxy_forwarding():
    # When request comes from trusted proxy (e.g. 127.0.0.1 Nginx ingress)
    req = MagicMock()
    req.client.host = "127.0.0.1"
    req.headers = {"x-forwarded-for": "198.51.100.42, 10.0.0.1"}
    assert get_client_ip(req) == "198.51.100.42"

def test_client_ip_untrusted_peer_spoof_rejection():
    # When request comes directly from untrusted public IP, spoofed header MUST be ignored
    req = MagicMock()
    req.client.host = "203.0.113.50"
    req.headers = {"x-forwarded-for": "198.51.100.42"}
    assert get_client_ip(req) == "203.0.113.50"

def test_rate_limiter_tiered_fallback():
    rate_limiter.reset()
    client_key = "test_ip_99.88.77.66"

    # Must permit requests up to limit
    for _ in range(5):
        rate_limiter.check_rate_limit(client_key, max_requests=5, window_seconds=60)

    # 6th request in window must raise HTTPException 429
    with pytest.raises(HTTPException) as exc:
        rate_limiter.check_rate_limit(client_key, max_requests=5, window_seconds=60)
    assert exc.value.status_code == 429
