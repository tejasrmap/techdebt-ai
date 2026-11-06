import time
import threading
from typing import Any, Optional, Dict, Tuple

class CacheService:
    """
    High-performance thread-safe in-memory TTL cache with pattern invalidation
    and operational hit/miss telemetry for TechDebt AI v3.0.0.
    """
    _lock = threading.Lock()
    _store: Dict[str, Tuple[Any, float]] = {}  # key -> (value, expire_at)
    _hits: int = 0
    _misses: int = 0

    @classmethod
    def get(cls, key: str) -> Optional[Any]:
        """Retrieve item from cache if present and not expired."""
        now = time.time()
        with cls._lock:
            item = cls._store.get(key)
            if item is None:
                cls._misses += 1
                return None
            val, expire_at = item
            if expire_at < now:
                del cls._store[key]
                cls._misses += 1
                return None
            cls._hits += 1
            return val

    @classmethod
    def set(cls, key: str, value: Any, ttl_seconds: int = 300):
        """Store item in cache with expiration in seconds."""
        expire_at = time.time() + ttl_seconds
        with cls._lock:
            # Enforce max cache size limit (5,000 entries) with basic eviction
            if len(cls._store) > 5000:
                # Evict oldest 500 items
                old_keys = list(cls._store.keys())[:500]
                for k in old_keys:
                    cls._store.pop(k, None)
            cls._store[key] = (value, expire_at)

    @classmethod
    def delete(cls, key: str) -> bool:
        """Delete specific key from cache."""
        with cls._lock:
            return cls._store.pop(key, None) is not None

    @classmethod
    def invalidate_prefix(cls, prefix: str) -> int:
        """Invalidate all keys matching the prefix (e.g. 'dash_org_123_')."""
        with cls._lock:
            matching = [k for k in cls._store.keys() if k.startswith(prefix)]
            for k in matching:
                cls._store.pop(k, None)
            return len(matching)

    @classmethod
    def clear(cls):
        """Completely purge cache."""
        with cls._lock:
            cls._store.clear()

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Retrieve cache performance statistics."""
        with cls._lock:
            total = cls._hits + cls._misses
            hit_ratio = round((cls._hits / total) * 100.0, 2) if total > 0 else 0.0
            return {
                "items_count": len(cls._store),
                "hits": cls._hits,
                "misses": cls._misses,
                "total_requests": total,
                "hit_ratio_percent": hit_ratio
            }
