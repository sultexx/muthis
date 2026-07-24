# tests/test_net_session_policy.py
"""RateLimiter + SessionCache (DEC-17) — the per-domain throttle and the
RAM-only session LRU. Pure: an injected clock/sleep drives the limiter
deterministically; the cache is plain memory. No network."""

from __future__ import annotations

import asyncio

from muthis.broker.net.session_policy import RateLimiter, SessionCache


def _sleep_recorder(sink):
    async def sleep(seconds):
        sink.append(seconds)

    return sleep


def test_rate_limiter_first_call_does_not_wait():
    slept: list[float] = []
    limiter = RateLimiter(min_interval_s=1.0, now=lambda: 100.0, sleep=_sleep_recorder(slept))
    asyncio.run(limiter.acquire("a.com"))
    assert slept == []


def test_rate_limiter_second_call_within_interval_throttles():
    slept: list[float] = []
    clock = {"t": 100.0}
    limiter = RateLimiter(min_interval_s=2.0, now=lambda: clock["t"], sleep=_sleep_recorder(slept))

    async def go():
        await limiter.acquire("a.com")   # t=100.0 -> no wait, last=100.0
        clock["t"] = 100.5               # 0.5 s later
        await limiter.acquire("a.com")   # needs 2.0 -> waits the remaining 1.5

    asyncio.run(go())
    assert len(slept) == 1 and abs(slept[0] - 1.5) < 1e-9


def test_rate_limiter_is_per_domain():
    slept: list[float] = []
    limiter = RateLimiter(min_interval_s=5.0, now=lambda: 100.0, sleep=_sleep_recorder(slept))

    async def go():
        await limiter.acquire("a.com")
        await limiter.acquire("b.com")   # a different domain never waits on a's clock

    asyncio.run(go())
    assert slept == []


def test_session_cache_get_and_put():
    cache: SessionCache[str] = SessionCache(max_entries=3)
    assert cache.get("x") is None
    cache.put("x", "1")
    assert cache.get("x") == "1"


def test_session_cache_evicts_least_recently_used():
    cache: SessionCache[int] = SessionCache(max_entries=2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)  # "a" is evicted
    assert cache.get("a") is None and cache.get("b") == 2 and cache.get("c") == 3


def test_session_cache_get_refreshes_recency():
    cache: SessionCache[int] = SessionCache(max_entries=2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1  # touch "a" -> now most recent
    cache.put("c", 3)           # "b" is evicted, not "a"
    assert cache.get("b") is None and cache.get("a") == 1 and cache.get("c") == 3


def test_session_cache_default_capacity_is_50():
    cache: SessionCache[int] = SessionCache()
    for i in range(60):
        cache.put(f"k{i}", i)
    assert len(cache) == 50
    assert cache.get("k9") is None      # the first 10 were evicted
    assert cache.get("k10") == 10 and cache.get("k59") == 59
