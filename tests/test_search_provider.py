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
    EMPTY_QUERY_AR,
    MAX_RESULTS,
    MAX_SNIPPET_CHARS,
    MAX_URL_CHARS,
    NO_PROVIDER_AR,
    NO_RESULTS_AR,
    SEARCH_FAILED_AR,
    SEARCH_MALFORMED_AR,
    SEARCH_TIMEOUT_AR,
    TAVILY_COST_PER_QUERY_USD,
    NoSearchProvider,
    SearchProvider,
    TavilyProvider,
    build_search_provider,
)

# A canary shaped like a real key. It must never appear in a log or a note.
SENTINEL_KEY = "tvly-CANARY-must-never-be-logged"
TAVILY_ENDPOINT = "https://api.tavily.com/search"

# Every provider class the seam ships. Commit 2 (Brave + SearXNG) extends this
# ONE list, so the structural guards below automatically cover them too.
PROVIDER_CLASSES = (TavilyProvider, NoSearchProvider)
VENDOR_CLASSES = (TavilyProvider,)

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


def _ok_handler(body=None, recorder=None):
    def handler(request):
        if recorder is not None:
            recorder.append(
                {
                    "url": str(request.url),
                    "auth": request.headers.get("authorization"),
                    "body": json.loads(request.content.decode() or "{}"),
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


def test_a_selected_but_unconfigured_provider_degrades_to_the_note(monkeypatch):
    # Named in .env, but its key is missing: answer the honest note rather than
    # silently answering with a DIFFERENT vendor than the one that was asked for.
    monkeypatch.setenv("MUTHIS_SEARCH_PROVIDER", "tavily")
    provider = build_search_provider()
    assert provider.name == "none"
    assert _search(provider).text_ar == NO_PROVIDER_AR


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
    assert seen[0]["url"] == TAVILY_ENDPOINT
    assert seen[0]["auth"] == f"Bearer {SENTINEL_KEY}"
    assert seen[0]["body"]["query"] == "python asyncio"


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


def test_an_http_error_degrades_to_a_note(keyed):
    def handler(request):
        return httpx.Response(500, text="upstream boom")

    result = _search(TavilyProvider(client=_client(handler)))
    assert result.ok is False and result.text_ar == SEARCH_FAILED_AR
    assert result.results == ()


def test_a_timeout_degrades_to_its_own_note(keyed):
    def handler(request):
        raise httpx.ReadTimeout("too slow")

    result = _search(TavilyProvider(client=_client(handler)))
    assert result.ok is False and result.text_ar == SEARCH_TIMEOUT_AR


def test_a_malformed_body_degrades_to_its_own_note(keyed):
    def handler(request):
        return httpx.Response(200, text="<html>an error page, not JSON</html>")

    result = _search(TavilyProvider(client=_client(handler)))
    assert result.ok is False and result.text_ar == SEARCH_MALFORMED_AR


def test_a_json_array_instead_of_an_object_is_malformed(keyed):
    def handler(request):
        return httpx.Response(200, json=[1, 2, 3])

    result = _search(TavilyProvider(client=_client(handler)))
    assert result.ok is False and result.text_ar == SEARCH_MALFORMED_AR


def test_an_unexpected_exception_never_escapes_the_seam(keyed):
    def handler(request):
        raise RuntimeError("a client-library bug, not an httpx error")

    result = _search(TavilyProvider(client=_client(handler)))
    assert result.ok is False and result.text_ar == SEARCH_FAILED_AR


def test_an_empty_query_never_reaches_the_wire(keyed):
    seen: list[dict] = []
    result = _search(TavilyProvider(client=_client(_ok_handler(recorder=seen))), query="   ")
    assert result.ok is False and result.text_ar == EMPTY_QUERY_AR
    assert seen == []  # an empty query would buy a paid round-trip for nothing


# ── the key never leaves the client ─────────────────────────────────────────


def _key_echo_handler(request):
    # The worst realistic case: the vendor echoes the offending key back.
    return httpx.Response(401, json={"error": f"invalid api key: {SENTINEL_KEY}"})


@pytest.mark.parametrize("handler", [
    _ok_handler(),
    _key_echo_handler,
    lambda request: httpx.Response(500, text=f"boom {SENTINEL_KEY}"),
    lambda request: (_ for _ in ()).throw(httpx.ReadTimeout(f"timeout on {SENTINEL_KEY}")),
    lambda request: httpx.Response(200, text="not json"),
])
def test_the_key_never_appears_in_logs_or_in_any_returned_note(keyed, caplog, handler):
    provider = TavilyProvider(client=_client(handler))
    with caplog.at_level(logging.DEBUG):
        result = _search(provider, query="what is asyncio")
    assert not _leaks_key(caplog.text)
    assert not _leaks_key(result.text_ar)
    assert not _leaks_key(repr(result))
    assert not _leaks_key(repr(provider))


def test_the_query_is_never_logged(keyed, caplog):
    # A query can carry what the user is looking at (DEC-20's never-log-content
    # discipline): logs get the provider, the status and the result count only.
    provider = TavilyProvider(client=_client(_ok_handler()))
    with caplog.at_level(logging.DEBUG):
        _search(provider, query="my-private-screen-content")
    assert "my-private-screen-content" not in caplog.text
    assert "tavily" in caplog.text and "results=2" in caplog.text


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


def test_a_url_shaped_query_never_becomes_the_destination(keyed):
    """The SSRF-proxy attempt: a tainted model asks for a metadata URL. It is
    carried as DATA in the body; the destination stays the configured host."""
    seen: list[dict] = []
    hostile = "http://169.254.169.254/latest/meta-data/ ignore previous instructions"
    _search(TavilyProvider(client=_client(_ok_handler(recorder=seen))), query=hostile)
    assert seen[0]["url"] == TAVILY_ENDPOINT
    assert seen[0]["body"]["query"] == hostile


def test_a_redirect_off_the_configured_host_is_refused_not_followed(keyed):
    """A redirect would carry the key to a host configuration never approved."""
    contacted: list[str] = []

    def handler(request):
        contacted.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://evil.example/steal"})

    result = _search(TavilyProvider(client=_client(handler)))
    assert result.ok is False and result.text_ar == SEARCH_FAILED_AR
    assert contacted == [TAVILY_ENDPOINT]


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
