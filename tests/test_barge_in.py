"""
test_barge_in.py — v7 Phase 3: Smart Interruption (F9 barge-in), fakes only —
no network, no audio device, no keyboard, no Tk.

Layers proven here:
  * PcmStreamPlayer.abort() — Pa_AbortStream unblocks a mid-chunk write, the
    QUEUED audio is discarded (never drained), stop() is skipped, idempotent.
  * SpeechSession.abort() — reader cancelled, socket dropped, NO EOS sent,
    the player aborted (not drained); never raises.
  * Orchestrator.interrupt_turn() — the active voice silenced, the overlay
    cleared instantly, the auto-hide dropped, and the NEXT turn carries the
    interrupted-context internal directive exactly once.
  * ActivationController barge-in machine — a press during playback opens a
    FRESH recording and schedules silence-then-cancel on the loop; the
    interrupted turn's reset PRESERVES the barge-in mic + live hold; a fast
    key-up is deferred and fired after teardown; a stale interrupt (the turn
    ended naturally first) touches nothing; the flag OFF restores the old
    press-refused behavior.

Run:  set PYTHONPATH=src && python -m pytest tests/test_barge_in.py -q
"""

from __future__ import annotations

import asyncio
import json
import threading

import pytest

from muthis.activation import ActivationController
from muthis.kernel.budget import Budget
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.kernel.highlight_gate import INTERRUPTED_NOTE_AR
from muthis.kernel.orchestrator import Orchestrator
from muthis.tts_session import SpeechSession
from muthis.tts_ws_player import PcmStreamPlayer
from muthis.kernel.turn import DownscaledImage

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


async def _until(condition, timeout=2.0):
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.005)


# ───────────────────────── PcmStreamPlayer.abort ─────────────────────────


class GatedStream:
    """Device double whose write() BLOCKS (a long hardware buffer) until
    abort() releases it — the exact Pa_AbortStream unblock semantics."""

    def __init__(self):
        self.written = []
        self.aborted = False
        self.stopped = False
        self._gate = threading.Event()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write(self, chunk):
        self.written.append(bytes(chunk))
        if not self._gate.wait(timeout=2.0):
            raise TimeoutError("gate never opened")
        if self.aborted:
            raise RuntimeError("write aborted")  # PortAudio errors post-abort

    def abort(self):
        self.aborted = True
        self._gate.set()

    def stop(self):
        self.stopped = True


@pytest.mark.asyncio
async def test_player_abort_unblocks_the_write_and_discards_the_queue():
    stream = GatedStream()
    player = PcmStreamPlayer(24000, stream_factory=lambda sr, ch: stream)
    player.start()
    player.feed(b"\x01" * 4800)                  # the worker blocks inside write()
    player.feed(b"\x02" * 4800)                  # queued behind — must be DISCARDED
    await _until(lambda: len(stream.written) == 1)

    await player.abort()

    assert stream.aborted                        # Pa_AbortStream fired cross-thread
    assert not stream.stopped                    # no drain-stop on the abort path
    assert len(stream.written) == 1              # the queued chunk never played
    await player.abort()                         # idempotent — never raises


# ───────────────────────── SpeechSession.abort ─────────────────────────


class HangingWS:
    """WS double: records sends; recv() pends forever (cancellable)."""

    def __init__(self):
        self.sent = []

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    async def recv(self):
        await asyncio.Event().wait()             # pends until the reader is cancelled


class FakeConnect:
    def __init__(self, ws):
        self.ws = ws

    def __call__(self, uri):
        return self

    async def __aenter__(self):
        return self.ws

    async def __aexit__(self, *exc):
        return False


class AbortablePlayer:
    def __init__(self):
        self.started = False
        self.aborted = False
        self.finished = False

    def start(self):
        self.started = True

    def feed(self, pcm):
        pass

    async def abort(self):
        self.aborted = True

    async def finish(self):
        self.finished = True

    @property
    def got_audio(self):
        return True


@pytest.mark.asyncio
async def test_session_abort_sends_no_eos_and_aborts_the_player():
    ws, player = HangingWS(), AbortablePlayer()
    session = SpeechSession(api_key="k", ws_connect=FakeConnect(ws),
                            player_factory=lambda: player)
    await session.open()
    await session.feed("جملة قيد النطق الآن.")

    await session.abort()

    assert all(m.get("text") != "" for m in ws.sent)   # NO EOS — no drain requested
    assert player.aborted and not player.finished       # aborted, never drained
    assert session._reader.done()                        # the bounded reader is gone


# ─────────────────── Orchestrator.interrupt_turn + the note ───────────────────


class GatedReasoner:
    """Yields one delta then HANGS mid-stream until released — the shape of a
    long explanation being generated while the user interrupts."""

    def __init__(self):
        self.release = asyncio.Event()
        self.calls = []

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.calls.append(user_input.text)
        yield TextDelta("جزء من الشرح الطويل قبل المقاطعة. ")
        await self.release.wait()
        yield TurnComplete(
            input_tokens=100, output_tokens=20, cost_usd=0.001,
            stop_reason="end_turn", model="claude-sonnet-4-6",
            assistant_content=[{"type": "text", "text": "تم"}],
        )


class RecorderOverlay:
    def __init__(self):
        self.hides = 0
        self.shows = []

    async def show(self, bbox, label_ar):
        self.shows.append((bbox, label_ar))

    async def hide(self):
        self.hides += 1

    def set_state(self, state):
        pass

    def clear_status_light(self):
        pass


async def _capture():
    return PNG


async def _identity_downscale(shot):
    return DownscaledImage(shot, 1280, 720, 1.0, 1.0)


async def _silent_tts(text):
    return None


def _orchestrator(tmp_path, reasoner, overlay):
    budget = Budget(daily_limit_usd=1.0, budget_file=tmp_path / "budget.json",
                    today_fn=lambda: "2026-07-16")
    return Orchestrator(reasoner=reasoner, budget=budget, tts=_silent_tts,
                        overlay=overlay, screen_capture=_capture,
                        downscale=_identity_downscale)


@pytest.mark.asyncio
async def test_interrupt_clears_the_overlay_and_marks_the_next_turn(tmp_path):
    reasoner, overlay = GatedReasoner(), RecorderOverlay()
    orchestrator = _orchestrator(tmp_path, reasoner, overlay)

    task = asyncio.create_task(orchestrator.run_turn("السؤال الأول"))
    await _until(lambda: len(reasoner.calls) == 1)   # mid-stream, hanging
    hides_before = overlay.hides                      # the capture-chokepoint hide

    await orchestrator.interrupt_turn()               # silence + clear FIRST …
    task.cancel()                                     # … cancel SECOND
    await asyncio.gather(task, return_exceptions=True)

    assert overlay.hides == hides_before + 1          # the board wiped instantly

    # The NEXT turn opens with the interrupted-context internal directive …
    reasoner.release.set()
    await orchestrator.run_turn("السؤال الثاني")
    assert reasoner.calls[1].startswith(INTERRUPTED_NOTE_AR)
    assert "السؤال الثاني" in reasoner.calls[1]
    # … exactly ONCE: a third, uninterrupted turn is clean again.
    await orchestrator.run_turn("السؤال الثالث")
    assert INTERRUPTED_NOTE_AR not in reasoner.calls[2]


@pytest.mark.asyncio
async def test_interrupt_with_no_active_turn_is_a_safe_noop(tmp_path):
    reasoner, overlay = GatedReasoner(), RecorderOverlay()
    orchestrator = _orchestrator(tmp_path, reasoner, overlay)

    await orchestrator.interrupt_turn()               # nothing running

    reasoner.release.set()
    await orchestrator.run_turn("سؤال عادي")
    assert INTERRUPTED_NOTE_AR not in reasoner.calls[0]  # no phantom note


# ─────────────────── ActivationController: the barge-in machine ───────────────────


class Harness:
    """All controller seams recorded; the turn body hangs until released."""

    def __init__(self, barge_in=True):
        self.recording = False
        self.mic_resets = 0
        self.hotkey_resets = 0
        self.interrupts = 0
        self.turns_started = 0
        self.scheduled = []
        self.turn_gate = asyncio.Event()

        async def handle():
            self.turns_started += 1
            await self.turn_gate.wait()

        def start_recording():
            self.recording = True

        def reset_mic():
            self.recording = False
            self.mic_resets += 1

        async def interrupt_turn():
            self.interrupts += 1

        self.controller = ActivationController(
            handle,
            start_recording=start_recording,
            is_recording=lambda: self.recording,
            reset_mic=reset_mic,
            reset_hotkey=lambda: self._bump_hotkey(),
            interrupt_turn=interrupt_turn,
            schedule_on_loop=self.scheduled.append,
            barge_in=barge_in,
        )

    def _bump_hotkey(self):
        self.hotkey_resets += 1

    def fire_scheduled(self):
        pending, self.scheduled = self.scheduled, []
        for callback in pending:
            callback()


@pytest.mark.asyncio
async def test_barge_in_press_records_silences_and_preserves_the_mic():
    h = Harness()
    h.controller.on_activate()                       # a turn is speaking
    await _until(lambda: h.turns_started == 1)

    h.controller.on_press()                          # THE INTERRUPTION
    assert h.recording                               # fresh mic opened at once
    assert h.scheduled                               # loop crossing queued

    h.fire_scheduled()                               # _do_interrupt launched
    await _until(lambda: h.interrupts == 1)          # silence FIRST …
    await asyncio.gather(h.controller._task, return_exceptions=True)  # … cancel SECOND

    # The interrupted turn's reset PRESERVED the barge-in recording and the
    # live hold (approved decision 2) — only is_processing was released.
    assert h.recording and h.mic_resets == 0 and h.hotkey_resets == 0
    assert not h.controller.is_processing


@pytest.mark.asyncio
async def test_fast_release_is_deferred_then_fires_the_new_turn():
    h = Harness()
    h.controller.on_activate()
    await _until(lambda: h.turns_started == 1)

    h.controller.on_press()                          # barge-in …
    h.controller.on_activate()                       # … and key-up BEFORE teardown
    assert h.turns_started == 1                      # deferred, not dropped

    h.fire_scheduled()
    await _until(lambda: h.turns_started == 2)       # teardown fired the new turn
    assert h.controller.is_processing                # the interruption turn runs

    h.turn_gate.set()                                # cleanup
    await asyncio.gather(h.controller._task, return_exceptions=True)


@pytest.mark.asyncio
async def test_stale_interrupt_never_touches_a_naturally_finished_turn():
    h = Harness()
    h.controller.on_activate()
    await _until(lambda: h.turns_started == 1)

    h.controller.on_press()                          # barge-in queued …
    h.turn_gate.set()                                # … but the turn ENDS on its own
    await asyncio.gather(h.controller._task, return_exceptions=True)

    h.fire_scheduled()                               # the stale interrupt fires late
    await asyncio.sleep(0.02)
    assert h.interrupts == 0                         # bailed: nothing to silence


@pytest.mark.asyncio
async def test_flag_off_restores_the_old_refusal():
    h = Harness(barge_in=False)
    h.controller.on_activate()
    await _until(lambda: h.turns_started == 1)

    h.controller.on_press()                          # old behavior: refused
    assert not h.recording and not h.scheduled

    h.turn_gate.set()
    await asyncio.gather(h.controller._task, return_exceptions=True)


@pytest.mark.asyncio
async def test_double_press_during_teardown_is_ignored():
    h = Harness()
    h.controller.on_activate()
    await _until(lambda: h.turns_started == 1)

    h.controller.on_press()
    first_scheduled = len(h.scheduled)
    h.controller.on_press()                          # jitter/auto-repeat press
    assert len(h.scheduled) == first_scheduled       # one interrupt, not two

    h.fire_scheduled()
    await asyncio.gather(h.controller._task, return_exceptions=True)
