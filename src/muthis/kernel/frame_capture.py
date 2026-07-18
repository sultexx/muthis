# src/muthis/kernel/frame_capture.py
"""
FrameCapture — the hide→settle→capture chokepoint, extracted WHOLE from
orchestrator._capture_downscaled (V2 Phase 1 M1-2).

WHY the extraction: orchestrator.py sat at the 300-line ceiling and Phase 1
must inject the ToolRouter seam there (roadmap part 2 §1) — the law says
extract BEFORE adding, and this method was the cleanest single-responsibility
seam (it already owned every capture of the app: the initial frame AND each
in-loop refresh).

The ORDER inside capture() is load-bearing and unchanged from V1:
cancel stale auto-hide → clear the status dot → hide the overlay → settle
(OVERLAY_SETTLE_S) → grab physical pixels → downscale to the payload COPY →
relight the dot ("thinking") → record sent dims + physical↔sent scale
factors on the TurnResult. Claude must never see our own overlay, a ghost
of the previous highlight, or the corner dot baked into a screenshot.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from .turn import TurnResult

# Hide our rectangle, then yield this long before grabbing so the Tk thread has
# cleared it — Claude never sees a ghost of the previous highlight. 50 ms is ample.
OVERLAY_SETTLE_S = 0.05


class FrameCapture:
    """One per Orchestrator; built from the same injected seams. Stateless
    between calls — it owns no lifecycle (Law 11), only the chokepoint."""

    def __init__(self, *, overlay, screen_capture, downscale, auto_hide,
                 settle_s: float = OVERLAY_SETTLE_S) -> None:
        self._overlay = overlay
        self._screen_capture = screen_capture
        self._downscale = downscale
        self._auto_hide = auto_hide
        self._settle_s = settle_s

    async def capture(self, result: TurnResult) -> Optional[bytes]:
        """Capture physical pixels → the downscaled COPY (the ONLY thing sent),
        recording the physical↔sent scale factors so highlight coords map back.
        Ghosting: clear the status dot + hide the rectangle BEFORE every grab —
        the one chokepoint for the initial capture AND each in-loop refresh;
        order is load-bearing (cancel + clear + hide → settle → capture)."""
        self._auto_hide.cancel()  # drop any stale auto-hide before the explicit hide
        self._overlay.clear_status_light()  # ghost the corner dot — Claude never sees it
        await self._overlay.hide()
        await asyncio.sleep(self._settle_s)
        sent = await self._downscale(await self._screen_capture())
        self._overlay.set_state("thinking")  # dot reappears (thinking) after the grab
        result.sent_width, result.sent_height = sent.sent_width, sent.sent_height
        result.scale_x, result.scale_y = sent.scale_x, sent.scale_y
        return sent.sent_bytes


__all__ = ["FrameCapture", "OVERLAY_SETTLE_S"]
