import threading
import time
from typing import Any

from cachetools import LRUCache


class SwrCache:
    """Stale-while-revalidate cache.

    `get(key)` returns `(value, "fresh"|"stale")` if the entry is within hard TTL,
    `None` if absent or past hard TTL. Stale hits are the caller's signal to
    queue a background revalidation; the cached value is still served immediately.
    """

    def __init__(self, *, soft_ttl: float, hard_ttl: float, maxsize: int = 1024):
        self._cache: LRUCache = LRUCache(maxsize=maxsize)
        self._lock = threading.Lock()
        self.soft_ttl = soft_ttl
        self.hard_ttl = hard_ttl

    def get(self, key: Any) -> tuple[Any, str] | None:
        with self._lock:
            entry = self._cache.get(key)
        if entry is None:
            return None
        value, fetched_at = entry
        age = time.time() - fetched_at
        if age > self.hard_ttl:
            with self._lock:
                self._cache.pop(key, None)
            return None
        return value, ("fresh" if age <= self.soft_ttl else "stale")

    def get_with_meta(self, key: Any) -> tuple[Any, float] | None:
        """Like `get`, but exposes the absolute `fetched_at` timestamp.

        Used by the poll endpoint to decide whether the cache entry is newer
        than a given ticket — independent of soft/hard TTL state.
        """
        with self._lock:
            entry = self._cache.get(key)
        if entry is None:
            return None
        value, fetched_at = entry
        age = time.time() - fetched_at
        if age > self.hard_ttl:
            with self._lock:
                self._cache.pop(key, None)
            return None
        return value, fetched_at

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._cache[key] = (value, time.time())

    def __contains__(self, key: Any) -> bool:
        return self.get(key) is not None

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
