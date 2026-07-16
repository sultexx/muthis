"""
test_read_file_tool.py — v7 Phase 4: the read_local_file schema + its agentic
loop execution, proven with FAKES only (no network, no Tk, no real files).

Covers: (1) the schema is registered (path required, range optional, the
description teaches line numbers + the secrets refusal); (2) the PEDAGOGY
flow — read → whiteboard draw → forced-text explanation — runs in THREE
passes with the read call paired to the file content and the draw gate
UNTOUCHED by the read (tool_choice stays "auto" after a read, becomes "none"
only after the draw); (3) a read failure note rides the pairing and the turn
continues; (4) two reads in ONE pass — the first is serviced once, the second
gets the already-read directive, and the gate still never flips; (5) the
default stub seam answers the Arabic unavailable note (history stays
API-valid without wiring).

Run:  set PYTHONPATH=src && python -m pytest tests/test_read_file_tool.py -q
"""

from __future__ import annotations

import pytest

from muthis.budget import Budget
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.file_reader import FILE_ALREADY_READ_AR, FILE_READ_UNAVAILABLE_AR
from muthis.highlight_gate import SHAPES_ACK_TEXT_AR
from muthis.orchestrator import Orchestrator
from muthis.turn import DownscaledImage

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
FILE_CONTENT = "محتوى الملف blink.ino (الأسطر 1-2 من 2):\n    1 | int led = 2;\n    2 | void setup() {}"


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


class FakeShapesOverlay:
    """Overlay double recording both draw seams verbatim."""

    def __init__(self):
        self.shows = []
        self.shape_draws = []
        self.hides = 0

    async def show(self, bbox, label_ar):
        self.shows.append((bbox, label_ar))

    async def hide(self):
        self.hides += 1

    def set_state(self, state):
        pass

    def clear_status_light(self):
        pass

    async def draw_shapes(self, shapes):
        self.shape_draws.append(tuple(shapes))


# ──────────────────────────────── Helpers ────────────────────────────────


async def _capture():
    return PNG


async def _downscale(screenshot):
    return DownscaledImage(PNG, 1280, 720, 1.0, 1.0)


async def _silent_tts(text):
    return None


def _turn_complete(stop_reason="end_turn", assistant_content=None):
    return TurnComplete(
        input_tokens=100, output_tokens=20, cost_usd=0.001,
        stop_reason=stop_reason, model="claude-sonnet-4-6",
        assistant_content=assistant_content or [{"type": "text", "text": "هنا"}],
    )


def _read_call(tid="toolu_r1", path="C:/proj/blink.ino"):
    return ToolCall(name="read_local_file", args={"path": path}, tool_use_id=tid)


def _draw_call(tid="toolu_s1"):
    return ToolCall(name="draw_shapes", tool_use_id=tid, args={
        "dim_screen": True,
        "shapes": [{"kind": "rectangle", "x1": 100, "y1": 200, "x2": 900, "y2": 260}],
    })


def _tool_use_block(call):
    return {"type": "tool_use", "id": call.tool_use_id,
            "name": call.name, "input": call.args}


def _orchestrator(tmp_path, reasoner, overlay, **kwargs):
    budget = Budget(daily_limit_usd=1.0, budget_file=tmp_path / "budget.json",
                    today_fn=lambda: "2026-07-03")
    return Orchestrator(reasoner=reasoner, budget=budget, tts=_silent_tts,
                        overlay=overlay, screen_capture=_capture,
                        downscale=_downscale, **kwargs)


def _pairing_results(history):
    """{tool_result id: content} extracted from history."""
    results = {}
    for message in history:
        for block in message.get("content", []):
            if block.get("type") == "tool_result":
                results[block["tool_use_id"]] = block["content"]
    return results


# ──────────────────────────────── Tests ────────────────────────────────


def test_read_local_file_schema_registered():
    from muthis.cloud.tool_schemas import LOOK_ONLY_TOOLS
    schema = next(t for t in LOOK_ONLY_TOOLS if t["name"] == "read_local_file")
    assert schema["input_schema"]["required"] == ["path"]
    properties = schema["input_schema"]["properties"]
    assert set(properties) == {"path", "start_line", "end_line"}
    # The description must teach the numbered-lines contract, the read-only
    # honesty, and the secrets refusal — the model plans around all three.
    assert "LINE NUMBERS" in schema["description"]
    assert "READ-ONLY" in schema["description"]
    assert ".env" in schema["description"]


@pytest.mark.asyncio
async def test_pedagogy_flow_read_then_whiteboard_then_explain(tmp_path):
    """The Phase 4 spine: read → dim+boxes → explanation, in three passes.
    The read call NEVER flips the draw gate — pass 2 keeps tool_choice="auto"
    so the model CAN draw; only the draw forces pass 3 to "none"."""
    read, draw = _read_call(), _draw_call()
    reasoner = FakeReasoner([
        [TextDelta("لحظة."), read,
         _turn_complete(stop_reason="tool_use",
                        assistant_content=[_tool_use_block(read)])],
        [TextDelta("أبشر، شوف."), draw,
         _turn_complete(stop_reason="tool_use",
                        assistant_content=[_tool_use_block(draw)])],
        [TextDelta("السطر الأول يعرّف led."), _turn_complete()],
    ])
    overlay = FakeShapesOverlay()
    seen_args = []

    async def fake_read(args):
        seen_args.append(dict(args))
        return FILE_CONTENT

    orchestrator = _orchestrator(tmp_path, reasoner, overlay, read_file=fake_read)
    result = await orchestrator.run_turn("اشرح لي ملف blink.ino")

    assert reasoner.tool_choices == ["auto", "auto", "none"]
    assert seen_args == [{"path": "C:/proj/blink.ino"}]        # serviced once
    assert len(overlay.shape_draws) == 1                       # the boxes drew
    results = _pairing_results(orchestrator.history)
    assert results[read.tool_use_id] == FILE_CONTENT           # content paired
    assert results[draw.tool_use_id] == SHAPES_ACK_TEXT_AR     # gate flipped at draw
    assert "السطر الأول يعرّف led." in result.spoken_text
    assert result.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_read_failure_note_rides_pairing_and_turn_continues(tmp_path):
    read = _read_call(path="C:/ghost.py")
    reasoner = FakeReasoner([
        [read, _turn_complete(stop_reason="tool_use",
                              assistant_content=[_tool_use_block(read)])],
        [TextDelta("ما لقيت الملف المطلوب."), _turn_complete()],
    ])

    async def failing_read(args):
        return "ما لقيت الملف «C:/ghost.py»."

    orchestrator = _orchestrator(tmp_path, reasoner, FakeShapesOverlay(),
                                 read_file=failing_read)
    result = await orchestrator.run_turn("اشرح لي الملف")

    results = _pairing_results(orchestrator.history)
    assert "ما لقيت الملف" in results[read.tool_use_id]
    assert result.stop_reason == "end_turn"                    # loop ended cleanly


@pytest.mark.asyncio
async def test_two_reads_one_pass_first_serviced_second_directed(tmp_path):
    first, second = _read_call("toolu_r1"), _read_call("toolu_r2", path="C:/b.py")
    reasoner = FakeReasoner([
        [first, second,
         _turn_complete(stop_reason="tool_use",
                        assistant_content=[_tool_use_block(first),
                                           _tool_use_block(second)])],
        [TextDelta("الشرح."), _turn_complete()],
    ])
    calls = []

    async def fake_read(args):
        calls.append(dict(args))
        return FILE_CONTENT

    orchestrator = _orchestrator(tmp_path, reasoner, FakeShapesOverlay(),
                                 read_file=fake_read)
    await orchestrator.run_turn("اشرح")

    assert len(calls) == 1                                     # one real read only
    results = _pairing_results(orchestrator.history)
    assert results["toolu_r1"] == FILE_CONTENT
    assert results["toolu_r2"] == FILE_ALREADY_READ_AR
    # Reads never touch the draw gate: the follow-up pass stayed "auto".
    assert reasoner.tool_choices == ["auto", "auto"]


@pytest.mark.asyncio
async def test_default_stub_seam_answers_unavailable(tmp_path):
    read = _read_call()
    reasoner = FakeReasoner([
        [read, _turn_complete(stop_reason="tool_use",
                              assistant_content=[_tool_use_block(read)])],
        [TextDelta("قراءة الملفات مو متاحة."), _turn_complete()],
    ])
    orchestrator = _orchestrator(tmp_path, reasoner, FakeShapesOverlay())

    await orchestrator.run_turn("اقرأ الملف")

    results = _pairing_results(orchestrator.history)
    assert results[read.tool_use_id] == FILE_READ_UNAVAILABLE_AR
