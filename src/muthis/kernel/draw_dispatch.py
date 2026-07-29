# src/muthis/kernel/draw_dispatch.py
"""
Unified draw dispatch — ONE pending draw per pass, ONE gate for BOTH draw tools.

Phase B-1 wires draw_shapes into the agentic loop with the SAME two-pass
discipline as highlight_target: buffer the FIRST draw-type ToolCall of the pass
(scaled sent→physical HERE), apply it on the overlay at speak-time, and let the
pairing (turn.build_tool_result_message → highlight_gate.draw_result_text) flip
the per-turn HighlightGate so the NEXT run() is forced tool_choice="none"
(highlight_gate.loop_tool_choice). A single `pending: Optional[PendingDraw]`
covers both tools, so within one pass the first draw wins no matter which tool
(or mix of tools) asked — exactly the suppression next_highlight always gave
highlight_target, now spanning draw_shapes too.

LOOK-only: applying a PendingDraw only DRAWS overlay graphics — never the
mouse, never a click, never typing.

Lives in its own module because orchestrator.py is at the ≤300-line ceiling
(split, don't compress) and highlight_gate.py cannot host it (turn.py imports
highlight_gate — importing turn back would be a cycle).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from ..cloud.protocol import ToolCall
from .highlight_gate import HighlightGate
from ..shapes import Shape, parse_shapes_args, scale_shapes_to_physical
from .turn import PhysicalBBox, scale_bbox_to_physical

logger = logging.getLogger("muthis.draw_dispatch")

# The two LOOK draw tools — either one buffers into the SAME PendingDraw slot
# and (at pairing time) flips the SAME per-turn gate.
HIGHLIGHT_TOOL = "highlight_target"
DRAW_SHAPES_TOOL = "draw_shapes"
DRAW_TOOLS = frozenset({HIGHLIGHT_TOOL, DRAW_SHAPES_TOOL})


@dataclass(frozen=True)
class PendingDraw:
    """The ONE buffered draw of a pass, ALREADY sent→physical, applied at
    speak-time. Exactly one payload is set: `highlight` for highlight_target
    (drawn via overlay.show — behavior identical to the pre-B-1 loop),
    `shapes` for draw_shapes (drawn via overlay.draw_shapes). `dim` (v7
    Phase 2, draw_shapes only) is the WHITEBOARD: the whole screen fades
    dark behind the shapes; run_turn's finally lifts it at speech end."""

    highlight: Optional[tuple[PhysicalBBox, str]] = None
    shapes: tuple[Shape, ...] = ()
    dim: bool = False

    async def apply(self, overlay: Any) -> None:
        """Draw on the overlay (LOOK-only graphics). An overlay without
        draw_shapes (e.g. stub_overlay) logs and skips — a draw must never
        crash the turn; the pairing/gate upstream still run normally."""
        if self.highlight is not None:
            await overlay.show(*self.highlight)
        elif self.shapes:
            if self.dim:
                # Whiteboard: darken FIRST so the shapes land on the board
                # (both are queue commands on the Tk thread, FIFO-ordered).
                # Duck-typed like draw_shapes: an overlay without it (stubs,
                # old fakes) just skips the dim, never the drawing.
                dim_screen = getattr(overlay, "dim_screen", None)
                if dim_screen is not None:
                    dim_screen()
                else:
                    logger.warning(
                        "[draw_dispatch] overlay lacks dim_screen — drawing undimmed")
            draw = getattr(overlay, "draw_shapes", None)
            if draw is None:
                logger.warning(
                    "[draw_dispatch] overlay lacks draw_shapes — skipping draw")
                return
            await draw(self.shapes)


def next_draw(
    gate: HighlightGate,
    pending: Optional[PendingDraw],
    event: ToolCall,
    scale_x: float,
    scale_y: float,
) -> Optional[PendingDraw]:
    """Circuit breaker (draw half), generalized over BOTH draw tools: buffer
    the FIRST draw of the turn and return `pending` unchanged for every later
    one — `gate.drawn` blocks across passes (flipped at pairing time by
    draw_result_text), `pending is not None` blocks within the SAME pass — so
    at most ONE draw happens per user turn no matter which tool, or mix of
    tools, asked. Mirrors turn.next_highlight (same scale site for the bbox).
    A draw_shapes call whose list parses to nothing valid buffers nothing;
    it is still paired + gated upstream so the loop cannot spin on it."""
    if gate.drawn or pending is not None:
        return pending
    if event.name == HIGHLIGHT_TOOL:
        bbox = scale_bbox_to_physical(event.args, scale_x, scale_y)
        return PendingDraw(highlight=(bbox, event.args.get("label_ar", "")))
    shapes = parse_shapes_args(event.args)
    if not shapes:
        logger.warning("[draw_dispatch] draw_shapes carried no valid shapes")
        return pending
    return PendingDraw(shapes=scale_shapes_to_physical(shapes, scale_x, scale_y),
                       dim=bool(event.args.get("dim_screen")))


__all__ = [
    "DRAW_TOOLS", "HIGHLIGHT_TOOL", "DRAW_SHAPES_TOOL", "PendingDraw",
    "next_draw",
]
