"""
TechDebt AI v3.1.0 — Distributed Rate Limiter with Redis + DB RateLimitBucket fallback.

Provides:
- Proxy-aware IP extraction (X-Forwarded-For, X-Real-IP, Cloudflare CF-Connecting-IP)
- Distributed sliding-window rate limiting via Redis (when configured)
- Durable PostgreSQL/SQLite RateLimitBucket fallback (when Redis unavailable)
- Thread-safe in-memory fast tier for high throughput
- Standardized HTTP 429 response with Retry-After header
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from collections import defaultdict
from fastapi import Request, HTTPException, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str:
    """Extract real client IP taking proxies and ingress headers into account."""
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()

    xff = request.headers.get("x-forwarded-for")
    if xff:
        # First IP in X-Forwarded-For is client originating IP
        return xff.split(",")[0].strip()

    x_real = request.headers.get("x-real-ip")
    if x_real:
        return x_real.strip()

    if request.client:
        return request.client.host
    return "127.0.0.1"


class DistributedRateLimiter:
    """
    Tiered distributed rate limiter:
    1. Redis sliding window (if REDIS_URL configured)
    2. Database RateLimitBucket sliding window (if db session available)
    3. Thread-safe in-memory fallback
    """

    def __init__(self):
        self._memory_buckets: Dict[str, List[float]] = defaultdict(list)
        self._redis_client = None
        self._redis_checked = False

    def _get_redis(self):
        if not self._redis_checked:
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                try:
                    import redis
                    self._redis_client = redis.from_url(redis_url, decode_responses=True)
                    self._redis_client.ping()
                    logger.info("Distributed rate limiter connected to Redis.")
                except Exception as e:
                    logger.warning(f"Redis rate limiter unavailable: {e}. Falling back to DB/Memory.")
                    self._redis_client = None
            self._redis_checked = True
        return self._redis_client

    def check_rate_limit(
        self,
        key_or_request: Any,
        max_requests: int = 60,
        window_seconds: int = 60,
        db: Optional[Session] = None
    ) -> None:
        """
        Enforces sliding-window rate limit. Raises HTTP 429 if exceeded.
        """
        if isinstance(key_or_request, str):
            key = key_or_request
        elif hasattr(key_or_request, "url") and hasattr(key_or_request, "headers"):
            client_ip = get_client_ip(key_or_request)
            path = key_or_request.url.path
            key = f"rl:{client_ip}:{path}"
        else:
            key = str(key_or_request)

        # 1. Try Redis
        r = self._get_redis()
        if r is not None:
            try:
                now = time.time()
                pipeline = r.pipeline()
                pipeline.zremrangebyscore(key, 0, now - window_seconds)
                pipeline.zadd(key, {str(now): now})
                pipeline.zcard(key)
                pipeline.expire(key, window_seconds + 5)
                _, _, count, _ = pipeline.execute()

                if count > max_requests:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds}s.",
                        headers={"Retry-After": str(window_seconds)}
                    )
                return
            except HTTPException:
                raise
            except Exception as e:
                logger.debug(f"Redis rate check error: {e}. Using DB/Memory tier.")

        # 2. Try DB RateLimitBucket if db provided
        if db is not None:
            try:
                from app.models.all_models import RateLimitBucket
                now = time.time()
                window_start = int(now // window_seconds)
                bucket_id = f"{key}:{window_start}"

                bucket = db.query(RateLimitBucket).filter(RateLimitBucket.bucket_key == bucket_id).first()
                if bucket:
                    if bucket.request_count >= max_requests:
                        retry_after = max(1, int(window_seconds - (now % window_seconds)))
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds}s.",
                            headers={"Retry-After": str(retry_after)}
                        )
                    bucket.request_count += 1
                    db.commit()
                    return
                else:
                    new_bucket = RateLimitBucket(
                        bucket_key=bucket_id,
                        window_start=window_start,
                        request_count=1,
                        expires_at=datetime.utcnow() + timedelta(seconds=window_seconds * 2)
                    )
                    db.add(new_bucket)
                    db.commit()
                    return
            except HTTPException:
                raise
            except Exception as e:
                db.rollback()
                logger.debug(f"DB rate check error: {e}. Using in-memory tier.")

        # 3. In-memory fallback
        now = time.time()
        timestamps = self._memory_buckets[key]
        self._memory_buckets[key] = [t for t in timestamps if now - t < window_seconds]

        if len(self._memory_buckets[key]) >= max_requests:
            retry_after = int(window_seconds - (now - self._memory_buckets[key][0]))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds}s.",
                headers={"Retry-After": str(max(1, retry_after))}
            )

        self._memory_buckets[key].append(now)

    def reset(self) -> None:
        self._memory_buckets.clear()


rate_limiter = DistributedRateLimiter()


def rate_limit_auth(request: Request, db: Optional[Session] = None):
    rate_limiter.check_rate_limit(request, max_requests=10, window_seconds=60, db=db)


def rate_limit_standard(request: Request, db: Optional[Session] = None):
    rate_limiter.check_rate_limit(request, max_requests=120, window_seconds=60, db=db)


def rate_limit_ai(request: Request, db: Optional[Session] = None):
    rate_limiter.check_rate_limit(request, max_requests=30, window_seconds=60, db=db)


def rate_limit_reports(request: Request, db: Optional[Session] = None):
    rate_limiter.check_rate_limit(request, max_requests=20, window_seconds=60, db=db)


def rate_limit_ingestion(request: Request, db: Optional[Session] = None):
    rate_limiter.check_rate_limit(request, max_requests=15, window_seconds=60, db=db)
