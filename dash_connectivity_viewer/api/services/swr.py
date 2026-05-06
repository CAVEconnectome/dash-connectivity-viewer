import logging
import threading
import time
from typing import Any

from cachetools import LRUCache

from ..caches import CacheSerializer, _DEFAULT_SERIALIZER


logger = logging.getLogger("dcv.cache")


class SwrCache:
    """Stale-while-revalidate cache.

    `get(key)` returns `(value, "fresh"|"stale")` if the entry is within hard TTL,
    `None` if absent or past hard TTL. Stale hits are the caller's signal to
    queue a background revalidation; the cached value is still served immediately.

    Like `_LazyTTLCache`, accepts an optional `CacheSerializer`. The default
    is the process-wide one (identity unless `DCV_CACHE_SERIALIZE=pickle`),
    so the SWR cache is also ready to swap to Redis without touching call
    sites — same two-piece migration as the TTL caches.
    """

    def __init__(
        self,
        *,
        soft_ttl: float,
        hard_ttl: float,
        maxsize: int = 1024,
        serializer: CacheSerializer | None = None,
    ):
        self._cache: LRUCache = LRUCache(maxsize=maxsize)
        self._lock = threading.Lock()
        self.soft_ttl = soft_ttl
        self.hard_ttl = hard_ttl
        self.serializer: CacheSerializer = serializer or _DEFAULT_SERIALIZER

    def _safe_loads(self, key: Any, stored_value: Any) -> tuple[bool, Any]:
        """Try to deserialize. Returns `(ok, value)` — on failure, evicts
        the poisoned entry and logs. Used by both read paths so a
        deploy-compat break (pickle protocol shift, class moved, major
        version bump on a deserialized lib) degrades to a cache miss
        rather than 500-ing every request.
        """
        try:
            return True, self.serializer.loads(stored_value)
        except Exception as exc:
            with self._lock:
                self._cache.pop(key, None)
            logger.warning(
                "swr_deserialize_failed key=%r serializer=%s error=%s: %s",
                key, type(self.serializer).__name__, type(exc).__name__, exc,
            )
            return False, None

    def get(self, key: Any) -> tuple[Any, str] | None:
        with self._lock:
            entry = self._cache.get(key)
        if entry is None:
            return None
        stored_value, fetched_at = entry
        age = time.time() - fetched_at
        if age > self.hard_ttl:
            with self._lock:
                self._cache.pop(key, None)
            return None
        ok, value = self._safe_loads(key, stored_value)
        if not ok:
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
        stored_value, fetched_at = entry
        age = time.time() - fetched_at
        if age > self.hard_ttl:
            with self._lock:
                self._cache.pop(key, None)
            return None
        ok, value = self._safe_loads(key, stored_value)
        if not ok:
            return None
        return value, fetched_at

    def get_full(self, key: Any) -> tuple[Any, str, float] | None:
        """Combined `get` + `get_with_meta`: returns `(value, freshness,
        fetched_at)` or None. Used by the live-mode delta path in
        `lookup_decorations`, which needs all three: freshness to decide
        whether to schedule a background refresh, and fetched_at to
        compute the get_delta_roots time window for targeted fill-in.
        Saves a second cache read.
        """
        with self._lock:
            entry = self._cache.get(key)
        if entry is None:
            return None
        stored_value, fetched_at = entry
        age = time.time() - fetched_at
        if age > self.hard_ttl:
            with self._lock:
                self._cache.pop(key, None)
            return None
        ok, value = self._safe_loads(key, stored_value)
        if not ok:
            return None
        return value, ("fresh" if age <= self.soft_ttl else "stale"), fetched_at

    def set(self, key: Any, value: Any) -> None:
        stored = self.serializer.dumps(value)
        with self._lock:
            self._cache[key] = (stored, time.time())

    def __contains__(self, key: Any) -> bool:
        return self.get(key) is not None

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
