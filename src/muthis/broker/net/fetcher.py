# src/muthis/broker/net/fetcher.py
"""
HardenedFetcher — the broker-owned embodiment of the net.fetch capability
(DEC-17, V2 Roadmap §3.3). External plugin code never holds a socket; it will
receive `ctx.net.fetch_readable(url)` backed by this object, and web_research
(first party) eats the same dogfood with NO privileged path.

Defenses, each a DEC-17 clause:
  * SSRF — every URL and every redirect hop is validated by `address_guard`
    (resolve once, validate the IP OBJECT, connect to THAT IP with Host + SNI
    preserved so TLS verifies the hostname). Redirects are followed MANUALLY
    (follow_redirects=False), each hop re-validated IN FULL, capped at 5.
  * Limits — 2 MB raw cap, content-type allowlist (html / plain / json), 10 s
    timeout, honest MuthisBot agent, per-domain rate limit, RAM-only session
    LRU (the cache never launders taint).
  * Policy — robots.txt respected (`robots.py`); PDF refused honestly until
    doc_rag.
  * Isolation — ZERO credentials (no cookies, no auth headers, trust_env=False)
    on a SEPARATE long-lived httpx client, never the key-bearing API client
    (the Clicky lesson).
  * Discipline — NEVER raises (every failure is a short Arabic note, Law 11)
    and NEVER logs content: domain + status + size, English only, error paths
    too.

Third-party: httpx (the SAME 0.28.1 P0 pinned the SNI technique on). Siblings
`address_guard` / `robots` / `session_policy`; otherwise stdlib.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from typing import Optional, Union
from urllib.parse import urljoin, urlsplit

import httpx

from .address_guard import (
    PinnedRequest,
    Resolver,
    system_resolver,
    validate_and_pin,
)
from .robots import RobotsCache
from .session_policy import RateLimiter, SessionCache

logger = logging.getLogger("muthis.broker.net")

# An honest, self-identifying agent (never a browser impersonation).
USER_AGENT_TOKEN = "MuthisBot"
USER_AGENT = f"{USER_AGENT_TOKEN}/1.0 (+https://muthis.local/bot)"

MAX_BYTES = 2_000_000       # §3.3 raw cap
TIMEOUT_S = 10.0            # §3.3 per-request wall
MAX_REDIRECTS = 5          # §3.3 hop cap (5 redirects followed, the 6th refused)
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# content-type allowlist (main type only; charset params stripped).
ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {"text/html", "text/plain", "application/json"}
)
_PDF_CONTENT_TYPE = "application/pdf"

# ─── Model-facing Arabic notes (fetch-loop domain; validation notes live in
#     address_guard). Every failure is one of these — the fetcher never raises.
ROBOTS_BLOCKED_AR = "الموقع يمنع الوصول الآلي — افتحه على شاشتك وأنا أقرأه لك."
PDF_UNSUPPORTED_AR = "هذا ملف PDF وقراءته ما زالت غير متاحة. افتحه على شاشتك وأنا أشرح لك منه."
CONTENT_TYPE_AR = "نوع محتوى هذا الرابط غير مدعوم — أقرأ صفحات الويب والنص وJSON فقط."
TOO_LARGE_AR = "محتوى الرابط أكبر من الحد المسموح (٢ ميغابايت). جرّب صفحة أصغر أو افتحه على شاشتك."
TIMEOUT_AR = "انتهت مهلة الاتصال بالموقع. جرّب مرة ثانية أو افتحه على شاشتك."
NETWORK_ERROR_AR = "ما قدرت أوصل للموقع. تأكد من الرابط والاتصال، أو افتحه على شاشتك."
TOO_MANY_REDIRECTS_AR = "الرابط فيه إعادة توجيه كثيرة. جرّب الرابط النهائي مباشرة."


@dataclass(frozen=True)
class FetchResult:
    """What net.fetch hands back. On failure `ok` is False and `text_ar` is the
    short Arabic note; on success `content` is the decoded readable text and
    `domain` is the real (post-redirect) domain the DEC-20 badge draws from."""

    ok: bool
    text_ar: str
    content: str = ""
    final_url: str = ""
    domain: str = ""
    status: int = 0
    content_type: str = ""
    size_bytes: int = 0
    from_cache: bool = False


@dataclass(frozen=True)
class _Raw:
    """The transport-layer result of one validated fetch (post-redirects)."""

    status: int
    content_type: str
    body: bytes
    final_url: str
    domain: str


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
    ) -> None:
        # ONE long-lived client, SEPARATE from the key-bearing API client. Zero
        # creds: trust_env=False kills proxy / NETRC / host env; no cookies are
        # ever set; follow_redirects=False so WE re-validate every hop.
        self._client = client or httpx.AsyncClient(
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(TIMEOUT_S),
            headers={"User-Agent": USER_AGENT},
        )
        self._resolver = resolver
        self._rate = rate_limiter or RateLimiter()
        self._cache: "SessionCache[FetchResult]" = cache or SessionCache()
        self._robots = RobotsCache(
            fetch_text=self._fetch_robots_text,
            user_agent_token=USER_AGENT_TOKEN,
            enabled=robots_enabled,
        )

    async def aclose(self) -> None:
        """Close the long-lived client (lifecycle owned by the composition
        root, like every other seam)."""
        await self._client.aclose()

    async def fetch_readable(self, url: str) -> FetchResult:
        """The net.fetch entry: an SSRF-hardened GET returning readable content
        or a short Arabic note. NEVER raises (Law 11)."""
        try:
            return await self._fetch_readable(url)
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

        raw = await self._fetch_raw(url)
        if isinstance(raw, str):  # an Arabic-note failure (SSRF / limit / network)
            return FetchResult(ok=False, text_ar=raw, domain=domain)

        note = _content_type_note(raw.content_type)
        if note is not None:
            logger.info("[fetch] %s status=%s unsupported-type", raw.domain, raw.status)
            return FetchResult(
                ok=False, text_ar=note, domain=raw.domain,
                status=raw.status, content_type=raw.content_type,
            )
        text = raw.body.decode("utf-8", errors="replace")
        result = FetchResult(
            ok=True, text_ar="", content=text, final_url=raw.final_url,
            domain=raw.domain, status=raw.status, content_type=raw.content_type,
            size_bytes=len(raw.body),
        )
        self._cache.put(key, result)
        logger.info("[fetch] %s status=%s bytes=%s", raw.domain, raw.status, len(raw.body))
        return result

    async def _fetch_raw(self, url: str) -> Union[_Raw, str]:
        """Validate → pin → issue → follow redirects MANUALLY (each hop
        re-validated IN FULL, ≤5) → cap at 2 MB. Returns _Raw or an Arabic
        note. Robots / content-type / cache do NOT live here — this is reused
        to fetch robots.txt itself, so it must not recurse or over-filter."""
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

    async def _fetch_robots_text(self, robots_url: str) -> Optional[str]:
        """The RobotsCache seam: fetch robots.txt through the SAME hardened path
        (so it is SSRF-guarded too). Decoded text on success, None on any
        blocked / unreachable / capped result."""
        raw = await self._fetch_raw(robots_url)
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
    host = (p.hostname or "")
    port = f":{p.port}" if p.port else ""
    return f"{p.scheme}://{host}{port}{p.path}?{p.query}"


__all__ = [
    "HardenedFetcher", "FetchResult", "USER_AGENT", "USER_AGENT_TOKEN",
    "MAX_BYTES", "TIMEOUT_S", "MAX_REDIRECTS", "ALLOWED_CONTENT_TYPES",
    "ROBOTS_BLOCKED_AR", "PDF_UNSUPPORTED_AR", "CONTENT_TYPE_AR",
    "TOO_LARGE_AR", "TIMEOUT_AR", "NETWORK_ERROR_AR", "TOO_MANY_REDIRECTS_AR",
]
