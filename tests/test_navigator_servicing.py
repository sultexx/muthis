"""
test_navigator_servicing.py — Navigator v1 SERVICED through the kernel (T4).

THIS FILE LANDED BEFORE THE MOUNT, and that ordering is DEC-39's requirement
rather than a preference. A mounted-but-unserviced tool falls through to the
LOOK-only `else`, receives the POINTER ack, flips the per-turn draw gate and
hard-terminates the turn — the M2 bug the rule was written from. **The four
negatives that would have caught it are asserted here, by name.**

THE PASS ECONOMY IS AN ACCEPTANCE CRITERION, so it is driven rather than
assumed: advance + point completes in TWO passes with the advance never touching
the gate, advance alone completes in THREE with the gate unflipped, and neither
comes near `MAX_AGENTIC_ITERATIONS`. A turn that exceeded the cap would be a
defect, not a slow path.
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.kernel.budget import Budget
from muthis.kernel.deferral_notes import (
    NAV_ONE_PER_PASS_AR, NAV_PLAN_TOOL, NAV_STEP_TOOL, NAV_TOOLS,
)
from muthis.kernel.highlight_gate import (
    HIGHLIGHT_ACK_TEXT_AR, SHAPES_ACK_TEXT_AR, HighlightGate, loop_tool_choice,
)
from muthis.kernel.mode_transition import ModeAuthority, TransitionRequest
from muthis.kernel.navigator_service import MAX_STEPS, service_navigator_call
from muthis.kernel.orchestrator import MAX_AGENTIC_ITERATIONS, Orchestrator
from muthis.kernel.plan import Plan
from muthis.kernel.session_mode import SessionMode
from muthis.kernel.turn import DownscaledImage
from muthis.kernel.turn_prelude import TurnPrelude

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
STEPS = ["افتح الإعدادات", "اختر الشبكة", "احفظ"]
PLAN_ARGS = {"title": "توصيل الشبكة", "steps": STEPS}


def _call(name, tool_use_id, args):
    return ToolCall(name=name, args=args, tool_use_id=tool_use_id)


def _block(name, tool_use_id, args):
    return {"type": "tool_use", "id": tool_use_id, "name": name, "input": args}


def _prelude():
    prelude = TurnPrelude(session_mode=SessionMode())
    return prelude


def _service(call, prelude):
    return service_navigator_call(call, authority=prelude.authority,
                                  mode=prelude.session_mode)


# ─── The verbs, serviced ────────────────────────────────────────────────────

def test_plan_creates_the_mode_and_the_kernel_numbers_it():
    prelude = _prelude()
    note = _service(_call(NAV_PLAN_TOOL, "n1", PLAN_ARGS), prelude)
    mode = prelude.session_mode

    assert mode.active is True
    assert (mode.current_step, mode.total_steps) == (1, 3)
    assert "3" in note and "توجيه داخلي" in note


@pytest.mark.parametrize("action,expected", [
    ("advance", 2), ("back", 1),
])
def test_advance_and_back_move_one_step(action, expected):
    prelude = _prelude()
    _service(_call(NAV_PLAN_TOOL, "n1", PLAN_ARGS), prelude)
    if action == "back":
        _service(_call(NAV_STEP_TOOL, "n2", {"action": "advance"}), prelude)
    _service(_call(NAV_STEP_TOOL, "n3", {"action": action}), prelude)
    assert prelude.session_mode.current_step == expected


def test_done_ends_the_mode():
    prelude = _prelude()
    _service(_call(NAV_PLAN_TOOL, "n1", PLAN_ARGS), prelude)
    note = _service(_call(NAV_STEP_TOOL, "n2", {"action": "done"}), prelude)
    assert prelude.session_mode.active is False
    assert "انتهى" in note


# ─── jump takes the NUMBER, never the id (DEC-71, paid forward) ─────────────

def test_jump_resolves_the_spoken_NUMBER_to_the_stable_id():
    prelude = _prelude()
    _service(_call(NAV_PLAN_TOOL, "n1", PLAN_ARGS), prelude)
    _service(_call(NAV_STEP_TOOL, "n2", {"action": "jump", "step_number": 3}), prelude)
    current = prelude.session_mode.plan.current_step
    assert prelude.session_mode.current_step == 3
    assert current is not None and current.text == STEPS[2]


def test_a_jump_after_a_DELETE_lands_on_the_step_the_number_now_names():
    """THE DISCRIMINATING CASE. The number is resolved against the plan AS IT IS
    NOW and converted to a STABLE ID, so an edited plan cannot leave a jump
    pointing at a step that has moved. A design that stored the position instead
    would silently land elsewhere — the DEC-63 failure in a new place."""
    prelude = _prelude()
    _service(_call(NAV_PLAN_TOOL, "n1", PLAN_ARGS), prelude)
    plan = prelude.session_mode.plan
    edited = plan.without_step(plan.steps[0].id)          # drop step one
    prelude.authority.request(TransitionRequest(kind="edit_plan", plan=edited))

    _service(_call(NAV_STEP_TOOL, "n2", {"action": "jump", "step_number": 2}), prelude)
    landed = prelude.session_mode.plan.current_step
    assert landed is not None and landed.text == STEPS[2], (
        "the jump resolved against a stale position rather than the live plan")
    assert prelude.session_mode.current_step == 2


@pytest.mark.parametrize("number", [0, -4, 99, None, "2", True])
def test_an_out_of_range_or_malformed_jump_is_refused_and_moves_nothing(number):
    prelude = _prelude()
    _service(_call(NAV_PLAN_TOOL, "n1", PLAN_ARGS), prelude)
    note = _service(
        _call(NAV_STEP_TOOL, "n2", {"action": "jump", "step_number": number}), prelude)
    assert prelude.session_mode.current_step == 1, "a bad jump moved the plan"
    assert "توجيه داخلي" in note and "ما تغيّر شي" in note


# ─── Model-authored arguments never raise ──────────────────────────────────

@pytest.mark.parametrize("args", [
    {}, {"steps": "not a list"}, {"steps": []}, {"steps": [1, 2, 3]},
    {"steps": ["  ", ""]}, {"title": 5, "steps": ["a"]}, None,
])
def test_malformed_plan_arguments_become_a_note_never_an_exception(args):
    prelude = _prelude()
    note = _service(_call(NAV_PLAN_TOOL, "n1", args), prelude)
    assert isinstance(note, str) and note
    if args in ({}, {"steps": "not a list"}, {"steps": []}, {"steps": [1, 2, 3]},
                {"steps": ["  ", ""]}, None):
        assert prelude.session_mode.active is False, "a bad plan started a mode"


@pytest.mark.parametrize("action", ["teleport", "", None, 7, "ADVANCE"])
def test_an_unknown_action_is_refused_and_names_the_valid_ones(action):
    prelude = _prelude()
    _service(_call(NAV_PLAN_TOOL, "n1", PLAN_ARGS), prelude)
    note = _service(_call(NAV_STEP_TOOL, "n2", {"action": action}), prelude)
    assert "advance" in note and "done" in note
    assert prelude.session_mode.current_step == 1


def test_the_step_list_is_bounded_and_entries_are_flattened():
    prelude = _prelude()
    _service(_call(NAV_PLAN_TOOL, "n1",
                   {"title": "t", "steps": [f"خطوة\n{i}" for i in range(40)]}), prelude)
    plan = prelude.session_mode.plan
    assert plan.total == MAX_STEPS
    assert all("\n" not in step.text for step in plan.steps)


# ─── The servicer CANNOT bypass the one evaluation point ───────────────────

def test_the_servicer_holds_no_mutator_and_so_cannot_bypass_the_authority():
    """A PROPERTY, not a side effect. `ModeAuthority`'s public surface is exactly
    `request`, so the servicer is handed nothing it could use to change state
    directly — it reads the frame and writes through the authority. A later
    "convenience" accessor on the authority would quietly undo this, so both
    halves are pinned: the surface here, and the absence of any mutator call in
    `navigator_service.py`."""
    import ast
    import pathlib

    assert {n for n in dir(ModeAuthority) if not n.startswith("_")} == {"request"}

    source = (pathlib.Path(__file__).resolve().parent.parent / "src" / "muthis"
              / "kernel" / "navigator_service.py").read_text(encoding="utf-8")
    called = {node.func.attr for node in ast.walk(ast.parse(source))
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not (called & {"enter", "leave", "record_progress"})
    assert "request" in called, "the servicer no longer routes through the authority"


# ─── THE FOUR DEC-39 NEGATIVES ─────────────────────────────────────────────

class _NavReasoner:
    """Pass 1 emits a navigator call (optionally with a highlight); the
    continuation explains."""

    def __init__(self, *, with_draw=False, second_nav=False):
        self.calls: list[tuple] = []
        self._with_draw = with_draw
        self._second_nav = second_nav

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.calls.append((user_input.text, tool_choice))
        if len(self.calls) == 1:
            args = {"action": "advance"}
            content = [_block(NAV_STEP_TOOL, "nav_1", args)]
            yield ToolCall(name=NAV_STEP_TOOL, args=args, tool_use_id="nav_1")
            if self._second_nav:
                yield ToolCall(name=NAV_STEP_TOOL, args=args, tool_use_id="nav_2")
                content.append(_block(NAV_STEP_TOOL, "nav_2", args))
            if self._with_draw:
                bbox = {"x1": 10, "y1": 10, "x2": 60, "y2": 40, "label_ar": "هنا"}
                yield ToolCall(name="highlight_target", args=bbox, tool_use_id="hl_1")
                content.append(_block("highlight_target", "hl_1", bbox))
            yield TurnComplete(input_tokens=10, output_tokens=5, cost_usd=0.0001,
                               stop_reason="tool_use", model="claude-sonnet-4-6",
                               assistant_content=content)
        else:
            yield TextDelta("الخطوة الثانية: اختر الشبكة.")
            yield TurnComplete(input_tokens=5, output_tokens=5, cost_usd=0.0001,
                               stop_reason="end_turn", model="claude-sonnet-4-6",
                               assistant_content=[{"type": "text", "text": "شرح"}])


class _Overlay:
    def __init__(self):
        self.shown = []

    async def show(self, bbox, label_ar=None):
        self.shown.append(bbox)

    async def hide(self):
        pass

    def set_state(self, state):
        pass

    def clear_status_light(self):
        pass


def _orchestrator(reasoner, tmp_path, mode, overlay=None):
    async def _capture():
        return PNG

    async def _downscale(raw):
        return DownscaledImage(sent_bytes=raw, sent_width=1280, sent_height=720,
                               scale_x=1.5, scale_y=1.5)

    return Orchestrator(
        reasoner=reasoner,
        budget=Budget(daily_limit_usd=1.0, budget_file=tmp_path / "b.json"),
        screen_capture=_capture, downscale=_downscale,
        overlay=overlay or _Overlay(), session_mode=mode)


def _built_prelude(orchestrator) -> TurnPrelude:
    """The prelude the ORCHESTRATOR built, reached the way production reaches it.

    NOT a prelude this test injected into `TurnPass`. Assigning one by hand here
    would mask the production line that passes it — and the test would then pass
    with that wiring deleted, which is the self-built-graph defect this project
    has now met at M2, at T3 and once inside this very file."""
    return orchestrator._prelude


def _run_turn(orchestrator, text="التالي"):
    return asyncio.run(orchestrator.run_turn(text))


def test_a_navigator_call_gets_NO_POINTER_ACK_no_gate_flip_and_no_violation(tmp_path, caplog):
    """THE FOUR NEGATIVES, in one drive. Each is a separate failure mode of the
    SAME defect — an id nobody answered — and asserting only one of them would
    leave the other three free."""
    mode = SessionMode()
    orchestrator = _orchestrator(_NavReasoner(), tmp_path, mode)
    prelude = _built_prelude(orchestrator)
    _service(_call(NAV_PLAN_TOOL, "n0", PLAN_ARGS), prelude)

    with caplog.at_level("ERROR"):
        _run_turn(orchestrator)

    pairing = next(m for m in orchestrator.history
                   if m["role"] == "user" and isinstance(m["content"], list)
                   and any(b.get("type") == "tool_result" for b in m["content"]))
    answer = next(b for b in pairing["content"] if b["tool_use_id"] == "nav_1")

    # (1) NOT the pointer ack — the draw branch never saw it.
    assert answer["content"] not in (HIGHLIGHT_ACK_TEXT_AR, SHAPES_ACK_TEXT_AR)
    # (2) it was really SERVICED — the mode moved.
    assert mode.current_step == 2
    # (3) the draw gate never flipped, so the loop was never terminated.
    assert orchestrator._highlight_gate.drawn is False
    assert loop_tool_choice(orchestrator._highlight_gate) == "auto"
    # (4) no LOOK-only violation was logged.
    assert "LOOK-only violation" not in caplog.text


def test_a_SECOND_navigator_id_in_one_pass_is_answered_and_moves_nothing(tmp_path):
    mode = SessionMode()
    orchestrator = _orchestrator(_NavReasoner(second_nav=True), tmp_path, mode)
    _service(_call(NAV_PLAN_TOOL, "n0", PLAN_ARGS), _built_prelude(orchestrator))
    _run_turn(orchestrator)

    pairing = next(m for m in orchestrator.history
                   if m["role"] == "user" and isinstance(m["content"], list)
                   and any(b.get("type") == "tool_result" for b in m["content"]))
    second = next(b for b in pairing["content"] if b["tool_use_id"] == "nav_2")
    assert second["content"] == NAV_ONE_PER_PASS_AR
    assert mode.current_step == 2, "the second call moved the plan again"


# ─── THE PASS ECONOMY, driven ──────────────────────────────────────────────

def test_advance_AND_point_in_one_pass_completes_in_TWO(tmp_path):
    """The advance is serviced without touching the gate (like a read); the draw
    is buffered to the Option-A sync point and flips the gate; the next pass is
    forced to text. Two passes, well inside the cap."""
    mode = SessionMode()
    reasoner, overlay = _NavReasoner(with_draw=True), _Overlay()
    orchestrator = _orchestrator(reasoner, tmp_path, mode, overlay)
    _service(_call(NAV_PLAN_TOOL, "n0", PLAN_ARGS), _built_prelude(orchestrator))
    _run_turn(orchestrator)

    assert len(reasoner.calls) == 2 <= MAX_AGENTIC_ITERATIONS
    assert [c[1] for c in reasoner.calls] == ["auto", "none"]
    assert mode.current_step == 2, "the advance was not serviced"
    assert overlay.shown, "the step's pointing never reached the overlay"
    assert orchestrator._highlight_gate.drawn is True, "the DRAW should flip it"


def test_advance_WITHOUT_pointing_leaves_the_gate_unflipped(tmp_path):
    """Three passes at most, and `auto` survives the advance — so a later pass
    may still point. That is what "the Navigator consumes no visual intent"
    means at the level of the loop."""
    mode = SessionMode()
    reasoner = _NavReasoner(with_draw=False)
    orchestrator = _orchestrator(reasoner, tmp_path, mode)
    _service(_call(NAV_PLAN_TOOL, "n0", PLAN_ARGS), _built_prelude(orchestrator))
    _run_turn(orchestrator)

    assert len(reasoner.calls) <= 3 <= MAX_AGENTIC_ITERATIONS
    assert reasoner.calls[1][1] == "auto", "the advance forced the explain pass"
    assert orchestrator._highlight_gate.drawn is False


def test_the_record_carries_the_navigator_result_additively():
    from muthis.kernel.pass_servicing import PassServiced

    assert [f.name for f in dataclasses.fields(PassServiced)] == [
        "read_results", "run_result", "nav_result"]
    assert PassServiced().nav_result is None
