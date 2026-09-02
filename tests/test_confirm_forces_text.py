# tests/test_confirm_forces_text.py
"""
DEC-131 (1): a REFUSED, UNAPPROVED high-impact call forces tool_choice="none".

WHY THIS EXISTS, MEASURED RATHER THAN SUPPOSED. `gate.drawn` was the ONLY route
to "none" in the whole tree, so a draw was this system's single forcing function
for speech. A web turn under taint draws nothing, never left "auto", and the
model spent every pass re-calling the tool the gate had just refused: 16 refusals
across 4 turns, four agentic caps, and the user was NEVER ASKED — the note
ordering the request was delivered on a channel nothing obliged the model to use.

THE PREDICATE IS THE TRAP, AND `test_an_APPROVED_pending_does_NOT_force` IS THE
TEST THAT MATTERS. The obvious predicate — "something is pending" — stays TRUE
across the approval, because `observe()` marks the pending approved and leaves it
in place. A brake keyed on that would gag the very pass that must re-issue the
approved call, so the approval could never be spent and the fix would break the
success path it exists to reach. That test carries its own control: it asserts
`pending_tool` is STILL set at the moment the brake must NOT fire, so it fails if
someone "simplifies" the predicate back.
"""

from __future__ import annotations

import asyncio
import pathlib

from muthis.kernel.highlight_gate import HighlightGate, loop_tool_choice
from muthis.kernel.tool_router import ToolRouter, namespaced_name
from muthis.trust.confirm_gate import APPROVAL_WORD_AR, ConfirmGate
from muthis.trust.high_impact import NETWORK_CAPABILITY, RouteImpact
from muthis_sdk import ToolDescriptor, ToolPlugin, ToolResult

SEARCH = namespaced_name("web", "search")
NETWORK = frozenset({NETWORK_CAPABILITY})
ARGS = {"query": "بايثون"}


class _WebPlugin(ToolPlugin):
    def descriptors(self):
        return [ToolDescriptor(name="search",
                               schema={"name": "search", "description": "d",
                                       "input_schema": {}},
                               kernel_serviced=False)]

    async def execute(self, tool, args, ctx):
        return ToolResult(text_ar="نتائج البحث")


def _web_router(*, tainted: bool) -> ToolRouter:
    router = ToolRouter()
    router.mount(_WebPlugin(), namespace="web", provenance="web:test",
                 taint=True, impact=RouteImpact(capabilities=NETWORK))
    if tainted:
        router.session_taint.raise_taint("web:test")
    return router


def _service(router):
    return asyncio.run(router.service(SEARCH, dict(ARGS)))


# ─── The brake ───────────────────────────────────────────────────────────────

def test_a_clean_gate_forces_nothing():
    """The negative control: with nothing refused and nothing drawn, the pass
    stays "auto" — the model must still be able to make its first call."""
    assert loop_tool_choice(HighlightGate(), ConfirmGate()) == "auto"


def test_an_UNAPPROVED_refusal_forces_text_only():
    """THE FIX. A real refusal, through the real router, under a real taint."""
    router = _web_router(tainted=True)
    assert loop_tool_choice(HighlightGate(), router.confirm_gate) == "auto", (
        "forcing before anything was refused — the brake is stuck on")

    _service(router)                                   # the model calls: REFUSED

    assert router.confirm_gate.awaiting_approval is True
    assert loop_tool_choice(HighlightGate(), router.confirm_gate) == "none", (
        "a refused high-impact call did NOT force text-only, so the model can "
        "spend the whole turn re-calling it — the 16-refusal defect")


def test_an_APPROVED_pending_does_NOT_force():
    """THE PREDICATE TRAP, with its control. After the word is heard the brake
    must LIFT, or the approved call can never be re-issued and the approval can
    never be spent. The control is the `pending_tool` assertion: the pending is
    still there, so a brake keyed on ITS presence would fire here and deadlock."""
    router = _web_router(tainted=True)
    _service(router)                                   # turn N: refused
    router.confirm_gate.new_turn()                     # turn N+1 begins
    router.confirm_gate.observe(APPROVAL_WORD_AR)      # the user approves

    assert router.confirm_gate.pending_tool == SEARCH, (
        "CONTROL FAILED: the pending is gone, so this test no longer "
        "distinguishes the two predicates and proves nothing")
    assert router.confirm_gate.awaiting_approval is False
    assert loop_tool_choice(HighlightGate(), router.confirm_gate) == "auto", (
        "the brake stayed on after approval — the approved call is gagged and "
        "the user can never spend the word they were asked for")

    assert _service(router).result.is_error is False, "the approval never released"


def test_a_high_impact_call_in_a_CLEAN_session_forces_nothing():
    """Both conditions, not one: taint is half the gate. An untainted session
    runs untouched, so the brake must not appear in the common path."""
    router = _web_router(tainted=False)
    _service(router)
    assert router.confirm_gate.awaiting_approval is False
    assert loop_tool_choice(HighlightGate(), router.confirm_gate) == "auto"


# ─── The original condition, unmoved ─────────────────────────────────────────

def test_the_DRAW_condition_is_untouched():
    """DEC-42: the property that already worked stays exactly as it was."""
    gate = HighlightGate()
    gate.drawn = True
    assert loop_tool_choice(gate) == "none"
    assert loop_tool_choice(gate, ConfirmGate()) == "none"
    assert loop_tool_choice(HighlightGate()) == "auto"


def test_either_condition_alone_is_enough():
    """They are independent reasons, not a conjunction."""
    router = _web_router(tainted=True)
    _service(router)
    drawn = HighlightGate()
    drawn.drawn = True
    assert loop_tool_choice(drawn, ConfirmGate()) == "none"           # draw only
    assert loop_tool_choice(HighlightGate(), router.confirm_gate) == "none"
    assert loop_tool_choice(drawn, router.confirm_gate) == "none"     # both


# ─── The fail-open default, closed structurally ──────────────────────────────

def test_the_PRODUCTION_call_site_actually_wires_the_confirm_gate():
    """`confirm` defaults to None so seven existing call sites stay untouched,
    and that default is FAIL-OPEN: a `loop_tool_choice(gate)` in production
    would silently restore the defect with every test still green. The ONE site
    that matters is asserted here rather than trusted — the same shape as the
    'exactly one FileHandler construction site' guard."""
    turn_pass = (pathlib.Path(__file__).resolve().parents[1]
                 / "src" / "muthis" / "kernel" / "turn_pass.py")
    text = turn_pass.read_text(encoding="utf-8")
    assert "loop_tool_choice(gate, self._router.confirm_gate)" in text, (
        "turn_pass.py no longer passes the confirm gate into loop_tool_choice, "
        "so the DEC-131 brake is wired to nothing in production")
    assert text.count("loop_tool_choice(") == 1, (
        "a second tool_choice decision site appeared — the reason this fix "
        "cost zero lines was that there is exactly one")


def test_an_object_without_the_attribute_is_simply_not_a_brake():
    """Duck-typed on purpose (no `trust` import in this kernel module), so an
    unrelated object must read as 'no confirm gate', never as a crash."""
    assert loop_tool_choice(HighlightGate(), object()) == "auto"
    assert loop_tool_choice(HighlightGate(), None) == "auto"
