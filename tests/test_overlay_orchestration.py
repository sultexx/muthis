"""
test_overlay_orchestration.py — the overlay step proven at the orchestrator↔
overlay seam with a FAKE overlay (no real Tk window, no real screen).

Three guarantees of this phase, all enforced by the ORCHESTRATOR (not the
overlay):
  * scale mapping — the orchestrator multiplies the model's SENT-image coords by
    the turn's scale_x/scale_y, so the overlay receives ALREADY-PHYSICAL coords
    and never rescales,
  * ghosting/order — overlay.hide() runs before EVERY screen capture (the
    initial grab AND each request_screen_refresh recapture), so Claude never
    sees its own rectangle baked into a screenshot,
  * LOOK-only — only highlight_target geometry ever reaches the overlay; any
    other tool is refused at the boundary and never drawn or executed.

No network, no audio, fully deterministic.

Run:  set PYTHONPATH=src && python -m pytest tests/test_overlay_orchestration.py -q
"""

from __future__ import annotations

import logging

import pytest

from muthis.kernel.budget import Budget
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.kernel.orchestrator import Orchestrator
from muthis.kernel.turn import DownscaledImage

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


# ──────────────────────────────── Fakes ────────────────────────────────


class FakeReasoner:
    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls = []

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.calls.append((user_input, screenshot, list(history)))
        for event in self._scripts.pop(0):
            yield event


class FakeOverlay:
    """Overlay protocol double. Records show() bboxes/labels EXACTLY as received
    (asserted to be physical — it never scales) and the ordered event log."""

    def __init__(self, log):
        self.shows = []      # (bbox, label_ar) verbatim
        self.hides = 0
        self._log = log

    async def show(self, bbox, label_ar):
        self.shows.append((bbox, label_ar))
        self._log.append("show")

    async def hide(self):
        self.hides += 1
        self._log.append("hide")

    def set_state(self, state):          # 2-B status light — no-op (not logged)
        pass

    def clear_status_light(self):
        pass


class FakeCapture:
    """Records each capture in the shared ordered log."""

    def __init__(self, log, png=PNG):
        self._log = log
        self._png = png
        self.calls = 0

    async def capture(self):
        self.calls += 1
        self._log.append("capture")
        return self._png


def _scale_downscale(scale_x, scale_y, sent=PNG):
    """A downscale seam that reports the per-axis factors under test (the orch
    records these on the turn and uses them to scale highlight coords)."""

    async def _downscale(screenshot):
        return DownscaledImage(sent, 1280, 720, scale_x, scale_y)

    return _downscale


async def _silent_tts(text):
    return None


def _turn_complete(cost_usd=0.001, stop_reason="end_turn", assistant_content=None):
    return TurnComplete(
        input_tokens=100, output_tokens=20, cost_usd=cost_usd,
        stop_reason=stop_reason, model="claude-sonnet-4-6",
        assistant_content=assistant_content or [{"type": "text", "text": "هنا"}],
    )


def _highlight(x1, y1, x2, y2, label="زر الحفظ", tid="toolu_h1"):
    return ToolCall(
        name="highlight_target",
        args={"x1": x1, "y1": y1, "x2": x2, "y2": y2, "label_ar": label},
        tool_use_id=tid,
    )


def _orchestrator(tmp_path, scripts, *, overlay, capture, downscale):
    reasoner = FakeReasoner(scripts)
    budget = Budget(
        daily_limit_usd=1.0,
        budget_file=tmp_path / "budget.json",
        today_fn=lambda: "2026-06-13",
    )
    orchestrator = Orchestrator(
        reasoner=reasoner, budget=budget, tts=_silent_tts,
        overlay=overlay, screen_capture=capture.capture, downscale=downscale,
    )
    return orchestrator, reasoner


# ──────────────────────────────── Tests ────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_scales_sent_coords_to_physical_for_overlay(tmp_path):
    log = []
    overlay = FakeOverlay(log)
    capture = FakeCapture(log)
    script = [_highlight(640, 360, 700, 420), _turn_complete()]
    orchestrator, _ = _orchestrator(
        tmp_path, [script], overlay=overlay, capture=capture,
        downscale=_scale_downscale(1.5, 1.5),
    )

    await orchestrator.run_turn("وين زر الحفظ؟")

    # The orchestrator did the multiply: sent (640,360,700,420) × 1.5 →
    # physical (960,540,1050,630). The overlay received PHYSICAL coords and
    # applied no scaling of its own.
    assert overlay.shows == [((960, 540, 1050, 630), "زر الحفظ")]


@pytest.mark.asyncio
async def test_per_axis_scale_factors_are_applied_independently(tmp_path):
    # scale_x != scale_y: x must use scale_x, y must use scale_y (no cross-talk).
    log = []
    overlay = FakeOverlay(log)
    capture = FakeCapture(log)
    script = [_highlight(100, 100, 200, 200), _turn_complete()]
    orchestrator, _ = _orchestrator(
        tmp_path, [script], overlay=overlay, capture=capture,
        downscale=_scale_downscale(1.5, 2.0),
    )

    await orchestrator.run_turn("وين الزر؟")

    assert overlay.shows == [((150, 200, 300, 400), "زر الحفظ")]


@pytest.mark.asyncio
async def test_overlay_hidden_before_every_capture_initial_and_refresh(tmp_path):
    log = []
    overlay = FakeOverlay(log)
    capture = FakeCapture(log)
    refresh = ToolCall(name="request_screen_refresh", args={}, tool_use_id="toolu_r1")
    refresh_assistant = [
        {"type": "tool_use", "id": "toolu_r1",
         "name": "request_screen_refresh", "input": {}},
    ]
    scripts = [
        # Turn 1 asks for a fresh screenshot...
        [refresh, _turn_complete(stop_reason="tool_use",
                                 assistant_content=refresh_assistant)],
        # ...the follow-up answers and highlights.
        [_highlight(10, 20, 30, 40), _turn_complete()],
    ]
    orchestrator, _ = _orchestrator(
        tmp_path, scripts, overlay=overlay, capture=capture,
        downscale=_scale_downscale(1.0, 1.0),
    )

    await orchestrator.run_turn("وين الزر؟")

    # Two captures happened (initial + the refresh recapture)...
    assert capture.calls == 2
    assert overlay.hides >= 2
    # ...and EVERY capture was immediately preceded by a hide() — the rectangle
    # is never baked into the image Claude reasons over.
    for i, event in enumerate(log):
        if event == "capture":
            assert i > 0 and log[i - 1] == "hide", f"capture #{i} not preceded by hide: {log}"


@pytest.mark.asyncio
async def test_look_only_action_tool_never_reaches_overlay(tmp_path, caplog):
    log = []
    overlay = FakeOverlay(log)
    capture = FakeCapture(log)
    # A hypothetical action tool the model must never get to invoke. The
    # orchestrator refuses anything that isn't highlight_target / refresh.
    action = ToolCall(name="hypothetical_action", args={"foo": 1}, tool_use_id="toolu_x1")
    script = [_highlight(10, 20, 30, 40), action, _turn_complete()]
    orchestrator, _ = _orchestrator(
        tmp_path, [script], overlay=overlay, capture=capture,
        downscale=_scale_downscale(1.0, 1.0),
    )

    with caplog.at_level(logging.ERROR):
        result = await orchestrator.run_turn("وين الزر؟")

    # The overlay saw ONLY the highlight geometry; the action tool was refused
    # at the LOOK-only boundary — never drawn, never executed.
    assert overlay.shows == [((10, 20, 30, 40), "زر الحفظ")]
    assert [c.name for c in result.tool_calls] == ["highlight_target"]
    assert "LOOK-only violation" in caplog.text
