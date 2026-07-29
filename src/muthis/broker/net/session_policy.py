# src/muthis/broker/net/session_policy.py
"""
Session policy for the hardened fetcher (DEC-17): a per-domain rate limiter and
a RAM-only LRU page cache. Both are per-SESSION state — built with the fetcher,
they die with it (nothing is persisted). They live apart from the SSRF fetch
loop so `fetcher.py` stays a single responsibility under the ≤300-line law, and
because neither needs the network or a fetcher callback they are trivially
testable with an injected clock / sleep. Pure stdlib.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Awaitable, Callable, Generic, Optional, TypeVar

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]

DEFAULT_MIN_INTERVAL_S = 1.0
DEFAULT_CACHE_SIZE = 50

T = TypeVar("T")


class RateLimiter:
    """Per-domain minimum interval. THROTTLES (awaits the remainder) rather
    than refusing — a slow-down, never a lost fetch. `now`/`sleep` are injected
    so tests drive it deterministically without a real clock."""

    def __init__(
        self,
        *,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
        now: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._min = min_interval_s
        self._now = now
        self._sleep = sleep
        self._last: dict[str, float] = {}

    async def acquire(self, domain: str) -> None:
        last = self._last.get(domain)
        now = self._now()
        if last is not None:
            wait = self._min - (now - last)
            if wait > 0:
                await self._sleep(wait)
                now = self._now()
        self._last[domain] = now


class SessionCache(Generic[T]):
    """A bounded RAM-only LRU (default 50 entries). Dies with the session
    (never persisted). It returns stored values AS-IS and does NOT touch their
    taint status — taint is raised centrally at the router (DEC-14) on EVERY
    result, cached or fresh, so a cached page re-enters the same wrapping (the
    cache never launders taint)."""

    def __init__(self, *, max_entries: int = DEFAULT_CACHE_SIZE) -> None:
        self._max = max_entries
        self._store: "OrderedDict[str, T]" = OrderedDict()

    def get(self, key: str) -> Optional[T]:
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def put(self, key: str, value: T) -> None:
        self._store[key] = value
        self._store.move_to_end(key)
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def __len__(self) -> int:
        return len(self._store)


__all__ = [
    "RateLimiter",
    "SessionCache",
    "Clock",
    "Sleep",
    "DEFAULT_MIN_INTERVAL_S",
    "DEFAULT_CACHE_SIZE",
]
