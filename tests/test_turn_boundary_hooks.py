# tests/test_turn_boundary_hooks.py
"""
The DEC-37 turn boundary, driven END TO END through the real kernel path.

WHY THIS FILE EXISTS AT ALL: cross-turn leakage is invisible to every
single-turn test. `FetchGate` and `FetchedDomains` both looked correct for a
whole milestone while resetting NOTHING — they were inert, and only a test that
runs TURN 1 and then TURN 2 can tell an enforced cap from an unwired one. So the
two load-bearing assertions here are both about the SECOND turn: a fetch in turn
1 must not count against turn 2's cap, and turn 2's badge must not carry turn 1's
domains (a stale badge would attribute a source the turn never read — inverting
the whole point of DEC-20's deterministic backstop).

The wiring is exercised REAL, not simulated: a real `ToolRouter` carrying real
`turn_hooks`, a real `TurnPass` firing them from `new_turn_voice()`, the real
`WebResearchPlugin` with its real `FetchGate`, and the real `Broker` owning a
real `FetchedDomains`. The ONLY fake is `ctx.net.fetch_readable`, which stands in
for the hardened fetcher's network — and it records the domain at the same single
site the real fetcher does (`test_domain_badge.py` proves that recording).

No test here imports `muthis.main` (standing rule — live credentials); the
composition root's registration is asserted by AST source scan instead.
"""

from __future__ import annotations

import ast
import asyncio
import pathlib

from muthis.broker.broker import Broker
from muthis.broker.grants import GrantsStore
from muthis.broker.net import FetchedDomains
from muthis.cloud.protocol import TurnComplete, UserInput
from muthis.kernel.highlight_gate import HighlightGate
from muthis.kernel.tool_router import ToolRouter
from muthis.kernel.turn import TurnResult
from muthis.kernel.turn_pass import TurnPass
from muthis.overlay.domain_badge import format_badge
from muthis_plugins.web_research.fetch_gate import MAX_FETCHES_PER_TURN
from muthis_plugins.web_research.plugin import WebResearchPlugin
from muthis_sdk import NetCapability, PluginContext

COMPOSITION_PY = (
    pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis" / "composition.py"
)


# ─── The real graph, minus the network ───────────────────────────────────────


class _FakePage:
    def __init__(self, domain: str) -> None:
        self.ok = True
        self.domain = domain
        self.content = "نص الصفحة"


def _net_recording_into(collector: FetchedDomains) -> NetCapability:
    """`ctx.net`, standing in for the hardened fetcher: it records the FINAL
    domain into the collector at the same ONE site the real fetcher uses."""

    async def fetch_readable(url: str):
        domain = url.split("//", 1)[-1].split("/", 1)[0]
        collector.record(domain)  # what HardenedFetcher does, first-hand
        return _FakePage(domain)

    return NetCapability(fetch_readable=fetch_readable)


class _FakeReasoner:
    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        yield TurnComplete(input_tokens=1, output_tokens=1, cost_usd=0.0,
                           stop_reason="end_turn", model="fake")


class _FakeBudget:
    def record_turn(self, turn_complete):
        return None


class _FakeVoice:
    async def ensure_open(self):
        return False

    async def speak_or_feed(self, text):
        return None


def _graph(*, register_plugin=True, register_broker=True):
    """The production shape: each consumer's OWN owner supplies the reset, and
    the router only carries them."""
    collector = FetchedDomains()
    broker = Broker(grants=GrantsStore(), fetched_domains=collector)
    plugin = WebResearchPlugin()
    hooks = []
    if register_plugin:
        hooks.append(plugin.new_turn)
    if register_broker:
        hooks.append(broker.new_turn)
    router = ToolRouter(turn_hooks=tuple(hooks))
    turn_pass = TurnPass(reasoner=_FakeReasoner(), budget=_FakeBudget(),
                         overlay=object(), voice=object(), stream_tts=False,
                         router=router)
    ctx = PluginContext(net=_net_recording_into(collector))
    return turn_pass, router, plugin, collector, ctx


def _begin_turn(turn_pass) -> None:
    """A real turn boundary: exactly what the orchestrator calls."""
    turn_pass.new_turn_voice()


def _run_pass(turn_pass, text="افتح لي الصفحة") -> None:
    asyncio.run(turn_pass.consume(UserInput(text=text), None, [],
                                  HighlightGate(), TurnResult(), _FakeVoice()))


def _fetch(plugin, ctx, url):
    return asyncio.run(plugin.execute("fetch", {"url": url}, ctx))


# ─── THE TWO CROSS-TURN INVARIANTS ───────────────────────────────────────────


def test_a_fetch_in_turn_one_does_not_count_against_turn_twos_cap():
    """DEC-22 is a PER-USER-TURN cap. Without the wiring this bounds the whole
    PROCESS, and the third turn of a session would be unable to read anything."""
    turn_pass, _router, plugin, _collector, ctx = _graph()

    _begin_turn(turn_pass)                      # ── turn 1
    _run_pass(turn_pass)
    for i in range(MAX_FETCHES_PER_TURN):
        assert _fetch(plugin, ctx, f"https://a{i}.example/p").is_error is False
    spent = _fetch(plugin, ctx, "https://a3.example/p")
    assert spent.is_error is True, "the cap did not bind inside turn 1 — vacuous"

    _begin_turn(turn_pass)                      # ── turn 2
    _run_pass(turn_pass)

    fresh = _fetch(plugin, ctx, "https://b0.example/p")
    assert fresh.is_error is False, "turn 1's fetches were charged to turn 2"
    assert plugin._gate.fetches_remaining() == MAX_FETCHES_PER_TURN - 1


def test_turn_twos_badge_does_not_carry_turn_ones_domains():
    """DEC-20/DEC-36: the badge means "content retrieved and read THIS turn". A
    domain surviving into the next turn would attribute a source the turn never
    read — the deterministic backstop corroborating a fabrication."""
    turn_pass, _router, plugin, collector, ctx = _graph()

    _begin_turn(turn_pass)                      # ── turn 1
    _fetch(plugin, ctx, "https://docs.python.org/3/library/asyncio.html")
    assert collector.domains() == ("docs.python.org",), "nothing recorded — vacuous"
    assert "docs.python.org" in format_badge(collector.domains())

    _begin_turn(turn_pass)                      # ── turn 2

    assert collector.domains() == (), "turn 1's domains survived into turn 2"
    assert format_badge(collector.domains()) == "", "a stale badge would be drawn"

    _fetch(plugin, ctx, "https://peps.python.org/pep-0008/")
    assert collector.domains() == ("peps.python.org",)
    assert "docs.python.org" not in format_badge(collector.domains())


# ─── Each consumer resets through its OWN owner ──────────────────────────────


def test_registering_only_the_plugin_leaves_the_collector_unreset():
    """The two consumers are independent by design — one hook per OWNER. This is
    the negative control for the test above: if a single registration reset both,
    the composition root's two-entry tuple would be untested ceremony."""
    turn_pass, _router, plugin, collector, ctx = _graph(register_broker=False)

    _begin_turn(turn_pass)
    _fetch(plugin, ctx, "https://a.example/p")
    _begin_turn(turn_pass)

    assert collector.domains() == ("a.example",)   # broker.new_turn was never registered
    assert plugin._gate.fetches_remaining() == MAX_FETCHES_PER_TURN  # plugin's own did run


def test_registering_only_the_broker_leaves_the_cap_unreset():
    turn_pass, _router, plugin, collector, ctx = _graph(register_plugin=False)

    _begin_turn(turn_pass)
    for i in range(MAX_FETCHES_PER_TURN):
        _fetch(plugin, ctx, f"https://a{i}.example/p")
    _begin_turn(turn_pass)

    assert _fetch(plugin, ctx, "https://b.example/p").is_error is True
    assert collector.domains() == ()                # the broker's own hook DID run


# ─── The carrier's contract ──────────────────────────────────────────────────


def test_the_router_carries_an_immutable_tuple_it_never_inspects():
    """DEC-37: a BLIND CARRIER. The field is public because no security
    invariant applies (contrast session_taint / confirm_gate, which must not be
    swappable) — but the contents must still not be mutable in place."""
    router = ToolRouter(turn_hooks=[lambda: None])   # a LIST goes in...
    assert isinstance(router.turn_hooks, tuple), "the carrier stored a mutable list"
    assert router.turn_hooks == tuple(router.turn_hooks)


def test_a_default_router_carries_no_hooks():
    assert ToolRouter().turn_hooks == ()


def test_a_raising_hook_never_kills_the_turn():
    """The InterruptHooks discipline (DEC-3-C), applied at the turn boundary:
    bookkeeping may not take down a turn (Law 11). It is LOGGED, never silently
    swallowed — a reset that failed must be visible."""
    calls = []

    def boom():
        calls.append("boom")
        raise RuntimeError("hook exploded")

    def after():
        calls.append("after")

    router = ToolRouter(turn_hooks=(boom, after))
    turn_pass = TurnPass(reasoner=_FakeReasoner(), budget=_FakeBudget(),
                         overlay=object(), voice=object(), stream_tts=False,
                         router=router)

    turn_pass.new_turn_voice()   # must not raise

    assert calls == ["boom", "after"], "a raising hook stopped the later ones"


def test_a_raising_hook_is_logged(caplog):
    router = ToolRouter(turn_hooks=(lambda: 1 / 0,))
    turn_pass = TurnPass(reasoner=_FakeReasoner(), budget=_FakeBudget(),
                         overlay=object(), voice=object(), stream_tts=False,
                         router=router)

    with caplog.at_level("WARNING"):
        turn_pass.new_turn_voice()

    assert any("turn-boundary hook raised" in r.message for r in caplog.records)


def test_the_sandbox_gate_still_resets_on_the_same_hook():
    """DEC-19: ONE turn-boundary hook, now with several consumers. The proven
    T5 path must keep working beside the two new ones."""
    class _FakeSandbox:
        def __init__(self):
            self.turns = 0

        def new_turn(self):
            self.turns += 1

    sandbox = _FakeSandbox()
    turn_pass, _router, plugin, _collector, _ctx = _graph()
    turn_pass._sandbox = sandbox          # the injected servicer seam
    turn_pass.new_turn_voice()

    assert sandbox.turns == 1


# ─── The composition root, by SOURCE SCAN (never an import) ──────────────────


def test_the_composition_root_registers_both_owners_on_the_turn_boundary():
    """AST, not an import: `composition.py` is reached from `muthis.main`, which
    runs `load_dotenv()` at module level. Without this the carrier could be
    perfect while production registers nothing — both guards silently inert
    again, which is exactly the state this commit exists to end."""
    tree = ast.parse(COMPOSITION_PY.read_text(encoding="utf-8"))

    registered = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "build_core_router"
        and any(kw.arg == "turn_hooks" for kw in node.keywords)
    ]
    assert registered, "the composition root no longer registers any turn hooks"

    (hooks_kw,) = [kw for kw in registered[0].keywords if kw.arg == "turn_hooks"]
    owners = {
        f"{getattr(elt.value, 'id', '')}.{elt.attr}"
        for elt in getattr(hooks_kw.value, "elts", [])
        if isinstance(elt, ast.Attribute)
    }
    assert owners == {"web_plugin.new_turn", "broker.new_turn"}, (
        f"each consumer must reset through its OWN owner (DEC-37); found {owners}")

    # The VALUE, not merely the keyword: `fetched_domains=None` would keep the
    # argument present while the badge accumulated for the whole process. (A
    # mutation caught exactly that hole in this assertion — a guard that checks
    # for a parameter's NAME checks nothing about what production wires.)
    owned = [
        kw for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Broker"
        for kw in node.keywords if kw.arg == "fetched_domains"
    ]
    assert owned, "the broker no longer owns the provenance collector (D2)"
    assert all(isinstance(kw.value, ast.Name) for kw in owned), (
        "the broker must be handed the real collector, not a constant (D2)")
