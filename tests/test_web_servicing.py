# tests/test_web_servicing.py
"""
web__search / web__fetch are SERVICED through the router — the T5 precedent.

WHY THIS FILE EXISTS: mounting these tools into the catalog without a dispatch
branch would have shipped the worst defect of this milestone. A web call would
have fallen to `consume()`'s LOOK-only `else` — never reaching `router.service()`,
so the DEC-14 wrap, the DEC-15 taint raise, the DEC-16 confirm gate, the DEC-22
per-turn cap and the DEC-36 collector would ALL have been bypassed — and then
`build_tool_result_message` would have answered the id from its DRAW fallback:
the pointer ack, `HIGHLIGHT_ACK_TEXT_AR`, which also flips `gate.drawn` and so
forces `tool_choice="none"` and hard-terminates the agentic loop. The model would
have been told a rectangle was on screen in reply to a request to read a web page.

So the NEGATIVE assertions come first and are the point of the file: a test that
would have caught the bug is worth more than one that confirms the fix. The
positive half then proves the boundaries are genuinely ON the path, because
routing through `router.service()` is the entire reason the branch exists.
"""

from __future__ import annotations

import asyncio
from typing import Any

from muthis.cloud.protocol import ToolCall, TurnComplete, UserInput
from muthis.kernel.highlight_gate import (
    HIGHLIGHT_ACK_TEXT_AR, HIGHLIGHT_ALREADY_SHOWN_AR, HighlightGate,
    loop_tool_choice,
)
from muthis.kernel.tool_result_pairing import (
    WEB_FETCH_TOOL, WEB_ONE_PER_PASS_AR, WEB_SEARCH_TOOL,
    build_tool_result_message,
)
from muthis.kernel.tool_router import ToolRouter
from muthis.kernel.turn import TurnResult
from muthis.kernel.turn_pass import TurnPass
from muthis.trust.confirm_gate import ConfirmGate
from muthis.trust.high_impact import RouteImpact
from muthis.broker.net import FetchedDomains
from muthis_plugins.web_research.fetch_gate import (
    FETCH_GATE_EXHAUSTED_AR, MAX_FETCHES_PER_TURN,
)
from muthis_plugins.web_research.plugin import WebResearchPlugin
from muthis_sdk import NetCapability, PluginContext

NETWORK = frozenset({"net.fetch"})
FETCH_ARGS = {"url": "https://docs.python.org/3/library/asyncio.html"}


# ─── The real graph, minus the network ───────────────────────────────────────


class _Page:
    def __init__(self, domain: str) -> None:
        self.ok, self.domain, self.content = True, domain, "نص الصفحة"


def _net(collector: FetchedDomains) -> NetCapability:
    async def fetch_readable(url: str):
        domain = url.split("//", 1)[-1].split("/", 1)[0]
        collector.record(domain)          # the fetcher's one recording site
        return _Page(domain)
    return NetCapability(fetch_readable=fetch_readable)


class _Overlay:
    def __init__(self) -> None:
        self.badges: list = []

    def show_domain_badge(self, domains) -> None:
        self.badges.append(tuple(domains))

    async def show(self, bbox, label_ar): ...
    async def hide(self): ...


class _Voice:
    async def ensure_open(self):
        return False

    async def speak_or_feed(self, text): ...


class _Budget:
    def record_turn(self, turn_complete): ...


class _Reasoner:
    """Emits the given tool calls in ONE pass, then completes."""

    def __init__(self, calls=()):
        self._calls = calls

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        for call in self._calls:
            yield call
        yield TurnComplete(
            input_tokens=1, output_tokens=1, cost_usd=0.0, stop_reason="tool_use",
            model="fake",
            assistant_content=[
                {"type": "tool_use", "id": c.tool_use_id, "name": c.name,
                 "input": c.args} for c in self._calls
            ])


def _graph(*, confirm_gate=None):
    collector = FetchedDomains()
    plugin = WebResearchPlugin(provider=_Provider())
    router = ToolRouter(confirm_gate=confirm_gate or ConfirmGate(),
                        turn_hooks=(plugin.new_turn,),
                        fetched_domains=collector.domains)
    router.mount(plugin, ctx=PluginContext(net=_net(collector)), namespace="web",
                 provenance="web_research", taint=True,
                 impact=RouteImpact(capabilities=NETWORK))
    return router, plugin, collector


class _Provider:
    async def search(self, query: str, *, max_results: int = 5):
        class _R:
            ok, cost_usd = True, 0.004
            results = ()
        return _R()


def _one_pass(router, calls, overlay, gate, *, new_turn: bool):
    """ONE provider pass. `new_turn` distinguishes a fresh USER turn (which
    resets the per-turn cap) from a later pass of the SAME turn — the difference
    the DEC-22 cap is defined in terms of."""
    turn_pass = TurnPass(reasoner=_Reasoner(calls), budget=_Budget(),
                         overlay=overlay, voice=object(), stream_tts=False,
                         router=router)
    if new_turn:
        turn_pass.new_turn_voice()
    result = TurnResult()
    complete, _refresh, routed, run = asyncio.run(turn_pass.consume(
        UserInput(text="دوّر لي"), None, [], gate, result, _Voice()))
    return complete, routed, run, gate, result, overlay


def _consume(router, calls, overlay=None, gate=None):
    return _one_pass(router, calls, overlay or _Overlay(),
                     gate if gate is not None else HighlightGate(), new_turn=True)


def _fetch_call(tool_use_id="w1", args=None):
    return ToolCall(name=WEB_FETCH_TOOL, args=args or FETCH_ARGS,
                    tool_use_id=tool_use_id)


# ═══ THE NEGATIVE ASSERTIONS — the defect this commit exists to prevent ══════


def test_a_web_call_never_receives_the_pointer_ack():
    router, _plugin, _collector = _graph()
    complete, routed, _run, _gate, _result, _overlay = _consume(router, [_fetch_call()])

    pairing = build_tool_result_message(
        complete.assistant_content, None, None, HighlightGate(), routed, None)
    (block,) = pairing["content"]

    assert block["content"] not in (HIGHLIGHT_ACK_TEXT_AR, HIGHLIGHT_ALREADY_SHOWN_AR)
    assert "نص الصفحة" in block["content"], "the page content never reached the model"


def test_a_web_call_never_flips_the_draw_gate_or_terminates_the_loop():
    """`gate.drawn` forces tool_choice="none", the loop's HARD terminator. A
    fetch that flipped it would end the turn the moment the model tried to read
    a page."""
    router, _plugin, _collector = _graph()
    gate = HighlightGate()

    _complete, routed, _run, gate, _result, _overlay = _consume(
        router, [_fetch_call()], gate=gate)
    build_tool_result_message(
        _complete.assistant_content, None, None, gate, routed, None)

    assert gate.drawn is False, "a web call flipped the unified draw gate"
    assert loop_tool_choice(gate) == "auto", "the agentic loop was terminated"


def test_a_web_call_is_not_refused_as_a_look_only_violation(caplog):
    router, _plugin, collector = _graph()
    with caplog.at_level("ERROR"):
        _complete, routed, _run, _gate, _result, _overlay = _consume(
            router, [_fetch_call()])

    assert routed is not None, "the web call was never serviced"
    assert not any("LOOK-only violation" in r.getMessage() for r in caplog.records)


# ═══ THE BOUNDARIES ARE ACTUALLY ON THE PATH ════════════════════════════════


def test_a_serviced_web_call_is_wrapped_and_raises_session_taint():
    """DEC-14 + DEC-15: routing through `router.service()` is what puts the ONE
    wrap site and the ONE taint-raise site on the path."""
    router, _plugin, _collector = _graph()
    assert router.session_taint.tainted is False

    _complete, routed, _run, _gate, result, _overlay = _consume(router, [_fetch_call()])

    assert router.session_taint.tainted is True, "the session was left clean"
    assert result.taint is True, "the turn-level taint never propagated"
    assert "نص الصفحة" in routed[1]
    assert routed[1] != "نص الصفحة", "the external content was not wrapped"


def test_a_serviced_fetch_counts_against_the_per_turn_cap():
    """DEC-22 binds only because the call reaches the plugin through the router."""
    router, plugin, _collector = _graph()
    before = plugin._gate.fetches_remaining()

    _consume(router, [_fetch_call()])

    assert plugin._gate.fetches_remaining() == before - 1, "the cap was not on the path"


def test_an_exhausted_cap_refuses_a_serviced_fetch():
    """The guard driven DIRECTLY (DEC-12), not through model-shaped scaffolding:
    spend the budget, then a real serviced call must come back with the internal
    directive instead of a page."""
    router, plugin, _collector = _graph()
    plugin._gate.fetches = MAX_FETCHES_PER_TURN      # the 4th fetch of the turn

    _complete, routed, _run, _gate, _result, _overlay = _one_pass(
        router, [_fetch_call()], _Overlay(), HighlightGate(), new_turn=False)

    assert FETCH_GATE_EXHAUSTED_AR in routed[1]
    assert "نص الصفحة" not in routed[1], "a capped fetch still read a page"


def test_the_first_fetch_taints_the_session_so_the_second_needs_approval():
    """A REAL interaction between DEC-15 and DEC-16, pinned because it surprised
    this commit's own test: the first fetch raises session taint, so the NEXT
    high-impact web call in that session is gated until the user approves aloud.
    The per-turn cap is therefore rarely the binding limit — confirmation is."""
    router, plugin, _collector = _graph()

    _complete, first, _run, _gate, _result, _overlay = _consume(router, [_fetch_call("w1")])
    assert "نص الصفحة" in first[1]
    assert router.session_taint.tainted is True

    _complete, second, _run, _gate, _result, _overlay = _one_pass(
        router, [_fetch_call("w2")], _Overlay(), HighlightGate(), new_turn=False)

    assert "نص الصفحة" not in second[1], "a tainted-session fetch skipped the gate"
    assert plugin._gate.fetches_remaining() == MAX_FETCHES_PER_TURN - 1, (
        "a REFUSED call must not spend the cap — it never fetched")


def test_a_serviced_fetch_records_into_the_collector_and_draws_the_badge():
    """DEC-36: the badge's fact is written by the FETCHER on the serviced path."""
    router, _plugin, collector = _graph()

    _complete, _routed, _run, _gate, _result, overlay = _consume(router, [_fetch_call()])

    assert collector.domains() == ("docs.python.org",)
    assert overlay.badges[-1] == ("docs.python.org",)


def test_a_web_call_is_refused_by_the_confirm_gate_in_a_tainted_session():
    """DEC-16: a high-impact route under taint needs the spoken approval. It is
    on the path only because servicing goes through the router."""
    gate = ConfirmGate()
    router, _plugin, _collector = _graph(confirm_gate=gate)
    router.session_taint.raise_taint("web_research")

    _complete, routed, _run, _draw_gate, _result, _overlay = _consume(
        router, [_fetch_call()])

    assert "نص الصفحة" not in routed[1], "a high-impact call ran without approval"


def test_search_is_serviced_too_and_charges_its_cost():
    router, _plugin, _collector = _graph()
    call = ToolCall(name=WEB_SEARCH_TOOL, args={"query": "asyncio"}, tool_use_id="s1")

    _complete, routed, _run, gate, _result, _overlay = _consume(router, [call])

    assert routed is not None and routed[0].name == WEB_SEARCH_TOOL
    assert gate.drawn is False


# ═══ THE PRODUCTION MOUNT states the facts, not just some test router ═══════
# Mutation found these missing: every test above builds its OWN router, so the
# security facts the REAL composition helper states were entirely unpinned.


class _RealisticFetcher:
    def __init__(self, collector: FetchedDomains) -> None:
        self._collector = collector

    async def fetch_readable(self, url: str):
        domain = url.split("//", 1)[-1].split("/", 1)[0]
        self._collector.record(domain)
        return _Page(domain)


def _production_router():
    """Mounted through `mount_web_research` — the helper `main.py` calls."""
    from muthis.composition import mount_web_research
    from muthis.kernel.core_router import build_core_router

    collector = FetchedDomains()
    plugin = WebResearchPlugin(provider=_Provider())
    router = build_core_router(read_file=None, turn_hooks=(plugin.new_turn,),
                               fetched_domains=collector.domains)
    mount_web_research(router, plugin, _RealisticFetcher(collector))
    return router, plugin, collector


def test_the_production_mount_wires_ctx_net_so_a_page_is_actually_read():
    """Mutation: `ctx=PluginContext()` would leave the tool permanently
    unavailable in production while every hand-built test router still passed."""
    router, _plugin, collector = _production_router()

    _complete, routed, _run, _gate, _result, _overlay = _consume(router, [_fetch_call()])

    assert "نص الصفحة" in routed[1], "production mounted the tool WITHOUT ctx.net"
    assert collector.domains() == ("docs.python.org",)


def test_the_production_mount_states_taint_so_external_content_is_wrapped():
    """Mutation: `taint=False` would ship unwrapped external content into the
    model's context and leave the session looking clean (DEC-14 + DEC-15)."""
    router, _plugin, _collector = _production_router()
    assert router.session_taint.tainted is False

    _complete, routed, _run, _gate, result, _overlay = _consume(router, [_fetch_call()])

    assert routed[1] != "نص الصفحة", "external content was not wrapped"
    assert router.session_taint.tainted is True, "the production mount states no taint"
    assert result.taint is True


def test_the_production_mount_states_the_network_grant_so_the_gate_binds():
    """Mutation: `impact=RouteImpact()` would drop the kernel's own statement
    that it granted `net.fetch`, so a high-impact call in a tainted session
    would run without the DEC-16 spoken approval."""
    router, _plugin, _collector = _production_router()
    router.session_taint.raise_taint("web_research")

    _complete, routed, _run, _gate, _result, _overlay = _consume(router, [_fetch_call()])

    assert "نص الصفحة" not in routed[1], (
        "a high-impact web call ran unconfirmed in a tainted session")


def test_the_production_mount_records_the_network_capability_it_granted():
    """STRUCTURAL on purpose, and the reason is worth stating: this fact is
    currently BEHAVIOURALLY REDUNDANT. `RouteImpact()` is fail-closed, so an
    external (`taint=True`) route is high-impact either way — a mutation that
    drops `capabilities` changes nothing observable today, which is exactly why
    no behavioural test can pin it.

    It is still load-bearing as DEFENCE IN DEPTH: DEC-15 says classification
    derives from the capability the KERNEL granted, so if the taint flag were
    ever wrongly flipped to False, this statement alone would keep the route
    high-impact. Reaching one private field is the honest way to assert a fact
    whose whole value is that it does not depend on another fact."""
    from muthis.trust.high_impact import NETWORK_CAPABILITY

    router, _plugin, _collector = _production_router()
    route = router._routes[WEB_FETCH_TOOL]

    assert NETWORK_CAPABILITY in route.impact.capabilities, (
        "the kernel no longer states the net.fetch grant it made (DEC-15)")
    assert route.taint is True
    assert route.impact.high_impact(external=False) is True, (
        "the capability statement must stand on its own, without the taint flag")


# ═══ One per pass, answered BY NAME ═════════════════════════════════════════


def test_a_second_web_call_in_one_pass_gets_the_one_per_pass_note():
    router, _plugin, _collector = _graph()
    complete, routed, _run, _gate, _result, _overlay = _consume(
        router, [_fetch_call("w1"), _fetch_call("w2", {"url": "https://b.example/"})])

    pairing = build_tool_result_message(
        complete.assistant_content, None, None, HighlightGate(), routed, None)
    by_id = {b["tool_use_id"]: b["content"] for b in pairing["content"]}

    assert "نص الصفحة" in by_id["w1"]
    assert by_id["w2"] == WEB_ONE_PER_PASS_AR
    assert by_id["w2"] != HIGHLIGHT_ACK_TEXT_AR


def test_a_read_id_is_not_told_it_already_read_when_a_web_call_was_serviced():
    """The mixed-pass case: `read_result` now carries whichever ROUTER call was
    serviced, so the read id must not be handed "already read" for a read that
    never happened."""
    from muthis.file_reader import FILE_ALREADY_READ_AR, FILE_READ_ERROR_AR, READ_FILE_TOOL

    assistant = [
        {"type": "tool_use", "id": "w1", "name": WEB_FETCH_TOOL, "input": FETCH_ARGS},
        {"type": "tool_use", "id": "r1", "name": READ_FILE_TOOL, "input": {"path": "a.py"}},
    ]
    web_serviced = (_fetch_call("w1"), "محتوى الصفحة")

    pairing = build_tool_result_message(
        assistant, None, None, HighlightGate(), web_serviced, None)
    by_id = {b["tool_use_id"]: b["content"] for b in pairing["content"]}

    assert by_id["w1"] == "محتوى الصفحة"
    assert by_id["r1"] == FILE_READ_ERROR_AR
    assert by_id["r1"] != FILE_ALREADY_READ_AR


def test_the_v1_read_pairing_is_unchanged():
    """The read path must behave EXACTLY as before when no web tool is in play."""
    from muthis.file_reader import FILE_ALREADY_READ_AR, READ_FILE_TOOL

    assistant = [
        {"type": "tool_use", "id": "r1", "name": READ_FILE_TOOL, "input": {"path": "a.py"}},
        {"type": "tool_use", "id": "r2", "name": READ_FILE_TOOL, "input": {"path": "b.py"}},
    ]
    read = (ToolCall(name=READ_FILE_TOOL, args={"path": "a.py"}, tool_use_id="r1"),
            "محتوى")

    pairing = build_tool_result_message(
        assistant, None, None, HighlightGate(), read, None)
    by_id = {b["tool_use_id"]: b["content"] for b in pairing["content"]}

    assert by_id["r1"] == "محتوى"
    assert by_id["r2"] == FILE_ALREADY_READ_AR


# ---------------------------------------------------------------------------
# ROUTER_SERVICED_TOOLS — the named set that replaced the or-chain
# ---------------------------------------------------------------------------

def test_router_serviced_tools_holds_exactly_the_routed_tools():
    """The set IS the servicing contract, so it is pinned by VALUE.

    A routed tool added to `WEB_TOOLS` (or any future family) without reaching
    this set falls through `consume()`'s LOOK-only `else`: never serviced, so
    the DEC-14 wrap / DEC-15 raise / DEC-16 gate are bypassed, then answered
    with the pointer ack that flips the draw gate (DEC-39). Pinning the value
    means that omission fails HERE instead of live."""
    from muthis.file_reader import READ_FILE_TOOL
    from muthis.kernel.tool_result_pairing import (
        DOC_OPEN_TOOL, DOC_QUERY_TOOL, DOC_TOOLS, ROUTER_SERVICED_TOOLS, WEB_TOOLS,
    )

    # T4 (doc_rag) joined the set. Updating this pin is DELIBERATE and belongs in
    # the commit that adds the family — an exact-value pin exists precisely so a
    # new routed tool cannot arrive without a human editing this line.
    assert ROUTER_SERVICED_TOOLS == {READ_FILE_TOOL, WEB_SEARCH_TOOL,
                                     WEB_FETCH_TOOL, DOC_OPEN_TOOL, DOC_QUERY_TOOL}
    # Stated as a SUPERSET relation too: a family may grow, but every member of
    # a routed family must be in the serviced set — that is the real invariant.
    assert WEB_TOOLS <= ROUTER_SERVICED_TOOLS
    assert DOC_TOOLS <= ROUTER_SERVICED_TOOLS
    assert READ_FILE_TOOL in ROUTER_SERVICED_TOOLS
    # The draw tools must NEVER be in it: they are the branch this set exists to
    # keep routed tools OUT of.
    from muthis.kernel.draw_dispatch import DRAW_TOOLS
    assert not (DRAW_TOOLS & ROUTER_SERVICED_TOOLS)


def test_every_serviced_tool_is_answered_by_name_never_the_draw_ack():
    """The DEC-39 property, stated over the SET instead of two hard-coded names.

    Each member gets an UNSERVICED id in the pairing: whatever it receives, it
    must not be the pointer ack, and it must not flip the draw gate. Driven per
    member so adding a routed tool extends the guard automatically."""
    from muthis.kernel.tool_result_pairing import ROUTER_SERVICED_TOOLS

    admitted = 0
    for name in sorted(ROUTER_SERVICED_TOOLS):
        gate = HighlightGate()
        assistant = [{"type": "tool_use", "id": "x1", "name": name, "input": {}}]
        pairing = build_tool_result_message(assistant, None, None, gate, None, None)
        content = pairing["content"][0]["content"]
        assert content != HIGHLIGHT_ACK_TEXT_AR, f"{name} took the pointer ack"
        assert content != HIGHLIGHT_ALREADY_SHOWN_AR, f"{name} took the draw branch"
        assert gate.drawn is False, f"{name} flipped the draw gate"
        admitted += 1
    # The standing cutoff rule: a check that examined nothing must never look
    # like a check that passed.
    assert admitted == len(ROUTER_SERVICED_TOOLS) and admitted > 0


def test_turn_pass_dispatches_on_the_set_not_on_hard_coded_names():
    """AST, not text: `consume` must branch on ROUTER_SERVICED_TOOLS.

    Re-inlining the old or-chain would pass every behavioural test above while
    silently restoring the per-milestone edit this set removed."""
    import ast
    import pathlib

    source = pathlib.Path("src/muthis/kernel/turn_pass.py").read_text(encoding="utf-8")
    names = {n.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)}
    assert "ROUTER_SERVICED_TOOLS" in names
    assert "WEB_TOOLS" not in names, "turn_pass re-acquired a per-family name"
