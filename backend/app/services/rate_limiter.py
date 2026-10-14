import time
from typing import Dict, List
from collections import defaultdict
from fastapi import Request, HTTPException, status

class InMemoryRateLimiter:
    def __init__(self):
        # Maps bucket_key -> list of request timestamps
        self.buckets: Dict[str, List[float]] = defaultdict(list)

    def check_rate_limit(self, request: Request, max_requests: int = 60, window_seconds: int = 60) -> None:
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        key = f"{client_ip}:{path}"

        now = time.time()
        # Clean timestamps older than window
        self.buckets[key] = [t for t in self.buckets[key] if now - t < window_seconds]

        if len(self.buckets[key]) >= max_requests:
            retry_after = int(window_seconds - (now - self.buckets[key][0]))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Please wait {max(1, retry_after)} seconds before retrying.",
                headers={"Retry-After": str(max(1, retry_after))}
            )

        self.buckets[key].append(now)

    def reset(self):
        self.buckets.clear()

rate_limiter = InMemoryRateLimiter()

def rate_limit_auth(request: Request):
    rate_limiter.check_rate_limit(request, max_requests=10, window_seconds=60)

def rate_limit_standard(request: Request):
    rate_limiter.check_rate_limit(request, max_requests=120, window_seconds=60)

