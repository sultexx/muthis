"""
test_uat_fixes.py — v1.0-RC2: the two UAT bugs, fakes only (no network, no
audio device, no keyboard).

UAT BUG 1 (barge-in audio overlap — the old voice never died):
  * the barge-in window stays OPEN through run_turn's finish() DRAIN — the
    audio tail is still audibly playing there, and the old code cleared
    `_active_turn_voice` BEFORE the drain, so a late F9 silenced nothing;
  * TurnVoice.interrupt() now works while finish() is mid-close (its own
    `_interrupted` flag, not `_closed`) and aborts the session INTO the
    concurrent drain; finish() past the interrupt runs NO fallback speak and
    never stomps the barge-in "listening" light;
  * a CANCELLED buffered ElevenLabs speak ABORTS its player instead of
    draining the queued tail (ElevenLabs delivers ~10× realtime, so that
    queue can hold the WHOLE remaining clip);
  * the Gemini fallback clip now plays through the abortable PcmStreamPlayer
    (the old winsound sync play was UNSTOPPABLE once started).

UAT BUG 2 (dialogue echo — «أبشر شوف» … «أبشر شوف» again):
  * the tts.py cascade gains the ECHO GUARD: an ElevenLabs failure that
    lands AFTER audio reached the user's ears no longer replays the SAME
    text through Gemini;
  * speech_stream gains `strip_leading_repeat` + `EchoGuard` and TurnVoice
    strips a verbatim leading repeat of the previous short ack from the
    IMMEDIATELY NEXT utterance (one-shot, boundary-strict) — the model-side
    echo the persona alone cannot prevent.

Run:  set PYTHONPATH=src && python -m pytest tests/test_uat_fixes.py -q
"""

from __future__ import annotations

import asyncio

import pytest

from muthis import tts_elevenlabs, tts_gemini
from muthis.budget import Budget
from muthis.cloud.protocol import TextDelta, TurnComplete
from muthis.orchestrator import Orchestrator
from muthis.speech_stream import EchoGuard, strip_leading_repeat
from muthis.tts import TTS
from muthis.tts_elevenlabs import stream_pcm
from muthis.turn import DownscaledImage
from muthis.turn_voice import TurnVoice

ACK = "أبشر، شوف"
LONG_SENTENCE = "الجملة الأولى في هذا الاختبار طويلة كفاية للبثّ."
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
FAKE_PCM = b"\x01\x02" * 64


# ──────────────────────────────── Fakes ────────────────────────────────


class FakeVoice:
    def __init__(self):
        self.spoken = []

    async def speak(self, text):
        self.spoken.append(text)

    def show_caption(self, text, delay_s=0.0):
        pass

    def clear_caption(self):
        pass


class FakeOverlay:
    def __init__(self):
        self.states = []
        self.hides = 0

    def set_state(self, state):
        self.states.append(state)

    def clear_status_light(self):
        pass

    async def show(self, bbox, label_ar):
        pass

    async def hide(self):
        self.hides += 1


class FakeSession:
    """The test_turn_voice session double, plus a GATED close for the
    drain-window tests: close() blocks until abort() releases it — exactly
    the shape of a long audio tail being drained when the user presses F9."""

    def __init__(self, *, gate_close=False):
        self.fed = []
        self.closed = False
        self.aborted = False
        self.close_entered = asyncio.Event()
        self._release = asyncio.Event()
        if not gate_close:
            self._release.set()

    async def open(self):
        pass

    async def feed(self, sentence, flush=False):
        self.fed.append(sentence)

    async def close(self):
        self.closed = True
        self.close_entered.set()
        await self._release.wait()

    async def abort(self):
        self.aborted = True
        self._release.set()

    @property
    def got_audio(self):
        return bool(self.fed)


def _turn_voice(session=None, *, enabled=True):
    voice, overlay = FakeVoice(), FakeOverlay()
    factory = (lambda: session) if session is not None else None
    return TurnVoice(voice=voice, overlay=overlay,
                     session_factory=factory, enabled=enabled), voice, overlay


# ─────────────────── Bug 2 — the pure echo helper ───────────────────


def test_strip_leading_repeat_core_cases():
    assert strip_leading_repeat(f"{ACK}! الكود واضح.", ACK) == "الكود واضح."
    assert strip_leading_repeat("أَبْشِر، شوف. تمام", ACK) == "تمام"      # tashkeel
    assert strip_leading_repeat("ابشر شوف الحين نبدأ", ACK) == "الحين نبدأ"  # hamza
    assert strip_leading_repeat(ACK, ACK) == ""                # echo-only → empty
    assert strip_leading_repeat("أبشر", ACK) == "أبشر"         # partial: untouched
    assert strip_leading_repeat("الشرح يبدأ هنا.", ACK) == "الشرح يبدأ هنا."


def test_strip_leading_repeat_is_boundary_strict():
    # «سم» must never bite «سمعت» — the repeat may not run into a longer word.
    assert strip_leading_repeat("سمعت طلبك وسويته.", "سم") == "سمعت طلبك وسويته."
    assert strip_leading_repeat("سم، تفضل اسأل.", "سم") == "تفضل اسأل."


def test_echo_guard_is_one_shot_and_short_only():
    guard = EchoGuard()
    guard.remember(ACK)
    assert guard.consume(f"{ACK}. الشرح.") == "الشرح."
    assert guard.consume(f"{ACK}. الشرح.") == f"{ACK}. الشرح."  # disarmed after one
    guard.remember("جملة طويلة جداً تتجاوز حد الأربعين حرفاً بلا أي شك إطلاقاً")
    assert guard.consume("جملة طويلة") == "جملة طويلة"          # long never arms


# ─────────────────── Bug 2 — TurnVoice echo suppression ───────────────────


@pytest.mark.asyncio
async def test_streamed_pass_echo_of_the_ack_is_stripped():
    session = FakeSession()
    turn_voice, voice, _overlay = _turn_voice(session)

    await turn_voice.speak_or_feed(ACK)                 # pass 1: the fed ack
    await turn_voice.push_stream(f"{ACK}. ")            # pass 2 opens with the echo
    await turn_voice.push_stream(LONG_SENTENCE)         # …then the real content
    await turn_voice.end_stream()
    await turn_voice.finish()

    assert session.fed[0] == ACK
    assert len(session.fed) == 2
    assert ACK not in session.fed[1]                    # echo gone from the stream
    assert "الجملة الأولى" in session.fed[1]
    assert voice.spoken == []                           # no buffered fallback


@pytest.mark.asyncio
async def test_buffered_pass_echo_is_stripped_and_one_shot():
    turn_voice, voice, _overlay = _turn_voice(enabled=False)   # buffered turn

    await turn_voice.speak_or_feed(ACK)
    await turn_voice.speak_or_feed(f"{ACK}. الشرح الكامل هنا بعد التأشير.")
    await turn_voice.speak_or_feed(f"{ACK} مرة ثالثة مقصودة.")  # guard already used

    assert voice.spoken[0] == ACK
    assert voice.spoken[1] == "الشرح الكامل هنا بعد التأشير."
    # One-shot: the third utterance is NOT the immediate next one anymore —
    # its own leading ack is legitimate content and stays.
    assert voice.spoken[2].startswith(ACK)


@pytest.mark.asyncio
async def test_echo_only_second_pass_speaks_nothing():
    turn_voice, voice, _overlay = _turn_voice(enabled=False)
    await turn_voice.speak_or_feed(ACK)
    await turn_voice.speak_or_feed(ACK)                 # the pure echo pass
    await turn_voice.finish()
    assert voice.spoken == [ACK]                        # spoken exactly once


# ─────────────────── Bug 2 — the tts.py cascade echo guard ───────────────────


@pytest.mark.asyncio
async def test_elevenlabs_failure_after_audio_never_replays_via_gemini(monkeypatch):
    class AudioReachedPlayer:
        got_audio = True                                # audio hit the user's ears

    async def stream_then_die(text, **kwargs):
        raise RuntimeError("total timeout after audio")

    def forbidden_gemini(text, api_key, voice=None):
        raise AssertionError("Gemini must NOT replay text that already played")

    tts_obj = TTS(api_key="fake-el", gemini_api_key="fake-gem",
                  player_factory=lambda rate=None: AudioReachedPlayer())
    monkeypatch.setattr(tts_elevenlabs, "stream_pcm", stream_then_die)
    monkeypatch.setattr(tts_gemini, "synthesize_pcm_blocking", forbidden_gemini)

    result = await tts_obj.speak("جملة طويلة انقطعت بعد ما انسمعت")

    assert result.success is False
    assert result.provider == "elevenlabs"              # honest: EL played then died
    assert "total timeout" in (result.error or "")


# ─────────────────── Bug 1 — interrupt lands DURING the drain ───────────────────


@pytest.mark.asyncio
async def test_turn_voice_interrupt_mid_finish_aborts_the_drain():
    session = FakeSession(gate_close=True)
    turn_voice, voice, overlay = _turn_voice(session)
    await turn_voice.speak_or_feed(ACK)                 # audio is "playing"

    finish_task = asyncio.create_task(turn_voice.finish())
    await session.close_entered.wait()                  # the drain is in flight
    await turn_voice.interrupt()                        # the user pressed F9
    await finish_task

    assert session.aborted                              # the drain was unblocked
    assert voice.spoken == []                           # NO fallback re-speak
    assert "thinking" not in overlay.states             # the listening light survives


@pytest.mark.asyncio
async def test_turn_voice_interrupt_after_finish_is_a_safe_noop():
    session = FakeSession()
    turn_voice, voice, _overlay = _turn_voice(session)
    await turn_voice.speak_or_feed(ACK)
    await turn_voice.finish()
    await turn_voice.interrupt()                        # late press: never raises
    assert voice.spoken == []


@pytest.mark.asyncio
async def test_orchestrator_barge_in_window_stays_open_through_the_drain(tmp_path):
    """THE UAT-1 regression: the pipeline is DONE, finish() is draining the
    audio tail, the user presses F9 — interrupt_turn must still find the
    active TurnVoice and silence the session."""
    session = FakeSession(gate_close=True)

    class OnePassReasoner:
        async def run(self, user_input, screenshot, history, tool_choice="auto"):
            yield TextDelta("جواب طويل يسمعه المستخدم الآن.")
            yield TurnComplete(input_tokens=10, output_tokens=5, cost_usd=0.001,
                               stop_reason="end_turn", model="m",
                               assistant_content=[{"type": "text", "text": "ok"}])

    async def capture():
        return PNG

    async def downscale(shot):
        return DownscaledImage(PNG, 1280, 720, 1.0, 1.0)

    async def silent_tts(text):
        return None

    budget = Budget(daily_limit_usd=1.0, budget_file=tmp_path / "budget.json",
                    today_fn=lambda: "2026-07-03")
    orchestrator = Orchestrator(
        reasoner=OnePassReasoner(), budget=budget, tts=silent_tts,
        overlay=FakeOverlay(), screen_capture=capture, downscale=downscale,
        stream_tts=True, speech_session_factory=lambda: session,
    )

    turn_task = asyncio.create_task(orchestrator.run_turn("سؤال"))
    await session.close_entered.wait()                  # the tail is draining
    assert orchestrator._active_turn_voice is not None  # the window is still open
    await orchestrator.interrupt_turn()

    assert session.aborted                              # the old audio died
    await turn_task                                     # the turn ends cleanly
    assert orchestrator._interrupted_last_turn is True  # next turn gets the note


# ─────────────────── Bug 1 — cancelled buffered speaks abort, never drain ───────────────────


class AbortRecordingPlayer:
    """A player whose finish() hangs like a long tail; abort() releases it."""

    def __init__(self):
        self.started = False
        self.fed = []
        self.aborted = False
        self.finish_entered = asyncio.Event()
        self._release = asyncio.Event()
        self.got_audio = False

    def start(self):
        self.started = True

    def feed(self, pcm):
        self.fed.append(pcm)
        self.got_audio = True

    async def finish(self):
        self.finish_entered.set()
        await self._release.wait()

    async def abort(self):
        self.aborted = True
        self._release.set()


@pytest.mark.asyncio
async def test_cancelled_stream_pcm_aborts_the_player():
    player = AbortRecordingPlayer()
    recv_entered = asyncio.Event()

    class HangingWS:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def send(self, message):
            pass

        async def recv(self):
            recv_entered.set()
            await asyncio.Event().wait()                # audio "still streaming"

    task = asyncio.create_task(stream_pcm(
        "نص يُقاطَع", api_key="k", player=player,
        ws_connect=lambda uri: HangingWS(), total_timeout_sec=60.0))
    await recv_entered.wait()
    task.cancel()                                       # the barge-in cancel
    with pytest.raises(asyncio.CancelledError):
        await task

    assert player.aborted                               # silenced, tail dropped


@pytest.mark.asyncio
async def test_cancelled_gemini_play_aborts_the_player():
    player = AbortRecordingPlayer()
    tts_obj = TTS(api_key=None, gemini_api_key="fake-gem",
                  player_factory=lambda rate=None: player)

    task = asyncio.create_task(tts_obj._play_pcm(FAKE_PCM, 24000))
    await player.finish_entered.wait()                  # the clip is "playing"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert player.started and player.fed == [FAKE_PCM]
    assert player.aborted                               # winsound could never do this
