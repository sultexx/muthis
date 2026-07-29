# src/muthis/activation.py
"""
ActivationController — the single activation gate, extracted WHOLE from
main.py (v7 Phase 3 — that file sat AT 299/300 and barge-in needs room;
the ≤300-line law: split, don't compress). main.py re-exports the name so every
existing import keeps working.

Push-to-talk (unchanged): key-DOWN starts the mic DIRECTLY on the keyboard
thread; key-UP is bridged to the loop and launches ONE turn; is_processing
refuses overlaps; reset_turn_state() in the turn's finally is the SINGLE
per-turn reset (Regression B).

**BARGE-IN (v7 Phase 3, approved blueprint 3-A):** a press WHILE a turn is
playing is no longer refused — it is the user interrupting the teacher:
  keyboard thread:  mark _interrupting → open a FRESH recording immediately
                    (the user is already speaking) → schedule_on_loop(...)
  loop thread:      _do_interrupt(): await orchestrator.interrupt_turn()
                    (silence the voice, clear board/captions, mark the
                    next-turn context note) THEN cancel the old turn task —
                    strictly in that order, so the cancelled task's finally
                    finds the TurnVoice already closed (finish() no-ops; no
                    decision-15 fallback can re-speak silenced text).
  the old finally:  reset_turn_state() sees _interrupting and PRESERVES the
                    barge-in mic + the live hold (approved decision 2 — a
                    full reset would kill the user's interruption recording
                    and eat their key-up); only is_processing resets. A
                    key-up that lands before the teardown finishes is
                    deferred (_pending_activation) and fired right here.

Race armor: _do_interrupt captures the OLD task before any await and bails
if the turn already ended on its own (_interrupting cleared by reset), so a
naturally-finishing turn — or the deferred NEW turn — can never be silenced
by a stale interrupt. Flag MUTHIS_BARGE_IN (default ON; falsey restores the
old press-refused behavior exactly).

The controller never imports the mic, Claude, tkinter, or the keyboard —
every side effect is an injected seam, so the whole machine is fake-testable.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

# Kept on main's logger: the log surface is unchanged by the split.
logger = logging.getLogger("muthis.main")

BARGE_IN_ENV = "MUTHIS_BARGE_IN"


def _barge_in_from_env() -> bool:
    raw = os.getenv(BARGE_IN_ENV)
    if raw is None:
        return True  # premium default: the teacher stops when interrupted
    return raw.strip().lower() not in ("0", "false", "no", "off")


class ActivationController:
    """The single activation gate. Runs on the asyncio loop (plus on_press on the
    keyboard thread): it starts recording on key-down and bridges one key-up to
    exactly one turn, refusing overlaps on BOTH counts — except a press during
    playback, which (barge-in) interrupts the speaking turn instead."""

    def __init__(
        self,
        handle_activation,
        *,
        start_recording=None,
        is_recording=None,
        reset_mic=None,
        reset_hotkey=None,
        earcon=None,
        set_state=None,
        interrupt_turn=None,
        schedule_on_loop=None,
        barge_in: Optional[bool] = None,
    ) -> None:
        self._handle_activation = handle_activation
        # Mic seams, injected so the controller stays mic-agnostic and testable.
        self._start_recording = start_recording or (lambda: None)
        self._is_recording = is_recording or (lambda: False)
        # Fire-and-forget UI sound seam (default no-op; a fake in tests).
        self._earcon = earcon or (lambda name: None)
        # Status-light seam (2-B): SYNC fire-and-forget, keyboard-thread-safe.
        self._set_state = set_state or (lambda state: None)
        # Per-turn reset seams (the single source of truth).
        self._reset_mic = reset_mic or (lambda: None)
        self._reset_hotkey = reset_hotkey or (lambda: None)
        # Barge-in seams (v7 Phase 3): the orchestrator's async silencer and
        # loop.call_soon_threadsafe (the ONE sanctioned keyboard→loop crossing).
        self._interrupt_turn = interrupt_turn
        self._schedule_on_loop = schedule_on_loop or (lambda callback: callback())
        self._barge_in_enabled = _barge_in_from_env() if barge_in is None else barge_in
        self._is_processing = False
        self._interrupting = False        # a barge-in teardown is in flight
        self._pending_activation = False  # key-up arrived mid-teardown → deferred
        # Kept so a clean shutdown (and tests) can await the in-flight turn.
        self._task = None

    @property
    def is_processing(self) -> bool:
        return self._is_processing

    def on_press(self) -> None:
        """Key-DOWN. Runs DIRECTLY on the keyboard thread (start_recording only
        opens the audio stream — no asyncio). During a turn: barge-in (if
        enabled) — otherwise refused. Idle: opens a fresh stream, self-healing
        a leaked one."""
        if self._is_processing:
            if not (self._barge_in_enabled and self._interrupt_turn is not None):
                logger.info("[main] hotkey press ignored — a turn is in progress")
                return
            if self._interrupting:
                logger.info("[main] barge-in already in flight — press ignored")
                return
            self._interrupting = True
            logger.info("[main] BARGE-IN — interrupting the speaking turn")
            if self._is_recording():  # defensive: never two open streams
                self._reset_mic()
            self._open_recording()
            self._schedule_on_loop(self._begin_interrupt)
            return
        if self._is_recording():
            # is_recording True with NO turn running == a leaked stream (a prior
            # hold whose turn never ran, e.g. a lost key-up). Heal it and reopen
            # fresh — never refuse forever, or F9 wedges.
            logger.warning("[main] stale recording with no turn — resetting mic")
            self._reset_mic()
        self._open_recording()

    def _open_recording(self) -> None:
        """Open the mic + confirm before chirping (a failed start leaves
        is_recording False → no false 'listening' cue)."""
        self._start_recording()
        if self._is_recording():
            self._earcon("listening")
            self._set_state("listening")  # neon cyan dot — the mic is open

    def _begin_interrupt(self) -> None:
        """LOOP thread (via schedule_on_loop): launch the bounded interrupt
        task. Not the Batch-3 wedge: fired once per press, every await inside
        is bounded, and it gates nothing — is_processing stays owned by the
        turn's own finally."""
        asyncio.create_task(self._do_interrupt())

    async def _do_interrupt(self) -> None:
        """Silence FIRST, cancel SECOND (the approved ordering): the cancelled
        task's finally must find the TurnVoice already closed. Captures the
        OLD task before any await and bails if the turn already ended on its
        own — a stale interrupt must never touch the deferred NEW turn."""
        if not self._interrupting:
            return                        # the turn finished naturally already
        task = self._task                 # the OLD turn — captured pre-await
        try:
            await self._interrupt_turn()  # abort voice + clear board + mark note
        except Exception:  # noqa: BLE001 — still cancel; silence best-effort
            logger.exception("[main] interrupt_turn failed — cancelling anyway")
        if task is not None and not task.done():
            task.cancel()

    def on_activate(self) -> None:
        """Key-UP, scheduled via call_soon_threadsafe — therefore runs on the
        LOOP thread, where asyncio.create_task is legal. During a barge-in
        teardown the release is DEFERRED (reset_turn_state fires it); during a
        normal turn it is dropped; otherwise it launches ONE turn."""
        if self._is_processing:
            if self._interrupting:
                self._pending_activation = True
                logger.info("[main] barge-in release deferred — old turn still tearing down")
                return
            logger.info("[main] hotkey release ignored — a turn is already in progress")
            return
        self._is_processing = True
        self._earcon("processing")   # mask the think/answer latency (fire-and-forget)
        self._set_state("thinking")  # amber dot — the pipeline is starting
        self._task = asyncio.create_task(self._run_one_turn())

    async def _run_one_turn(self) -> None:
        try:
            await self._handle_activation()
        except Exception:  # one bad turn must not kill a run-forever app
            # No transcript/screenshot here — only the English failure + stack.
            logger.exception("[main] turn failed unexpectedly")
        finally:
            # ESSENTIAL: EVERY path (success, raise, cancel, timeout) fully resets
            # per-turn state together — or F9 wedges. One source of truth.
            self.reset_turn_state()
            logger.info("[main] turn ended — state reset; F9 ready")

    def reset_turn_state(self) -> None:
        """The SINGLE per-turn reset (Regression B): mic to idle, hotkey
        debounce cleared, is_processing released — all together. BARGE-IN
        EXCEPTION (approved decision 2): when this reset belongs to an
        INTERRUPTED turn, the fresh recording and the live hold ARE the
        user's interruption — preserve them (no mic reset, no debounce clear,
        no idle light); a deferred key-up fires here, on the loop thread."""
        if self._interrupting:
            self._interrupting = False
            self._is_processing = False
            logger.info("[main] interrupted turn torn down — barge-in mic preserved")
            if self._pending_activation:
                self._pending_activation = False
                self.on_activate()    # the deferred release starts the new turn
            return
        self._reset_mic()
        self._reset_hotkey()
        self._set_state("idle")      # dot dark — the true, single turn end
        self._is_processing = False


__all__ = ["ActivationController", "BARGE_IN_ENV"]
