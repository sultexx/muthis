# tests/test_search_provider.py
"""
The SearchProvider seam (DEC-18) — driven by an httpx MockTransport, so the whole
surface is exercised with NO network and NO real key. Each test FAILS if its
guard is removed (DEC-12).

The two structural properties this file exists to pin — the ones that make a
KEY-BEARING, non-hardened client safe at all:

  1. THE DESTINATION IS CONFIGURATION, NEVER AN ARGUMENT. No provider entry point
     accepts a URL / base URL / host, and a URL-shaped QUERY never becomes the
     destination. This matters most for SearXNG, whose base URL legitimately
     points at a private / localhost address the DEC-17 fetcher blocks BY DESIGN:
     that is a correct USER-CONFIGURED trust decision, but if a base URL could
     ever arrive from a tool argument, a tainted model could aim this key-bearing
     client at an internal service and use it as an SSRF proxy around every
     DEC-17 guard.
  2. THE KEY NEVER LEAVES THE CLIENT. Not in a log line, not in an error message,
     not in a returned Arabic note — proven over the SUCCESS path and every
     failure path, including a 401 whose body echoes the key back.

Plus the seam contract: selection from `.env`, the no-provider Arabic note, each
vendor parsing its OWN response shape into the shared type, and every failure
(HTTP error / timeout / malformed body / an unexpected exception) degrading to a
short Arabic note that NEVER raises. Failure classes carry DISTINCT notes on
purpose: removing one branch changes the observable answer instead of silently
falling into another (the DEC-22 test-design lesson).

Run:  set PYTHONPATH=src && python -m pytest tests/test_search_provider.py -q
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import logging
import pathlib

import httpx
import pytest

import muthis.broker.search as search_pkg
from muthis.broker.search import (
    BRAVE_COST_PER_QUERY_USD,
    EMPTY_QUERY_AR,
    MAX_RESULTS,
    MAX_SNIPPET_CHARS,
    MAX_URL_CHARS,
    NO_PROVIDER_AR,
    NO_RESULTS_AR,
    SEARCH_FAILED_AR,
    SEARCH_MALFORMED_AR,
    SEARCH_TIMEOUT_AR,
    SEARXNG_COST_PER_QUERY_USD,
    TAVILY_COST_PER_QUERY_USD,
    BraveProvider,
    NoSearchProvider,
    SearchProvider,
    SearxngProvider,
    TavilyProvider,
    build_search_provider,
)
from muthis.logging_policy import THIRD_PARTY_HTTP_LOGGERS, configure_logging

# A canary shaped like a real key. It must never appear in a log or a note.
SENTINEL_KEY = "tvly-CANARY-must-never-be-logged"
TAVILY_ENDPOINT = "https://api.tavily.com/search"
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
# A LOOPBACK base URL on purpose: SearXNG is self-hosted, so a private
# destination is the NORMAL case — and it is exactly what the DEC-17 fetcher
# blocks by design. Legitimate here because it is a trust decision the machine's
# owner made in .env, never something a caller or the model can supply.
SEARXNG_BASE = "http://127.0.0.1:8888"
SEARXNG_ENDPOINT = SEARXNG_BASE + "/search"

# Every provider class the seam ships. The structural guards below iterate these
# ONE lists, so a new vendor is covered by them the moment it is added here.
PROVIDER_CLASSES = (TavilyProvider, BraveProvider, SearxngProvider, NoSearchProvider)
VENDOR_CLASSES = (TavilyProvider, BraveProvider, SearxngProvider)
KEYED_VENDORS = (TavilyProvider, BraveProvider)  # SearXNG carries no credential
ENDPOINTS = {
    TavilyProvider: TAVILY_ENDPOINT,
    BraveProvider: BRAVE_ENDPOINT,
    SearxngProvider: SEARXNG_ENDPOINT,
}

# Parameter names that would hand a caller the destination. A provider must not
# accept ANY of them anywhere in its public surface.
DESTINATION_PARAMS = frozenset(
    {"url", "base_url", "endpoint", "host", "hostname", "server", "api_base",
     "base", "uri", "address", "target"}
)


# ── harness ──────────────────────────────────────────────────────────────────


@pytest.fixture
def keyed(monkeypatch):
    """A configured Tavily. (conftest clears these vars for every test, so an
    UNSET provider is the deterministic default.)"""
    monkeypatch.setenv("TAVILY_API_KEY", SENTINEL_KEY)


@pytest.fixture
def configured_all(monkeypatch):
    """EVERY vendor configured, so a test can parametrize across all three and
    prove the seam behaves identically whichever one answers."""
    monkeypatch.setenv("TAVILY_API_KEY", SENTINEL_KEY)
    monkeypatch.setenv("BRAVE_API_KEY", SENTINEL_KEY)
    monkeypatch.setenv("SEARXNG_BASE_URL", SEARXNG_BASE)


@pytest.fixture
def logging_policy():
    """Apply the composition root's logging policy exactly as `main.main()` does
    (DEC-28), then restore — a test must not leave global levels changed."""
    saved = [
        (logging.getLogger(name), logging.getLogger(name).level)
        for name in THIRD_PARTY_HTTP_LOGGERS
    ]
    configure_logging()
    yield
    for logger, level in saved:
        logger.setLevel(level)


def _vendor_id(vendor) -> str:
    return vendor.name


def _raise(exc):
    raise exc


def _client(handler) -> httpx.AsyncClient:
    # Mirrors the production client config, with a MockTransport (no network).
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False, follow_redirects=False
    )


def _search(provider, query: str = "python asyncio", **kwargs):
    async def go():
        try:
            return await provider.search(query, **kwargs)
        finally:
            await provider.aclose()

    return asyncio.run(go())


def _close(provider) -> None:
    asyncio.run(provider.aclose())


def _leaks_key(text: str) -> bool:
    """CASE-INSENSITIVE: selection lower-cases the value it reads from the
    environment, so a naive `SENTINEL_KEY in text` check would miss a key echoed
    through that path — a hole found by mutating this very guard."""
    return SENTINEL_KEY.lower() in (text or "").lower()


def _tavily_body(count: int = 2, snippet: str = "a snippet") -> dict:
    """Tavily's documented reply shape (title / url / content)."""
    return {
        "answer": "a model-written summary the seam deliberately ignores",
        "results": [
            {"title": f"t{i}", "url": f"https://example.com/{i}", "content": snippet}
            for i in range(count)
        ],
    }


def _body_for(vendor, count: int = 2, snippet: str = "a snippet") -> dict:
    """Each vendor's OWN documented reply shape — the thing its module has to
    parse into the shared type. Brave nests under `web` and calls the snippet
    `description`; SearXNG is flat and calls it `content`."""
    hits = [
        {"title": f"t{i}", "url": f"https://example.com/{i}"} for i in range(count)
    ]
    if vendor is BraveProvider:
        return {"web": {"results": [{**h, "description": snippet} for h in hits]}}
    if vendor is SearxngProvider:
        return {"results": [{**h, "content": snippet} for h in hits]}
    return _tavily_body(count, snippet)


def _ok_handler(body=None, recorder=None):
    def handler(request):
        if recorder is not None:
            url = request.url
            recorder.append(
                {
                    # DESTINATION without the query string, so a GET vendor's
                    # parameters can never be mistaken for part of the address.
                    "dest": f"{url.scheme}://{url.netloc.decode()}{url.path}",
                    "url": str(url),
                    "params": dict(url.params),
                    "headers": {k.lower(): v for k, v in request.headers.items()},
                    "body": json.loads(request.content.decode()) if request.content else {},
                }
            )
        return httpx.Response(200, json=body if body is not None else _tavily_body())

    return handler


# ── the no-provider path (the stub_read_file precedent) ──────────────────────


def test_no_provider_configured_answers_the_arabic_note_and_never_raises():
    provider = build_search_provider()
    assert provider.name == "none"
    result = _search(provider)
    assert result.ok is False
    assert result.text_ar == NO_PROVIDER_AR
    assert result.results == () and result.cost_usd == 0.0


# ── selection from .env ──────────────────────────────────────────────────────


def test_provider_is_selected_from_env(keyed):
    provider = build_search_provider()
    assert provider.name == "tavily"
    _close(provider)


def test_an_explicit_env_selection_is_honored_case_insensitively(monkeypatch, keyed):
    monkeypatch.setenv("MUTHIS_SEARCH_PROVIDER", "  TaViLy ")
    provider = build_search_provider()
    assert provider.name == "tavily"
    _close(provider)


@pytest.mark.parametrize("name", ["tavily", "brave", "searxng"])
def test_a_selected_but_unconfigured_provider_degrades_to_the_note(monkeypatch, name):
    # Named in .env, but its key (or, for SearXNG, its base URL) is missing:
    # answer the honest note rather than silently answering with a DIFFERENT
    # vendor than the one that was asked for.
    monkeypatch.setenv("MUTHIS_SEARCH_PROVIDER", name)
    provider = build_search_provider()
    assert provider.name == "none"
    assert _search(provider).text_ar == NO_PROVIDER_AR


@pytest.mark.parametrize("env, expected", [
    ({"TAVILY_API_KEY": SENTINEL_KEY}, "tavily"),
    ({"BRAVE_API_KEY": SENTINEL_KEY}, "brave"),
    ({"SEARXNG_BASE_URL": SEARXNG_BASE}, "searxng"),
    # Several configured: DEC-18's DEFAULT wins, then the roadmap §3.1 order.
    ({"TAVILY_API_KEY": SENTINEL_KEY, "BRAVE_API_KEY": SENTINEL_KEY,
      "SEARXNG_BASE_URL": SEARXNG_BASE}, "tavily"),
    ({"BRAVE_API_KEY": SENTINEL_KEY, "SEARXNG_BASE_URL": SEARXNG_BASE}, "brave"),
])
def test_auto_detection_routes_among_all_three(monkeypatch, env, expected):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    provider = build_search_provider()
    assert provider.name == expected
    _close(provider)


@pytest.mark.parametrize("name", ["tavily", "brave", "searxng"])
def test_an_explicit_selection_wins_over_auto_detection(monkeypatch, configured_all, name):
    # Everything is configured, so only the explicit choice can decide.
    monkeypatch.setenv("MUTHIS_SEARCH_PROVIDER", name)
    provider = build_search_provider()
    assert provider.name == name
    _close(provider)


def test_an_unknown_provider_name_degrades_and_is_never_echoed(monkeypatch, caplog):
    # The paste-the-key-into-the-wrong-variable mistake must not log the key.
    monkeypatch.setenv("MUTHIS_SEARCH_PROVIDER", SENTINEL_KEY)
    with caplog.at_level(logging.DEBUG):
        provider = build_search_provider()
    assert provider.name == "none"
    assert not _leaks_key(caplog.text)


# ── each vendor parses its OWN shape into the shared type ────────────────────


def test_tavily_parses_its_own_response_shape(keyed):
    seen: list[dict] = []
    result = _search(TavilyProvider(client=_client(_ok_handler(recorder=seen))))

    assert result.ok is True and result.provider == "tavily"
    assert [r.url for r in result.results] == [
        "https://example.com/0", "https://example.com/1",
    ]
    assert result.results[0].title == "t0"
    assert result.results[0].snippet == "a snippet"   # Tavily's key is `content`
    assert result.cost_usd == TAVILY_COST_PER_QUERY_USD
    # the QUERY rides the body, the KEY rides the client's header, and the URL is
    # the fixed configured endpoint — never assembled from either.
    assert seen[0]["dest"] == TAVILY_ENDPOINT
    assert seen[0]["headers"]["authorization"] == f"Bearer {SENTINEL_KEY}"
    assert seen[0]["body"]["query"] == "python asyncio"


def test_brave_parses_its_own_response_shape(configured_all):
    seen: list[dict] = []
    handler = _ok_handler(_body_for(BraveProvider), seen)
    result = _search(BraveProvider(client=_client(handler)))

    assert result.ok is True and result.provider == "brave"
    assert [r.url for r in result.results] == [
        "https://example.com/0", "https://example.com/1",
    ]
    assert result.results[0].snippet == "a snippet"   # Brave's key is `description`
    assert result.cost_usd == BRAVE_COST_PER_QUERY_USD
    # A GET vendor: the query is a PARAMETER of the fixed endpoint, never part of it.
    assert seen[0]["dest"] == BRAVE_ENDPOINT
    assert seen[0]["params"] == {"q": "python asyncio", "count": str(MAX_RESULTS)}
    assert seen[0]["headers"]["x-subscription-token"] == SENTINEL_KEY


def test_a_brave_reply_without_the_web_object_is_no_results(configured_all):
    # The nesting is reached DEFENSIVELY: an ad-only or error-shaped reply has
    # nothing to normalize, which is the ordinary note — never an exception.
    result = _search(BraveProvider(client=_client(_ok_handler({"query": {"original": "x"}}))))
    assert result.ok is False and result.text_ar == NO_RESULTS_AR


def test_searxng_parses_its_own_response_shape(configured_all):
    seen: list[dict] = []
    handler = _ok_handler(_body_for(SearxngProvider), seen)
    result = _search(SearxngProvider(client=_client(handler)))

    assert result.ok is True and result.provider == "searxng"
    assert [r.url for r in result.results] == [
        "https://example.com/0", "https://example.com/1",
    ]
    assert result.results[0].snippet == "a snippet"   # SearXNG's key is `content`
    # Self-hosted: 0.0 BY CONSTRUCTION, not a pinned vendor price (DEC-26).
    assert result.cost_usd == SEARXNG_COST_PER_QUERY_USD == 0.0
    assert seen[0]["dest"] == SEARXNG_ENDPOINT
    assert seen[0]["params"] == {"q": "python asyncio", "format": "json"}


def test_searxng_sends_no_credential_at_all(configured_all):
    """The MAXIMUM-PRIVACY option carries no key, no token, no cookie — and the
    OTHER vendors' keys, present in this environment, never bleed into it."""
    seen: list[dict] = []
    handler = _ok_handler(_body_for(SearxngProvider), seen)
    _search(SearxngProvider(client=_client(handler)))
    headers = seen[0]["headers"]
    assert "authorization" not in headers
    assert "x-subscription-token" not in headers
    assert "cookie" not in headers
    assert not _leaks_key(json.dumps(headers))


def test_searxng_clamps_the_count_although_upstream_has_no_count_parameter(configured_all):
    seen: list[dict] = []
    handler = _ok_handler(_body_for(SearxngProvider, 9), seen)
    result = _search(SearxngProvider(client=_client(handler)), max_results=50)
    assert "count" not in seen[0]["params"]      # no such parameter exists upstream
    assert len(result.results) == MAX_RESULTS    # so the seam enforces §3.1's cap


def test_searxng_without_a_base_url_answers_the_note_and_never_fires():
    """No base URL = the user never made the trust decision. Say so honestly
    instead of firing a doomed request (and never invent a default instance)."""
    seen: list[dict] = []
    result = _search(SearxngProvider(client=_client(_ok_handler(recorder=seen))))
    assert result.ok is False and result.text_ar == NO_PROVIDER_AR
    assert seen == []


def test_zero_results_is_a_note_not_a_crash(keyed):
    result = _search(TavilyProvider(client=_client(_ok_handler({"results": []}))))
    assert result.ok is False and result.text_ar == NO_RESULTS_AR
    # It was still served and paid for — the cost is exposed regardless of ok.
    assert result.cost_usd == TAVILY_COST_PER_QUERY_USD


def test_malformed_result_entries_are_dropped_never_raised(keyed):
    body = {"results": [
        "not a dict",
        {"no": "url"},
        {"url": ""},
        {"url": 5},
        {"title": "ok", "url": "https://ok.example/", "content": "c"},
    ]}
    result = _search(TavilyProvider(client=_client(_ok_handler(body))))
    assert result.ok is True and len(result.results) == 1
    assert result.results[0].url == "https://ok.example/"


def test_a_non_list_results_field_is_no_results(keyed):
    result = _search(TavilyProvider(client=_client(_ok_handler({"results": "nope"}))))
    assert result.ok is False and result.text_ar == NO_RESULTS_AR


# ── every failure degrades to its OWN short Arabic note, and NEVER raises ────


@pytest.mark.parametrize("vendor", VENDOR_CLASSES, ids=_vendor_id)
def test_an_http_error_degrades_to_a_note(configured_all, vendor):
    def handler(request):
        return httpx.Response(500, text="upstream boom")

    result = _search(vendor(client=_client(handler)))
    assert result.ok is False and result.text_ar == SEARCH_FAILED_AR
    assert result.results == () and result.provider == vendor.name


@pytest.mark.parametrize("vendor", VENDOR_CLASSES, ids=_vendor_id)
def test_a_timeout_degrades_to_its_own_note(configured_all, vendor):
    def handler(request):
        return _raise(httpx.ReadTimeout("too slow"))

    result = _search(vendor(client=_client(handler)))
    assert result.ok is False and result.text_ar == SEARCH_TIMEOUT_AR


@pytest.mark.parametrize("vendor", VENDOR_CLASSES, ids=_vendor_id)
def test_a_malformed_body_degrades_to_its_own_note(configured_all, vendor):
    # Also SearXNG's realistic misconfiguration: an instance whose JSON format
    # is not enabled answers HTML, which is a malformed reply, not a crash.
    def handler(request):
        return httpx.Response(200, text="<html>an error page, not JSON</html>")

    result = _search(vendor(client=_client(handler)))
    assert result.ok is False and result.text_ar == SEARCH_MALFORMED_AR


@pytest.mark.parametrize("vendor", VENDOR_CLASSES, ids=_vendor_id)
def test_a_json_array_instead_of_an_object_is_malformed(configured_all, vendor):
    def handler(request):
        return httpx.Response(200, json=[1, 2, 3])

    result = _search(vendor(client=_client(handler)))
    assert result.ok is False and result.text_ar == SEARCH_MALFORMED_AR


@pytest.mark.parametrize("vendor", VENDOR_CLASSES, ids=_vendor_id)
def test_an_unexpected_exception_never_escapes_the_seam(configured_all, vendor):
    def handler(request):
        return _raise(RuntimeError("a client-library bug, not an httpx error"))

    result = _search(vendor(client=_client(handler)))
    assert result.ok is False and result.text_ar == SEARCH_FAILED_AR


@pytest.mark.parametrize("vendor", VENDOR_CLASSES, ids=_vendor_id)
def test_an_empty_query_never_reaches_the_wire(configured_all, vendor):
    seen: list[dict] = []
    result = _search(vendor(client=_client(_ok_handler(recorder=seen))), query="   ")
    assert result.ok is False and result.text_ar == EMPTY_QUERY_AR
    assert seen == []  # an empty query would buy a paid round-trip for nothing


# ── the key never leaves the client ─────────────────────────────────────────


def _key_echo_handler(request):
    # The worst realistic case: the vendor echoes the offending key back.
    return httpx.Response(401, json={"error": f"invalid api key: {SENTINEL_KEY}"})


@pytest.mark.parametrize("vendor", KEYED_VENDORS, ids=_vendor_id)
@pytest.mark.parametrize("handler", [
    _ok_handler(),
    _key_echo_handler,
    lambda request: httpx.Response(500, text=f"boom {SENTINEL_KEY}"),
    lambda request: _raise(httpx.ReadTimeout(f"timeout on {SENTINEL_KEY}")),
    lambda request: httpx.Response(200, text="not json"),
])
def test_the_key_never_appears_in_logs_or_in_any_returned_note(
    configured_all, caplog, vendor, handler
):
    provider = vendor(client=_client(handler))
    with caplog.at_level(logging.DEBUG):
        result = _search(provider, query="what is asyncio")
    assert not _leaks_key(caplog.text)
    assert not _leaks_key(result.text_ar)
    assert not _leaks_key(repr(result))
    assert not _leaks_key(repr(provider))


@pytest.mark.parametrize("vendor", VENDOR_CLASSES, ids=_vendor_id)
def test_the_query_is_never_logged(configured_all, caplog, logging_policy, vendor):
    """A query can carry what the user is looking at (DEC-20's never-log-content
    discipline), so the log gets the provider, the status and the result count —
    nothing else.

    The guarantee now holds END-TO-END, over EVERY emitted record rather than
    only our own: this asserts across ALL loggers, at DEBUG (more permissive than
    production's INFO). It was previously scoped to `muthis.*`, because `httpx`
    logs the FULL request URL at INFO — which for a GET vendor embeds the query —
    and the composition root ran everything at INFO. That leak is CLOSED by the
    DEC-28 logging policy, which this test applies exactly as `main.main()` does;
    removing that policy turns this RED as well as its own regression test."""
    provider = vendor(client=_client(_ok_handler(_body_for(vendor))))
    with caplog.at_level(logging.DEBUG):
        _search(provider, query="my-private-screen-content")
    emitted = "\n".join(f"{r.name}: {r.getMessage()}" for r in caplog.records)
    assert "my-private-screen-content" not in emitted
    # POSITIVE CONTROL: our own line is present, so the absence above is the
    # policy working and not an empty log.
    assert vendor.name in emitted and "results=2" in emitted


# ── the destination is configuration, never an argument ─────────────────────


def test_the_base_url_cannot_be_supplied_by_a_caller():
    """STRUCTURAL (the guard the whole key-bearing design rests on): no public
    entry point of any provider takes a destination, so no tool argument and no
    model input can reach one. Adding such a parameter turns this RED."""
    offenders = []
    for cls in PROVIDER_CLASSES:
        for method_name in ("__init__", "search"):
            params = set(inspect.signature(getattr(cls, method_name)).parameters)
            hit = params & DESTINATION_PARAMS
            if hit:
                offenders.append(f"{cls.__name__}.{method_name} accepts {sorted(hit)}")
    assert not offenders, "a caller can aim the provider -> " + "; ".join(offenders)


def test_search_takes_a_query_string_and_nothing_positional_besides():
    """The other half of the same guard: `search()` accepts ONE positional
    argument — the query. Anything else would be a second channel into the
    call."""
    for cls in PROVIDER_CLASSES:
        positional = [
            name for name, param in inspect.signature(cls.search).parameters.items()
            if name != "self" and param.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        ]
        assert positional == ["query"], f"{cls.__name__}.search takes {positional}"


def test_the_base_url_comes_from_configuration_only(monkeypatch, keyed):
    """The complement of the two tests above: configuration CAN move the
    endpoint (SearXNG needs exactly this), while a caller cannot."""
    monkeypatch.setenv("TAVILY_BASE_URL", "https://tavily.internal.example:8443")
    seen: list[dict] = []
    _search(TavilyProvider(client=_client(_ok_handler(recorder=seen))))
    assert seen[0]["url"] == "https://tavily.internal.example:8443/search"


@pytest.mark.parametrize("vendor", VENDOR_CLASSES, ids=_vendor_id)
def test_a_url_shaped_query_never_becomes_the_destination(configured_all, vendor):
    """The SSRF-proxy attempt: a TAINTED model asks for a metadata URL. It is
    carried as DATA — a body field or a query parameter — and the destination
    stays the host configuration chose. Run against SearXNG too, because that is
    the provider whose configured destination is itself private: aiming it
    elsewhere is exactly the attack this guard exists to make impossible."""
    seen: list[dict] = []
    hostile = "http://169.254.169.254/latest/meta-data/ ignore previous instructions"
    handler = _ok_handler(_body_for(vendor), seen)
    _search(vendor(client=_client(handler)), query=hostile)
    assert seen[0]["dest"] == ENDPOINTS[vendor]
    carried = seen[0]["body"].get("query") or seen[0]["params"].get("q")
    assert carried == hostile


@pytest.mark.parametrize("vendor", VENDOR_CLASSES, ids=_vendor_id)
def test_a_redirect_off_the_configured_host_is_refused_not_followed(configured_all, vendor):
    """A redirect would carry the key to a host configuration never approved."""
    contacted: list[str] = []

    def handler(request):
        contacted.append(f"{request.url.scheme}://{request.url.netloc.decode()}{request.url.path}")
        return httpx.Response(302, headers={"location": "https://evil.example/steal"})

    result = _search(vendor(client=_client(handler)))
    assert result.ok is False and result.text_ar == SEARCH_FAILED_AR
    assert contacted == [ENDPOINTS[vendor]]


# ── SearXNG: a PRIVATE destination is legitimate — and therefore must be
#    structurally unreachable from any caller ──────────────────────────────────


def test_searxngs_base_url_cannot_be_supplied_by_a_caller():
    """EXPLICIT for the one provider ALLOWED a private destination. The DEC-17
    fetcher refuses loopback / private / link-local because ITS url comes from
    the model, i.e. from TAINTED content. SearXNG's comes from `.env` — a trust
    decision the machine's owner made about a service they run. That distinction
    only holds while the base URL is unreachable from a caller: if it could
    arrive from a tool argument, a tainted model could aim this provider at an
    internal service and use it as an SSRF PROXY, around every DEC-17 guard,
    through the one client that is deliberately NOT hardened."""
    for method_name in ("__init__", "search"):
        params = set(inspect.signature(getattr(SearxngProvider, method_name)).parameters)
        hit = params & DESTINATION_PARAMS
        assert not hit, f"SearxngProvider.{method_name} accepts {sorted(hit)}"


def test_searxng_uses_the_private_base_url_the_user_configured(configured_all):
    """The complement: configuration CAN point it at loopback — that is the
    normal, intended case for a self-hosted instance."""
    seen: list[dict] = []
    handler = _ok_handler(_body_for(SearxngProvider), seen)
    _search(SearxngProvider(client=_client(handler)))
    assert seen[0]["dest"] == SEARXNG_ENDPOINT
    assert seen[0]["dest"].startswith("http://127.0.0.1")  # a destination the fetcher blocks


# ── results are UNTRUSTED DATA: carried, bounded, never followed ─────────────


def test_result_urls_are_carried_but_never_fetched_by_the_provider(keyed):
    """The provider does nothing clever with a result: any URL it carries is
    fetched LATER and ONLY through the DEC-17 hardened fetcher."""
    contacted: list[str] = []
    body = {"results": [
        {"title": "t", "url": "http://127.0.0.1:8080/admin", "content": "c"},
    ]}

    def handler(request):
        contacted.append(str(request.url))
        return httpx.Response(200, json=body)

    result = _search(TavilyProvider(client=_client(handler)))
    assert result.results[0].url == "http://127.0.0.1:8080/admin"  # carried verbatim
    assert contacted == [TAVILY_ENDPOINT]                          # exactly ONE request


def test_untrusted_text_is_bounded_and_an_over_long_url_is_dropped(keyed):
    body = {"results": [
        {"title": "t", "url": "https://ok.example/", "content": "x" * (MAX_SNIPPET_CHARS * 3)},
        {"title": "t2", "url": "https://e.example/" + "a" * MAX_URL_CHARS, "content": "c"},
    ]}
    result = _search(TavilyProvider(client=_client(_ok_handler(body))))
    assert len(result.results) == 1                       # the over-long URL is DROPPED
    assert len(result.results[0].snippet) == MAX_SNIPPET_CHARS + 1   # + the ellipsis


def test_max_results_is_clamped_to_the_cap(keyed):
    seen: list[dict] = []
    result = _search(
        TavilyProvider(client=_client(_ok_handler(_tavily_body(9), recorder=seen))),
        max_results=50,
    )
    assert seen[0]["body"]["max_results"] == MAX_RESULTS   # the REQUEST is clamped
    assert len(result.results) == MAX_RESULTS              # and so is what is kept


def test_a_garbage_max_results_falls_back_to_the_cap(keyed):
    seen: list[dict] = []
    _search(TavilyProvider(client=_client(_ok_handler(recorder=seen))), max_results="lots")
    assert seen[0]["body"]["max_results"] == MAX_RESULTS


# ── contract + scope ────────────────────────────────────────────────────────


def test_every_provider_satisfies_the_protocol():
    for cls in PROVIDER_CLASSES:
        provider = cls()
        assert isinstance(provider, SearchProvider), cls.__name__
        _close(provider)


def test_the_cost_is_exposed_but_no_budget_is_recorded_yet():
    """DEC-10 stub-first: `record_plugin_call` lands with the plugin at T6, so
    the package must not reach for the ledger yet — but the per-query cost must
    be EXPOSED so T6 has something to record. An AST scan (the bypass-guard
    precedent), so the prose in these docstrings never false-positives."""
    offenders = []
    for path in sorted(pathlib.Path(search_pkg.__file__).parent.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif isinstance(node, (ast.Name, ast.Attribute)):
                label = node.id if isinstance(node, ast.Name) else node.attr
                if label == "record_plugin_call":
                    offenders.append(f"{path.name} calls record_plugin_call")
                continue
            else:
                continue
            if any("budget" in name for name in names):
                offenders.append(f"{path.name} imports {names}")
    assert not offenders, "the seam records budget before its T6 consumer -> " + "; ".join(offenders)
    for cls in VENDOR_CLASSES:
        assert isinstance(cls.cost_per_query_usd, float)
    assert NoSearchProvider.cost_per_query_usd == 0.0
