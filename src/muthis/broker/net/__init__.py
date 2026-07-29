# src/muthis/broker/net/__init__.py
"""
The broker-owned hardened fetcher — the embodiment of the `net.fetch`
capability (DEC-17). External plugin code never holds an OS handle: the fetcher
lives HERE, in the broker, and hands back readable content, never a socket.

`address_guard` is the SSRF validator (built + tested first); `fetcher` is the
IP-pinned fetch loop; `session_policy` holds the per-domain rate limiter and the
RAM-only LRU; `client_pool` keeps ONE client per HOSTNAME so a TLS connection is
never reused across hosts (DEC-42).

WIRED SINCE T6 (DEC-24): the composition root builds ONE `HardenedFetcher` and
injects `fetch_readable` into the Broker, which hands a granted plugin
`ctx.net.fetch_readable` — and hands a denied plugin NOTHING. The contract is
binary (M1-4): granted → the seam is PRESENT, denied → ABSENT, no third state
and no refusing stub. A plugin never sees this package.
"""

from __future__ import annotations

from .client_pool import (
    DEFAULT_MAX_CLIENTS,
    ClientFactory,
    ClientRegistry,
    default_client_factory,
)
from .address_guard import (
    BAD_URL_AR,
    BLOCKED_ADDRESS_AR,
    SCHEME_AR,
    UNRESOLVABLE_AR,
    PinnedRequest,
    Resolver,
    ip_block_reason,
    system_resolver,
    validate_and_pin,
)
from .fetcher import (
    ALLOWED_CONTENT_TYPES,
    CONTENT_TYPE_AR,
    EXTRACT_FAILED_AR,
    EXTRACT_TRUNCATED_AR,
    MAX_BYTES,
    MAX_EXTRACT_CHARS,
    MAX_REDIRECTS,
    NETWORK_ERROR_AR,
    PDF_UNSUPPORTED_AR,
    ROBOTS_BLOCKED_AR,
    TIMEOUT_AR,
    TIMEOUT_S,
    TOO_LARGE_AR,
    TOO_MANY_REDIRECTS_AR,
    USER_AGENT,
    USER_AGENT_TOKEN,
    FetchResult,
    HardenedFetcher,
)
from .provenance import MAX_TRACKED_DOMAINS, FetchedDomains
from .session_policy import RateLimiter, SessionCache

__all__ = [
    # validator
    "PinnedRequest",
    "Resolver",
    "ip_block_reason",
    "system_resolver",
    "validate_and_pin",
    "BAD_URL_AR",
    "SCHEME_AR",
    "BLOCKED_ADDRESS_AR",
    "UNRESOLVABLE_AR",
    # fetcher
    "HardenedFetcher",
    "FetchResult",
    "USER_AGENT",
    "USER_AGENT_TOKEN",
    "MAX_BYTES",
    "TIMEOUT_S",
    "MAX_REDIRECTS",
    "ALLOWED_CONTENT_TYPES",
    "MAX_EXTRACT_CHARS",
    "ROBOTS_BLOCKED_AR",
    "PDF_UNSUPPORTED_AR",
    "CONTENT_TYPE_AR",
    "EXTRACT_FAILED_AR",
    "EXTRACT_TRUNCATED_AR",
    "TOO_LARGE_AR",
    "TIMEOUT_AR",
    "NETWORK_ERROR_AR",
    "TOO_MANY_REDIRECTS_AR",
    # provenance (DEC-20: the badge is drawn from THIS, never from plugin text)
    "FetchedDomains",
    "MAX_TRACKED_DOMAINS",
    # session policy
    "RateLimiter",
    "SessionCache",
    # DEC-42: a client per HOSTNAME, so a TLS connection never crosses hosts
    "ClientFactory",
    "ClientRegistry",
    "DEFAULT_MAX_CLIENTS",
    "default_client_factory",
]
