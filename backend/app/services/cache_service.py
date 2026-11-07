"""
TechDebt AI v3.1.0 — Cache Service with true OrderedDict LRU eviction and per-item TTL.
"""

import time
import threading
from collections import OrderedDict
from typing import Any, Optional, Dict, Tuple


class CacheService:
    """
    High-performance thread-safe in-memory TTL cache with exact OrderedDict LRU eviction,
    pattern invalidation, and operational hit/miss telemetry for TechDebt AI v3.1.0.
    """
    _lock = threading.Lock()
    _store: OrderedDict[str, Tuple[Any, float]] = OrderedDict()  # key -> (value, expire_at)
    _max_entries: int = 5000
    _hits: int = 0
    _misses: int = 0
    _evictions: int = 0

    @classmethod
    def get(cls, key: str) -> Optional[Any]:
        """Retrieve item from cache if present and not expired, refreshing LRU position."""
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
            # Move to end (most recently used)
            cls._store.move_to_end(key)
            cls._hits += 1
            return val

    @classmethod
    def set(cls, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Store item in cache with expiration in seconds and LRU enforcement."""
        expire_at = time.time() + ttl_seconds
        with cls._lock:
            if key in cls._store:
                cls._store[key] = (value, expire_at)
                cls._store.move_to_end(key)
                return

            # If capacity exceeded, evict least recently used (first item in OrderedDict)
            while len(cls._store) >= cls._max_entries:
                cls._store.popitem(last=False)
                cls._evictions += 1

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
    def clear(cls) -> None:
        """Completely purge cache and reset counters."""
        with cls._lock:
            cls._store.clear()
            cls._hits = 0
            cls._misses = 0
            cls._evictions = 0

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Retrieve cache performance statistics."""
        with cls._lock:
            total = cls._hits + cls._misses
            hit_ratio = round((cls._hits / total) * 100.0, 2) if total > 0 else 0.0
            return {
                "items_count": len(cls._store),
                "max_entries": cls._max_entries,
                "hits": cls._hits,
                "misses": cls._misses,
                "evictions": cls._evictions,
                "total_requests": total,
                "hit_ratio_percent": hit_ratio
            }
