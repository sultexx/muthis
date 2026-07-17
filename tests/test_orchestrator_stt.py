"""
test_orchestrator_stt.py — real-STT wiring through handle_activation.

No microphone, no network, fully deterministic. FakeMic and FakeSTT have
the EXACT call shapes of muthis.mic.Mic.record (() → Optional[bytes]) and
muthis.stt.STT.transcribe (bytes → str), so the injection seams proven here
are the same ones production uses. A final test proves importing the real
mic/stt modules loads no audio-device library (lazy imports — CI-safe).

Run:  pytest tests/test_orchestrator_stt.py -q
"""

from __future__ import annotations

import sys

import pytest

from muthis.kernel.budget import Budget
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.kernel.orchestrator import MIC_FAILED_AR, STT_EMPTY_AR, Orchestrator

WAV_BYTES = b"RIFF" + b"\x00" * 64          # canned utterance "recording"
TRANSCRIPT_AR = "وين زر الحفظ؟ رقمي السري 9999"  # PII-laden on purpose
ASSISTANT_TEXT_AR = "زر الحفظ فوق يسار"


class FakeMic:
    """Same call shape as muthis.mic.Mic.record."""

    def __init__(self, audio=WAV_BYTES):
        self.calls = 0
        self._audio = audio

    async def record(self):
        self.calls += 1
        return self._audio


class FakeSTT:
    """Same call shape as muthis.stt.STT.transcribe."""

    def __init__(self, transcript=TRANSCRIPT_AR):
        self.received_audio = []
        self._transcript = transcript

    async def transcribe(self, audio_wav):
        self.received_audio.append(audio_wav)
        return self._transcript


class FakeTTS:
    def __init__(self):
        self.spoken = []

    async def speak(self, text):
        self.spoken.append(text)
        return None


class FakeReasoner:
    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls = []

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.calls.append((user_input, screenshot, history))
        for event in self._scripts.pop(0):
            yield event


class FakeOverlay:
    """Overlay protocol double — records show() bboxes/labels (already physical)
    and hide() calls; same seam production injects as overlay=SidekickOverlay()."""

    def __init__(self):
        self.shows = []
        self.hides = 0

    async def show(self, bbox, label_ar):
        self.shows.append((bbox, label_ar))

    async def hide(self):
        self.hides += 1

    def set_state(self, state):          # 2-B status light — no-op double
        pass

    def clear_status_light(self):
        pass


def _turn_complete():
    return TurnComplete(
        input_tokens=850, output_tokens=64, cost_usd=0.0025,
        stop_reason="end_turn", model="claude-sonnet-4-6",
        assistant_content=[{"type": "text", "text": ASSISTANT_TEXT_AR}],
    )


def _highlight():
    return ToolCall(
        name="highlight_target",
        args={"x1": 10, "y1": 20, "x2": 110, "y2": 60, "label_ar": "زر الحفظ"},
        tool_use_id="toolu_h1",
    )


def _orchestrator(tmp_path, scripts, *, mic, stt):
    reasoner = FakeReasoner(scripts)
    budget = Budget(
        daily_limit_usd=1.0,
        budget_file=tmp_path / "budget.json",
        today_fn=lambda: "2026-06-12",
    )
    fake_tts = FakeTTS()
    overlay = FakeOverlay()
    orchestrator = Orchestrator(
        reasoner=reasoner,
        budget=budget,
        mic=mic.record,            # production seam: Orchestrator(mic=Mic().record)
        stt=stt.transcribe,        # production seam: stt=STT().transcribe
        tts=fake_tts.speak,
        overlay=overlay,
    )
    return orchestrator, reasoner, budget, fake_tts, overlay


@pytest.mark.asyncio
async def test_activation_feeds_transcript_to_provider_and_turn_flows(tmp_path):
    script = [TextDelta(ASSISTANT_TEXT_AR), _highlight(), _turn_complete()]
    mic, stt = FakeMic(), FakeSTT()
    orchestrator, reasoner, budget, fake_tts, overlay = _orchestrator(
        tmp_path, [script], mic=mic, stt=stt,
    )

    result = await orchestrator.handle_activation()

    # mic → STT → provider: exactly one capture, the EXACT bytes forwarded,
    # the EXACT transcript handed to ClaudeAgent.run.
    assert mic.calls == 1
    assert stt.received_audio == [WAV_BYTES]
    assert reasoner.calls[0][0].text == TRANSCRIPT_AR

    # The full turn still flows: spoken text, overlay highlight, accounting.
    assert result.spoken_text == ASSISTANT_TEXT_AR
    assert fake_tts.spoken == [ASSISTANT_TEXT_AR]
    assert overlay.shows == [((10, 20, 110, 60), "زر الحفظ")]
    assert budget.spent_today_usd() == 0.0025

    # Privacy: the transcript (and its PII) never reached the TTS.
    for utterance in fake_tts.spoken:
        assert TRANSCRIPT_AR not in utterance
        assert "9999" not in utterance


@pytest.mark.asyncio
async def test_mic_failure_aborts_before_stt_and_provider(tmp_path):
    mic, stt = FakeMic(audio=None), FakeSTT()
    orchestrator, reasoner, budget, fake_tts, _overlay = _orchestrator(
        tmp_path, [], mic=mic, stt=stt,
    )

    result = await orchestrator.handle_activation()

    assert stt.received_audio == []          # STT never reached
    assert reasoner.calls == []              # provider never called
    assert budget.spent_today_usd() == 0.0   # no budget burn
    assert fake_tts.spoken == [MIC_FAILED_AR]
    assert result.spoken_text == "" and not result.budget_blocked


@pytest.mark.asyncio
async def test_empty_transcript_aborts_before_provider(tmp_path):
    mic, stt = FakeMic(), FakeSTT(transcript="   ")
    orchestrator, reasoner, budget, fake_tts, _overlay = _orchestrator(
        tmp_path, [], mic=mic, stt=stt,
    )

    result = await orchestrator.handle_activation()

    assert stt.received_audio == [WAV_BYTES]
    assert reasoner.calls == []              # provider never called
    assert budget.spent_today_usd() == 0.0
    assert fake_tts.spoken == [STT_EMPTY_AR]
    assert result.spoken_text == ""


def test_real_mic_module_never_loads_portaudio_at_import():
    """CI safety: importing the REAL modules opens no device — sounddevice
    is a lazy, call-time import that the test suite never triggers."""
    import muthis.mic   # noqa: F401
    import muthis.stt   # noqa: F401

    assert "sounddevice" not in sys.modules
