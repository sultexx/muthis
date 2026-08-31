# tests/test_domain_badge.py
"""
The DEC-20 domain badge — provenance collection + rendering, mutation-verified.

THE DECIDING PROPERTY, and the only one that makes the badge worth having: the
domain is recorded by the BROKER'S FETCHER, first-hand, and NEVER travels through
plugin code. The badge is the deterministic backstop whose job is to expose a
HALLUCINATED attribution; a fact routed through plugin-supplied text or a
plugin-populated field would put the guard DOWNSTREAM of the very output it
checks — a fabricated source would draw its own corroborating badge. So that
property is asserted STRUCTURALLY, by source scan as well as attribute scan (the
shape used for web_research's no-key property: an endpoint can arrive as a
literal, not an attribute, and so can a domain).

FETCHES ONLY (a correctness rule, not a scope cut): a search returns up to five
candidate links the model did NOT read. Recording them would let a hallucinated
citation look verified whenever its domain happened to sit in the result list —
inverting the badge's purpose. A snippet-only turn therefore shows an EMPTY
badge, which is the honest signal, and is asserted here as behaviour.

No test imports `muthis.main` (standing rule): live credentials.
"""

from __future__ import annotations

import ast
import asyncio
import logging
import pathlib

import httpx
import pytest

from muthis.broker.net import FetchedDomains, HardenedFetcher, MAX_TRACKED_DOMAINS
from muthis.broker.net.fetcher import USER_AGENT
from muthis.overlay.caption_bar import MAX_CHARS_PER_LINE, MAX_LINES, CAPTION_TAG
from muthis.overlay.domain_badge import (
    DOMAIN_BADGE_TAG,
    MAX_SHOWN,
    SOURCE_LABEL_AR,
    DomainBadge,
    format_badge,
)
from muthis.overlay.window_commands import dispatch_command
from muthis_plugins.web_research import WebResearchPlugin
from muthis_sdk import NetCapability, PluginContext

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
PLUGINS = SRC / "muthis_plugins"


def _html(text: str) -> str:
    return f"<html><body><p>{text}</p></body></html>"


def _fetch(url, mapping, *, handler=None, domains=None, robots_enabled=False):
    """One real fetch through the real fetcher on a MockTransport (no network)."""
    def default_handler(request):
        return httpx.Response(200, text=_html("some readable body text here"),
                              headers={"content-type": "text/html"})

    async def go():
        fetcher = HardenedFetcher(
            client_factory=lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(handler or default_handler),
                trust_env=False, follow_redirects=False,
                headers={"User-Agent": USER_AGENT}),
            resolver=lambda hostname, port: mapping[hostname],
            robots_enabled=robots_enabled,
            domains=domains,
        )
        try:
            return await fetcher.fetch_readable(url)
        finally:
            await fetcher.aclose()

    return asyncio.run(go())


# ─── THE FETCHER records it, first-hand ──────────────────────────────────────


def test_a_successful_fetch_records_its_domain():
    collector = FetchedDomains()
    result = _fetch("https://docs.example.com/page?q=secret",
                    {"docs.example.com": ["93.184.216.34"]}, domains=collector)
    assert result.ok
    assert collector.domains() == ("docs.example.com",)


def test_the_recorded_domain_is_the_FINAL_post_redirect_host():
    """DEC-20's purpose is exposing where content ACTUALLY came from, and a
    redirect is exactly the case where the requested host and the read host
    differ. Recording the requested one would report an intention, not a fact."""
    def handler(request):
        if request.headers.get("host") == "start.example.com":
            return httpx.Response(301, headers={"location": "https://final.example.com/p"})
        return httpx.Response(200, text=_html("body text of the final page"),
                              headers={"content-type": "text/html"})

    collector = FetchedDomains()
    result = _fetch("https://start.example.com/p",
                    {"start.example.com": ["93.184.216.34"],
                     "final.example.com": ["93.184.216.35"]},
                    handler=handler, domains=collector)
    assert result.ok and result.domain == "final.example.com"
    assert collector.domains() == ("final.example.com",)


def test_a_failed_fetch_records_nothing():
    """The badge means "content actually retrieved and read". A blocked, refused
    or unsupported fetch read nothing, so it must claim nothing."""
    collector = FetchedDomains()
    result = _fetch("https://blocked.example.com/p",
                    {"blocked.example.com": ["127.0.0.1"]}, domains=collector)
    assert not result.ok
    assert collector.domains() == ()


def test_a_cached_page_still_counts_as_read_this_turn():
    """DEC-17: the cache does not launder taint. By the same logic a cache hit
    IS content the model read this turn, so it belongs on the badge — and the
    single recording site on the public entry covers it without a second path."""
    collector = FetchedDomains()
    mapping = {"docs.example.com": ["93.184.216.34"]}
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, text=_html("cached body text goes here"),
                              headers={"content-type": "text/html"})

    async def go():
        fetcher = HardenedFetcher(
            client_factory=lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(handler), trust_env=False,
                follow_redirects=False, headers={"User-Agent": USER_AGENT}),
            resolver=lambda hostname, port: mapping[hostname],
            robots_enabled=False, domains=collector)
        try:
            await fetcher.fetch_readable("https://docs.example.com/p")
            collector.new_turn()                       # a new turn begins
            second = await fetcher.fetch_readable("https://docs.example.com/p")
        finally:
            await fetcher.aclose()
        return second

    second = asyncio.run(go())
    assert second.from_cache is True and calls["n"] == 1  # really was the cache
    assert collector.domains() == ("docs.example.com",)


def test_robots_lookups_are_never_recorded():
    """robots.txt is machinery, not content the user was shown. It travels a
    separate internal path, so it can never be mistaken for a source."""
    collector = FetchedDomains()
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /",
                                  headers={"content-type": "text/plain"})
        return httpx.Response(200, text=_html("body"),
                              headers={"content-type": "text/html"})

    result = _fetch("https://docs.example.com/p", {"docs.example.com": ["93.184.216.34"]},
                    handler=handler, domains=collector, robots_enabled=True)
    assert not result.ok                    # robots disallowed the page
    assert collector.domains() == ()        # ...and nothing was recorded


# ─── NEVER through plugin code — structural, source AND attribute ────────────


def test_no_plugin_source_can_reach_the_provenance_collector():
    """The deciding property, as STRUCTURE. An attribute scan alone is not
    enough — a domain could be produced as a literal or parsed out of text — so
    the plugin tree is scanned for any reference to the collector, its module,
    or its recording verb."""
    forbidden = {"FetchedDomains", "provenance", "record_domain", "domains"}
    for source in sorted(PLUGINS.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
        leaked = forbidden & names
        assert not leaked, f"{source.relative_to(PLUGINS)} reaches the collector: {leaked}"


def test_the_web_plugin_holds_no_collector_attribute():
    plugin = WebResearchPlugin(provider=None)
    attrs = {n.lstrip("_") for n in vars(plugin)} | {
        n for n in dir(plugin) if not n.startswith("__")}
    assert not ({"domains", "provenance", "badge", "FetchedDomains"} & attrs)


def test_a_search_performs_zero_collector_writes():
    """Refinement 4 as behaviour: five candidate links the model did not read
    must not become five claims that it did."""
    class _Hit:
        def __init__(self, url):
            self.url, self.title, self.snippet = url, "t", "s"

    class _Provider:
        name, cost_per_query_usd = "fake", 0.0

        async def search(self, query, *, max_results=5):
            class _R:
                ok, text_ar, cost_usd = True, "", 0.0
                results = tuple(_Hit(f"https://site{i}.example/p") for i in range(5))
            return _R()

    collector = FetchedDomains()
    plugin = WebResearchPlugin(provider=_Provider())
    result = asyncio.run(plugin.execute("search", {"query": "x"}, PluginContext()))

    assert result.is_error is False
    assert "site0.example" in result.text_ar     # carried as DATA for the model
    assert collector.domains() == ()             # ...but claimed by nobody


# ─── The collector's own contract ────────────────────────────────────────────


def test_new_turn_restores_an_empty_record():
    collector = FetchedDomains()
    collector.record("a.example")
    collector.record("b.example")
    assert collector.domains() == ("a.example", "b.example")
    collector.new_turn()
    assert collector.domains() == ()


def test_the_record_is_ordered_deduped_bounded_and_defensive():
    collector = FetchedDomains()
    for _ in range(2):
        collector.record("Docs.Example.COM")     # case-folded, deduped
    collector.record("  b.example  ")            # trimmed
    collector.record("")                         # ignored
    collector.record(None)                       # never raises
    collector.record(12345)
    assert collector.domains() == ("docs.example.com", "b.example")

    for i in range(MAX_TRACKED_DOMAINS + 5):     # bounded
        collector.record(f"h{i}.example")
    assert len(collector.domains()) == MAX_TRACKED_DOMAINS


def test_the_collector_returns_a_defensive_copy():
    collector = FetchedDomains()
    collector.record("a.example")
    snapshot = collector.domains()
    collector.record("b.example")
    assert snapshot == ("a.example",)  # the badge cannot mutate the record


def test_the_collector_module_imports_nothing_and_cannot_log():
    """DEC-20/DEC-28: a domain must not reach a log. The safest way to keep one
    out is to have no way to write it — so the module has no logger at all, and
    that is asserted structurally rather than promised."""
    source = SRC / "muthis" / "broker" / "net" / "provenance.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert imported <= {"__future__"}, imported


def test_recording_emits_no_log_line_anywhere(caplog):
    collector = FetchedDomains()
    with caplog.at_level(logging.DEBUG):
        collector.record("secret-internal.example.com")
        logging.getLogger("positive.control").warning("control")  # not an empty log
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "control" in text
    assert "secret-internal.example.com" not in text


# ─── Rendering: domain only, and never the caption's budget ──────────────────


def test_the_badge_shows_domains_only_and_never_a_url():
    text = format_badge(["docs.python.org", "developer.mozilla.org"])
    assert text.startswith(SOURCE_LABEL_AR)
    assert "docs.python.org" in text and "developer.mozilla.org" in text
    assert "http" not in text and "?" not in text and "/" not in text


def test_nothing_read_renders_nothing():
    """An empty badge is the honest signal for a snippet-only answer — not a
    blank chip that looks like a source."""
    assert format_badge([]) == ""
    assert format_badge(["", "   ", None]) == ""


def test_the_badge_is_bounded_and_counts_the_overflow():
    text = format_badge([f"s{i}.example" for i in range(6)])
    assert text.count("·") == MAX_SHOWN - 1
    assert "+3" in text  # the rest are COUNTED, never silently dropped


def test_the_badge_never_eats_the_captions_text_budget():
    """DEC-20: the VOICE carries the teaching. The badge is its own element with
    its own anchor and tag, so it cannot consume a line of speech.

    DEC-128 (shape C2) moved MAX_LINES 2 -> 3 for rolling captions, and this
    guard now pins the axis that actually decides collision instead of both at
    once. The badge is bottom-LEFT, the caption bottom-CENTER, and
    `domain_badge.py` documents their separation as HORIZONTAL and "BY
    CONSTRUCTION": more LINES grow the chip UPWARD, away from the badge, while a
    wider LINE grows TOWARD it and would turn that structural guarantee into an
    offset that drifts with the font. So `MAX_CHARS_PER_LINE` is the number this
    test exists to hold; `MAX_LINES` is DECLARED here, not owned here — moving it
    is a caption decision, and the message says so rather than reading as "the
    badge broke"."""
    assert DOMAIN_BADGE_TAG != CAPTION_TAG
    assert MAX_CHARS_PER_LINE == 60, (
        "the caption's HORIZONTAL budget moved — that is the axis the badge's "
        "collision-freedom rests on. Re-check domain_badge.py's bottom-left "
        "anchor before declaring this")
    assert MAX_LINES == 3, (
        "the caption's LINE COUNT moved. Harmless for the badge (the chip grows "
        "upward, away from it) — but declare it as a caption decision: see "
        "DEC-128 shape C2, where 3 was measured and 4 buys nothing")


class _Canvas:
    """Duck-typed canvas: records items per tag, so tag scoping is observable."""

    def __init__(self):
        self.items: dict[int, str] = {}
        self.deleted: list[str] = []
        self._next = 0

    def _add(self, tags):
        self._next += 1
        self.items[self._next] = tags
        return self._next

    def create_text(self, *a, **kw):
        return self._add(kw.get("tags", ""))

    def create_polygon(self, *a, **kw):
        return self._add(kw.get("tags", ""))

    def bbox(self, item):
        return (10, 10, 100, 30)

    def tag_lower(self, a, b):
        pass

    def delete(self, tag):
        self.deleted.append(tag)
        self.items = {i: t for i, t in self.items.items() if t != tag}


def test_the_badge_is_tag_scoped_and_never_deletes_all():
    canvas = _Canvas()
    caption_item = canvas._add(CAPTION_TAG)     # a caption sharing the canvas
    badge = DomainBadge(canvas, (1920, 1080))

    badge.show(["docs.python.org"])
    assert all(t == DOMAIN_BADGE_TAG for i, t in canvas.items.items() if i != caption_item)
    badge.clear()

    assert "all" not in canvas.deleted
    assert canvas.deleted == [DOMAIN_BADGE_TAG, DOMAIN_BADGE_TAG]
    assert canvas.items[caption_item] == CAPTION_TAG  # the caption survived


# ─── The inherited lifecycle, through the REAL dispatcher ────────────────────


class _Spy:
    def __init__(self):
        self.calls: list = []

    def show(self, domains):
        self.calls.append(("show", tuple(domains)))

    def clear(self):
        self.calls.append(("clear",))

    # the other view objects dispatch_command needs
    def __getattr__(self, name):
        def _noop(*a, **kw):
            self.calls.append((name,))
        return _noop


def _dispatch(command, badge):
    spy = _Spy()
    return dispatch_command(command, rect=_Spy(), pointer=_Spy(), animator=_Spy(),
                            caption=spy, badge=badge)


@pytest.mark.parametrize("command", [("clear_caption",), ("hide",)])
def test_the_badge_is_cleared_by_the_captions_own_lifecycle(command):
    """DEC-20: `clear()` and the hide-before-capture chokepoint cover ghosting
    with NO new code — so the badge must ride the SAME commands, not its own."""
    badge = _Spy()
    _dispatch(command, badge)
    assert ("clear",) in badge.calls


def test_show_domain_badge_reaches_the_badge_and_nothing_else():
    badge = _Spy()
    _dispatch(("show_domain_badge", ("docs.python.org",)), badge)
    assert badge.calls == [("show", ("docs.python.org",))]


def test_the_dispatcher_stays_backward_compatible_without_a_badge():
    """Every pre-badge call site and fake must keep working — the optional-kwarg
    discipline every overlay widget before this one followed."""
    assert dispatch_command(("hide",), rect=_Spy(), pointer=_Spy(), animator=_Spy()) is True
    assert dispatch_command(("show_domain_badge", ("a.example",)),
                            rect=_Spy(), pointer=_Spy(), animator=_Spy()) is True
