"""
test_overlay_autohide.py — the auto-hide timer for the cyan LOOK overlay.

Two layers, all DETERMINISTIC (asyncio control, NEVER a real 7 s sleep):
  * AutoHideController in isolation — schedule() arms a NON-blocking task that
    fires overlay.hide() after the (injected, tiny) timeout; a SECOND schedule()
    before the timeout cancels-and-replaces the first task so the first hide
    never fires early; cancel() drops a pending timer without hiding; cancel() is
    a no-op when idle.
  * The orchestrator WIRING — a highlight_target arms the auto-hide (which then
    fires), and the next turn's hide-before-capture chokepoint cancels a stale
    timer (no orphan, no early hide of the next rectangle).

Time is controlled by injecting timeout_s=0 (fires on the next loop tick — we
drive it by AWAITING the task) or a large timeout that never elapses in-test (we
assert cancellation by awaiting the cancelled task). No test waits real seconds.

Run:  set PYTHONPATH=src && python -m pytest tests/test_overlay_autohide.py -q
"""

from __future__ import annotations

import asyncio

import pytest

from muthis.budget import Budget
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.orchestrator import Orchestrator
from muthis.overlay_autohide import AutoHideController, DEFAULT_OVERLAY_TIMEOUT_S
from muthis.turn import DownscaledImage

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


# ──────────────────────────────── Fakes ────────────────────────────────


class FakeOverlay:
    """Overlay protocol double: counts hide()/show() — no Tk, no screen."""

    def __init__(self):
        self.shows = []
        self.hides = 0

    async def show(self, bbox, label_ar):
        self.shows.append((bbox, label_ar))

    async def hide(self):
        self.hides += 1


class FakeReasoner:
    """Scripted CloudReasoner: each run() replays the next event list."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls = []

    async def run(self, user_input, screenshot, history):
        self.calls.append((user_input, screenshot, list(history)))
        for event in self._scripts.pop(0):
            yield event


async def _silent_tts(text):
    return None


async def _capture():
    return PNG


async def _identity_downscale(screenshot):
    return DownscaledImage(screenshot, 1280, 720, 1.0, 1.0)


def _turn_complete():
    return TurnComplete(
        input_tokens=100, output_tokens=20, cost_usd=0.001,
        stop_reason="end_turn", model="claude-sonnet-4-6",
        assistant_content=[{"type": "text", "text": "هنا"}],
    )


def _highlight(tid="toolu_h1"):
    return ToolCall(
        name="highlight_target",
        args={"x1": 10, "y1": 20, "x2": 110, "y2": 60, "label_ar": "زر الحفظ"},
        tool_use_id=tid,
    )


def _orchestrator(tmp_path, scripts, *, overlay, overlay_timeout_s):
    budget = Budget(
        daily_limit_usd=1.0,
        budget_file=tmp_path / "budget.json",
        today_fn=lambda: "2026-06-14",
    )
    reasoner = FakeReasoner(scripts)
    orchestrator = Orchestrator(
        reasoner=reasoner, budget=budget, tts=_silent_tts, overlay=overlay,
        screen_capture=_capture, downscale=_identity_downscale,
        overlay_timeout_s=overlay_timeout_s,
    )
    return orchestrator, reasoner


# ───────────────────── AutoHideController in isolation ─────────────────────


def test_default_timeout_is_seven_seconds():
    assert DEFAULT_OVERLAY_TIMEOUT_S == 7.0


@pytest.mark.asyncio
async def test_schedule_is_non_blocking_then_hides_after_timeout():
    overlay = FakeOverlay()
    controller = AutoHideController(overlay, timeout_s=0)

    controller.schedule()
    # Non-blocking: schedule() returned WITHOUT hiding (the task only runs later).
    assert overlay.hides == 0

    await controller.task  # drive the timer to completion deterministically
    assert overlay.hides == 1


@pytest.mark.asyncio
async def test_second_schedule_cancels_and_replaces_the_first():
    overlay = FakeOverlay()
    # Large timeout: neither timer elapses on its own during the test.
    controller = AutoHideController(overlay, timeout_s=1000)

    controller.schedule()
    first = controller.task
    controller.schedule()
    second = controller.task

    assert second is not first
    # The first task was cancelled (replaced) — awaiting it re-raises, proving it
    # never reached overlay.hide().
    with pytest.raises(asyncio.CancelledError):
        await first
    assert first.cancelled()
    assert overlay.hides == 0  # the FIRST hide did NOT fire early

    # Clean up the still-pending replacement so no task outlives the test.
    controller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await second


@pytest.mark.asyncio
async def test_cancel_drops_a_pending_timer_without_hiding():
    overlay = FakeOverlay()
    controller = AutoHideController(overlay, timeout_s=1000)

    controller.schedule()
    task = controller.task
    controller.cancel()

    assert controller.task is None
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
    assert overlay.hides == 0


@pytest.mark.asyncio
async def test_cancel_is_a_noop_when_idle():
    overlay = FakeOverlay()
    controller = AutoHideController(overlay, timeout_s=1000)
    controller.cancel()  # nothing scheduled — must not raise
    assert controller.task is None
    assert overlay.hides == 0


# ───────────────────── Wired through the Orchestrator ─────────────────────


@pytest.mark.asyncio
async def test_highlight_arms_auto_hide_which_then_fires(tmp_path):
    overlay = FakeOverlay()
    script = [_highlight(), _turn_complete()]
    orchestrator, _ = _orchestrator(
        tmp_path, [script], overlay=overlay, overlay_timeout_s=0,
    )

    await orchestrator.run_turn("وين زر الحفظ؟")

    # The highlight reached the overlay, and the auto-hide was armed.
    assert overlay.shows == [((10, 20, 110, 60), "زر الحفظ")]
    await orchestrator._auto_hide.task  # drive the armed timer to completion
    # Two hides total: the pre-capture (ghosting) hide AND the auto-hide.
    assert overlay.hides == 2


@pytest.mark.asyncio
async def test_next_turn_capture_cancels_a_stale_auto_hide(tmp_path):
    overlay = FakeOverlay()
    scripts = [
        [_highlight(), _turn_complete()],            # turn 1: shows + arms timer
        [TextDelta("اشرح لك"), _turn_complete()],     # turn 2: explain-only, no show
    ]
    # Large timeout so the auto-hide can only end via the capture-chokepoint cancel.
    orchestrator, _ = _orchestrator(
        tmp_path, scripts, overlay=overlay, overlay_timeout_s=1000,
    )

    await orchestrator.run_turn("وين زر الحفظ؟")
    stale = orchestrator._auto_hide.task
    assert stale is not None and not stale.done()

    await orchestrator.run_turn("اشرح لي الشاشة")

    # Turn 2's hide-before-capture cancelled the stale timer — it never fired its
    # own hide (no early hide of a rectangle that is already gone), and nothing is
    # left pending afterwards (no orphan task).
    with pytest.raises(asyncio.CancelledError):
        await stale
    assert stale.cancelled()
    assert orchestrator._auto_hide.task is None
    # Hides came ONLY from the two capture chokepoints (turn 1 + turn 2).
    assert overlay.hides == 2
