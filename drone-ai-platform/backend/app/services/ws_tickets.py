from __future__ import annotations

import asyncio
import hashlib
import secrets
import time


class WebSocketTicketStore:
    """One-use, short-lived credentials so long-lived JWTs never appear in WebSocket URLs."""

    def __init__(self, ttl_seconds: int = 45) -> None:
        self.ttl_seconds = ttl_seconds
        self._tickets: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    async def issue(self, user_id: str) -> str:
        raw_ticket = secrets.token_urlsafe(32)
        key = hashlib.sha256(raw_ticket.encode("utf-8")).hexdigest()
        now = time.monotonic()
        async with self._lock:
            self._tickets = {item: value for item, value in self._tickets.items() if value[1] > now}
            self._tickets[key] = (user_id, now + self.ttl_seconds)
        return raw_ticket

    async def consume(self, raw_ticket: str) -> str | None:
        key = hashlib.sha256(raw_ticket.encode("utf-8")).hexdigest()
        async with self._lock:
            value = self._tickets.pop(key, None)
        if value is None or value[1] <= time.monotonic():
            return None
        return value[0]
