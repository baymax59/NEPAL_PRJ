"""Limit failed logins per computer (client address), on top of the per-account lockout (Step 14.2).

The account lockout (Step 10) stops someone guessing one account's password. This stops one computer
trying a few passwords on many accounts ("password spraying"). Kept in memory: it applies per backend
process and resets when the backend restarts. That suits this setup: one backend behind one web server.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from functools import lru_cache

from app.core.config import get_settings


class FailedLoginLimiter:
    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()  # requests run in several threads

    def _recent(self, key: str) -> deque[float]:
        """This address's failures still inside the window (older ones are dropped)."""
        times = self._failures.get(key, deque())
        cutoff = self.clock() - self.window
        while times and times[0] <= cutoff:
            times.popleft()
        if times:
            self._failures[key] = times
        else:
            self._failures.pop(key, None)  # so the table doesn't grow forever
        return times

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self.limit

    def retry_after(self, key: str) -> int:
        """Seconds until this address may try again."""
        with self._lock:
            times = self._recent(key)
            return math.ceil(times[0] + self.window - self.clock()) if len(times) >= self.limit else 0

    def record_failure(self, key: str) -> None:
        with self._lock:
            times = self._recent(key)
            times.append(self.clock())
            self._failures[key] = times


@lru_cache
def get_login_limiter() -> FailedLoginLimiter:
    """FastAPI dependency: one limiter for the whole backend process (tests replace it)."""
    settings = get_settings()
    return FailedLoginLimiter(settings.max_failed_logins_per_ip, settings.failed_login_window_minutes * 60)
