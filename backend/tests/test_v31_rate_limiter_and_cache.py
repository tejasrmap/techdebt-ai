"""
TechDebt AI v3.1.0 — Tests for Distributed Rate Limiter, Cache LRU/TTL, and Database Integration.
"""

import time
import pytest
from fastapi import HTTPException, Request
from app.services.rate_limiter import DistributedRateLimiter, get_client_ip
from app.services.cache_service import CacheService
from app.database import SessionLocal
from app.models.all_models import RateLimitBucket


def test_cache_service_lru_and_ttl():
    """Verify CacheService exact LRU eviction and per-item TTL expiration."""
    CacheService.clear()
    CacheService._max_entries = 3

    # Add 3 entries
    CacheService.set("k1", "v1", ttl_seconds=60)
    CacheService.set("k2", "v2", ttl_seconds=60)
    CacheService.set("k3", "v3", ttl_seconds=60)

    # Access k1 to make k2 least recently used
    assert CacheService.get("k1") == "v1"

    # Add 4th entry -> k2 should be evicted
    CacheService.set("k4", "v4", ttl_seconds=60)

    assert CacheService.get("k1") == "v1"
    assert CacheService.get("k2") is None  # evicted!
    assert CacheService.get("k3") == "v3"
    assert CacheService.get("k4") == "v4"

    stats = CacheService.get_stats()
    assert stats["evictions"] == 1
    assert stats["items_count"] == 3

    # Test TTL expiration
    CacheService.set("short", "val", ttl_seconds=0.01)
    time.sleep(0.02)
    assert CacheService.get("short") is None

    # Reset max entries to default
    CacheService._max_entries = 5000
    CacheService.clear()


def test_proxy_aware_client_ip():
    """Verify get_client_ip extracts client address from CF, X-Forwarded-For, and direct connection."""
    class MockRequest:
        def __init__(self, headers, client_host="10.0.0.1"):
            self.headers = headers
            self.client = type("Client", (), {"host": client_host})()

    # Cloudflare header priority
    r_cf = MockRequest({"cf-connecting-ip": "203.0.113.195", "x-forwarded-for": "198.51.100.1"})
    assert get_client_ip(r_cf) == "203.0.113.195"

    # X-Forwarded-For multi-hop (first IP is client)
    r_xff = MockRequest({"x-forwarded-for": "198.51.100.25, 10.0.0.2, 10.0.0.3"})
    assert get_client_ip(r_xff) == "198.51.100.25"

    # Direct client fallback
    r_direct = MockRequest({}, client_host="192.168.1.50")
    assert get_client_ip(r_direct) == "192.168.1.50"


def test_distributed_rate_limiter_in_memory_and_db_fallback():
    """Verify rate limiter blocks requests exceeding quota and persists buckets to database."""
    limiter = DistributedRateLimiter()
    limiter.reset()

    # In-memory quota check
    test_key = "test_limiter_user_1"
    for _ in range(5):
        limiter.check_rate_limit(test_key, max_requests=5, window_seconds=10)

    with pytest.raises(HTTPException) as exc_info:
        limiter.check_rate_limit(test_key, max_requests=5, window_seconds=10)
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers

    # Database RateLimitBucket quota check
    db = SessionLocal()
    try:
        db_key = f"db_rate_key_{int(time.time())}"
        for _ in range(3):
            limiter.check_rate_limit(db_key, max_requests=3, window_seconds=60, db=db)

        # 4th request must exceed limit
        with pytest.raises(HTTPException) as exc_info_db:
            limiter.check_rate_limit(db_key, max_requests=3, window_seconds=60, db=db)
        assert exc_info_db.value.status_code == 429

        # Verify bucket exists in DB
        now_bucket = int(time.time() // 60)
        bucket_record = db.query(RateLimitBucket).filter(
            RateLimitBucket.bucket_key == f"{db_key}:{now_bucket}"
        ).first()
        assert bucket_record is not None
        assert bucket_record.request_count == 3
    finally:
        db.close()
