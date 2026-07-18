"""
test_mic_ptt.py — push-to-talk mic: start()/stop() with a fake stream (no
PortAudio, no device), plus the empty-tap → STT_EMPTY_AR turn behavior.

A FakeStream stands in for sounddevice.InputStream: start()/stop()/close() and a
push() the test drives to deliver audio blocks through the SAME callback the real
backend would call. So the buffering + flush path is exercised exactly,
deterministically, with zero hardware.

Run:  pytest tests/test_mic_ptt.py -q
"""

from __future__ import annotations

import sys

import pytest

from muthis.kernel.budget import Budget
from muthis.mic import Mic
from muthis.kernel.orchestrator import STT_EMPTY_AR, Orchestrator


class FakeStream:
    """Stand-in for sounddevice.InputStream. push() simulates PortAudio handing a
    block to the callback on its own thread; stop()/close() record teardown."""

    def __init__(self):
        self.callback = None
        self.started = False
        self.stopped = False
        self.closed = False

    def bind(self, callback):
        self.callback = callback
        return self

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True

    def push(self, block: bytes):
        self.callback(block)


def _mic_with_stream(**kwargs):
    fake = FakeStream()
    mic = Mic(stream_factory=lambda callback: fake.bind(callback), **kwargs)
    return mic, fake


@pytest.mark.asyncio
async def test_start_then_stop_returns_all_buffered_frames_in_order():
    # min 0 → no short-tap cutoff: we assert the EXACT captured bytes.
    mic, fake = _mic_with_stream(min_record_seconds=0.0)

    mic.start()
    assert mic.is_recording is True
    # Frames arrive between start and stop, including one right before stop —
    # flush correctness means every one is present, in order.
    fake.push(b"\x01\x01")
    fake.push(b"\x02\x02")
    fake.push(b"\x03\x03")
    audio = await mic.stop()

    assert mic.is_recording is False
    assert audio == Mic._to_wav(b"\x01\x01\x02\x02\x03\x03")
    assert fake.stopped and fake.closed     # stream torn down on stop


@pytest.mark.asyncio
async def test_short_tap_yields_empty_but_valid_wav_not_none():
    # A hold well under the minimum: a few bytes, far below one second.
    mic, fake = _mic_with_stream(min_record_seconds=0.35)

    mic.start()
    fake.push(b"\x07\x07" * 20)             # tiny, << 0.35 s
    audio = await mic.stop()

    # NOT None (so it is NOT a hardware failure → not MIC_FAILED_AR) but empty of
    # audio (header only) → STT will transcribe it to "" → STT_EMPTY_AR.
    assert audio == Mic._to_wav(b"")
    assert audio is not None and len(audio) > 0


@pytest.mark.asyncio
async def test_stop_returns_none_when_stream_failed_to_start():
    def boom_factory(callback):
        raise OSError("no input device")

    mic = Mic(stream_factory=boom_factory)
    mic.start()                             # swallowed — start() never raises

    assert mic.is_recording is False
    assert await mic.stop() is None         # → orchestrator speaks MIC_FAILED_AR


@pytest.mark.asyncio
async def test_stop_without_start_returns_none():
    mic, _fake = _mic_with_stream()
    assert await mic.stop() is None


# ─── empty tap → STT_EMPTY_AR, Claude NOT called (through the real seam) ──────

class FakeSTT:
    def __init__(self, transcript=""):
        self.received = []
        self._transcript = transcript

    async def transcribe(self, audio_wav):
        self.received.append(audio_wav)
        return self._transcript


class FakeTTS:
    def __init__(self):
        self.spoken = []

    async def speak(self, text):
        self.spoken.append(text)
        return None


class SpyReasoner:
    """CloudReasoner double that records whether it was ever asked to run."""

    def __init__(self):
        self.calls = 0

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.calls += 1
        if False:           # make this an async generator without ever yielding
            yield


@pytest.mark.asyncio
async def test_empty_tap_speaks_stt_empty_and_never_calls_claude(tmp_path):
    # The REAL production seam: orchestrator.mic = Mic().stop. A quick tap, then
    # the turn: stop() flushes an empty capture → STT "" → STT_EMPTY_AR, and the
    # reasoner (ClaudeAgent in production) is NEVER called (budget protection).
    mic, fake = _mic_with_stream(min_record_seconds=0.35)
    mic.start()
    fake.push(b"\x00\x00" * 20)             # empty tap

    reasoner = SpyReasoner()
    stt = FakeSTT(transcript="")
    tts = FakeTTS()
    budget = Budget(
        daily_limit_usd=1.0,
        budget_file=tmp_path / "budget.json",
        today_fn=lambda: "2026-06-14",
    )
    orchestrator = Orchestrator(
        reasoner=reasoner,
        budget=budget,
        mic=mic.stop,                        # the new seam under test
        stt=stt.transcribe,
        tts=tts.speak,
    )

    result = await orchestrator.handle_activation()

    assert tts.spoken == [STT_EMPTY_AR]      # quiet cancel, the chosen message
    assert reasoner.calls == 0               # NO Claude call
    assert budget.spent_today_usd() == 0.0   # no budget burn
    assert result.spoken_text == ""


def test_mic_module_imports_no_portaudio():
    """CI safety: importing the mic loads no sounddevice — it is a lazy,
    call-time import behind the default stream factory (a fake is injected in
    these tests, so the real factory is never built)."""
    import muthis.mic   # noqa: F401

    assert "sounddevice" not in sys.modules


# ─── reset() — the not-via-stop() teardown (Regression B) ─────────────────────


@pytest.mark.asyncio
async def test_reset_aborts_an_open_hold_without_returning_audio():
    # The failure/cancel/timeout path: reset() forces the mic idle WITHOUT
    # returning audio (unlike stop()), closing the stream so no callback lingers.
    mic, fake = _mic_with_stream(min_record_seconds=0.0)
    mic.start()
    fake.push(b"\x09\x09")
    assert mic.is_recording is True

    mic.reset()

    assert mic.is_recording is False
    assert fake.stopped and fake.closed       # stream closed (no late _on_frames)


@pytest.mark.asyncio
async def test_reset_then_start_returns_only_fresh_frames_no_stale():
    # The stuck-state cure: after reset the next hold starts clean — the aborted
    # hold's frames are GONE, never leaked into the next turn's audio.
    mic, fake = _mic_with_stream(min_record_seconds=0.0)
    mic.start()
    fake.push(b"\xAA\xAA")                     # stale frame from the aborted hold
    mic.reset()

    mic.start()                               # fresh hold
    fake.push(b"\xBB\xBB")
    audio = await mic.stop()

    assert audio == Mic._to_wav(b"\xBB\xBB")   # ONLY the fresh frame, no stale 0xAA


def test_reset_is_safe_when_never_started():
    # Idempotent: reset() with no open stream is a clean no-op (never raises).
    mic, fake = _mic_with_stream()
    mic.reset()
    assert mic.is_recording is False
    assert not fake.stopped and not fake.closed


def test_reset_never_raises_even_if_close_fails():
    # Teardown must never throw — a failing stream close is swallowed, state idle.
    class BadStream(FakeStream):
        def stop(self):
            raise OSError("device gone")

    bad = BadStream()
    mic = Mic(stream_factory=lambda cb: bad.bind(cb))
    mic.start()

    mic.reset()                               # swallows the error

    assert mic.is_recording is False
