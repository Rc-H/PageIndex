"""Sliding-window rate limiter for LLM requests.

Tracks request timestamps in a deque and blocks (sync or async) when the
window is full. The window is 60 seconds by default.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float = 60.0):
        self._max_requests = max_requests
        self._window = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def _purge(self, now: float):
        cutoff = now - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    def wait(self):
        """Block the current thread until a slot is available."""
        while True:
            with self._lock:
                now = time.monotonic()
                self._purge(now)
                if len(self._timestamps) < self._max_requests:
                    self._timestamps.append(now)
                    return
                sleep_until = self._timestamps[0] + self._window
            time.sleep(max(sleep_until - time.monotonic(), 0.05))

    async def wait_async(self):
        """Await until a slot is available (non-blocking for the event loop)."""
        while True:
            with self._lock:
                now = time.monotonic()
                self._purge(now)
                if len(self._timestamps) < self._max_requests:
                    self._timestamps.append(now)
                    return
                sleep_until = self._timestamps[0] + self._window
            await asyncio.sleep(max(sleep_until - time.monotonic(), 0.05))


_global_limiter: RateLimiter | None = None
_init_lock = threading.Lock()


def get_rate_limiter() -> RateLimiter:
    global _global_limiter
    if _global_limiter is None:
        with _init_lock:
            if _global_limiter is None:
                from pageindex.infrastructure.settings import load_settings
                rpm = load_settings().service.llm_max_requests_per_minute
                _global_limiter = RateLimiter(max_requests=rpm)
    return _global_limiter
