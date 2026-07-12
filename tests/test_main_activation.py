"""
test_main_activation.py — the concurrency guard in the composition root.

Fakes only, no mic/keyboard/screen. The ActivationController is built with a
fake handle_activation seam (the same shape as Orchestrator.handle_activation),
so we test the guard in isolation:
  * while a turn is in flight (is_processing True) a second press is dropped;
  * once the turn finishes the flag clears and a new press works again;
  * a turn that RAISES still resets the flag (finally), so activation survives
    a failed turn instead of wedging until restart.

Run:  pytest tests/test_main_activation.py -q
"""

from __future__ import annotations

import asyncio

import pytest

from muthis.main import ActivationController


class GatedOrchestrator:
    """handle_activation blocks on a caller-controlled gate, so the test owns
    exactly when a turn finishes. Same () -> awaitable shape production uses."""

    def __init__(self):
        self.calls = 0
        self.gate = asyncio.Event()

    async def handle_activation(self):
        self.calls += 1
        await self.gate.wait()


class FlakyOrchestrator:
    """Raises on the first turn, succeeds on the second — proves the guard is
    released after a failure and activation still works afterward."""

    def __init__(self):
        self.calls = 0

    async def handle_activation(self):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_second_activation_ignored_while_processing():
    orch = GatedOrchestrator()
    controller = ActivationController(orch.handle_activation)

    controller.on_activate()        # turn 1 starts
    await asyncio.sleep(0)          # let the task reach gate.wait()
    assert orch.calls == 1
    assert controller.is_processing is True

    controller.on_activate()        # press while busy — must be dropped
    await asyncio.sleep(0)
    assert orch.calls == 1          # no second turn started

    orch.gate.set()                 # finish turn 1
    await controller._task          # deterministically run the finally
    assert controller.is_processing is False


@pytest.mark.asyncio
async def test_activation_works_again_after_turn_completes():
    orch = GatedOrchestrator()
    controller = ActivationController(orch.handle_activation)

    controller.on_activate()
    orch.gate.set()
    await controller._task
    assert controller.is_processing is False

    # A fresh press after completion launches a brand-new turn.
    orch.gate.clear()
    controller.on_activate()
    await asyncio.sleep(0)
    assert orch.calls == 2
    assert controller.is_processing is True


@pytest.mark.asyncio
async def test_failed_turn_resets_flag_and_activation_recovers():
    orch = FlakyOrchestrator()
    controller = ActivationController(orch.handle_activation)

    controller.on_activate()        # turn 1 RAISES inside the task
    await controller._task          # swallowed + flag reset in finally
    assert controller.is_processing is False
    assert orch.calls == 1

    controller.on_activate()        # activation still works after the failure
    await controller._task
    assert orch.calls == 2
    assert controller.is_processing is False


# ─── key-DOWN guard: start recording only when truly idle ─────────────────────

class FakeMicControl:
    """The mic seams the controller drives: start() opens a hold, is_recording
    reports it, reset() forces it idle (the production mic.reset). No audio, no
    device — just the booleans/counters the guard reads (same shapes production
    wires as mic.start / lambda: mic.is_recording / mic.reset)."""

    def __init__(self, *, recording=False, start_fails=False):
        self.starts = 0
        self.resets = 0
        self._recording = recording
        self._start_fails = start_fails

    def start(self):
        self.starts += 1
        if not self._start_fails:        # a failed open leaves is_recording False
            self._recording = True

    def reset(self):
        self.resets += 1
        self._recording = False

    @property
    def is_recording(self):
        return self._recording


def _controller_with_mic(handle_activation, mic, *, reset_hotkey=None, earcon=None):
    return ActivationController(
        handle_activation,
        start_recording=mic.start,
        is_recording=lambda: mic.is_recording,
        reset_mic=mic.reset,
        reset_hotkey=reset_hotkey or (lambda: None),
        earcon=earcon or (lambda name: None),
    )


@pytest.mark.asyncio
async def test_press_starts_recording_when_idle():
    orch = GatedOrchestrator()
    mic = FakeMicControl()
    controller = _controller_with_mic(orch.handle_activation, mic)

    controller.on_press()

    assert mic.starts == 1
    assert orch.calls == 0                  # a press starts NO turn (release does)
    assert controller.is_processing is False


@pytest.mark.asyncio
async def test_press_while_processing_starts_no_recording_then_recovers():
    orch = GatedOrchestrator()
    mic = FakeMicControl()
    controller = _controller_with_mic(orch.handle_activation, mic)

    controller.on_activate()                # turn 1 in flight
    await asyncio.sleep(0)
    assert controller.is_processing is True

    controller.on_press()                   # press DURING the turn — refused
    assert mic.starts == 0                   # no recording started

    orch.gate.set()
    await controller._task                   # turn done, flag cleared in finally
    assert controller.is_processing is False

    controller.on_press()                    # the same key works again afterward
    assert mic.starts == 1


@pytest.mark.asyncio
async def test_press_with_leaked_recording_heals_and_reopens():
    # is_recording True with NO turn running == a LEAKED stream (a hold whose turn
    # never ran — e.g. a lost key-up). The self-heal resets the mic and opens a
    # fresh one rather than refusing forever, so F9 can never wedge. (Auto-repeat
    # within ONE physical hold is debounced upstream in hotkey.py, not here.)
    orch = GatedOrchestrator()
    mic = FakeMicControl(recording=True)     # a leaked, unowned hold
    controller = _controller_with_mic(orch.handle_activation, mic)

    controller.on_press()

    assert mic.resets == 1                    # healed the leaked stream first
    assert mic.starts == 1                    # then opened a fresh one
    assert mic.is_recording is True


@pytest.mark.asyncio
async def test_lost_key_up_does_not_wedge_the_next_press():
    # The full lost-key-up sequence: press 1 opens the mic, but its key-up is LOST
    # so on_activate never fires — no turn, mic still recording. Press 2 must still
    # open a fresh stream (heal), not be wedged.
    orch = GatedOrchestrator()
    mic = FakeMicControl()
    controller = _controller_with_mic(orch.handle_activation, mic)

    controller.on_press()                     # press 1 (key-down) opens the mic
    assert mic.starts == 1 and mic.is_recording is True
    assert controller.is_processing is False  # key-up LOST → no turn ran

    controller.on_press()                     # press 2 — heals and reopens
    assert mic.resets == 1
    assert mic.starts == 2 and mic.is_recording is True


@pytest.mark.asyncio
async def test_turn_end_resets_mic_and_hotkey_together():
    # The single source of truth: a NORMAL turn end resets mic + hotkey debounce
    # + is_processing together (even though the fake handle_activation never
    # touched the mic — proving the finally's reset_turn_state owns it).
    orch = GatedOrchestrator()
    mic = FakeMicControl(recording=True)
    held = {"value": True}
    controller = _controller_with_mic(
        orch.handle_activation, mic, reset_hotkey=lambda: held.__setitem__("value", False))

    controller.on_activate()
    orch.gate.set()
    await controller._task

    assert controller.is_processing is False
    assert mic.resets == 1 and mic.is_recording is False
    assert held["value"] is False             # hotkey debounce cleared too


@pytest.mark.asyncio
async def test_failed_turn_resets_mic_and_reopens_next_press():
    # Regression B: a turn that RAISES after the mic was recording must still reset
    # the mic (not just is_processing), so the NEXT press opens a fresh stream.
    orch = FlakyOrchestrator()
    mic = FakeMicControl(recording=True)      # mic was left recording
    controller = _controller_with_mic(orch.handle_activation, mic)

    controller.on_activate()                  # turn 1 RAISES
    await controller._task

    assert controller.is_processing is False
    assert mic.is_recording is False          # reset on the FAILURE path
    assert mic.resets == 1

    controller.on_press()                     # F9 opens fresh after the failure
    assert mic.starts == 1 and mic.is_recording is True


@pytest.mark.asyncio
async def test_cancelled_turn_resets_mic_in_finally():
    # Timeout/shutdown path: a cancelled turn task still runs the finally, so the
    # mic is reset even though the turn never reached its own mic.stop().
    orch = GatedOrchestrator()
    mic = FakeMicControl(recording=True)
    controller = _controller_with_mic(orch.handle_activation, mic)

    controller.on_activate()
    await asyncio.sleep(0)                     # reach gate.wait()
    controller._task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await controller._task

    assert controller.is_processing is False
    assert mic.is_recording is False          # finally reset even on cancel
    assert mic.resets == 1


@pytest.mark.asyncio
async def test_consecutive_f9_turns_open_a_fresh_mic_each_time():
    # Two full F9 turns in a row: the mic opens fresh BOTH times (no stale stream
    # leaks forward — the per-turn reset guarantees a clean start each press).
    orch = GatedOrchestrator()
    mic = FakeMicControl()
    controller = _controller_with_mic(orch.handle_activation, mic)

    controller.on_press()                     # turn 1: key-down opens the mic
    assert mic.starts == 1 and mic.is_recording is True
    controller.on_activate()
    orch.gate.set()
    await controller._task
    assert mic.is_recording is False          # reset at turn 1 end

    orch.gate.clear()
    controller.on_press()                     # turn 2: a brand-new fresh stream
    assert mic.starts == 2 and mic.is_recording is True


# ─── earcons: lifecycle cues wired through the controller (fakes only) ─────────


@pytest.mark.asyncio
async def test_press_plays_listening_earcon_after_mic_opens():
    # F9 down → the mic opens → the "listening" cue fires (AFTER start, fire-and-
    # forget), and recording still started — the cue never delays the mic.
    orch = GatedOrchestrator()
    mic = FakeMicControl()
    played = []
    controller = _controller_with_mic(orch.handle_activation, mic, earcon=played.append)

    controller.on_press()

    assert mic.starts == 1 and mic.is_recording is True
    assert played == ["listening"]


@pytest.mark.asyncio
async def test_failed_mic_open_plays_no_listening_earcon():
    # If the stream fails to open (is_recording stays False) there is NO false
    # "listening" cue — the chirp signals the mic ACTUALLY opened.
    orch = GatedOrchestrator()
    mic = FakeMicControl(start_fails=True)
    played = []
    controller = _controller_with_mic(orch.handle_activation, mic, earcon=played.append)

    controller.on_press()

    assert mic.starts == 1 and mic.is_recording is False
    assert played == []


@pytest.mark.asyncio
async def test_release_plays_processing_earcon():
    # F9 up → the turn is claimed → the "processing" cue fires to mask latency.
    orch = GatedOrchestrator()
    mic = FakeMicControl()
    played = []
    controller = _controller_with_mic(orch.handle_activation, mic, earcon=played.append)

    controller.on_activate()
    await asyncio.sleep(0)
    assert "processing" in played

    orch.gate.set()
    await controller._task                    # clean up the in-flight turn
