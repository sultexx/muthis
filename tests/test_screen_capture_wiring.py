"""
test_screen_capture_wiring.py — vision wired through the orchestrator's injected
screen_capture seam (fakes only, deterministic, no real screen).

A fake capture's EXACT bytes (not None) must reach the reasoner; a
request_screen_refresh must trigger a SECOND capture and answer it via
assistant_content + a tool_result image; and the captured bytes must never be
logged during a turn. The ScreenCapture module itself is unit-tested in
test_screen_capture.py; broader pipeline coverage in test_orchestrator*.py.

Run:  set PYTHONPATH=src && python -m pytest tests/test_screen_capture_wiring.py -q
"""

from __future__ import annotations

import base64
import logging

import pytest

from muthis.budget import Budget
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.orchestrator import Orchestrator

CANNED_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class _FakeReasoner:
    """Records (user_input, screenshot, history) per run(); replays scripts."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls = []

    async def run(self, user_input, screenshot, history):
        self.calls.append((user_input, screenshot, list(history)))
        for event in self._scripts.pop(0):
            yield event


class _CountingCapture:
    def __init__(self, png):
        self._png = png
        self.calls = 0

    async def capture(self):
        self.calls += 1
        return self._png


async def _silent_tts(text):
    return None


async def _silent_overlay(tool_call):
    return None


def _turn_complete(cost_usd=0.001, stop_reason="end_turn", assistant_content=None):
    return TurnComplete(
        input_tokens=100, output_tokens=20, cost_usd=cost_usd,
        stop_reason=stop_reason, model="claude-sonnet-4-6",
        assistant_content=assistant_content or [{"type": "text", "text": "هنا"}],
    )


def _orchestrator(tmp_path, scripts, capture):
    reasoner = _FakeReasoner(scripts)
    budget = Budget(
        daily_limit_usd=1.0,
        budget_file=tmp_path / "budget.json",
        today_fn=lambda: "2026-06-13",
    )
    orchestrator = Orchestrator(
        reasoner=reasoner,
        budget=budget,
        tts=_silent_tts,
        overlay=_silent_overlay,
        screen_capture=capture.capture,
    )
    return orchestrator, reasoner


@pytest.mark.asyncio
async def test_orchestrator_passes_captured_bytes_to_reasoner(tmp_path):
    cap = _CountingCapture(CANNED_PNG)
    orchestrator, reasoner = _orchestrator(
        tmp_path, [[TextDelta("هنا"), _turn_complete()]], cap,
    )

    await orchestrator.run_turn("وين الزر؟")

    _user_input, screenshot, _history = reasoner.calls[0]
    assert screenshot == CANNED_PNG   # the EXACT captured bytes...
    assert screenshot is not None     # ...not None
    assert cap.calls == 1


@pytest.mark.asyncio
async def test_request_screen_refresh_recaptures_and_follows_up(tmp_path):
    refresh_call = ToolCall(
        name="request_screen_refresh", args={}, tool_use_id="toolu_r1",
    )
    refresh_assistant = [
        {"type": "tool_use", "id": "toolu_r1",
         "name": "request_screen_refresh", "input": {}},
    ]
    scripts = [
        [refresh_call, _turn_complete(stop_reason="tool_use",
                                      assistant_content=refresh_assistant)],
        [TextDelta("الزر هنا"), _turn_complete()],
    ]
    cap = _CountingCapture(CANNED_PNG)
    orchestrator, reasoner = _orchestrator(tmp_path, scripts, cap)

    await orchestrator.run_turn("وين الزر؟")

    assert cap.calls == 2                 # initial capture + one fresh recapture
    assert len(reasoner.calls) == 2

    # Follow-up: assistant_content carries forward, the fresh image rides inside
    # the tool_result, and the wrapper-level screenshot arg is therefore None.
    _ui, followup_screenshot, followup_history = reasoner.calls[1]
    assert followup_screenshot is None
    assert followup_history[-2] == {"role": "assistant", "content": refresh_assistant}
    tool_result = followup_history[-1]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "toolu_r1"
    image_source = tool_result["content"][0]["source"]
    assert image_source["media_type"] == "image/png"
    assert base64.standard_b64decode(image_source["data"]) == CANNED_PNG


@pytest.mark.asyncio
async def test_captured_bytes_never_logged_during_turn(tmp_path, caplog):
    cap = _CountingCapture(CANNED_PNG)
    orchestrator, _reasoner = _orchestrator(
        tmp_path, [[TextDelta("هنا"), _turn_complete()]], cap,
    )

    with caplog.at_level(logging.DEBUG):
        await orchestrator.run_turn("وين الزر؟")

    encoded = base64.standard_b64encode(CANNED_PNG).decode("ascii")
    assert encoded not in caplog.text
    assert CANNED_PNG.hex() not in caplog.text
