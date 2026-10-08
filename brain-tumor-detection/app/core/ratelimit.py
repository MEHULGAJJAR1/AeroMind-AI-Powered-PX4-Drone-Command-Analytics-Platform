"""Tiny in-process sliding-window rate limiter.

A single-process limiter is enough for local deployments and single-worker
containers. For multi-worker production deployments put nginx / a gateway in
front, or swap this class for a Redis-backed implementation — the public API
(``allow`` / ``consume``) stays the same.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int
    limit: int
    window: int


class SlidingWindowRateLimiter:
    """Per-key sliding window counter (thread safe)."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = int(max_requests)
        self.window_seconds = max(1, int(window_seconds))
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.max_requests > 0

    def consume(self, key: str, now: float | None = None) -> RateLimitResult:
        """Register a request for ``key`` and report whether it is allowed."""
        if not self.enabled:
            return RateLimitResult(True, -1, 0, self.max_requests, self.window_seconds)

        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds

        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (current - bucket[0])) + 1)
                return RateLimitResult(False, 0, retry_after, self.max_requests, self.window_seconds)

            bucket.append(current)
            remaining = self.max_requests - len(bucket)
            return RateLimitResult(True, remaining, 0, self.max_requests, self.window_seconds)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def prune(self, now: float | None = None) -> None:
        """Drop empty buckets so long-lived processes do not leak memory."""
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            for key in [k for k, bucket in self._events.items() if not bucket or bucket[-1] <= cutoff]:
                self._events.pop(key, None)
