"""
test_highlight_sync.py — the highlight↔audio synchronization guarantees.

The bug this pins: the cyan rectangle used to be drawn the instant a
highlight_target ToolCall arrived mid-stream — ~12 s before the buffered audio,
and its 7 s auto-hide expired before the audio even began. The fix BUFFERS the
highlight (FIRST wins — circuit breaker) and draws it the instant BEFORE the
reply is spoken, so the rectangle and the audio start together. The auto-hide
is armed ONCE, at TURN END after the speech has drained (v7.1 Fix F — a timer
armed at the draw was measured hiding the rectangle mid-explanation), so the
rectangle survives the whole spoken explanation + 7 s.

Fakes only, fully deterministic: a reasoner that logs every stream yield and a
combined overlay/TTS recorder that logs show/hide/capture/speak into ONE ordered
list, plus an injected tiny auto-hide timeout driven by hand (no real screen, no
real audio, no real 7 s wait).

Run:  set PYTHONPATH=src && python -m pytest tests/test_highlight_sync.py -q
"""

from __future__ import annotations

import pytest

from muthis.kernel.budget import Budget
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.kernel.orchestrator import Orchestrator

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


# ──────────────────────────────── Fakes ────────────────────────────────


class LoggingReasoner:
    """Scripted CloudReasoner that appends a ("yield", EventType) marker to the
    SHARED order log as it emits each event — so a test can prove the overlay is
    drawn only AFTER the whole stream drained, never on ToolCall receipt. After
    each event is consumed it also snapshots whether the auto-hide timer is armed
    (it must NOT be — arming on receipt was the 12 s-early bug)."""

    def __init__(self, log, scripts):
        self._log = log
        self._scripts = list(scripts)
        self.calls = []
        self.orchestrator = None                 # back-ref, set in _build
        self.armed_after_yield = []              # (EventType, bool) per consumed event

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.calls.append((user_input, screenshot, list(history)))
        for event in self._scripts.pop(0):
            self._log.append(("yield", type(event).__name__))
            yield event
            if self.orchestrator is not None:
                task = self.orchestrator._auto_hide.task
                self.armed_after_yield.append(
                    (type(event).__name__, task is not None and not task.done()))


class SyncRecorder:
    """Combined overlay (show/hide) + TTS + screen_capture seam. Every call is
    appended to the SHARED ordered log; shows/spoken keep the payloads. tts()
    snapshots the auto-hide task AT the moment of speaking, proving the timer is
    armed at the draw (right before speak), not 12 s earlier on receipt."""

    def __init__(self, log):
        self._log = log
        self.shows = []                          # (bbox, label_ar) per overlay.show
        self.hides = 0
        self.captures = 0
        self.spoken = []
        self.auto_hide_armed_at_speak = []       # one bool snapshot per speak
        self.orchestrator = None                 # set in _build

    async def tts(self, text):
        task = None if self.orchestrator is None else self.orchestrator._auto_hide.task
        self.auto_hide_armed_at_speak.append(task is not None and not task.done())
        self.spoken.append(text)
        self._log.append("speak")
        return None

    # ── Overlay protocol; bbox arrives ALREADY physical ──
    async def show(self, bbox, label_ar):
        self.shows.append((bbox, label_ar))
        self._log.append("show")

    async def hide(self):
        self.hides += 1
        self._log.append("hide")

    def set_state(self, state):          # 2-B status light — no-op in this fake
        pass

    def clear_status_light(self):        # (a dedicated fake records the sequence)
        pass

    async def screen_capture(self):
        self.captures += 1
        self._log.append("capture")
        return PNG_BYTES


def _turn_complete(cost_usd=0.0025, stop_reason="end_turn", assistant_content=None):
    return TurnComplete(
        input_tokens=850, output_tokens=64, cost_usd=cost_usd,
        stop_reason=stop_reason, model="claude-sonnet-4-6",
        assistant_content=assistant_content or [{"type": "text", "text": "هنا"}],
    )


def _highlight(x1=10, y1=20, x2=110, y2=60, label_ar="زر الحفظ", tool_use_id="toolu_h1"):
    return ToolCall(
        name="highlight_target",
        args={"x1": x1, "y1": y1, "x2": x2, "y2": y2, "label_ar": label_ar},
        tool_use_id=tool_use_id,
    )


def _build(tmp_path, scripts, *, overlay_timeout_s=7.0):
    """Wire an Orchestrator over the logging fakes. Identity downscale stub (the
    default) leaves bboxes unchanged, so a sent bbox lands physical 1:1."""
    log = []
    reasoner = LoggingReasoner(log, scripts)
    recorder = SyncRecorder(log)
    budget = Budget(
        daily_limit_usd=1.0, budget_file=tmp_path / "budget.json",
        today_fn=lambda: "2026-06-11",
    )
    orchestrator = Orchestrator(
        reasoner=reasoner, budget=budget, tts=recorder.tts, overlay=recorder,
        screen_capture=recorder.screen_capture, overlay_timeout_s=overlay_timeout_s,
    )
    reasoner.orchestrator = orchestrator
    recorder.orchestrator = orchestrator
    return orchestrator, reasoner, recorder, log


# ──────────────────────────────── Tests ────────────────────────────────


@pytest.mark.asyncio
async def test_highlight_is_drawn_immediately_before_speak_not_on_receipt(tmp_path):
    # The core sync guarantee: the draw lands AFTER the whole stream has drained
    # and IMMEDIATELY before the audio — not when the ToolCall arrived mid-stream.
    script = [
        TextDelta("زر الحفظ "), TextDelta("فوق يسار"),
        _highlight(), _turn_complete(),
    ]
    orchestrator, _reasoner, recorder, log = _build(tmp_path, [script])

    await orchestrator.run_turn("وين زر الحفظ؟")

    assert log.count("show") == 1
    show_i, speak_i = log.index("show"), log.index("speak")
    last_yield_i = max(i for i, event in enumerate(log) if isinstance(event, tuple))
    toolcall_i = log.index(("yield", "ToolCall"))

    assert toolcall_i < last_yield_i < show_i        # NOT drawn when the tool arrived
    assert show_i == speak_i - 1                      # draw is the instant before audio
    assert log[show_i + 1] == "speak"

    # Buffer-then-speak intact, and the bbox reached the overlay already physical.
    assert recorder.spoken == ["زر الحفظ فوق يسار"]
    assert recorder.shows == [((10, 20, 110, 60), "زر الحفظ")]


@pytest.mark.asyncio
async def test_auto_hide_is_armed_at_turn_end_not_at_draw(tmp_path):
    # v7.1 Fix F (measured): a timer armed AT the draw kept hiding the rectangle
    # mid-explanation (draw+7 s landed before speech end, because the draw and
    # its explanation live in different passes). The ONLY arm site is now
    # run_turn's finally, AFTER the speech drain — the 7 s count from speech END.
    script = [TextDelta("هنا"), _highlight(), _turn_complete()]
    orchestrator, reasoner, recorder, log = _build(
        tmp_path, [script], overlay_timeout_s=0.0)

    await orchestrator.run_turn("وين زر الحفظ؟")

    # Through the ENTIRE stream — including the moment highlight_target was
    # consumed — no auto-hide timer was armed (arming here was the early-hide bug).
    assert reasoner.armed_after_yield                      # snapshots were captured
    assert not any(armed for _event, armed in reasoner.armed_after_yield)
    # NOT armed at the draw/speak step either — arming there hid the rectangle
    # mid-explanation. The arm belongs to the turn end alone.
    assert recorder.auto_hide_armed_at_speak == [False]

    # At end-of-turn the timer IS armed and still pending (it counts from the
    # post-speech finally, not the draw) and hides only once driven.
    task = orchestrator._auto_hide.task
    assert task is not None and not task.done()
    assert log[-1] == "speak"
    await task                                             # drive the 0 s timer
    assert log[-1] == "hide"


@pytest.mark.asyncio
async def test_first_highlight_wins_drawn_once_at_speak(tmp_path):
    # Circuit breaker: two highlight_target calls in ONE pass → only the FIRST
    # bbox is painted, exactly once, at the single speak-time draw. The second is
    # suppressed (no redraw) — the model is told to explain, not to point again.
    first = _highlight(x1=1, y1=1, x2=2, y2=2, label_ar="الأول", tool_use_id="toolu_a")
    last = _highlight(x1=10, y1=20, x2=110, y2=60, label_ar="الأخير", tool_use_id="toolu_b")
    script = [TextDelta("هنا"), first, last, _turn_complete()]
    orchestrator, _reasoner, recorder, log = _build(tmp_path, [script])

    await orchestrator.run_turn("وين الزر؟")

    assert log.count("show") == 1
    assert recorder.shows == [((1, 1, 2, 2), "الأول")]
    assert log[log.index("show") + 1] == "speak"


@pytest.mark.asyncio
async def test_refresh_capture_is_clean_and_highlight_waits_for_speak(tmp_path):
    # Ghosting safety: a request_screen_refresh still hides before the recapture,
    # and a pending highlight is NEVER drawn before that capture (so it can't be
    # baked into the screenshot Claude sees). Turn 1 refreshes; turn 2 highlights.
    refresh = ToolCall(name="request_screen_refresh", args={}, tool_use_id="toolu_r1")
    refresh_assistant = [{"type": "tool_use", "id": "toolu_r1",
                          "name": "request_screen_refresh", "input": {}}]
    scripts = [
        [refresh, _turn_complete(stop_reason="tool_use",
                                 assistant_content=refresh_assistant)],
        [TextDelta("زر الحفظ هنا"), _highlight(), _turn_complete()],
    ]
    orchestrator, _reasoner, recorder, log = _build(tmp_path, scripts)

    await orchestrator.run_turn("وين زر الحفظ؟")

    # EVERY capture is immediately preceded by a hide (the ghosting fix, intact).
    capture_idxs = [i for i, event in enumerate(log) if event == "capture"]
    assert len(capture_idxs) == 2                          # initial + one recapture
    assert all(log[i - 1] == "hide" for i in capture_idxs)

    # No "show" precedes the refresh recapture — the pending highlight is not drawn
    # before it, so it can never be baked into that screenshot.
    second_capture = capture_idxs[1]
    assert "show" not in log[:second_capture]

    # The highlight is painted exactly once, AFTER the refresh capture, at the
    # follow-up turn's speak.
    assert log.count("show") == 1
    assert log.index("show") > second_capture
    assert log[log.index("show") + 1] == "speak"
    assert recorder.shows == [((10, 20, 110, 60), "زر الحفظ")]


@pytest.mark.asyncio
async def test_pending_highlight_does_not_leak_into_next_turn(tmp_path):
    # The buffered highlight is a per-turn local: a later turn with NO
    # highlight_target draws nothing — no stale rectangle leaks forward.
    scripts = [
        [TextDelta("زر الحفظ فوق"), _highlight(), _turn_complete()],
        [TextDelta("تحت قائمة File"), _turn_complete()],   # no tool call this turn
    ]
    orchestrator, _reasoner, recorder, log = _build(tmp_path, scripts)

    await orchestrator.run_turn("وين زر الحفظ؟")
    assert recorder.shows == [((10, 20, 110, 60), "زر الحفظ")]   # turn 1 drew once

    await orchestrator.run_turn("وقائمة الفتح؟")

    assert recorder.shows == [((10, 20, 110, 60), "زر الحفظ")]   # still exactly one
    assert log.count("show") == 1
    assert recorder.spoken == ["زر الحفظ فوق", "تحت قائمة File"]
