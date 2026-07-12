# src/muthis/overlay/pointer_widget.py
"""
PointerWidget — draws the small gliding LOOK pointer (a cursor-style arrow) on
the overlay canvas it SHARES with the RectangleWidget.

LOOK-ONLY: this is a DRAWN shape only. It never moves, warps, or clicks the real
OS mouse — the gliding arrow is pure visual output. (PointerAnimator reads the OS
cursor position once, read-only, as the glide's START; see pointer_animator.py.)

Pure VIEW on the Tk thread: move_to() is handed ALREADY-PHYSICAL pixel coords
(the orchestrator scaled sent→physical; the animator interpolates between two
physical points). It shares the RectangleWidget's canvas — Tk -transparentcolor
keys at the WINDOW level, so two stacked canvases can't composite — and owns ONLY
its own items via POINTER_TAG, so clearing the pointer never disturbs the
rectangle and vice-versa.

NEON LOOK (Batch 1): color and glow come from the injected `OverlayStyle` (from
`.env`, neon defaults). The arrow is drawn in TWO passes — a dim, wide-outlined
HALO polygon then the bright CORE polygon with a crisp dark edge — emulating a
neon glow (Tk has no per-item alpha). Glow off → just the crisp core. Only the
LOOK changes: the tip still sits exactly on the glide coordinate.

No tkinter import here: the canvas is duck-typed (create_polygon/delete), so this
module and its unit test stay importable without a display.
"""

from __future__ import annotations

from typing import Optional

from .style import OverlayStyle, color_for, dim

# All pointer canvas items carry this tag, so the pointer can be cleared without
# disturbing the rectangle/caption that share the canvas.
POINTER_TAG = "muthis-pointer"

# The bright core keeps a thin crisp edge so the arrow reads over any UI.
POINTER_CORE_OUTLINE_WIDTH = 1

# A small classic cursor arrow as (dx, dy) offsets from the TIP. The tip sits
# exactly on the glide coordinate, so the arrow points AT the target.
_ARROW_OFFSETS = (
    (0, 0), (0, 16), (4, 12), (7, 18), (9, 17), (6, 11), (11, 11),
)


class PointerWidget:
    """The gliding neon arrow. Draws/moves/clears ONLY its own tagged items on a
    canvas it shares with the RectangleWidget (a real tk.Canvas in production)."""

    def __init__(self, canvas, style: Optional[OverlayStyle] = None) -> None:
        self._canvas = canvas
        # Injected for tuning/tests; from_env() is the graceful neon fallback.
        self._style = style or OverlayStyle.from_env()

    def move_to(self, x: int, y: int) -> None:
        """Redraw the arrow with its TIP at PHYSICAL (x, y). Replaces the previous
        frame by tag (never delete-all), so the rectangle is never touched."""
        self.clear()
        points: list[int] = []
        for dx, dy in _ARROW_OFFSETS:
            points.append(x + dx)
            points.append(y + dy)
        color = color_for(self._style, "pointer")
        style = self._style
        if style.glow_enabled:
            # Dim, wide-outlined silhouette underneath → a glow aura around the arrow.
            halo = dim(color, style.glow_intensity)
            self._canvas.create_polygon(
                *points, fill=halo, outline=halo,
                width=2 * style.glow_width, tags=POINTER_TAG,
            )
        self._canvas.create_polygon(
            *points, fill=color, outline=style.pointer_outline,
            width=POINTER_CORE_OUTLINE_WIDTH, tags=POINTER_TAG,
        )

    def clear(self) -> None:
        """Erase ONLY the pointer items (the hide()/ghosting path and the
        per-frame redraw). A no-op when nothing is drawn."""
        self._canvas.delete(POINTER_TAG)


__all__ = ["PointerWidget", "POINTER_TAG"]
