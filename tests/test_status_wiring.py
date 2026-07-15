"""
test_status_wiring.py — batch 2-B: the status light wired to the REAL turn phases.

Deterministic, fake-only. A single StatusOverlay records BOTH the ordered
set_state sequence (listening/thinking/speaking/idle) AND the ghosting chokepoint
(clear_status_light → hide → capture). In production the controller's set_state
seam and the orchestrator's overlay are the SAME SidekickOverlay, so the tests
wire both to ONE recorder to assert the merged, cross-component sequence across a
whole turn:
  * on_press  → listening (mic open),
  * on_activate → thinking (pipeline starting),
  * _speak     → speaking (per assistant message), back to thinking after,
  * reset      → idle (the single true turn end, even when the turn raises),
  * every _capture_downscaled grab is preceded by clear_status_light (ghosting).

Run:  pytest tests/test_status_wiring.py -q
"""

from __future__ import annotations

import pytest

from muthis.budget import Budget
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.main import ActivationController
from muthis.orchestrator import Orchestrator
from muthis.turn import DownscaledImage

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
WAV_BYTES = b"RIFF" + b"\x00" * 64
TEXT_AR = "زر الحفظ فوق يسار"


class StatusOverlay:
    """Overlay double recording the status-light sequence and the ghosting order.
    set_state → states (ordered); clear_status_light/hide/show/capture → events
    (ordered), so ONE list proves clear_status_light precedes every capture grab.
    set_state/clear_status_light are SYNC (2-B) — the orchestrator never awaits."""

    def __init__(self):
        self.states = []     # ordered set_state values
        self.events = []     # ordered clear_status_light / hide / show / capture

    # ── Overlay seam ──
    async def show(self, bbox, label_ar):
        self.events.append("show")

    async def hide(self):
        self.events.append("hide")

    def set_state(self, state):
        self.states.append(state)

    def clear_status_light(self):
        self.events.append("clear_status_light")

    # ── screen_capture seam (logged into the SAME ordered list) ──
    async def screen_capture(self):
        self.events.append("capture")
        return PNG_BYTES

    # ── tts seam ──
    async def tts(self, text):
        return None


class MicSwitch:
    """The controller's mic seams (start / is_recording / reset) as a flag."""

    def __init__(self):
        self.open = False

    def start(self):
        self.open = True

    def reset(self):
        self.open = False

    def is_open(self):
        return self.open


class FakeReasoner:
    """Scripted CloudReasoner: each run() replays the next event list."""

    def __init__(self, scripts):
        self._scripts = list(scripts)

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        for event in self._scripts.pop(0):
            yield event


async def _downscale(screenshot):
    return DownscaledImage(screenshot, 320, 180, 1.0, 1.0)


async def _mic():
    return WAV_BYTES


async def _stt(audio):
    return "وين زر الحفظ؟"


def _tc(stop_reason="end_turn", assistant_content=None):
    return TurnComplete(
        input_tokens=100, output_tokens=20, cost_usd=0.001,
        stop_reason=stop_reason, model="claude-sonnet-4-6",
        assistant_content=assistant_content if assistant_content is not None
        else [{"type": "text", "text": TEXT_AR}],
    )


def _orchestrator(tmp_path, scripts, overlay):
    budget = Budget(daily_limit_usd=1.0, budget_file=tmp_path / "b.json",
                    today_fn=lambda: "2026-06-12")
    return Orchestrator(
        reasoner=FakeReasoner(scripts), budget=budget,
        mic=_mic, stt=_stt, tts=overlay.tts,
        screen_capture=overlay.screen_capture, downscale=_downscale,
        overlay=overlay, overlay_timeout_s=1000,   # keep auto-hide from firing mid-test
    )


def _controller(orchestrator, overlay, mic):
    return ActivationController(
        orchestrator.handle_activation,
        start_recording=mic.start,
        is_recording=mic.is_open,
        set_state=overlay.set_state,
        reset_mic=mic.reset,
        reset_hotkey=lambda: None,
    )


@pytest.mark.asyncio
async def test_single_pass_turn_walks_listening_thinking_speaking_idle(tmp_path):
    overlay = StatusOverlay()
    mic = MicSwitch()
    orch = _orchestrator(tmp_path, [[TextDelta(TEXT_AR), _tc()]], overlay)
    ctrl = _controller(orch, overlay, mic)

    ctrl.on_press()          # mic opens → listening
    ctrl.on_activate()       # pipeline starts → thinking, launches the turn
    await ctrl._task         # run the whole turn (and its finally)

    s = overlay.states
    assert s[0] == "listening"                 # mic opened on key-down
    assert "thinking" in s                     # pipeline starting
    assert "speaking" in s                     # the voice played
    assert s[-1] == "idle" and s.count("idle") == 1  # exactly one true end
    assert s.index("listening") < s.index("speaking") < s.index("idle")


@pytest.mark.asyncio
async def test_two_pass_turn_speaks_each_pass_and_idles_only_at_the_end(tmp_path):
    overlay = StatusOverlay()
    mic = MicSwitch()
    highlight = ToolCall(
        name="highlight_target",
        args={"x1": 10, "y1": 20, "x2": 110, "y2": 60, "label_ar": "زر"},
        tool_use_id="toolu_h1",
    )
    point_ac = [
        {"type": "text", "text": "أشير الآن"},
        {"type": "tool_use", "id": "toolu_h1", "name": "highlight_target",
         "input": {"x1": 10, "y1": 20, "x2": 110, "y2": 60, "label_ar": "زر"}},
    ]
    scripts = [
        [TextDelta("أشير الآن"), highlight, _tc("tool_use", point_ac)],   # pass 1: point
        [TextDelta("وهذا شرحه"), _tc("end_turn", [{"type": "text", "text": "شرح"}])],
    ]
    orch = _orchestrator(tmp_path, scripts, overlay)
    ctrl = _controller(orch, overlay, mic)

    ctrl.on_press()
    ctrl.on_activate()
    await ctrl._task

    s = overlay.states
    assert s.count("speaking") == 2            # one per _speak (point, then explain)
    assert s.count("idle") == 1 and s[-1] == "idle"
    idle_i = s.index("idle")                   # idle is the TRUE end — never mid-loop
    assert all(i < idle_i for i, v in enumerate(s) if v == "speaking")


@pytest.mark.asyncio
async def test_status_dot_is_cleared_before_every_capture_grab(tmp_path):
    overlay = StatusOverlay()
    refresh = ToolCall(name="request_screen_refresh", args={}, tool_use_id="ref1")
    refresh_ac = [{"type": "tool_use", "id": "ref1",
                   "name": "request_screen_refresh", "input": {}}]
    scripts = [
        [refresh, _tc("tool_use", refresh_ac)],                    # asks for a fresh grab
        [TextDelta("تم التحديث"), _tc("end_turn", [{"type": "text", "text": "تم"}])],
    ]
    orch = _orchestrator(tmp_path, scripts, overlay)

    await orch.handle_activation()

    captures = [i for i, e in enumerate(overlay.events) if e == "capture"]
    assert len(captures) == 2                  # initial + serviced refresh
    for i in captures:                         # the exact chokepoint order, every grab
        assert overlay.events[i - 1] == "hide"               # rectangle ghosted
        assert overlay.events[i - 2] == "clear_status_light"  # dot ghosted BEFORE the grab


@pytest.mark.asyncio
async def test_empty_message_never_flips_to_speaking(tmp_path):
    overlay = StatusOverlay()
    orch = _orchestrator(tmp_path, [[_tc("end_turn", [])]], overlay)  # no TextDelta → empty speak

    await orch.run_turn("مرحبا")

    assert "speaking" not in overlay.states    # the _speak guard skips the flip


@pytest.mark.asyncio
async def test_turn_that_raises_still_ends_at_idle(tmp_path):
    overlay = StatusOverlay()
    mic = MicSwitch()

    async def boom():
        raise RuntimeError("turn blew up")

    ctrl = ActivationController(
        boom, start_recording=mic.start, is_recording=mic.is_open,
        set_state=overlay.set_state, reset_mic=mic.reset, reset_hotkey=lambda: None,
    )

    ctrl.on_press()
    ctrl.on_activate()
    await ctrl._task

    assert overlay.states[0] == "listening"
    assert "thinking" in overlay.states
    assert overlay.states[-1] == "idle"        # reset in the finally still fires
    assert ctrl.is_processing is False         # lock released despite the raise
