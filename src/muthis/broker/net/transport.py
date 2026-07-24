# src/muthis/broker/net/transport.py
"""
PinnedTransport — the WIRE layer of the hardened fetcher (DEC-17): given a URL,
get validated bytes over the wire. It owns the SSRF re-validation PER HOP
(address_guard), the MANUAL redirect loop (follow_redirects=False, 5-hop cap),
and the 2 MB raw cap. It holds NO policy — robots / content-type / cache / the
total budget all live in the orchestrator (fetcher.py). Reused verbatim for the
document fetch AND the robots.txt fetch, so it must not recurse or over-filter.

Split out under the ≤300-line law (DEC-23) so a future T7 fix to either layer
has room; `fetcher.py` re-exports these names so importers are unaffected.

NEVER raises: every failure is a short Arabic note (Law 11). NEVER logs content:
domain + status + size, English only.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Union
from urllib.parse import urljoin, urlsplit

import httpx

from .address_guard import PinnedRequest, Resolver, validate_and_pin

logger = logging.getLogger("muthis.broker.net")

# An honest, self-identifying agent (never a browser impersonation).
USER_AGENT_TOKEN = "MuthisBot"
USER_AGENT = f"{USER_AGENT_TOKEN}/1.0 (+https://muthis.local/bot)"

MAX_BYTES = 2_000_000       # §3.3 raw cap
TIMEOUT_S = 10.0            # §3.3 per-request wall (also the DEC-22 total budget)
MAX_REDIRECTS = 5          # §3.3 hop cap (5 redirects followed, the 6th refused)
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# ─── Transport-layer Arabic notes (policy notes live in fetcher.py) ───────────
TIMEOUT_AR = "الموقع بطيء وانتهت المهلة — افتحه على شاشتك وأنا أقرأ لك منه."
NETWORK_ERROR_AR = "ما قدرت أوصل للموقع. تأكد من الرابط والاتصال، أو افتحه على شاشتك."
TOO_LARGE_AR = "محتوى الرابط أكبر من الحد المسموح (٢ ميغابايت). جرّب صفحة أصغر أو افتحه على شاشتك."
TOO_MANY_REDIRECTS_AR = "الرابط فيه إعادة توجيه كثيرة. جرّب الرابط النهائي مباشرة."


@dataclass(frozen=True)
class _Raw:
    """The transport-layer result of one validated fetch (post-redirects)."""

    status: int
    content_type: str
    body: bytes
    final_url: str
    domain: str


class PinnedTransport:
    """The wire layer over an injected httpx client + resolver."""

    def __init__(self, client: httpx.AsyncClient, resolver: Resolver) -> None:
        self._client = client
        self._resolver = resolver

    async def fetch_raw(self, url: str) -> Union[_Raw, str]:
        """Validate → pin → issue → follow redirects MANUALLY (each hop
        re-validated IN FULL, ≤5) → cap at 2 MB. Returns _Raw or an Arabic
        note."""
        current = url
        for _hop in range(MAX_REDIRECTS + 1):
            pinned, note = await asyncio.to_thread(
                validate_and_pin, current, resolver=self._resolver
            )
            if note is not None:
                return note
            assert pinned is not None
            resp = await self._issue(pinned)
            if isinstance(resp, str):
                return resp
            try:
                if resp.status_code in _REDIRECT_STATUSES:
                    location = resp.headers.get("location")
                    if not location:
                        return NETWORK_ERROR_AR
                    current = urljoin(current, location)
                    continue
                body = await self._read_capped(resp)
                if isinstance(body, str):
                    return body
                ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                return _Raw(
                    status=resp.status_code, content_type=ctype, body=body,
                    final_url=current, domain=pinned.hostname,
                )
            finally:
                await resp.aclose()
        logger.info("[fetch] %s too-many-redirects", urlsplit(url).hostname or "")
        return TOO_MANY_REDIRECTS_AR

    async def _issue(self, pinned: PinnedRequest) -> Union[httpx.Response, str]:
        """Issue exactly the pinned request (connect to the IP, Host + SNI carry
        the hostname). Streamed so the body cap runs incrementally. httpx errors
        become Arabic notes — never a raise."""
        headers = {"Host": pinned.host_header, "User-Agent": USER_AGENT}
        extensions = {"sni_hostname": pinned.sni_hostname} if pinned.sni_hostname else {}
        try:
            req = self._client.build_request(
                "GET", pinned.pinned_url, headers=headers, extensions=extensions
            )
            return await self._client.send(req, stream=True)
        except httpx.TimeoutException:
            logger.info("[fetch] %s timeout", pinned.hostname)
            return TIMEOUT_AR
        except httpx.HTTPError as exc:
            logger.info("[fetch] %s transport-error (%s)", pinned.hostname, type(exc).__name__)
            return NETWORK_ERROR_AR

    async def _read_capped(self, resp: httpx.Response) -> Union[bytes, str]:
        """Enforce the 2 MB raw cap: refuse early on an honest Content-Length,
        and enforce again while streaming (a lying / absent length can't slip
        past). Returns the bytes or the too-large / network Arabic note."""
        clen = resp.headers.get("content-length")
        if clen and clen.isdigit() and int(clen) > MAX_BYTES:
            return TOO_LARGE_AR
        chunks = bytearray()
        try:
            async for chunk in resp.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > MAX_BYTES:
                    return TOO_LARGE_AR
        except httpx.TimeoutException:
            return TIMEOUT_AR
        except httpx.HTTPError:
            return NETWORK_ERROR_AR
        return bytes(chunks)


__all__ = [
    "PinnedTransport", "_Raw",
    "USER_AGENT", "USER_AGENT_TOKEN", "MAX_BYTES", "TIMEOUT_S", "MAX_REDIRECTS",
    "TIMEOUT_AR", "NETWORK_ERROR_AR", "TOO_LARGE_AR", "TOO_MANY_REDIRECTS_AR",
]
