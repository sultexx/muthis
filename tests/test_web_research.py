# tests/test_web_research.py
"""
The `web_research` plugin (V2 Phase 2 M2, T6a COMMIT 2), mutation-verified.

FOUR PROPERTIES ARE THE POINT, and each is driven directly rather than argued:

  1. THE PLUGIN HOLDS NO KEY, NO CLIENT, NO ENDPOINT (DEC-27). Asserted
     structurally — the same shape pinned for `ctx.net` in COMMIT 1 — because
     "we did not add one" is not a guarantee. A source scan is used as well as
     an attribute scan: a base URL could arrive as a literal, not an attribute.
  2. A SEARCH PERFORMS ZERO FETCHES (DEC-18). Asserted behaviourally AND
     structurally: `_search` does not take `ctx`, so there is no reachable fetch
     surface on the search path — the property cannot be regressed by an edit
     inside the body, only by changing the signature, which a test pins.
  3. THE PER-TURN CAP HOLDS AND `new_turn()` RESTORES IT (DEC-22) — the
     structural bound on the getaddrinfo threads DEC-22 could not cancel. The
     refused call must perform NO fetch, which is what makes it a bound.
  4. NOTHING EVER RAISES (Law 11). Every failure path — no provider, absent
     seam, bad argument, exhausted cap, refused fetch, a provider or fetcher
     that throws — returns a short Arabic note.

Plus: cost is READ from the provider and carried, and recorded NOWHERE (T6b).

No test here imports `muthis.main` (standing rule): live credentials, now
including a real TAVILY_API_KEY.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib
import re

import pytest

from muthis_plugins.web_research import MAX_FETCHES_PER_TURN, WebResearchPlugin
from muthis_plugins.web_research.fetch_gate import (
    FETCH_GATE_EXHAUSTED_AR,
    FetchGate,
)
from muthis_plugins.web_research.plugin import (
    BAD_URL_AR,
    EMPTY_QUERY_AR,
    FETCH_FAILED_AR,
    NET_ABSENT_AR,
    NO_PROVIDER_AR,
    UNKNOWN_TOOL_AR,
)
from muthis_sdk import NetCapability, PluginContext

PKG = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis_plugins" / "web_research"


def _code_literals(tree: ast.AST) -> list[str]:
    """String constants that are CODE, not docstrings. Docstrings and comments
    stay free to DISCUSS what the module must not implement — the established
    precedent of `test_untrusted_wrap_guard.py`, and every module here relies
    on it to record why a surface is absent."""
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and getattr(node, "body", None) and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and id(n) not in docstrings
    ]


# ─── Doubles (the plugin duck-types both, as the layering law forces) ─────────


class _Hit:
    def __init__(self, url, title="عنوان", snippet="مقتطف"):
        self.url, self.title, self.snippet = url, title, snippet


class _Response:
    def __init__(self, *, ok=True, results=(), text_ar="", cost_usd=0.008):
        self.ok, self.results, self.text_ar, self.cost_usd = ok, results, text_ar, cost_usd


class _Provider:
    """Records what it was handed, so "the plugin passes a QUERY and nothing
    else" is observable rather than assumed."""

    name = "fake"
    cost_per_query_usd = 0.008

    def __init__(self, response=None, raises=False):
        self._response = response or _Response(results=(_Hit("https://a.example/x"),))
        self._raises = raises
        self.calls = []

    async def search(self, query, *, max_results=5):
        self.calls.append((query, max_results))
        if self._raises:
            raise RuntimeError("vendor exploded")
        return self._response


class _Page:
    def __init__(self, *, ok=True, text_ar="", content="نص", domain="a.example"):
        self.ok, self.text_ar, self.content, self.domain = ok, text_ar, content, domain


class _Net:
    """Stands in for the broker's wired seam. `calls` is the zero-fetch proof."""

    def __init__(self, page=None, raises=False):
        self._page = page or _Page()
        self._raises = raises
        self.calls = []

    async def fetch_readable(self, url):
        self.calls.append(url)
        if self._raises:
            raise RuntimeError("transport exploded")
        return self._page


def _ctx(net=None):
    return PluginContext(net=NetCapability(fetch_readable=net.fetch_readable) if net else None)


def _run(coro):
    return asyncio.run(coro)


# ─── 1. NO KEY, NO CLIENT, NO ENDPOINT (DEC-27) ──────────────────────────────


def test_the_plugin_holds_no_key_no_client_and_no_endpoint():
    """The provider is INJECTED already-built: the broker owns the vendor client,
    the API key and the base URL. If any of those appeared here, a tainted model
    that reached the plugin would be one step from aiming a key-bearing call."""
    plugin = WebResearchPlugin(provider=_Provider())
    surface = {n for n in vars(plugin) if not n.startswith("_")}
    assert surface == set(), f"the plugin exposes state it should not: {surface}"

    forbidden = {"api_key", "key", "client", "session", "base_url", "endpoint",
                 "host", "headers", "transport", "url"}
    attrs = {n.lstrip("_") for n in vars(plugin)} | {
        n for n in dir(plugin) if not n.startswith("__")}
    assert not (forbidden & attrs), f"a credential/endpoint surface appeared: {forbidden & attrs}"


def test_no_source_in_the_package_names_a_key_or_a_base_url():
    """The attribute scan above cannot see a hard-coded literal, so scan the
    SOURCE too: no environment key read, no scheme-bearing endpoint constant.
    Docstrings and comments are stripped from consideration by scanning code
    nodes and non-docstring literals only (the test_pointer_look_only precedent)."""
    key_names = re.compile(r"(API_KEY|api_key|getenv|environ|Authorization|Bearer)")
    for source in sorted(PKG.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        code = [n for n in ast.walk(tree)
                if isinstance(n, (ast.Name, ast.Attribute, ast.Import, ast.ImportFrom))]
        names = {getattr(n, "id", "") or getattr(n, "attr", "") for n in code}
        names |= {a.name for n in code if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module or "" for n in code if isinstance(n, ast.ImportFrom)}
        assert not any(key_names.search(n) for n in names), f"{source.name}: reads a credential"
        literals = _code_literals(tree)
        assert not [t for t in literals if t.startswith(("http://", "https://"))], (
            f"{source.name}: holds an endpoint literal — the destination is "
            f"CONFIGURATION the broker owns, never a constant here")


def test_the_provider_receives_a_query_string_and_nothing_else():
    provider = _Provider()
    _run(WebResearchPlugin(provider=provider).execute(
        "search", {"query": "  python 3.14 release  "}, _ctx()))
    (query, _limit), = provider.calls
    assert query == "python 3.14 release"  # trimmed, never rewritten into a URL
    assert isinstance(query, str)


# ─── 2. A SEARCH PERFORMS ZERO FETCHES (DEC-18) ──────────────────────────────


def test_search_performs_zero_fetches():
    """Search results are page-owner-authored. Following one automatically would
    let a hostile result choose the fetcher's destination without the model ever
    deciding to visit it."""
    net = _Net()
    provider = _Provider(_Response(results=(
        _Hit("https://evil.example/a"), _Hit("https://evil.example/b"))))
    result = _run(WebResearchPlugin(provider=provider).execute(
        "search", {"query": "x"}, _ctx(net)))

    assert net.calls == [], "web__search fetched a result URL"
    assert "https://evil.example/a" in result.text_ar  # carried as DATA for the model
    assert result.is_error is False


def test_the_search_path_has_no_fetch_surface_in_scope_at_all():
    """The structural form of the property above: `_search` does not receive
    `ctx`, so zero-fetch cannot be regressed by an edit inside the body — only
    by changing this signature, which fails here."""
    assert list(inspect.signature(WebResearchPlugin._search).parameters) == ["self", "args"]


def test_a_result_url_is_carried_verbatim_never_edited():
    """Quietly rewriting an untrusted URL would silently produce a DIFFERENT
    destination — the reason the broker seam DROPS over-long URLs rather than
    truncating them."""
    url = "https://a.example/p?q=1&r=%20two#frag"
    result = _run(WebResearchPlugin(provider=_Provider(_Response(results=(_Hit(url),)))).execute(
        "search", {"query": "x"}, _ctx()))
    assert url in result.text_ar


# ─── 3. THE PER-TURN CAP (DEC-22) ────────────────────────────────────────────


def test_the_cap_refuses_the_fourth_fetch_and_performs_no_fetch_for_it():
    """The refused call must reach NO network at all — otherwise the cap bounds
    nothing, and the getaddrinfo threads DEC-22 could not cancel keep landing."""
    net = _Net()
    plugin = WebResearchPlugin(provider=_Provider())
    for _ in range(MAX_FETCHES_PER_TURN):
        assert _run(plugin.execute("fetch", {"url": "https://a.example"}, _ctx(net))).is_error is False
    assert len(net.calls) == MAX_FETCHES_PER_TURN

    refused = _run(plugin.execute("fetch", {"url": "https://a.example"}, _ctx(net)))
    assert refused.text_ar == FETCH_GATE_EXHAUSTED_AR and refused.is_error is True
    assert len(net.calls) == MAX_FETCHES_PER_TURN, "the refused fetch still hit the network"


def test_new_turn_restores_the_budget():
    net = _Net()
    plugin = WebResearchPlugin(provider=_Provider())
    for _ in range(MAX_FETCHES_PER_TURN + 2):
        _run(plugin.execute("fetch", {"url": "https://a.example"}, _ctx(net)))
    assert len(net.calls) == MAX_FETCHES_PER_TURN

    plugin.new_turn()
    assert _run(plugin.execute("fetch", {"url": "https://a.example"}, _ctx(net))).is_error is False
    assert len(net.calls) == MAX_FETCHES_PER_TURN + 1


def test_the_gate_counts_only_allowed_fetches_so_the_refusal_is_stable():
    """Counting on the refusing path too would let a persistent model drive the
    counter upward forever; the note must stay the same note."""
    gate = FetchGate()
    for _ in range(MAX_FETCHES_PER_TURN):
        assert gate.consume() is None
    assert gate.consume() == FETCH_GATE_EXHAUSTED_AR
    assert gate.consume() == FETCH_GATE_EXHAUSTED_AR
    assert gate.fetches == MAX_FETCHES_PER_TURN
    assert gate.fetches_remaining() == 0
    gate.new_turn()
    assert gate.fetches_remaining() == MAX_FETCHES_PER_TURN


def test_a_bad_url_argument_does_not_burn_a_fetch():
    """A malformed argument is the model's mistake, not a page visit. Spending a
    fetch on it would let one bad argument cost the turn a real source."""
    net = _Net()
    plugin = WebResearchPlugin(provider=_Provider())
    for args in ({}, {"url": ""}, {"url": 42}, {"url": "   "}):
        assert _run(plugin.execute("fetch", args, _ctx(net))).text_ar == BAD_URL_AR
    assert net.calls == []
    assert plugin._gate.fetches_remaining() == MAX_FETCHES_PER_TURN


def test_the_gate_is_its_own_object_never_the_draw_or_sandbox_gate():
    """DEC-3-B, applied again: two concerns, two objects. A shared instance is
    how one tool's budget silently starts closing another's circuit."""
    import muthis_plugins.web_research.fetch_gate as fg
    source = (PKG / "fetch_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert imported <= {"dataclasses", "typing", "__future__"}, imported
    assert not hasattr(fg.FetchGate(), "drawn") and not hasattr(fg.FetchGate(), "runs")


# ─── 4. NEVER RAISES — every failure is a short Arabic note ──────────────────


ARABIC = re.compile(r"[؀-ۿ]")


@pytest.mark.parametrize("tool,args,ctx_net,provider,expected", [
    ("search", {"query": "x"}, None, None, NO_PROVIDER_AR),
    ("search", {}, None, _Provider(), EMPTY_QUERY_AR),
    ("search", {"query": "   "}, None, _Provider(), EMPTY_QUERY_AR),
    ("search", {"query": 7}, None, _Provider(), EMPTY_QUERY_AR),
    ("fetch", {"url": "https://a.example"}, None, _Provider(), NET_ABSENT_AR),
    ("fetch", {}, _Net(), _Provider(), BAD_URL_AR),
    ("nope", {}, _Net(), _Provider(), UNKNOWN_TOOL_AR),
])
def test_every_refusal_is_a_short_arabic_note(tool, args, ctx_net, provider, expected):
    result = _run(WebResearchPlugin(provider=provider).execute(tool, args, _ctx(ctx_net)))
    assert result.text_ar == expected and result.is_error is True
    assert ARABIC.search(result.text_ar), "a user/model-facing note must be Arabic"


def test_a_provider_that_raises_becomes_a_note_not_an_exception():
    result = _run(WebResearchPlugin(provider=_Provider(raises=True)).execute(
        "search", {"query": "x"}, _ctx()))
    assert result.text_ar == FETCH_FAILED_AR and result.is_error is True


def test_a_fetcher_that_raises_becomes_a_note_not_an_exception():
    result = _run(WebResearchPlugin(provider=_Provider()).execute(
        "fetch", {"url": "https://a.example"}, _ctx(_Net(raises=True))))
    assert result.text_ar == FETCH_FAILED_AR and result.is_error is True


def test_a_refused_fetch_passes_the_fetchers_own_arabic_note_through():
    """The fetcher already speaks Arabic for robots / PDF / content-type / size /
    timeout. Re-wording them here would produce a second, less accurate voice —
    exactly the misleading-refusal failure DEC-35 records for FileReader."""
    note = "الموقع يمنع الوصول الآلي — افتحه على شاشتك وأنا أقرأه لك."
    result = _run(WebResearchPlugin(provider=_Provider()).execute(
        "fetch", {"url": "https://a.example"}, _ctx(_Net(_Page(ok=False, text_ar=note)))))
    assert result.text_ar == note and result.is_error is True


def test_an_empty_provider_result_is_a_note_and_still_carries_its_cost():
    """A served-but-empty query still cost money; dropping the figure would
    under-charge T6b's ledger on precisely the queries that felt free."""
    outcome = _run(WebResearchPlugin(provider=_Provider(
        _Response(ok=False, text_ar="ما طلعت نتائج.", cost_usd=0.008))).execute_with_cost(
            "search", {"query": "x"}, _ctx()))
    assert outcome.result.is_error is True and outcome.cost_usd == 0.008


# ─── COST: exposed, never recorded (T6b) ─────────────────────────────────────


def test_the_cost_is_read_from_the_provider_and_exposed():
    outcome = _run(WebResearchPlugin(provider=_Provider(
        _Response(results=(_Hit("https://a.example"),), cost_usd=0.008))).execute_with_cost(
            "search", {"query": "x"}, _ctx()))
    assert outcome.cost_usd == 0.008
    # a garbage figure degrades to 0.0 rather than raising into the turn
    weird = _run(WebResearchPlugin(provider=_Provider(
        _Response(results=(_Hit("https://a.example"),), cost_usd="free"))).execute_with_cost(
            "search", {"query": "x"}, _ctx()))
    assert weird.cost_usd == 0.0


def test_nothing_in_the_package_records_a_cost():
    """`record_plugin_call` is T6b's wiring. A ledger touched here would be dead
    code today and a second charging site tomorrow (stub-first, DEC-10)."""
    for source in sorted(PKG.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        names = {getattr(n, "id", "") or getattr(n, "attr", "") for n in ast.walk(tree)
                 if isinstance(n, (ast.Name, ast.Attribute))}
        assert not ({"record_plugin_call", "record_turn", "budget", "Budget"} & names), source.name


# ─── Descriptors, names, and the catalog boundary ────────────────────────────


def test_the_two_tools_are_declared_with_bare_names_the_router_namespaces():
    """The plugin never spells `web__search`: `namespaced_name` owns the DEC-11
    form, so there is exactly one place the separator can be wrong."""
    descriptors = WebResearchPlugin().descriptors()
    assert [d.name for d in descriptors] == ["search", "fetch"]
    assert all(d.read_only is True and d.kernel_serviced is False for d in descriptors)
    for source in sorted(PKG.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        spelled = [t for t in _code_literals(tree) if "web__" in t]
        assert not spelled, f"{source.name} spells the namespaced form itself: {spelled}"


def test_the_schemas_offer_no_provider_endpoint_or_credential_argument():
    """The model-facing half of DEC-27: the destination is CONFIGURATION. A
    tainted model must find no argument that could aim the key-bearing client."""
    for descriptor in WebResearchPlugin().descriptors():
        properties = descriptor.schema["input_schema"]["properties"]
        assert not ({"provider", "base_url", "host", "endpoint", "api_key",
                     "headers", "engine"} & set(properties))
    search, fetch = WebResearchPlugin().descriptors()
    assert set(search.schema["input_schema"]["properties"]) == {"query", "max_results"}
    assert set(fetch.schema["input_schema"]["properties"]) == {"url"}


def test_max_results_is_clamped_before_it_reaches_the_provider():
    provider = _Provider()
    for requested, expected in ((99, 5), (0, 1), (-3, 1), ("many", 5), (None, 5), (3, 3)):
        provider.calls.clear()
        _run(WebResearchPlugin(provider=provider).execute(
            "search", {"query": "x", "max_results": requested}, _ctx()))
        assert provider.calls[0][1] == expected, requested
