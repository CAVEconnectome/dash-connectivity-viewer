from cachetools import TTLCache

from flask import current_app


class _LazyTTLCache:
    def __init__(self, ttl_config_key: str, maxsize: int = 1024):
        self.ttl_config_key = ttl_config_key
        self.maxsize = maxsize
        self._cache: TTLCache | None = None

    def _resolve(self) -> TTLCache:
        if self._cache is None:
            ttl = current_app.config[self.ttl_config_key]
            self._cache = TTLCache(maxsize=self.maxsize, ttl=ttl)
        return self._cache

    def get(self, key, default=None):
        return self._resolve().get(key, default)

    def __contains__(self, key) -> bool:
        return key in self._resolve()

    def __getitem__(self, key):
        return self._resolve()[key]

    def __setitem__(self, key, value) -> None:
        self._resolve()[key] = value

    def pop(self, key, default=None):
        return self._resolve().pop(key, default)


query_cache = _LazyTTLCache("CACHE_QUERY_TTL_SECONDS", maxsize=4096)
table_meta_cache = _LazyTTLCache("CACHE_TABLE_META_TTL_SECONDS", maxsize=512)
# Universe of distinct string values per (ds, mat_version, table). One entry
# holds the entire `get_unique_string_values()` dict for a table; per-column
# slicing happens at the call site. Keyed by (ds, mat_version, table) so a
# single CAVE call answers every column on the table for free.
unique_values_cache = _LazyTTLCache("CACHE_UNIQUE_VALUES_TTL_SECONDS", maxsize=512)
