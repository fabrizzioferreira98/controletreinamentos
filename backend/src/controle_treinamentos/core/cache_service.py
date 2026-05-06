import threading
from datetime import datetime
from typing import Any, Optional


class CacheService:
    """
    Centralized, thread-safe memory cache.
    Eliminates dependency on global module state and allows easy replacement
    with an external cache backend (like Redis) in the future.
    """

    def __init__(self):
        self._panel_cache: dict[str, Any] = {}
        self._nav_cache: Optional[Any] = None
        self._dashboard_cache: Optional[Any] = None
        self._lock = threading.RLock()

    def get_panel_cache(self, cache_key: str, default_ttl_seconds: int = 300) -> Optional[Any]:
        with self._lock:
            cached = self._panel_cache.get(cache_key)
            if not cached:
                return None

            # Unpack regardless of format (backwards compatibility with 2 or 3 element tuples)
            if len(cached) == 2:
                created_at, payload = cached
                ttl_seconds = default_ttl_seconds
            else:
                created_at, payload, ttl_seconds = cached

            if (datetime.now() - created_at).total_seconds() > ttl_seconds:
                self._panel_cache.pop(cache_key, None)
                return None
            return payload

    def set_panel_cache(self, cache_key: str, payload: Any, ttl_seconds: int = 300):
        with self._lock:
            self._panel_cache[cache_key] = (datetime.now(), payload, max(1, int(ttl_seconds)))

    def clear_navigation_cache(self):
        with self._lock:
            self._nav_cache = None

    def clear_dashboard_cache(self):
        with self._lock:
            self._dashboard_cache = None

    def clear_panel_cache(self, prefix: Optional[str] = None, *, invalidate_global: bool = True):
        with self._lock:
            if not prefix:
                self._panel_cache.clear()
            else:
                keys = [key for key in list(self._panel_cache.keys()) if key.startswith(prefix)]
                for key in keys:
                    self._panel_cache.pop(key, None)

            if invalidate_global:
                # Guarantee immediate consistency for counters and cards after broad mutations
                self.clear_navigation_cache()
                self.clear_dashboard_cache()

    def clear_catalog_options_cache(self):
        # Option-only changes do not require invalidating dashboard/nav snapshots.
        self.clear_panel_cache("options:equipamentos:", invalidate_global=False)
        self.clear_panel_cache("options:tipos_treinamento:", invalidate_global=False)

    def get_dashboard_cache(self, ttl_seconds: int = 600) -> Optional[Any]:
        with self._lock:
            cached = self._dashboard_cache
            if not cached:
                return None
            created_at, payload = cached
            if (datetime.now() - created_at).total_seconds() > ttl_seconds:
                return None
            return payload

    def set_dashboard_cache(self, payload: Any):
        with self._lock:
            self._dashboard_cache = (datetime.now(), payload)

    def get_navigation_cache(self, ttl_seconds: int = 300) -> Optional[Any]:
        with self._lock:
            cached = self._nav_cache
            if not cached:
                return None
            created_at, payload = cached
            if (datetime.now() - created_at).total_seconds() > ttl_seconds:
                return None
            return payload

    def set_navigation_cache(self, payload: Any):
        with self._lock:
            self._nav_cache = (datetime.now(), payload)


# Singleton instance until fully dependency-injected by Application Factory
cache_service = CacheService()
