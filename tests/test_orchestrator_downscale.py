"""
test_orchestrator_downscale.py — the downscaled COPY (not physical pixels) is
what reaches the provider, and the scale factors are recorded on the turn.

Fakes only, deterministic, no real screen. A fake screen_capture returns
"physical" sentinel bytes; an injected fake downscale maps them to a DISTINCT
"sent" sentinel + known factors. We assert the reasoner received the SENT bytes
(never the physical ones) and that TurnResult carries the exact factors — and
that nothing applies them yet (no overlay in this phase).

The DEFAULT downscale seam (passthrough stub) is covered by test_orchestrator.py
and test_screen_capture_wiring.py, which assert the captured bytes reach the
reasoner unchanged.

Run:  set PYTHONPATH=src && python -m pytest tests/test_orchestrator_downscale.py -q
"""

from __future__ import annotations

import pytest

from muthis.budget import Budget
from muthis.cloud.protocol import TextDelta, TurnComplete
from muthis.orchestrator import Orchestrator
from muthis.turn import DownscaledImage

PHYSICAL_PNG = b"\x89PNG\r\n\x1a\n" + b"PHYSICAL" * 4
SENT_PNG = b"\x89PNG\r\n\x1a\n" + b"SENTSENT" * 2


class _FakeReasoner:
    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls = []

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.calls.append((user_input, screenshot, list(history)))
        for event in self._scripts.pop(0):
            yield event


class _FakeDownscale:
    """Records the bytes it was handed and returns a DISTINCT sent COPY + known
    factors — exactly the DownscaleFn seam shape (one Optional[bytes] arg in)."""

    def __init__(self):
        self.seen = []

    async def __call__(self, screenshot):
        self.seen.append(screenshot)
        return DownscaledImage(SENT_PNG, 1280, 720, 1.5, 1.5)


async def _physical_capture():
    return PHYSICAL_PNG


async def _silent_tts(text):
    return None


def _turn_complete():
    return TurnComplete(
        input_tokens=100, output_tokens=20, cost_usd=0.001,
        stop_reason="end_turn", model="claude-sonnet-4-6",
        assistant_content=[{"type": "text", "text": "هنا"}],
    )


def _orchestrator(tmp_path, downscale):
    reasoner = _FakeReasoner([[TextDelta("هنا"), _turn_complete()]])
    budget = Budget(
        daily_limit_usd=1.0,
        budget_file=tmp_path / "budget.json",
        today_fn=lambda: "2026-06-13",
    )
    orchestrator = Orchestrator(
        reasoner=reasoner,
        budget=budget,
        tts=_silent_tts,
        screen_capture=_physical_capture,
        downscale=downscale,
    )
    return orchestrator, reasoner


@pytest.mark.asyncio
async def test_downscaled_copy_reaches_reasoner_not_physical(tmp_path):
    downscale = _FakeDownscale()
    orchestrator, reasoner = _orchestrator(tmp_path, downscale)

    result = await orchestrator.run_turn("وين الزر؟")

    # The downscale step saw the PHYSICAL bytes...
    assert downscale.seen == [PHYSICAL_PNG]
    # ...but the provider received the SENT copy, never the physical pixels.
    _user_input, screenshot, _history = reasoner.calls[0]
    assert screenshot == SENT_PNG
    assert screenshot != PHYSICAL_PNG

    # The scale factors are recorded on the turn for the overlay step...
    assert (result.sent_width, result.sent_height) == (1280, 720)
    assert result.scale_x == 1.5 and result.scale_y == 1.5
    # ...and nothing applied them (LOOK-only, no overlay this phase).
    assert result.tool_calls == []
