# src/muthis/draw_dispatch.py
"""Compat shim (V2 Phase 0): the module moved to muthis.kernel.draw_dispatch.
Kept until Phase 1 (decision Q-4); new code imports from muthis.kernel.*."""

from .kernel.draw_dispatch import (
    DRAW_SHAPES_TOOL,
    DRAW_TOOLS,
    HIGHLIGHT_TOOL,
    PendingDraw,
    next_draw,
)

__all__ = [
    "DRAW_TOOLS", "HIGHLIGHT_TOOL", "DRAW_SHAPES_TOOL", "PendingDraw",
    "next_draw",
]
