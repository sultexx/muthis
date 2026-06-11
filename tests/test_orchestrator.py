"""
test_orchestrator.py — the stubbed turn-pipeline tests.

No network, fully deterministic. A scripted FakeReasoner stands in for
ClaudeAgent (same CloudReasoner contract: TextDelta* → ToolCall* → exactly
one TurnComplete); recording stubs stand in for TTS / overlay / screen
capture; Budget is the real gate over a tmp_path ledger with a frozen date.

Run:  pytest tests/test_orchestrator.py -q
"""

from __future__ import annotations

import base64

import pytest

from muthis.budget import Budget
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.orchestrator import BUDGET_REFUSAL_AR, Orchestrator

# ──────────────────────────────────────────────────────────────────────────
# Fakes and recorders
# ──────────────────────────────────────────────────────────────────────────

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class FakeReasoner:
    """Scripted CloudReasoner: each run() call replays the next event list
    and records exactly what the orchestrator handed it."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls = []  # (user_input, screenshot, history) per run()

    async def run(self, user_input, screenshot, history):
        self.calls.append((user_input, screenshot, history))
        for event in self._scripts.pop(0):
            yield event


class Recorder:
    """Async stub bundle that records everything routed through it."""

    def __init__(self):
        self.spoken = []        # every text chunk handed to TTS
        self.highlights = []    # every ToolCall handed to the overlay
        self.captures = 0       # screen_capture invocations

    async def tts(self, text):
        self.spoken.append(text)

    async def overlay(self, tool_call):
        self.highlights.append(tool_call)

    async def screen_capture(self):
        self.captures += 1
        return PNG_BYTES


def _turn_complete(cost_usd=0.0025, stop_reason="end_turn", assistant_content=None):
    return TurnComplete(
        input_tokens=850,
        output_tokens=64,
        cost_usd=cost_usd,
        stop_reason=stop_reason,
        model="claude-sonnet-4-6",
        assistant_content=assistant_content or [{"type": "text", "text": "هنا"}],
    )


def _highlight(tool_use_id="toolu_h1"):
    return ToolCall(
        name="highlight_target",
        args={"x1": 10, "y1": 20, "x2": 110, "y2": 60, "label_ar": "زر الحفظ"},
        tool_use_id=tool_use_id,
    )


def _orchestrator(tmp_path, scripts, daily_limit_usd=1.0):
    reasoner = FakeReasoner(scripts)
    budget = Budget(
        daily_limit_usd=daily_limit_usd,
        budget_file=tmp_path / "budget.json",
        today_fn=lambda: "2026-06-11",
    )
    recorder = Recorder()
    orchestrator = Orchestrator(
        reasoner=reasoner,
        budget=budget,
        tts=recorder.tts,
        overlay=recorder.overlay,
        screen_capture=recorder.screen_capture,
    )
    return orchestrator, reasoner, budget, recorder


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_normal_turn_flows_end_to_end(tmp_path):
    script = [
        TextDelta("زر الحفظ "),
        TextDelta("فوق يسار"),
        _highlight(),
        _turn_complete(cost_usd=0.0025),
    ]
    orchestrator, reasoner, budget, recorder = _orchestrator(tmp_path, [script])

    result = await orchestrator.run_turn("وين زر الحفظ؟")

    # Text reached the TTS stub chunk by chunk and was accumulated.
    assert recorder.spoken == ["زر الحفظ ", "فوق يسار"]
    assert result.spoken_text == "زر الحفظ فوق يسار"

    # highlight_target reached the overlay stub — and nothing else did.
    assert [c.name for c in recorder.highlights] == ["highlight_target"]
    assert result.tool_calls[0].args["label_ar"] == "زر الحفظ"

    # budget.record_turn consumed the exact provider cost.
    assert budget.spent_today_usd() == 0.0025
    assert result.cost_usd == 0.0025
    assert result.input_tokens == 850 and result.output_tokens == 64
    assert not result.budget_blocked and not result.timed_out

    # The provider saw the screenshot and an empty prior history.
    user_input, screenshot, history = reasoner.calls[0]
    assert user_input.text == "وين زر الحفظ؟"
    assert screenshot == PNG_BYTES
    assert history == []


@pytest.mark.asyncio
async def test_budget_blocked_turn_never_calls_provider(tmp_path):
    orchestrator, reasoner, budget, recorder = _orchestrator(
        tmp_path, scripts=[], daily_limit_usd=0.0,  # gate closed from turn one
    )

    result = await orchestrator.run_turn("وين زر الحفظ؟")

    assert result.budget_blocked
    assert reasoner.calls == []                  # provider NEVER touched
    assert recorder.spoken == [BUDGET_REFUSAL_AR]  # Arabic refusal spoken
    assert recorder.highlights == []
    assert orchestrator.history == []            # a refused turn leaves no trace
    assert result.cost_usd == 0.0


@pytest.mark.asyncio
async def test_history_accumulates_across_two_turns(tmp_path):
    first_assistant = [{"type": "text", "text": "زر الحفظ فوق"}]
    second_assistant = [{"type": "text", "text": "تحت قائمة File"}]
    scripts = [
        [TextDelta("زر الحفظ فوق"), _turn_complete(assistant_content=first_assistant)],
        [TextDelta("تحت قائمة File"), _turn_complete(assistant_content=second_assistant)],
    ]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("وين زر الحفظ؟")
    assert orchestrator.history == [
        {"role": "user", "content": [{"type": "text", "text": "وين زر الحفظ؟"}]},
        {"role": "assistant", "content": first_assistant},
    ]

    await orchestrator.run_turn("وقائمة الفتح؟")

    # Turn two was given exactly turn one's history (text only, no images).
    assert reasoner.calls[1][2] == orchestrator.history[:2]
    assert orchestrator.history == [
        {"role": "user", "content": [{"type": "text", "text": "وين زر الحفظ؟"}]},
        {"role": "assistant", "content": first_assistant},
        {"role": "user", "content": [{"type": "text", "text": "وقائمة الفتح؟"}]},
        {"role": "assistant", "content": second_assistant},
    ]


@pytest.mark.asyncio
async def test_request_screen_refresh_triggers_follow_up(tmp_path):
    refresh = ToolCall(name="request_screen_refresh", args={}, tool_use_id="toolu_r1")
    refresh_assistant = [
        {"type": "tool_use", "id": "toolu_r1", "name": "request_screen_refresh", "input": {}},
    ]
    scripts = [
        # Turn 1: the model wants a fresh screenshot.
        [refresh, _turn_complete(cost_usd=0.001, stop_reason="tool_use",
                                 assistant_content=refresh_assistant)],
        # Follow-up: with the new image it answers and highlights.
        [TextDelta("زر الحفظ هنا"), _highlight(), _turn_complete(cost_usd=0.002)],
    ]
    orchestrator, reasoner, budget, recorder = _orchestrator(tmp_path, scripts)

    result = await orchestrator.run_turn("وين زر الحفظ؟")

    # Two gated provider turns happened; both costs recorded and aggregated.
    assert len(reasoner.calls) == 2
    assert budget.spent_today_usd() == round(0.001 + 0.002, 6)
    assert result.cost_usd == round(0.001 + 0.002, 6)

    # Initial capture + one FRESH capture for the tool_result.
    assert recorder.captures == 2

    # The follow-up history carries assistant_content then the tool_result
    # answering toolu_r1 with the fresh screenshot; the wrapper-level
    # screenshot argument is None (the image rides inside the tool_result).
    _user_input, followup_screenshot, followup_history = reasoner.calls[1]
    assert followup_screenshot is None
    assert followup_history[-2] == {"role": "assistant", "content": refresh_assistant}
    tool_result = followup_history[-1]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "toolu_r1"
    image_source = tool_result["content"][0]["source"]
    assert image_source["media_type"] == "image/png"
    assert base64.standard_b64decode(image_source["data"]) == PNG_BYTES

    # The refresh tool stayed internal — the overlay saw only the highlight.
    assert [c.name for c in recorder.highlights] == ["highlight_target"]
    assert result.spoken_text == "زر الحفظ هنا"
