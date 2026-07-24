# src/muthis/broker/net/fetcher.py
"""
HardenedFetcher — the broker-owned embodiment of the net.fetch capability
(DEC-17, V2 Roadmap §3.3). External plugin code never holds a socket; it will
receive `ctx.net.fetch_readable(url)` backed by this object, and web_research
(first party) eats the same dogfood with NO privileged path.

This module is the READABLE ORCHESTRATION layer: cache → robots → rate-limit →
(wire) → content-type → decode → EXTRACT → cap → FetchResult. The wire layer
(SSRF re-validation per hop, manual redirects, the 2 MB cap) lives in
`transport.py` (PinnedTransport); the HTML→text extraction + the ~4k-token cap
live in `extract.py` — both split out under the ≤300-line law (DEC-23) and
re-exported here so importers are unaffected. Address validation is
`address_guard`; robots and the rate-limit/LRU are `robots` / `session_policy`.

Defenses, each a DEC-17 clause: content-type allowlist (html/plain/json), honest
MuthisBot agent, per-domain rate limit, RAM-only session LRU (never launders
taint), robots respected → an Arabic vision-path note, PDF refused honestly;
a SEPARATE long-lived httpx client, trust_env=False, zero cookies/auth (the
Clicky lesson); NEVER raises (Law 11); content is NEVER logged. The whole
operation runs under one TOTAL wall-clock budget (DEC-22) so a tainted slow
redirect chain can never starve the turn.

READABLE EXTRACTION (DEC-18, in extract.py): an HTML body is reduced to readable
prose (markup stripped, NOT injection — the DEC-14 router wrapper is the injection
guard), capped at ~4k tokens; text/plain and JSON pass through as-is. A miss
degrades to a short Arabic note — it NEVER falls back to raw HTML (token-costly +
injection-dense).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from typing import Optional
from urllib.parse import urlsplit

import httpx

from .address_guard import Resolver, system_resolver
from .extract import (  # re-exported below so importers keep working
    EXTRACT_FAILED_AR,
    EXTRACT_TRUNCATED_AR,
    MAX_EXTRACT_CHARS,
    cap_extract,
    extract_html,
)
from .robots import RobotsCache
from .session_policy import RateLimiter, SessionCache
from .transport import (  # re-exported below so importers keep working
    MAX_BYTES,
    MAX_REDIRECTS,
    NETWORK_ERROR_AR,
    TIMEOUT_AR,
    TIMEOUT_S,
    TOO_LARGE_AR,
    TOO_MANY_REDIRECTS_AR,
    USER_AGENT,
    USER_AGENT_TOKEN,
    PinnedTransport,
)

logger = logging.getLogger("muthis.broker.net")

# content-type allowlist (main type only; charset params stripped).
ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {"text/html", "text/plain", "application/json"}
)
_PDF_CONTENT_TYPE = "application/pdf"

# ─── Policy-layer Arabic notes (transport notes live in transport.py) ─────────
ROBOTS_BLOCKED_AR = "الموقع يمنع الوصول الآلي — افتحه على شاشتك وأنا أقرأه لك."
PDF_UNSUPPORTED_AR = "هذا ملف PDF وقراءته ما زالت غير متاحة. افتحه على شاشتك وأنا أشرح لك منه."
CONTENT_TYPE_AR = "نوع محتوى هذا الرابط غير مدعوم — أقرأ صفحات الويب والنص وJSON فقط."


@dataclass(frozen=True)
class FetchResult:
    """What net.fetch hands back. On failure `ok` is False and `text_ar` is the
    short Arabic note; on success `content` is the EXTRACTED, budget-capped
    readable text (markup stripped — DEC-18) and `domain` is the real
    (post-redirect) domain the DEC-20 badge draws from."""

    ok: bool
    text_ar: str
    content: str = ""
    final_url: str = ""
    domain: str = ""
    status: int = 0
    content_type: str = ""
    size_bytes: int = 0
    from_cache: bool = False


class HardenedFetcher:
    """One per session, composed at the root; owns ONE long-lived httpx client
    distinct from the API client. `fetch_readable` is the only public entry."""

    def __init__(
        self,
        *,
        client: Optional[httpx.AsyncClient] = None,
        resolver: Resolver = system_resolver,
        rate_limiter: Optional[RateLimiter] = None,
        cache: Optional["SessionCache[FetchResult]"] = None,
        robots_enabled: bool = True,
        total_budget_s: float = TIMEOUT_S,
    ) -> None:
        # ONE long-lived client, SEPARATE from the key-bearing API client. Zero
        # creds: trust_env=False kills proxy / NETRC / host env; no cookies are
        # ever set; follow_redirects=False so the transport re-validates each hop.
        self._client = client or httpx.AsyncClient(
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(TIMEOUT_S),
            headers={"User-Agent": USER_AGENT},
        )
        self._transport = PinnedTransport(self._client, resolver)
        self._rate = rate_limiter or RateLimiter()
        self._cache: "SessionCache[FetchResult]" = cache or SessionCache()
        self._robots = RobotsCache(
            fetch_text=self._fetch_robots_text,
            user_agent_token=USER_AGENT_TOKEN,
            enabled=robots_enabled,
        )
        self._total_budget_s = total_budget_s

    async def aclose(self) -> None:
        """Close the long-lived client (lifecycle owned by the composition
        root, like every other seam)."""
        await self._client.aclose()

    async def fetch_readable(self, url: str) -> FetchResult:
        """The net.fetch entry: an SSRF-hardened GET returning readable content
        or a short Arabic note. Runs under ONE TOTAL wall-clock budget covering
        the ENTIRE operation — DNS resolve + robots.txt + every redirect hop +
        streaming (DEC-22) — so a tainted slow chain can never starve the 90 s
        turn. On budget expiry it fails CLOSED to the timeout note. NEVER raises
        (Law 11)."""
        domain = urlsplit(url).hostname or ""
        try:
            async with asyncio.timeout(self._total_budget_s):
                return await self._fetch_readable(url)
        except TimeoutError:
            # The whole operation (incl. an uninterruptible getaddrinfo) is cut
            # here; a detached resolver thread may finish in the background, but
            # the TURN is freed. A per-turn fetch cap in web_research (T6) is the
            # structural bound on accumulation.
            logger.info("[fetch] %s total-budget-exceeded", domain)
            return FetchResult(ok=False, text_ar=TIMEOUT_AR, domain=domain)
        except Exception as exc:  # noqa: BLE001 — a fetch must never kill the turn
            logger.warning("[fetch] unexpected error (%s)", type(exc).__name__)
            return FetchResult(ok=False, text_ar=NETWORK_ERROR_AR)

    # ───────────────────────────── Internals ─────────────────────────────

    async def _fetch_readable(self, url: str) -> FetchResult:
        key = _cache_key(url)
        cached = self._cache.get(key)
        if cached is not None:
            # Cached content still crosses the router → same wrapping + taint.
            return replace(cached, from_cache=True)

        domain = urlsplit(url).hostname or ""
        if not await self._robots.allows(url):
            logger.info("[fetch] %s robots-disallowed", domain)
            return FetchResult(ok=False, text_ar=ROBOTS_BLOCKED_AR, domain=domain)
        if domain:
            await self._rate.acquire(domain)

        raw = await self._transport.fetch_raw(url)
        if isinstance(raw, str):  # an Arabic-note failure (SSRF / limit / network)
            return FetchResult(ok=False, text_ar=raw, domain=domain)

        note = _content_type_note(raw.content_type)
        if note is not None:
            logger.info("[fetch] %s status=%s unsupported-type", raw.domain, raw.status)
            return FetchResult(
                ok=False, text_ar=note, domain=raw.domain,
                status=raw.status, content_type=raw.content_type,
            )
        # Readable extraction (DEC-18, see extract.py): HTML → trafilatura (markup
        # stripped, NOT injection — the DEC-14 router wrapper is the injection
        # guard). text/plain + JSON are already readable. Runs OFF-loop, so it stays
        # INSIDE the DEC-22 total budget. A miss degrades to a note — NEVER raw HTML.
        decoded = raw.body.decode("utf-8", errors="replace")
        if raw.content_type == "text/html":
            readable = await asyncio.to_thread(extract_html, decoded)
            if not readable:
                logger.info("[fetch] %s status=%s extraction-empty", raw.domain, raw.status)
                return FetchResult(
                    ok=False, text_ar=EXTRACT_FAILED_AR, domain=raw.domain,
                    status=raw.status, content_type=raw.content_type,
                )
        else:
            readable = decoded
        content, truncated = cap_extract(readable)
        result = FetchResult(
            ok=True, text_ar="", content=content, final_url=raw.final_url,
            domain=raw.domain, status=raw.status, content_type=raw.content_type,
            size_bytes=len(raw.body),
        )
        self._cache.put(key, result)
        logger.info(
            "[fetch] %s status=%s bytes=%s chars=%s%s", raw.domain, raw.status,
            len(raw.body), len(content), " (truncated)" if truncated else "",
        )
        return result

    async def _fetch_robots_text(self, robots_url: str) -> Optional[str]:
        """The RobotsCache seam: fetch robots.txt through the SAME hardened
        transport (so it is SSRF-guarded too). Decoded text on success, None on
        any blocked / unreachable / capped result."""
        raw = await self._transport.fetch_raw(robots_url)
        if isinstance(raw, str):
            return None
        return raw.body.decode("utf-8", errors="replace")


# ─── Module helpers ───────────────────────────────────────────────────────────


def _content_type_note(main_type: str) -> Optional[str]:
    """None when the content type may be read; else the honest Arabic refusal
    (PDF gets its own doc_rag-deferred note)."""
    if main_type in ALLOWED_CONTENT_TYPES:
        return None
    if main_type == _PDF_CONTENT_TYPE:
        return PDF_UNSUPPORTED_AR
    return CONTENT_TYPE_AR


def _cache_key(url: str) -> str:
    """A stable key: scheme/host[:port]/path/query, with any userinfo and the
    fragment dropped (creds are never retained, even in a RAM key; the query
    distinguishes pages; the fragment never reaches the server)."""
    p = urlsplit((url or "").strip())
    host = p.hostname or ""
    port = f":{p.port}" if p.port else ""
    return f"{p.scheme}://{host}{port}{p.path}?{p.query}"


__all__ = [
    "HardenedFetcher", "FetchResult",
    # policy notes
    "ROBOTS_BLOCKED_AR", "PDF_UNSUPPORTED_AR", "CONTENT_TYPE_AR",
    "EXTRACT_FAILED_AR", "EXTRACT_TRUNCATED_AR",
    "ALLOWED_CONTENT_TYPES", "MAX_EXTRACT_CHARS",
    # re-exported transport surface (importers keep working)
    "USER_AGENT", "USER_AGENT_TOKEN", "MAX_BYTES", "TIMEOUT_S", "MAX_REDIRECTS",
    "TIMEOUT_AR", "NETWORK_ERROR_AR", "TOO_LARGE_AR", "TOO_MANY_REDIRECTS_AR",
]
