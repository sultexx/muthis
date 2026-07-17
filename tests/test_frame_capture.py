# tests/test_frame_capture.py
"""
FrameCapture (the M1-2 extraction) — the chokepoint's own unit contract.
The orchestrator-level behavior (hide-before-EVERY-capture, refresh path,
ghosting) stays covered by the untouched V1 suites; this pins the extracted
unit: ORDER, scale bookkeeping, and the settle yield.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from muthis.kernel.frame_capture import OVERLAY_SETTLE_S, FrameCapture
from muthis.kernel.turn import DownscaledImage, TurnResult


@dataclass
class _Log:
    events: list


def _fake_world(log):
    class Overlay:
        def clear_status_light(self):
            log.events.append("clear_light")

        async def hide(self):
            log.events.append("hide")

        def set_state(self, state):
            log.events.append(f"state:{state}")

    class AutoHide:
        def cancel(self):
            log.events.append("cancel_autohide")

    async def screen_capture():
        log.events.append("grab")
        return b"PHYS"

    async def downscale(raw):
        log.events.append("downscale")
        assert raw == b"PHYS"
        return DownscaledImage(sent_bytes=b"SENT", sent_width=800, sent_height=450,
                               scale_x=2.0, scale_y=2.25)

    return Overlay(), AutoHide(), screen_capture, downscale


def test_capture_order_is_load_bearing_and_scales_recorded():
    log = _Log(events=[])
    overlay, auto_hide, grab, down = _fake_world(log)
    frames = FrameCapture(overlay=overlay, screen_capture=grab, downscale=down,
                          auto_hide=auto_hide, settle_s=0)
    result = TurnResult()
    sent = asyncio.run(frames.capture(result))
    assert sent == b"SENT"
    assert log.events == ["cancel_autohide", "clear_light", "hide",
                          "grab", "downscale", "state:thinking"]
    assert (result.sent_width, result.sent_height) == (800, 450)
    assert (result.scale_x, result.scale_y) == (2.0, 2.25)


def test_default_settle_matches_the_v1_constant():
    assert OVERLAY_SETTLE_S == 0.05
