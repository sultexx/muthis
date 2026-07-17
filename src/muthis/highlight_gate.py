# src/muthis/highlight_gate.py
"""Compat shim (V2 Phase 0): the module moved to muthis.kernel.highlight_gate.
Kept until Phase 1 (decision Q-4); new code imports from muthis.kernel.*."""

from .kernel.highlight_gate import (
    HIGHLIGHT_ACK_TEXT_AR,
    HIGHLIGHT_ALREADY_SHOWN_AR,
    HighlightGate,
    INTERRUPTED_NOTE_AR,
    SHAPES_ACK_TEXT_AR,
    SHAPES_ALREADY_SHOWN_AR,
    draw_result_text,
    highlight_result_text,
    loop_tool_choice,
)

__all__ = [
    "HighlightGate", "HIGHLIGHT_ACK_TEXT_AR", "HIGHLIGHT_ALREADY_SHOWN_AR",
    "SHAPES_ACK_TEXT_AR", "SHAPES_ALREADY_SHOWN_AR", "INTERRUPTED_NOTE_AR",
    "draw_result_text", "highlight_result_text", "loop_tool_choice",
]
