"""Rate limiter for login and sensitive endpoints.

Uses in-memory sliding window. For horizontal scaling, switch to Redis
or DB-backed counters via the same interface.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import NamedTuple


class _Entry(NamedTuple):
    count: int
    window_start: float


class RateLimiter:
    """Thread-safe, in-memory sliding window rate limiter."""

    def __init__(self, *, max_attempts: int = 5, window_seconds: int = 300):
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._store: dict[str, _Entry] = defaultdict(lambda: _Entry(0, time.monotonic()))
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            entry = self._store[key]
            if now - entry.window_start > self._window_seconds:
                self._store[key] = _Entry(1, now)
                return True
            if entry.count >= self._max_attempts:
                return False
            self._store[key] = _Entry(entry.count + 1, entry.window_start)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def remaining(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None or now - entry.window_start > self._window_seconds:
                return self._max_attempts
            return max(0, self._max_attempts - entry.count)


# Singleton for login rate limiting
login_limiter = RateLimiter(max_attempts=5, window_seconds=300)
