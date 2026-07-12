"""
test_draw_shapes_tool.py — Phase B-1: the draw_shapes tool schema + its agentic
loop execution, proven with FAKES only (no network, no Tk, deterministic).

Covers: (1) the schema is registered (and re-exported from claude_agent);
(2) one draw_shapes call with THREE shapes → all three scaled sent→physical
and handed to overlay.draw_shapes in ONE draw; (3) the two-pass discipline —
after a draw_shapes the next run() is forced tool_choice="none"; (4) the
UNIFIED anti-loop gate covers repeated draw_shapes AND a draw_shapes +
highlight_target mix, and resets per user turn; (5) Option B pairing — every
draw_shapes tool_use gets a matching tool_result; (6) parse_shapes_args drops
malformed entries; (7) an overlay without draw_shapes never crashes the turn.

Run:  set PYTHONPATH=src && python -m pytest tests/test_draw_shapes_tool.py -q
"""

from __future__ import annotations

import logging

import pytest

from muthis.budget import Budget
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.highlight_gate import SHAPES_ACK_TEXT_AR, SHAPES_ALREADY_SHOWN_AR
from muthis.orchestrator import Orchestrator
from muthis.shapes import Shape, parse_shapes_args
from muthis.turn import DownscaledImage

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8

THREE_SHAPES = [
    {"kind": "line", "x1": 10, "y1": 20, "x2": 30, "y2": 40},
    {"kind": "circle", "x1": 50, "y1": 60, "x2": 70, "y2": 80},
    {"kind": "arrow", "x1": 100, "y1": 100, "x2": 200, "y2": 200, "label_ar": "هنا"},
]


# ──────────────────────────────── Fakes ────────────────────────────────


class FakeReasoner:
    """Scripted reasoner recording the tool_choice of EVERY run() call."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.tool_choices = []

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.tool_choices.append(tool_choice)
        for event in self._scripts.pop(0):
            yield event


class LoopingDrawReasoner:
    """Adversary: emits a draw ToolCall on EVERY pass where tools are allowed;
    only a forced tool_choice="none" makes it explain and end the turn."""

    def __init__(self, make_call):
        self._make_call = make_call
        self.tool_choices = []

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.tool_choices.append(tool_choice)
        if tool_choice == "none":
            yield TextDelta("هذا هو الشرح.")
            yield _turn_complete()
        else:
            call = self._make_call(len(self.tool_choices))
            yield call
            yield _turn_complete(stop_reason="tool_use",
                                 assistant_content=[_tool_use_block(call)])


class FakeShapesOverlay:
    """Overlay double with BOTH draw seams: show() (highlight) and
    draw_shapes() (geometry). Records verbatim; never scales."""

    def __init__(self):
        self.shows = []
        self.shape_draws = []  # one tuple[Shape, ...] per draw_shapes call
        self.hides = 0

    async def show(self, bbox, label_ar):
        self.shows.append((bbox, label_ar))

    async def hide(self):
        self.hides += 1

    def set_state(self, state):          # 2-B status light — no-op double
        pass

    def clear_status_light(self):
        pass

    async def draw_shapes(self, shapes):
        self.shape_draws.append(tuple(shapes))


class RectOnlyOverlay(FakeShapesOverlay):
    """An overlay WITHOUT draw_shapes (like stub_overlay) — a shapes draw on it
    must be skipped gracefully, never crash the turn."""
    draw_shapes = None


# ──────────────────────────────── Helpers ────────────────────────────────


async def _capture():
    return PNG


def _downscale(scale_x, scale_y):
    async def downscale(screenshot):
        return DownscaledImage(PNG, 1280, 720, scale_x, scale_y)
    return downscale


async def _silent_tts(text):
    return None


def _turn_complete(stop_reason="end_turn", assistant_content=None):
    return TurnComplete(
        input_tokens=100, output_tokens=20, cost_usd=0.001,
        stop_reason=stop_reason, model="claude-sonnet-4-6",
        assistant_content=assistant_content or [{"type": "text", "text": "هنا"}],
    )


def _draw_shapes(shapes, tid="toolu_s1"):
    return ToolCall(name="draw_shapes", args={"shapes": shapes}, tool_use_id=tid)


def _highlight(tid="toolu_h1"):
    return ToolCall(name="highlight_target", tool_use_id=tid,
                    args={"x1": 10, "y1": 20, "x2": 30, "y2": 40, "label_ar": "زر"})


def _tool_use_block(call):
    return {"type": "tool_use", "id": call.tool_use_id,
            "name": call.name, "input": call.args}


def _orchestrator(tmp_path, reasoner, overlay, scale=(1.0, 1.0)):
    budget = Budget(daily_limit_usd=1.0, budget_file=tmp_path / "budget.json",
                    today_fn=lambda: "2026-07-03")
    return Orchestrator(reasoner=reasoner, budget=budget, tts=_silent_tts,
                        overlay=overlay, screen_capture=_capture,
                        downscale=_downscale(*scale))


def _draw_then_explain_scripts(call):
    """Two passes: the draw (tool_use stop) then the forced-text explanation."""
    return [
        [call, _turn_complete(stop_reason="tool_use",
                              assistant_content=[_tool_use_block(call)])],
        [TextDelta("هذا هو الشرح."), _turn_complete()],
    ]


def _pairing_ids(history):
    """(tool_use ids, {tool_result id: content}) extracted from history."""
    uses, results = [], {}
    for message in history:
        for block in message.get("content", []):
            if block.get("type") == "tool_use":
                uses.append(block["id"])
            elif block.get("type") == "tool_result":
                results[block["tool_use_id"]] = block["content"]
    return uses, results


# ──────────────────────────────── Tests ────────────────────────────────


def test_draw_shapes_schema_registered_and_reexported():
    from muthis.cloud.claude_agent import LOOK_ONLY_TOOLS as reexported
    from muthis.cloud.tool_schemas import LOOK_ONLY_TOOLS
    assert reexported is LOOK_ONLY_TOOLS  # claude_agent re-export intact
    names = [t["name"] for t in LOOK_ONLY_TOOLS]
    assert names == ["highlight_target", "draw_shapes", "request_screen_refresh"]
    schema = next(t for t in LOOK_ONLY_TOOLS
                  if t["name"] == "draw_shapes")["input_schema"]
    assert schema["required"] == ["shapes"]
    item = schema["properties"]["shapes"]["items"]
    assert item["properties"]["kind"]["enum"] == ["line", "arrow", "circle", "rectangle"]
    assert item["required"] == ["kind", "x1", "y1", "x2", "y2"]  # label_ar optional


@pytest.mark.asyncio
async def test_three_shapes_scaled_per_axis_in_one_draw(tmp_path):
    overlay = FakeShapesOverlay()
    reasoner = FakeReasoner(_draw_then_explain_scripts(_draw_shapes(THREE_SHAPES)))
    orchestrator = _orchestrator(tmp_path, reasoner, overlay, scale=(1.5, 2.0))

    await orchestrator.run_turn("ارسم لي")

    # ONE draw_shapes call on the overlay carrying ALL THREE shapes, each
    # scaled sent→physical per-axis (x×1.5, y×2.0) — overlay never rescales.
    assert overlay.shape_draws == [(
        Shape(kind="line", points=(15, 40, 45, 80)),
        Shape(kind="circle", points=(75, 120, 105, 160)),
        Shape(kind="arrow", points=(150, 200, 300, 400), label_ar="هنا"),
    )]
    assert overlay.shows == []  # geometry never leaks into the rectangle seam


@pytest.mark.asyncio
async def test_second_pass_after_draw_shapes_is_tool_choice_none(tmp_path):
    overlay = FakeShapesOverlay()
    reasoner = FakeReasoner(_draw_then_explain_scripts(_draw_shapes(THREE_SHAPES)))
    orchestrator = _orchestrator(tmp_path, reasoner, overlay)

    result = await orchestrator.run_turn("ارسم لي")

    # Pass 1 free ("auto"); pass 2 — after the draw — is FORCED text-only.
    assert reasoner.tool_choices == ["auto", "none"]
    assert result.stop_reason == "end_turn"
    assert "هذا هو الشرح." in result.spoken_text


@pytest.mark.asyncio
async def test_unified_gate_terminates_repeated_draw_shapes(tmp_path):
    overlay = FakeShapesOverlay()
    reasoner = LoopingDrawReasoner(
        lambda n: _draw_shapes(THREE_SHAPES, tid=f"toolu_s{n}"))
    orchestrator = _orchestrator(tmp_path, reasoner, overlay)

    result = await orchestrator.run_turn("ارسم لي")

    # The adversary is stopped after ONE draw: exactly two passes, one draw,
    # the explanation still delivered — no infinite loop, no agentic-cap hit.
    assert reasoner.tool_choices == ["auto", "none"]
    assert len(overlay.shape_draws) == 1
    assert "هذا هو الشرح." in result.spoken_text


@pytest.mark.asyncio
async def test_unified_gate_covers_mixed_draw_tools(tmp_path):
    # Adversary alternates tools across passes: shapes first, highlight next.
    overlay = FakeShapesOverlay()
    reasoner = LoopingDrawReasoner(
        lambda n: _draw_shapes(THREE_SHAPES) if n == 1 else _highlight())
    orchestrator = _orchestrator(tmp_path, reasoner, overlay)

    await orchestrator.run_turn("ارسم لي")

    # tool_choice="none" after the FIRST draw blocks the OTHER tool too:
    # the highlight pass never happens — ONE gate covers both tools.
    assert reasoner.tool_choices == ["auto", "none"]
    assert len(overlay.shape_draws) == 1 and overlay.shows == []


@pytest.mark.asyncio
async def test_first_draw_of_pass_wins_across_both_tools(tmp_path):
    # BOTH tools in ONE pass: shapes arrives first and wins; the highlight is
    # suppressed but still paired (Option B) with the "already shown" note.
    shapes_call, highlight_call = _draw_shapes(THREE_SHAPES), _highlight()
    scripts = [
        [shapes_call, highlight_call,
         _turn_complete(stop_reason="tool_use",
                        assistant_content=[_tool_use_block(shapes_call),
                                           _tool_use_block(highlight_call)])],
        [TextDelta("هذا هو الشرح."), _turn_complete()],
    ]
    overlay = FakeShapesOverlay()
    orchestrator = _orchestrator(tmp_path, FakeReasoner(scripts), overlay)

    await orchestrator.run_turn("ارسم لي")

    assert len(overlay.shape_draws) == 1 and overlay.shows == []
    uses, results = _pairing_ids(orchestrator.history)
    assert set(uses) == set(results) == {"toolu_s1", "toolu_h1"}
    assert results["toolu_s1"] == SHAPES_ACK_TEXT_AR


@pytest.mark.asyncio
async def test_every_draw_shapes_tool_use_is_paired(tmp_path):
    overlay = FakeShapesOverlay()
    reasoner = FakeReasoner(_draw_then_explain_scripts(_draw_shapes(THREE_SHAPES)))
    orchestrator = _orchestrator(tmp_path, reasoner, overlay)

    await orchestrator.run_turn("ارسم لي")

    # API-valid history: the draw_shapes tool_use has its tool_result, and the
    # FIRST draw's result is the shapes ACK ("explain now" directive).
    uses, results = _pairing_ids(orchestrator.history)
    assert uses == ["toolu_s1"] and set(results) == {"toolu_s1"}
    assert results["toolu_s1"] == SHAPES_ACK_TEXT_AR
    assert SHAPES_ALREADY_SHOWN_AR not in results.values()


@pytest.mark.asyncio
async def test_gate_resets_between_user_turns(tmp_path):
    overlay = FakeShapesOverlay()
    reasoner = FakeReasoner(
        _draw_then_explain_scripts(_draw_shapes(THREE_SHAPES, tid="toolu_a"))
        + _draw_then_explain_scripts(_draw_shapes(THREE_SHAPES, tid="toolu_b")))
    orchestrator = _orchestrator(tmp_path, reasoner, overlay)

    await orchestrator.run_turn("ارسم لي")
    await orchestrator.run_turn("ارسم مرة ثانية")

    # A fresh gate per turn: each turn draws ONCE and is then forced to text.
    assert reasoner.tool_choices == ["auto", "none", "auto", "none"]
    assert len(overlay.shape_draws) == 2


@pytest.mark.asyncio
async def test_overlay_without_draw_shapes_never_crashes(tmp_path, caplog):
    overlay = RectOnlyOverlay()
    reasoner = FakeReasoner(_draw_then_explain_scripts(_draw_shapes(THREE_SHAPES)))
    orchestrator = _orchestrator(tmp_path, reasoner, overlay)

    with caplog.at_level(logging.WARNING):
        result = await orchestrator.run_turn("ارسم لي")

    # Draw skipped with a warning; pairing + gate + explanation all intact.
    assert "lacks draw_shapes" in caplog.text
    assert reasoner.tool_choices == ["auto", "none"]
    assert "هذا هو الشرح." in result.spoken_text


def test_parse_shapes_args_drops_malformed_entries():
    parsed = parse_shapes_args({"shapes": [
        {"kind": "line", "x1": 1, "y1": 2, "x2": 3, "y2": 4},   # valid
        {"kind": "triangle", "x1": 1, "y1": 2, "x2": 3, "y2": 4},  # bad kind
        {"kind": "arrow", "x1": 1, "y1": 2, "x2": 3},           # missing y2
        {"kind": "circle", "x1": "a", "y1": 2, "x2": 3, "y2": 4},  # non-numeric
        "not a dict",
    ]})
    assert parsed == (Shape(kind="line", points=(1.0, 2.0, 3.0, 4.0)),)
    assert parse_shapes_args({}) == ()
    assert parse_shapes_args({"shapes": "oops"}) == ()
