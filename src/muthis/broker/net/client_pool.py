# src/muthis/broker/net/client_pool.py
"""
ClientRegistry — ONE httpx client per HOSTNAME, so a TLS connection can never be
reused across hosts (DEC-42, closing a certificate-verification gap in DEC-17).

THE DEFECT, measured at T7 (2026-07-29) while building DEC-25's SNI negative.
The fetcher connects to a PINNED IP, so every request's httpcore origin is
`(scheme, <ip>, port)`. httpcore pools connections by ORIGIN and by nothing else
— `AsyncHTTPConnection.can_handle_request(origin)` compares `origin ==
self._origin` and never looks at the request's `sni_hostname`. Two DIFFERENT
hostnames resolving to ONE address — ordinary on any CDN — therefore SHARED a
pooled connection whose certificate had been verified for whichever host was
fetched FIRST. Measured on `docs.python.org`: a request carrying a deliberately
WRONG SNI answered 200 in 109 ms on a warm client (no handshake at all), while
the identical request on a fresh client is refused with
CERTIFICATE_VERIFY_FAILED.

WHAT WAS NEVER AT RISK: the SSRF guarantee. Every hop is still resolved once,
validated as an IP object and pinned by `address_guard`, before and after this
change. What did not survive connection reuse was the narrower guarantee that
the certificate was verified for the host actually being READ.

WHY A CLIENT PER HOSTNAME — the three alternatives, all measured, all rejected:

  * KEYING THE POOL BY HOSTNAME is NOT AVAILABLE. `can_handle_request` takes an
    origin and compares it whole; neither httpx 0.28.1 nor httpcore 1.0.9 exposes
    a hook that could add the hostname to that key. Checked in the installed
    source, not in the documentation.

  * ONE CLIENT PER FETCH leaves the WORST case open. A redirect from host A to
    host B inside a single `fetch_readable`, both on one IP, still shares that
    operation's client — and under DEC-15 the redirect target is chosen by
    TAINTED content, so the attacker-controlled path is precisely the one it
    fails to close. Scoping per REQUEST instead closes it, at strictly worse cost
    than the option below and with no better guarantee.

  * DISABLING KEEPALIVE closes the gap (measured: wrong SNI → ConnectError) but
    rests the property on a CONFIGURATION flag — an upgrade, a default shift or a
    future tuning commit reopens it silently. That would replace "the protection
    holds because connections happen not to be reused" with "…because a limit is
    set to zero": the same argument one layer up. Enforcement by CONSTRUCTION is
    this project's standard, and every ruling in this milestone turned on who
    owns the fact (DEC-14, DEC-15, DEC-20/36, DEC-34). A connection that lives
    inside a single-hostname client cannot be handed to another host at all —
    the reuse is UNREPRESENTABLE, not merely switched off.

  * A HOSTNAME ORIGIN PLUS A PINNING `network_backend` is the architecturally
    cleanest shape, and it does work — probed live through a hand-built httpx
    transport over `httpcore.AsyncConnectionPool(network_backend=…)`. It is
    REJECTED, and the reason is recorded HERE because a future reader will see it
    as the obvious refactor and must find the argument before starting:
    `connect_tcp` receives the HOSTNAME and no per-request data, so the backend
    must either RESOLVE AGAIN — reopening the DNS-rebinding window that
    `validate_and_pin` exists to close — or receive the validated address through
    shared mutable state that is only safe while nothing runs concurrently, which
    is a circumstance rather than a guarantee. Making it genuinely correct means
    moving resolve-and-validate INTO the backend, where a failure can only raise
    and the never-raise Arabic-note discipline (Law 11) needs a translation
    layer. That trades a PROVEN guarantee (SSRF) against an unproven redesign in
    order to fix a weaker one. If it is ever revisited, it is a milestone of its
    own, not a refactor.

THE COST IS NEARLY NOTHING, because the pooling that actually pays is INSIDE one
host: robots.txt, the document and every redirect hop of one fetch share a
hostname, and a second fetch of the same host reuses its connection exactly as
before (measured: two same-host fetches = 1 TCP connect, unchanged by this
module). Only CROSS-HOST reuse is lost, which is the thing being removed on
purpose. A NEW host costs one handshake — 181.9 ms median, 1.82% of the DEC-22
10 s total budget — which it already paid before.

BOUNDED, because a per-hostname registry is otherwise a memory-growth path over a
long session. The LRU is the `SessionCache` shape (session_policy.py) with one
addition that matters: an evicted client is CLOSED, never merely dropped, so an
eviction can never leak a socket. RAM-only, no persistence, dies with the
session.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Callable, Optional

import httpx

from .transport import TIMEOUT_S, USER_AGENT

logger = logging.getLogger("muthis.broker.net")

# How many hostnames keep a live client. The per-turn fetch cap is 3 (DEC-22),
# so a single turn can touch at most 3 hosts; 8 leaves room for a few turns of
# history without ever becoming a growth path.
DEFAULT_MAX_CLIENTS = 8

# The seam is a FACTORY, not a client, and that is load-bearing: a caller cannot
# express "one shared client for every host" without deliberately writing a
# factory that returns the same object. Passing a single client — the old shape —
# is exactly how this gap would come back.
ClientFactory = Callable[[], httpx.AsyncClient]


def default_client_factory() -> httpx.AsyncClient:
    """One client, SEPARATE from the key-bearing API client (DEC-17, the Clicky
    lesson). Zero credentials: `trust_env=False` kills proxy / NETRC / host env
    and no cookie is ever set; `follow_redirects=False` so the transport
    re-validates every hop itself."""
    return httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(TIMEOUT_S),
        headers={"User-Agent": USER_AGENT},
    )


class ClientRegistry:
    """Hostname → client, bounded and LRU-evicting. `acquire` is the entire
    surface the transport uses; `aclose` belongs to the composition root."""

    def __init__(
        self,
        *,
        factory: Optional[ClientFactory] = None,
        max_clients: int = DEFAULT_MAX_CLIENTS,
    ) -> None:
        self._factory = factory or default_client_factory
        self._max = max(1, int(max_clients))
        self._clients: "OrderedDict[str, httpx.AsyncClient]" = OrderedDict()

    async def acquire(self, hostname: str) -> httpx.AsyncClient:
        """The client that serves THIS hostname, and no other.

        The whole guarantee lives in this method: a client is created per key and
        never shared, so the connection pool inside it only ever carries requests
        for one host. Nothing downstream has to compare anything.

        The key is lower-cased and stripped because `address_guard` already
        lower-cases what it validates (`urlsplit().hostname`); normalising again
        here means two spellings of one host can never split into two clients and
        quietly double the handshakes.

        ASYNC because eviction CLOSES the evicted client, and closing is a
        coroutine. A synchronous version could only drop the reference, which is
        the socket leak this bound exists to prevent."""
        key = (hostname or "").strip().lower()
        existing = self._clients.get(key)
        if existing is not None:
            self._clients.move_to_end(key)
            return existing
        client = self._factory()
        self._clients[key] = client
        while len(self._clients) > self._max:
            _evicted_host, evicted = self._clients.popitem(last=False)
            await self._close(evicted)
        return client

    async def aclose(self) -> None:
        """Release every client. Owned by `HardenedFetcher`, which is owned by
        the composition root (the `agent.aclose()` precedent). The registry is
        emptied FIRST so a close that hangs cannot leave a half-closed client
        reachable by a later `acquire`."""
        clients = list(self._clients.values())
        self._clients.clear()
        for client in clients:
            await self._close(client)

    def hostnames(self) -> "tuple[str, ...]":
        """Live hostnames, least-recently-used first — observability and the
        eviction tests. Never the URLs (DEC-20/DEC-28: a path or query can carry
        the user's private question; a hostname cannot)."""
        return tuple(self._clients)

    def __len__(self) -> int:
        return len(self._clients)

    @staticmethod
    async def _close(client: httpx.AsyncClient) -> None:
        """Closing must never raise into a turn (Law 11) — a client that refuses
        to shut down is a logged English line, not a dead turn."""
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001 — teardown is never worth a turn
            logger.warning("[net] closing a pooled client raised — ignored")


__all__ = [
    "ClientFactory",
    "ClientRegistry",
    "DEFAULT_MAX_CLIENTS",
    "default_client_factory",
]
