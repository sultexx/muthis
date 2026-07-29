# tests/test_net_client_pool.py
"""DEC-42 — a TLS connection is never reused across hosts.

THE PROPERTY, stated once so every test below can be read against it: a request
for host B over a connection established for host A either verifies B's
certificate or does not reuse the connection. Under DEC-42 that reduces to
something a no-network test can prove exactly — host A and host B never share a
CLIENT — because a connection lives inside a client's pool and can be handed to
nothing outside it.

WHY THAT REDUCTION IS SOUND, and not a convenient restatement: httpcore pools by
ORIGIN alone (`can_handle_request` compares `origin == self._origin` and never
looks at `sni_hostname`), and the fetcher's origin is the PINNED IP — which is
why two hostnames on one address shared a connection at all. Nothing else in the
stack can move a connection between clients, so separate clients is the whole
guarantee. The LIVE half — that a wrong SNI really is refused at the handshake —
is DEC-25's, proven in `scripts/diag_web_research.py` (B8) with a fresh client
per attempt, because no unit test can perform a real handshake.

THE CONTROL THAT MATTERS: every separation test is paired with an assertion that
the SAME host DOES reuse its client. Without it a registry that simply returned a
brand-new client on every call would pass the separation tests vacuously — the
same trap as an SNI probe that passes because the handshake was skipped.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from muthis.broker.net.client_pool import (
    DEFAULT_MAX_CLIENTS,
    ClientRegistry,
    default_client_factory,
)
from muthis.broker.net.fetcher import HardenedFetcher

# ONE address for BOTH hostnames — the CDN case that produced the defect. If the
# two ever share a client, the second host rides a connection whose certificate
# was verified for the first.
SHARED_IP = "93.184.216.34"
HOST_A = "alpha.example.com"
HOST_B = "beta.example.com"


def _resolver(hostname, port):
    return [SHARED_IP]


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/robots.txt"):
        return httpx.Response(404)          # absent robots → the standard allows
    return httpx.Response(
        200, headers={"content-type": "text/plain; charset=utf-8"},
        content=b"page body for the diagnostic")


class _RecordingFactory:
    """Builds real clients over a mock transport and remembers each one, so a
    test can ask WHICH client served WHICH host."""

    def __init__(self, handler=_handler) -> None:
        self.built: list[httpx.AsyncClient] = []
        self._handler = handler

    def __call__(self) -> httpx.AsyncClient:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(self._handler),
            trust_env=False, follow_redirects=False)
        self.built.append(client)
        return client


# ── the registry's own contract ──────────────────────────────────────────────


def test_same_hostname_reuses_one_client_and_different_hostnames_never_do():
    async def go():
        registry = ClientRegistry(factory=_RecordingFactory())
        try:
            a1 = await registry.acquire(HOST_A)
            a2 = await registry.acquire(HOST_A)
            b1 = await registry.acquire(HOST_B)
            return a1, a2, b1, registry.hostnames()
        finally:
            await registry.aclose()

    a1, a2, b1, hosts = asyncio.run(go())
    # THE CONTROL: without this, "different hosts differ" would pass on a
    # registry that never reused anything at all.
    assert a1 is a2, "the same host must keep ONE client, or pooling is gone"
    assert a1 is not b1, "two hosts sharing a client is the DEC-42 defect"
    assert set(hosts) == {HOST_A, HOST_B}


def test_hostname_keys_are_normalised_so_one_host_is_never_two_clients():
    async def go():
        registry = ClientRegistry(factory=_RecordingFactory())
        try:
            return (await registry.acquire("Alpha.Example.COM"),
                    await registry.acquire("  alpha.example.com "),
                    len(registry))
        finally:
            await registry.aclose()

    first, second, size = asyncio.run(go())
    assert first is second and size == 1


def test_the_registry_is_bounded_and_an_evicted_client_is_CLOSED():
    """An unbounded per-hostname registry is a memory-growth path over a long
    session, and an eviction that merely drops the reference leaks the socket.

    THE CLOSED STATE IS SAMPLED INSIDE the async block, BEFORE `aclose()`. Read
    afterwards it would be True whatever eviction did — `aclose` closes
    everything — so the assertion would pass on a registry that never closed an
    evicted client at all. Measured: written the lazy way, it did."""
    async def go():
        registry = ClientRegistry(factory=_RecordingFactory(), max_clients=2)
        try:
            first = await registry.acquire("one.example.com")
            await registry.acquire("two.example.com")
            await registry.acquire("three.example.com")   # evicts the LRU (one)
            return first.is_closed, len(registry), registry.hostnames()
        finally:
            await registry.aclose()

    evicted_closed, size, hosts = asyncio.run(go())
    assert size == 2, "the bound must hold"
    assert "one.example.com" not in hosts and "three.example.com" in hosts
    assert evicted_closed, "an evicted client MUST be closed, never dropped"


def test_recently_used_hosts_survive_eviction():
    """Same sampling discipline: `keep` must be OPEN at the moment the eviction
    happened, which is only observable before the registry is torn down."""
    async def go():
        registry = ClientRegistry(factory=_RecordingFactory(), max_clients=2)
        try:
            keep = await registry.acquire("keep.example.com")
            await registry.acquire("drop.example.com")
            await registry.acquire("keep.example.com")     # refresh -> now MRU
            await registry.acquire("new.example.com")      # evicts drop, not keep
            return keep.is_closed, registry.hostnames()
        finally:
            await registry.aclose()

    keep_closed, hosts = asyncio.run(go())
    assert "keep.example.com" in hosts and "drop.example.com" not in hosts
    assert not keep_closed, "the most-recently-used host must survive eviction"


def test_aclose_closes_every_client_and_leaves_nothing_reachable():
    async def go():
        factory = _RecordingFactory()
        registry = ClientRegistry(factory=factory)
        for host in ("a.example.com", "b.example.com", "c.example.com"):
            await registry.acquire(host)
        await registry.aclose()
        return factory.built, len(registry), registry.hostnames()

    built, size, hosts = asyncio.run(go())
    assert len(built) == 3 and all(client.is_closed for client in built)
    assert size == 0 and hosts == ()


def test_a_closing_failure_is_logged_not_raised():
    """Law 11: teardown must never be able to kill a turn."""
    class _Stubborn:
        is_closed = False

        async def aclose(self):
            raise RuntimeError("refuses to close")

    async def go():
        registry = ClientRegistry(factory=_Stubborn, max_clients=1)
        await registry.acquire("a.example.com")
        await registry.acquire("b.example.com")   # evicts the stubborn one
        await registry.aclose()
        return len(registry)

    assert asyncio.run(go()) == 0


def test_the_default_factory_client_is_credential_free():
    async def go():
        client = default_client_factory()
        try:
            return client.trust_env, client.follow_redirects
        finally:
            await client.aclose()

    trust_env, follow_redirects = asyncio.run(go())
    assert trust_env is False and follow_redirects is False
    assert DEFAULT_MAX_CLIENTS >= 3   # the per-turn fetch cap must fit


# ── the property, driven through the REAL fetcher ────────────────────────────


def test_two_hostnames_on_ONE_ip_never_share_a_client_through_the_real_fetcher():
    """The defect's exact shape, end to end: both hosts resolve to the SAME
    address, both are fetched, and the two must not have shared a client.

    Driven through `HardenedFetcher.fetch_readable` — not the registry alone —
    so it also proves the transport keys on the VALIDATED hostname rather than on
    the pinned-IP URL it actually issues."""
    served: list[tuple[str, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        # Every request really is issued to the ONE shared IP: this is the
        # same-address case, not two hosts that happened to differ anyway.
        served.append((request.headers.get("host", ""), 0))
        assert request.url.host == SHARED_IP
        return _handler(request)

    async def go():
        factory = _RecordingFactory(handler)
        fetcher = HardenedFetcher(client_factory=factory, resolver=_resolver,
                                  robots_enabled=False)
        try:
            a = await fetcher.fetch_readable(f"https://{HOST_A}/page")
            b = await fetcher.fetch_readable(f"https://{HOST_B}/page")
            again = await fetcher.fetch_readable(f"https://{HOST_A}/other")
            clients = fetcher._clients
            return a, b, again, len(factory.built), sorted(clients.hostnames())
        finally:
            await fetcher.aclose()

    a, b, again, built, hosts = asyncio.run(go())
    assert a.ok and b.ok and again.ok
    assert sorted(hosts) == sorted([HOST_A, HOST_B])
    # ONE client per host, and no more: two hosts -> exactly two clients. The
    # third fetch is HOST_A again and must not have built a third client — that
    # is the control which stops this passing on a never-reuse registry.
    assert built == 2, f"expected one client per host, built {built}"
    assert {host for host, _ in served} == {HOST_A, HOST_B}


def test_a_cross_host_redirect_inside_ONE_fetch_still_switches_client():
    """The case that ruled out per-fetch scoping: under DEC-15 the redirect
    target is chosen by TAINTED content, so a redirect from host A to host B on
    the same address is the attacker-controlled path. It must change clients."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("host") == HOST_A:
            return httpx.Response(302, headers={"location": f"https://{HOST_B}/landed"})
        return _handler(request)

    async def go():
        factory = _RecordingFactory(handler)
        fetcher = HardenedFetcher(client_factory=factory, resolver=_resolver,
                                  robots_enabled=False)
        try:
            result = await fetcher.fetch_readable(f"https://{HOST_A}/start")
            return result, len(factory.built), sorted(fetcher._clients.hostnames())
        finally:
            await fetcher.aclose()

    result, built, hosts = asyncio.run(go())
    assert result.ok and result.domain == HOST_B
    assert built == 2, "the redirect hop must not ride the first host's client"
    assert sorted(hosts) == sorted([HOST_A, HOST_B])


def test_robots_and_the_document_still_share_the_host_client():
    """The pooling that pays is INSIDE one host and must survive: robots.txt and
    the document are the same hostname, so they get the same client. If this ever
    fails, DEC-42 has started costing a handshake it was measured not to cost."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/robots.txt"):
            return httpx.Response(200, headers={"content-type": "text/plain"},
                                  content=b"User-agent: *\nAllow: /\n")
        return _handler(request)

    async def go():
        factory = _RecordingFactory(handler)
        fetcher = HardenedFetcher(client_factory=factory, resolver=_resolver,
                                  robots_enabled=True)
        try:
            result = await fetcher.fetch_readable(f"https://{HOST_A}/page")
            return result, len(factory.built)
        finally:
            await fetcher.aclose()

    result, built = asyncio.run(go())
    assert result.ok
    assert built == 1, "robots + document are one host and must share one client"


def test_the_fetcher_closes_every_client_it_opened():
    async def go():
        factory = _RecordingFactory()
        fetcher = HardenedFetcher(client_factory=factory, resolver=_resolver,
                                  robots_enabled=False)
        await fetcher.fetch_readable(f"https://{HOST_A}/page")
        await fetcher.fetch_readable(f"https://{HOST_B}/page")
        await fetcher.aclose()
        return factory.built

    built = asyncio.run(go())
    assert len(built) == 2 and all(client.is_closed for client in built)


@pytest.mark.parametrize("hostname", ["", "   "])
def test_a_blank_hostname_never_raises(hostname):
    """A fetch must never die on bookkeeping (Law 11); a blank key is simply its
    own bucket."""
    async def go():
        registry = ClientRegistry(factory=_RecordingFactory())
        try:
            return await registry.acquire(hostname)
        finally:
            await registry.aclose()

    assert asyncio.run(go()) is not None
