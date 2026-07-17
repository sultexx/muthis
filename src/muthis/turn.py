# src/muthis/turn.py
"""Compat shim (V2 Phase 0): the module moved to muthis.kernel.turn.
Kept until Phase 1 (decision Q-4); new code imports from muthis.kernel.*."""

from .kernel.turn import (
    AGENTIC_CAP_NOTE_AR,
    BUDGET_REFUSAL_AR,
    DownscaledImage,
    DownscaleFn,
    HIGHLIGHT_ACK_TEXT_AR,
    HIGHLIGHT_ALREADY_SHOWN_AR,
    MIC_FAILED_AR,
    MicFn,
    NO_SCREENSHOT_TOOL_RESULT_AR,
    Overlay,
    PhysicalBBox,
    REFRESH_FOLLOWUP_TEXT_AR,
    STALE_SCREENSHOT_NOTE_AR,
    STT_EMPTY_AR,
    ScreenCaptureFn,
    SttFn,
    TtsFn,
    TurnResult,
    build_tool_result_message,
    next_highlight,
    scale_bbox_to_physical,
    strip_images_from_history,
)

__all__ = [
    "DownscaledImage",
    "MicFn", "SttFn", "TtsFn", "ScreenCaptureFn", "DownscaleFn",
    "Overlay", "PhysicalBBox", "scale_bbox_to_physical",
    "BUDGET_REFUSAL_AR", "REFRESH_FOLLOWUP_TEXT_AR",
    "NO_SCREENSHOT_TOOL_RESULT_AR", "MIC_FAILED_AR", "STT_EMPTY_AR",
    "AGENTIC_CAP_NOTE_AR", "HIGHLIGHT_ACK_TEXT_AR", "HIGHLIGHT_ALREADY_SHOWN_AR",
    "next_highlight",
    "TurnResult", "build_tool_result_message",
    "STALE_SCREENSHOT_NOTE_AR", "strip_images_from_history",
]
