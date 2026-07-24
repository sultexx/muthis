# tests/test_net_fetcher.py
"""HardenedFetcher (DEC-17) — the broker-owned IP-pinned fetcher. Driven by an
httpx MockTransport + a dict-backed fake resolver, so the whole SSRF/resource
surface is exercised with NO network. Each test FAILS if its guard is removed
(DEC-12).

SNI note: P0 (DEC-21-D) proved LIVE that a WRONG sni_hostname is rejected at the
TLS handshake and re-runs at T7. A no-network unit test cannot perform a real
handshake, so we reproduce the contract deterministically: the POSITIVE test
asserts the fetcher pins SNI to the HOSTNAME (never the IP) and does not disable
verification, and the NEGATIVE test asserts that when the transport rejects the
handshake the fetcher fails CLOSED to an Arabic note and never raises."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
import pytest

from muthis.broker.net.address_guard import BLOCKED_ADDRESS_AR, SCHEME_AR
from muthis.broker.net.fetcher import (
    CONTENT_TYPE_AR,
    EXTRACT_FAILED_AR,
    EXTRACT_TRUNCATED_AR,
    MAX_BYTES,
    MAX_EXTRACT_CHARS,
    NETWORK_ERROR_AR,
    PDF_UNSUPPORTED_AR,
    ROBOTS_BLOCKED_AR,
    TIMEOUT_AR,
    TOO_LARGE_AR,
    TOO_MANY_REDIRECTS_AR,
    USER_AGENT,
    FetchResult,
    HardenedFetcher,
)


def _html(text: str) -> str:
    """Minimal HTML that trafilatura extracts to EXACTLY `text` (verified live in
    the T3a probes) — so a content assertion can pin the extraction path."""
    return f"<html><body><p>{text}</p></body></html>"


def _resolver(mapping):
    def resolve(hostname, port):
        return mapping[hostname]

    return resolve


def _client(handler):
    # Mirrors the production client config, but with a MockTransport (no net).
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        trust_env=False,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT},
    )


def _run(handler, url, *, mapping=None, robots_enabled=True) -> FetchResult:
    async def go():
        fetcher = HardenedFetcher(
            client=_client(handler),
            resolver=_resolver(mapping or {}),
            robots_enabled=robots_enabled,
        )
        try:
            return await fetcher.fetch_readable(url)
        finally:
            await fetcher.aclose()

    return asyncio.run(go())


# ── IP pinning: the POSITIVE SNI control ─────────────────────────────────────
def test_pin_connects_to_ip_preserving_host_and_sni():
    seen = {}

    def handler(request):
        seen["url_host"] = request.url.host
        seen["host_header"] = request.headers.get("host")
        seen["sni"] = request.extensions.get("sni_hostname")
        seen["cookie"] = request.headers.get("cookie")
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, text=_html("hello world"), headers={"content-type": "text/html"})

    result = _run(handler, "https://example.com/p?q=1",
                  mapping={"example.com": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok and "hello" in result.content
    assert result.domain == "example.com" and result.status == 200
    assert seen["url_host"] == "104.20.23.154"   # connected to the validated IP
    assert seen["host_header"] == "example.com"  # Host preserved for the vhost
    assert seen["sni"] == "example.com"          # SNI = the HOSTNAME, not the IP
    assert seen["cookie"] is None and seen["auth"] is None  # zero credentials


# ── the NEGATIVE SNI control: a handshake rejection fails closed ─────────────
def test_handshake_rejection_fails_closed_to_a_note():
    def handler(request):
        # What a wrong SNI / cert mismatch produces live (P0/DEC-21-D).
        raise httpx.ConnectError("certificate verify failed: hostname mismatch")

    result = _run(handler, "https://example.com/",
                  mapping={"example.com": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok is False and result.text_ar == NETWORK_ERROR_AR


# ── manual redirects: a public->private hop is refused BEFORE it is contacted ─
def test_public_to_private_redirect_refused_at_the_hop():
    contacted = []

    def handler(request):
        contacted.append(request.url.host)
        if request.url.host == "104.20.23.154":
            return httpx.Response(301, headers={"location": "http://127.0.0.1/secret"})
        return httpx.Response(200, text="SHOULD-NOT-REACH")

    result = _run(handler, "https://pub.example/",
                  mapping={"pub.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok is False and result.text_ar == BLOCKED_ADDRESS_AR
    assert "127.0.0.1" not in contacted  # the internal target was never contacted


def _redirect_chain_handler(redirects_before_ok):
    calls = {"n": 0}

    def handler(request):
        i = calls["n"]
        calls["n"] += 1
        if i < redirects_before_ok:
            return httpx.Response(301, headers={"location": f"https://h{i}.example/"})
        return httpx.Response(200, text="done", headers={"content-type": "text/plain"})

    return handler, calls


def _chain_map():
    mapping = {f"h{i}.example": ["104.20.23.154"] for i in range(6)}
    mapping["start.example"] = ["104.20.23.154"]
    return mapping


def test_exactly_five_redirects_then_ok_succeeds():
    handler, _ = _redirect_chain_handler(5)
    result = _run(handler, "https://start.example/", mapping=_chain_map(), robots_enabled=False)
    assert result.ok and result.content == "done"


def test_six_redirects_hit_the_cap():
    handler, calls = _redirect_chain_handler(6)
    result = _run(handler, "https://start.example/", mapping=_chain_map(), robots_enabled=False)
    assert result.ok is False and result.text_ar == TOO_MANY_REDIRECTS_AR
    assert calls["n"] == 6  # 6 requests issued, the 6th redirect never followed


# ── the 2 MB cap: early (Content-Length) AND streaming (no length) ───────────
def test_too_large_by_content_length():
    def handler(request):
        return httpx.Response(200, content=b"A" * (MAX_BYTES + 1000),
                              headers={"content-type": "text/plain"})

    result = _run(handler, "https://big.example/",
                  mapping={"big.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok is False and result.text_ar == TOO_LARGE_AR


def test_too_large_while_streaming_without_content_length():
    async def body():
        for _ in range(30):
            yield b"A" * 100_000  # 3 MB, chunked -> no Content-Length header

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=body())

    result = _run(handler, "https://big.example/",
                  mapping={"big.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok is False and result.text_ar == TOO_LARGE_AR


def test_body_at_the_cap_is_allowed():
    def handler(request):
        return httpx.Response(200, content=b"A" * MAX_BYTES, headers={"content-type": "text/plain"})

    result = _run(handler, "https://ok.example/",
                  mapping={"ok.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok and result.size_bytes == MAX_BYTES


# ── timeout ──────────────────────────────────────────────────────────────────
def test_timeout_is_its_own_note():
    def handler(request):
        raise httpx.ConnectTimeout("too slow")

    result = _run(handler, "https://slow.example/",
                  mapping={"slow.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok is False and result.text_ar == TIMEOUT_AR


# ── content-type allowlist ───────────────────────────────────────────────────
@pytest.mark.parametrize("ctype, raw_body, expected", [
    # HTML is EXTRACTED; text/plain + JSON are already readable and pass through.
    ("text/html", _html("readable body"), "readable body"),
    ("text/html; charset=utf-8", _html("readable body"), "readable body"),
    ("text/plain", "readable body", "readable body"),
    ("application/json", '{"k": "v"}', '{"k": "v"}'),
])
def test_allowed_content_types_pass(ctype, raw_body, expected):
    def handler(request):
        return httpx.Response(200, text=raw_body, headers={"content-type": ctype})

    result = _run(handler, "https://ct.example/",
                  mapping={"ct.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok and result.content == expected


def test_pdf_refused_honestly():
    def handler(request):
        return httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})

    result = _run(handler, "https://doc.example/f.pdf",
                  mapping={"doc.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok is False and result.text_ar == PDF_UNSUPPORTED_AR


def test_unsupported_content_type_refused():
    def handler(request):
        return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})

    result = _run(handler, "https://img.example/x.png",
                  mapping={"img.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok is False and result.text_ar == CONTENT_TYPE_AR


# ── robots.txt ───────────────────────────────────────────────────────────────
def _robots_handler(*, disallow):
    def handler(request):
        if request.url.path == "/robots.txt":
            rules = "User-agent: *\nDisallow: /" if disallow else "User-agent: *\nAllow: /"
            return httpx.Response(200, text=rules, headers={"content-type": "text/plain"})
        return httpx.Response(200, text=_html("page"), headers={"content-type": "text/html"})

    return handler


def test_robots_disallow_redirects_to_the_vision_path():
    result = _run(_robots_handler(disallow=True), "https://r.example/page",
                  mapping={"r.example": ["104.20.23.154"]}, robots_enabled=True)
    assert result.ok is False and result.text_ar == ROBOTS_BLOCKED_AR


def test_robots_allow_permits_the_fetch():
    result = _run(_robots_handler(disallow=False), "https://r.example/page",
                  mapping={"r.example": ["104.20.23.154"]}, robots_enabled=True)
    assert result.ok and result.content == "page"


def test_missing_robots_defaults_to_allow():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404, text="not found")
        return httpx.Response(200, text=_html("page"), headers={"content-type": "text/html"})

    result = _run(handler, "https://r.example/page",
                  mapping={"r.example": ["104.20.23.154"]}, robots_enabled=True)
    assert result.ok and result.content == "page"


# ── privacy: content is NEVER logged (domain + status + size only) ───────────
def test_page_content_is_never_logged(caplog):
    canary = "CANARY-9f3a-secret-token"

    def handler(request):
        return httpx.Response(200, text=_html(f"page carrying {canary} inline"),
                              headers={"content-type": "text/html"})

    with caplog.at_level(logging.DEBUG, logger="muthis.broker.net"):
        result = _run(handler, "https://log.example/p",
                      mapping={"log.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok and canary in result.content   # the content really carried it
    assert canary not in caplog.text                 # but the logs never did
    assert "log.example" in caplog.text              # the domain IS logged (+status/size)


def test_content_is_never_logged_on_the_error_path(caplog):
    canary = "CANARY-err-77"

    def handler(request):
        return httpx.Response(200, content=f"secret {canary}".encode(),
                              headers={"content-type": "image/png"})  # a refused type

    with caplog.at_level(logging.DEBUG, logger="muthis.broker.net"):
        result = _run(handler, "https://log2.example/x",
                      mapping={"log2.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok is False and canary not in caplog.text


# ── session cache ────────────────────────────────────────────────────────────
def test_second_fetch_is_served_from_cache():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, text=_html("cached-body"), headers={"content-type": "text/html"})

    async def go():
        fetcher = HardenedFetcher(client=_client(handler),
                                  resolver=_resolver({"c.example": ["104.20.23.154"]}),
                                  robots_enabled=False)
        try:
            first = await fetcher.fetch_readable("https://c.example/p")
            second = await fetcher.fetch_readable("https://c.example/p")
            return first, second
        finally:
            await fetcher.aclose()

    first, second = asyncio.run(go())
    assert first.ok and first.from_cache is False
    assert second.ok and second.from_cache is True and second.content == "cached-body"
    assert calls["n"] == 1  # the network was hit exactly once


# ── isolation: the default client carries no credentials ─────────────────────
def test_default_client_is_credential_free():
    async def go():
        fetcher = HardenedFetcher()
        try:
            return fetcher._client.trust_env, fetcher._client.follow_redirects
        finally:
            await fetcher.aclose()

    trust_env, follow_redirects = asyncio.run(go())
    assert trust_env is False       # no proxy / NETRC / host env
    assert follow_redirects is False  # every hop is re-validated by us


# ── discipline: a bad scheme is a note, never a raise ────────────────────────
def test_non_http_scheme_is_a_note_not_a_raise():
    result = _run(lambda request: httpx.Response(200), "file:///etc/passwd",
                  mapping={}, robots_enabled=False)
    assert result.ok is False and result.text_ar == SCHEME_AR


# ── DEC-22: the TOTAL wall-clock budget (a tainted slow chain must not starve
#    the turn). The budget covers DNS + robots + every hop + streaming. ────────
def test_total_budget_cuts_a_slow_multi_hop_chain():
    calls = []

    def slow_resolver(hostname, port):
        calls.append(hostname)
        time.sleep(0.15)  # each hop is well UNDER any per-hop timeout
        return ["104.20.23.154"]

    hop = {"n": 0}

    def handler(request):
        hop["n"] += 1
        return httpx.Response(301, headers={"location": f"https://hop{hop['n']}.example/"})

    async def go():
        fetcher = HardenedFetcher(client=_client(handler), resolver=slow_resolver,
                                  robots_enabled=False, total_budget_s=0.35)
        try:
            return await fetcher.fetch_readable("https://start.example/")
        finally:
            await fetcher.aclose()

    result = asyncio.run(go())
    # No single hop is slow enough to trip a per-hop timeout; only the TOTAL
    # budget across hops can cut this -> the timeout note, NOT too-many-redirects.
    # Remove the budget and the chain runs all 6 hops -> TOO_MANY_REDIRECTS_AR (RED).
    assert result.ok is False and result.text_ar == TIMEOUT_AR
    assert result.text_ar != TOO_MANY_REDIRECTS_AR
    assert len(calls) >= 2  # it was a multi-hop chain, cut mid-flight


def test_total_budget_includes_the_robots_lookup():
    # The FIRST resolve (robots.txt) alone is slow enough to exhaust the budget.
    # If robots were OUTSIDE the budget it would complete and the (fast) page
    # would be fetched ok; because it is INSIDE, the page is never reached.
    n = {"i": 0}

    def resolver(hostname, port):
        n["i"] += 1
        if n["i"] == 1:
            time.sleep(0.5)  # the robots.txt round-trip alone > the budget
        return ["104.20.23.154"]

    reached = {"page": False}

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /",
                                  headers={"content-type": "text/plain"})
        reached["page"] = True
        return httpx.Response(200, text="page", headers={"content-type": "text/html"})

    async def go():
        fetcher = HardenedFetcher(client=_client(handler), resolver=resolver,
                                  robots_enabled=True, total_budget_s=0.2)
        try:
            return await fetcher.fetch_readable("https://r.example/page")
        finally:
            await fetcher.aclose()

    result = asyncio.run(go())
    assert result.ok is False and result.text_ar == TIMEOUT_AR
    assert reached["page"] is False  # the budget was spent on robots; the doc never ran


def test_fast_fetch_is_unaffected_by_the_budget():
    # A normal fetch (default 10 s budget) completes well within it.
    def handler(request):
        return httpx.Response(200, text=_html("quick"), headers={"content-type": "text/html"})

    result = _run(handler, "https://fast.example/",
                  mapping={"fast.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok and result.content == "quick"


# ── DEC-18: readable extraction over the fetch path ──────────────────────────
_ARTICLE_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
    "<title>Understanding Binary Search</title></head><body>"
    "<header><nav>Home | Docs | Blog SHOULD-DROP</nav></header><main><article>"
    "<h1>Understanding Binary Search</h1>"
    "<p>Binary search is a fundamental algorithm that locates a target value within "
    "a sorted array by repeatedly halving the portion that could contain it.</p>"
    "<p>This gives it a worst-case time complexity of O(log n), far better than the "
    "O(n) of a linear scan over large sorted datasets.</p>"
    "</article></main><footer><p>Copyright 2026 SHOULD-DROP</p></footer></body></html>"
)


def test_html_is_extracted_to_readable_text_stripping_boilerplate():
    def handler(request):
        return httpx.Response(200, text=_ARTICLE_HTML, headers={"content-type": "text/html"})

    result = _run(handler, "https://doc.example/bs",
                  mapping={"doc.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok
    assert "Binary search is a fundamental algorithm" in result.content  # prose kept
    assert "O(log n)" in result.content
    assert "SHOULD-DROP" not in result.content    # nav + footer boilerplate stripped
    assert "<p>" not in result.content and "<article>" not in result.content  # markup gone


def test_extraction_failure_degrades_to_a_note_and_never_leaks_raw_html():
    # A JS-only SPA shell has no server-rendered prose -> trafilatura returns None.
    # The contract: a short Arabic note, and the raw HTML/JS is NEVER the content
    # (remove the None-guard and fall back to raw HTML and this test goes RED).
    shell = ('<html><body><div id="root"></div>'
             '<script>window.SECRET_STATE={token:"LEAK-CANARY"};render();</script></body></html>')

    def handler(request):
        return httpx.Response(200, text=shell, headers={"content-type": "text/html"})

    result = _run(handler, "https://spa.example/app",
                  mapping={"spa.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok is False and result.text_ar == EXTRACT_FAILED_AR
    assert result.domain == "spa.example"
    assert result.content == ""                 # nothing leaked
    assert "LEAK-CANARY" not in result.content  # the raw JS/markup never becomes content
    assert "<script" not in result.content


def test_over_cap_content_is_truncated_with_the_arabic_note():
    # text/plain passes through un-extracted, so it drives cap_extract deterministically.
    big = "word " * 5000  # 25000 chars, well over MAX_EXTRACT_CHARS, under the 2 MB raw cap

    def handler(request):
        return httpx.Response(200, text=big, headers={"content-type": "text/plain"})

    result = _run(handler, "https://long.example/",
                  mapping={"long.example": ["104.20.23.154"]}, robots_enabled=False)
    assert result.ok
    assert result.content.endswith(EXTRACT_TRUNCATED_AR)         # the "request more" hint
    assert len(result.content) <= MAX_EXTRACT_CHARS + len(EXTRACT_TRUNCATED_AR)
    assert len(result.content) < len(big)                        # actually shorter
    assert result.size_bytes == len(big)                         # size_bytes is the RAW size
