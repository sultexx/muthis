# src/muthis/broker/net/address_guard.py
"""
Address guard — the SSRF validator that stands in front of the hardened
fetcher (DEC-17). EVERY property of the fetcher depends on this module, so it
is built and tested FIRST.

The single rule: validation operates on IP OBJECTS, never on URL text. A URL's
host is either an IP literal (validated directly) or a name RESOLVED ONCE via
the injected resolver; the RESOLVED address is then validated as an
`ipaddress` object and the fetcher connects to THAT exact IP (pinning), while
the Host header and TLS SNI keep the real hostname so the certificate verifies
against the name — closing DNS rebinding at the root (a validate-then-
connect-by-name flow re-resolves and is exploitable).

String matching is defeated by decimal-encoded addresses (`http://2130706433/`
is `127.0.0.1` — the STRING is not even a valid IP, but the resolver reads it
as loopback) and by IPv4-mapped IPv6 (`::ffff:127.0.0.1`); an `ipaddress`
object is not. We also unwrap IPv4 embedded in 6to4 / Teredo, and block on the
EXPLICIT flags AND `not is_global` — guards by construction, never by a single
library property (DEC-13: "it fails for another reason" is not a defense).

Refusals are short Arabic notes (the FileReader pattern); the English REASON
and the DOMAIN (never the full URL — a query can carry a private search) ride
the logs only. Pure stdlib (ipaddress / socket / urllib.parse); importable in
isolation, no asyncio (the fetcher runs the blocking resolve via to_thread).
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urlsplit

logger = logging.getLogger("muthis.broker.net")

ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}

# ─── Model-facing Arabic refusals (the validation domain) ─────────────────────
# One note per SSRF block — the specific internal range is an English log
# detail, never surfaced to the model (no infoleak about the internal network).
BAD_URL_AR = "الرابط غير صالح. مرّر رابط http أو https كامل."
SCHEME_AR = "أدعم روابط http/https فقط."
BLOCKED_ADDRESS_AR = "هذا الرابط يشير إلى عنوان داخلي أو غير عام، والوصول له ممنوع حمايةً للنظام."
UNRESOLVABLE_AR = "ما قدرت أحدد عنوان هذا الموقع. تأكد من الرابط."

# The resolver seam: (hostname, port) -> a list of IP strings. Production =
# getaddrinfo; tests inject a dict-backed fake. Sync (blocking DNS) — the
# fetcher calls it in a worker thread so the event loop never blocks.
Resolver = Callable[[str, int], "list[str]"]


@dataclass(frozen=True)
class PinnedRequest:
    """A validated, ready-to-issue request. The fetcher connects to
    `connect_ip` while `host_header` + `sni_hostname` carry the real hostname
    (the certificate verifies against the name, not the IP). Nothing else is
    issued — this IS the pin."""

    scheme: str
    hostname: str
    port: int
    connect_ip: str
    host_header: str
    sni_hostname: Optional[str]  # the hostname for https; None for plain http
    pinned_url: str              # scheme://<ip-or-[ipv6]>:port/path?query


def system_resolver(hostname: str, port: int) -> list[str]:
    """The production resolver: ONE getaddrinfo, IPs de-duplicated, order
    preserved. Blocking — the fetcher runs it via asyncio.to_thread."""
    import socket

    infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    ips: list[str] = []
    for info in infos:
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    return ips


def _embedded_ipv4(ip: object) -> Optional[object]:
    """Unwrap an IPv4 address hidden inside an IPv6 one (mapped / 6to4 /
    Teredo) so a loopback/private target cannot smuggle itself in as
    `::ffff:127.0.0.1`, `2002:7f00:1::`, etc. Returns the embedded IPv4Address
    or None."""
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return mapped
    sixtofour = getattr(ip, "sixtofour", None)
    if sixtofour is not None:
        return sixtofour
    teredo = getattr(ip, "teredo", None)
    if teredo is not None:
        return teredo[1]  # (server, client) -> the client node's IPv4
    return None


def ip_block_reason(ip_text: str) -> Optional[str]:
    """The core check on ONE resolved/literal IP. Returns an English REASON
    when the address must be blocked, else None. Belt-and-suspenders: unwrap
    any embedded IPv4 first, then the EXPLICIT flags AND `not is_global`."""
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return f"not an IP address: {ip_text!r}"
    embedded = _embedded_ipv4(ip)
    if embedded is not None:
        reason = ip_block_reason(str(embedded))
        if reason:
            return f"embedded IPv4 {embedded} blocked ({reason})"
    if ip.is_loopback:
        return "loopback"
    if ip.is_private:
        return "private"
    if ip.is_link_local:
        return "link-local (cloud metadata)"
    if ip.is_multicast:
        return "multicast"
    if ip.is_reserved:
        return "reserved"
    if ip.is_unspecified:
        return "unspecified"
    if not ip.is_global:
        return "not globally routable"
    return None


def validate_and_pin(
    url: str, *, resolver: Resolver = system_resolver
) -> "tuple[Optional[PinnedRequest], Optional[str]]":
    """Validate a URL end to end and return (PinnedRequest, None) or
    (None, arabic_note). Order: scheme → host present → resolve ONCE → validate
    EVERY resolved IP → build the pin. Refusing when ANY resolved IP is
    non-global closes the 'resolves to both a public and a private address'
    rebinding trick. Never raises."""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return None, BAD_URL_AR
    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        logger.info("[net] refused scheme %r", scheme)
        return None, SCHEME_AR
    hostname = parts.hostname  # excludes any user:pass@ (creds dropped), lowercased
    if not hostname:
        return None, BAD_URL_AR
    try:
        port = parts.port or _DEFAULT_PORTS[scheme]
    except ValueError:
        return None, BAD_URL_AR  # a non-numeric / out-of-range port

    # An IP literal validates directly; a name is resolved ONCE, then every
    # resolved address is validated as an object.
    try:
        candidates = [str(ipaddress.ip_address(hostname))]
    except ValueError:
        try:
            candidates = resolver(hostname, port)
        except Exception:  # noqa: BLE001 — a DNS failure is a polite refusal, not a crash
            logger.info("[net] resolve failed for %s", hostname)
            return None, UNRESOLVABLE_AR
        if not candidates:
            logger.info("[net] no address for %s", hostname)
            return None, UNRESOLVABLE_AR

    for ip_text in candidates:
        reason = ip_block_reason(ip_text)
        if reason:
            logger.warning("[net] blocked %s -> %s (%s)", hostname, ip_text, reason)
            return None, BLOCKED_ADDRESS_AR

    connect_ip = candidates[0]
    host_part = f"[{connect_ip}]" if ":" in connect_ip else connect_ip
    path_and_query = parts.path or "/"
    if parts.query:
        path_and_query += "?" + parts.query
    pinned_url = f"{scheme}://{host_part}:{port}{path_and_query}"
    # The Host header carries the real name; an IPv6 literal host must be
    # bracketed (RFC 7230), and a non-default port appended.
    host_label = f"[{hostname}]" if ":" in hostname else hostname
    host_header = (
        host_label if port == _DEFAULT_PORTS[scheme] else f"{host_label}:{port}"
    )
    sni_hostname = hostname if scheme == "https" else None
    return (
        PinnedRequest(
            scheme=scheme,
            hostname=hostname,
            port=port,
            connect_ip=connect_ip,
            host_header=host_header,
            sni_hostname=sni_hostname,
            pinned_url=pinned_url,
        ),
        None,
    )


__all__ = [
    "ALLOWED_SCHEMES",
    "PinnedRequest",
    "Resolver",
    "system_resolver",
    "ip_block_reason",
    "validate_and_pin",
    "BAD_URL_AR",
    "SCHEME_AR",
    "BLOCKED_ADDRESS_AR",
    "UNRESOLVABLE_AR",
]
