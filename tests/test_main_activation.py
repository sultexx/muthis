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
    """The mic seams the controller drives on key-down: start() opens a hold,
    is_recording reports it. No audio, no device — just the booleans the guard
    reads (same shapes production wires as mic.start / lambda: mic.is_recording)."""

    def __init__(self, *, recording=False):
        self.starts = 0
        self._recording = recording

    def start(self):
        self.starts += 1
        self._recording = True

    @property
    def is_recording(self):
        return self._recording


def _controller_with_mic(handle_activation, mic):
    return ActivationController(
        handle_activation,
        start_recording=mic.start,
        is_recording=lambda: mic.is_recording,
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
async def test_press_while_already_recording_does_not_restart():
    orch = GatedOrchestrator()
    mic = FakeMicControl(recording=True)     # a hold is already open
    controller = _controller_with_mic(orch.handle_activation, mic)

    controller.on_press()                    # auto-repeat / double-down — ignored

    assert mic.starts == 0
