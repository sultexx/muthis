"""
canned.py — the edges the harness fixes, so only the provider is real.

The kernel code between these edges runs unchanged: the web plugin's notes and
rendering, the confirm gate, the router's wrap and taint, the fetcher's status
rule, robots, extraction, cache and badge. What is canned is only what lies
OUTSIDE the machine:

  * web search — `CannedSearchProvider`, injected into the real
    `WebResearchPlugin` exactly as `build_search_provider()` is in production
    (DEC-27's seam). Every query gets the same fixed results;
  * the web — a `client_factory` over an httpx MockTransport and a fixed
    public resolver, the seams `tests/test_net_fetcher.py` already uses;
  * the screen — one fixed PNG per scenario, through the `screen_capture` seam.

Self-taint still fires on canned content, because the router raises it from the
ROUTE's declared taint, never from what a result says (`tool_router.py:209`).
All fixture content names `example.*` domains and invented figures, so nothing
here is, or could be mistaken for, a real source.
"""

from __future__ import annotations

import struct
import zlib
from typing import Callable

import httpx

from muthis.broker.net.transport import USER_AGENT
from muthis.broker.search.protocol import SearchResponse, SearchResult

FIXED_PUBLIC_IP = "93.184.216.34"      # a global address, so the SSRF guard admits it

SEARCH_RESULTS = (
    SearchResult(title="Python 3.13 release notes (fixture)",
                 url="https://docs.example.org/python/3.13",
                 snippet="Python 3.13 was released on 7 October 2024."),
    SearchResult(title="Python 3.12 release notes (fixture)",
                 url="https://docs.example.org/python/3.12",
                 snippet="Python 3.12 was released on 2 October 2023."),
    SearchResult(title="Gold price today (fixture)",
                 url="https://prices.example.org/gold",
                 snippet="Gold traded at 2,350 USD per troy ounce in this fixture."),
)

PAGE_HTML = ("<html><body><p>Fixture page. Python 3.13 was released on 7 October "
             "2024; Python 3.12 on 2 October 2023. Gold: 2,350 USD per ounce "
             "(invented figure).</p></body></html>")


class CannedSearchProvider:
    """Duck-typed like every provider behind DEC-18's seam."""

    name = "canned"
    cost_per_query_usd = 0.0

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str, *, max_results: int = 5) -> SearchResponse:
        self.queries.append(query)
        return SearchResponse(ok=True, text_ar="", results=SEARCH_RESULTS[:max(1, max_results)],
                              provider="canned", cost_usd=0.0)

    async def aclose(self) -> None:
        return None


def _web_handler(request: httpx.Request) -> httpx.Response:
    """Every page is the fixture page; robots.txt is absent (a 404 is
    "unavailable", which RFC 9309 allows — DEC-151)."""
    if request.url.path == "/robots.txt":
        return httpx.Response(404, text="not found")
    return httpx.Response(200, text=PAGE_HTML, headers={"content-type": "text/html"})


def client_factory() -> httpx.AsyncClient:
    """Mirrors the production client (zero credentials, no redirect following)
    over a mock transport: a FACTORY, as DEC-42 requires."""
    return httpx.AsyncClient(transport=httpx.MockTransport(_web_handler),
                             trust_env=False, follow_redirects=False,
                             headers={"User-Agent": USER_AGENT})


def resolver(hostname: str, port: int) -> list[str]:
    return [FIXED_PUBLIC_IP]


def fixed_capture(png: bytes) -> Callable:
    async def capture() -> bytes:
        return png
    return capture


def placeholder_png(width: int = 1920, height: int = 1080, shade: int = 0xE8) -> bytes:
    """A blank frame for the SELF-TEST only. It is never a live fixture: the live
    runner accepts only screens whose sha256 the manifest records as reviewed."""
    row = b"\x00" + bytes([shade]) * (width * 3)
    raw = row * height

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


__all__ = ["CannedSearchProvider", "FIXED_PUBLIC_IP", "SEARCH_RESULTS", "client_factory",
           "fixed_capture", "placeholder_png", "resolver"]
