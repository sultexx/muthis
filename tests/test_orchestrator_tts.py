"""
test_orchestrator_tts.py — the real-TTS wiring tests (buffer-then-speak).

No network, no audio, fully deterministic. FakeTTS has the EXACT call shape
of muthis.tts.TTS.speak (str → TTSResult), so the injection seam proven here
is the same one production uses: Orchestrator(..., tts=TTS().speak).

Covers:
  - one assistant message → exactly one speak() with the full TextDelta text
  - privacy boundary: the TTS never sees the user transcript or tool JSON
  - a budget-blocked turn still speaks the Arabic refusal (provider untouched)
  - a failing TTSResult(success=False, provider="none") never breaks the turn

Run:  pytest tests/test_orchestrator_tts.py -q
"""

from __future__ import annotations

import pytest

from muthis.budget import Budget
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.orchestrator import BUDGET_REFUSAL_AR, Orchestrator
from muthis.tts import TTSResult

# ──────────────────────────────────────────────────────────────────────────
# Fakes and helpers
# ──────────────────────────────────────────────────────────────────────────

# Deliberately PII-laden transcript — it must NEVER reach the TTS.
USER_TEXT_AR = "وين زر الحفظ؟ رقم حسابي 12345"
ASSISTANT_TEXT_AR = "زر الحفظ فوق يسار"


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


class FakeTTS:
    """Same call shape as muthis.tts.TTS.speak — records every utterance
    and answers with a canned TTSResult (never raises, like the real one)."""

    def __init__(self, result=TTSResult(success=True, provider="elevenlabs")):
        self.spoken = []
        self._result = result

    async def speak(self, text):
        self.spoken.append(text)
        return self._result


def _turn_complete(cost_usd=0.0025):
    return TurnComplete(
        input_tokens=850,
        output_tokens=64,
        cost_usd=cost_usd,
        stop_reason="end_turn",
        model="claude-sonnet-4-6",
        assistant_content=[{"type": "text", "text": ASSISTANT_TEXT_AR}],
    )


def _highlight():
    return ToolCall(
        name="highlight_target",
        args={"x1": 10, "y1": 20, "x2": 110, "y2": 60, "label_ar": "زر الحفظ"},
        tool_use_id="toolu_h1",
    )


def _orchestrator(tmp_path, scripts, *, fake_tts, daily_limit_usd=1.0):
    reasoner = FakeReasoner(scripts)
    budget = Budget(
        daily_limit_usd=daily_limit_usd,
        budget_file=tmp_path / "budget.json",
        today_fn=lambda: "2026-06-11",
    )
    orchestrator = Orchestrator(
        reasoner=reasoner,
        budget=budget,
        tts=fake_tts.speak,  # the production seam: Orchestrator(tts=TTS().speak)
    )
    return orchestrator, reasoner, budget


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assistant_message_spoken_exactly_once_with_full_text(tmp_path):
    script = [
        TextDelta("زر الحفظ "),
        TextDelta("فوق يسار"),
        _highlight(),
        _turn_complete(),
    ]
    fake_tts = FakeTTS()
    orchestrator, _reasoner, _budget = _orchestrator(
        tmp_path, [script], fake_tts=fake_tts,
    )

    result = await orchestrator.run_turn(USER_TEXT_AR)

    # Exactly ONE speak() per assistant message, with the full buffered text
    # equal to the accumulated TextDelta content.
    assert fake_tts.spoken == [ASSISTANT_TEXT_AR]
    assert fake_tts.spoken[0] == result.spoken_text
    assert not result.budget_blocked and not result.timed_out


@pytest.mark.asyncio
async def test_tts_never_sees_user_transcript_or_tool_json(tmp_path):
    script = [
        TextDelta(ASSISTANT_TEXT_AR),
        _highlight(),
        _turn_complete(),
    ]
    fake_tts = FakeTTS()
    orchestrator, _reasoner, _budget = _orchestrator(
        tmp_path, [script], fake_tts=fake_tts,
    )

    await orchestrator.run_turn(USER_TEXT_AR)

    # Privacy boundary: ONLY the assistant's synthesized Arabic crossed.
    assert fake_tts.spoken == [ASSISTANT_TEXT_AR]
    for utterance in fake_tts.spoken:
        assert USER_TEXT_AR not in utterance      # never the user transcript
        assert "12345" not in utterance           # never transcript PII
        assert "toolu_h1" not in utterance        # never tool ids
        assert "x1" not in utterance              # never tool args
        assert "{" not in utterance               # never serialized JSON


@pytest.mark.asyncio
async def test_budget_blocked_turn_speaks_refusal_without_provider_call(tmp_path):
    fake_tts = FakeTTS()
    orchestrator, reasoner, _budget = _orchestrator(
        tmp_path, scripts=[], fake_tts=fake_tts, daily_limit_usd=0.0,
    )

    result = await orchestrator.run_turn(USER_TEXT_AR)

    assert result.budget_blocked
    assert reasoner.calls == []                    # ClaudeAgent.run NOT called
    assert fake_tts.spoken == [BUDGET_REFUSAL_AR]  # refusal spoken out loud


@pytest.mark.asyncio
async def test_turn_continues_when_tts_reports_total_failure(tmp_path):
    script = [TextDelta(ASSISTANT_TEXT_AR), _turn_complete(cost_usd=0.0025)]
    fake_tts = FakeTTS(
        result=TTSResult(success=False, provider="none", error="no audio device"),
    )
    orchestrator, _reasoner, budget = _orchestrator(
        tmp_path, [script], fake_tts=fake_tts,
    )

    result = await orchestrator.run_turn(USER_TEXT_AR)

    # Voice loss ≠ turn loss: text, accounting, and history all intact.
    assert fake_tts.spoken == [ASSISTANT_TEXT_AR]
    assert result.spoken_text == ASSISTANT_TEXT_AR
    assert not result.timed_out and not result.budget_blocked
    assert budget.spent_today_usd() == 0.0025
    assert len(orchestrator.history) == 2          # user + assistant recorded
