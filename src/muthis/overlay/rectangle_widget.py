# src/muthis/overlay/rectangle_widget.py
"""
RectangleWidget — draws the single neon highlight rectangle + a short Arabic
caption on a full-window Tk canvas.

Pure VIEW: it owns no coordinates and never scales. draw() is handed
ALREADY-PHYSICAL pixel coords by SidekickOverlay (which got them physical from
the orchestrator), and the window sits at (0,0) filling the primary monitor, so
canvas coords == screen coords and the bbox is used verbatim.

NEON LOOK (Batch 1): the color (default neon cyan), the glow layering, and the
caption chip font/plate come from the injected `OverlayStyle` (from `.env`, neon
defaults). The rectangle is drawn in TWO passes — a dim outer HALO then the
bright CORE outline — emulating a glow; the caption rides a rounded semi-dark
chip. Interior stays unfilled so the highlighted element shows through. Only the
LOOK changes: draw()/clear() (delete-all) semantics are byte-for-byte the same,
so the ghosting rule is untouched.

Lives on the Tk thread only (constructed and called from SidekickOverlay._run).
tkinter is imported here, never by the orchestrator.
"""

from __future__ import annotations

from typing import Optional

import tkinter as tk

from .style import OverlayStyle, color_for, draw_caption_chip, glow_strokes


class RectangleWidget:
    """A transparent full-window canvas showing one rectangle + caption."""

    def __init__(
        self, root: tk.Tk, transparent_key: str,
        style: Optional[OverlayStyle] = None,
    ) -> None:
        # bg == the window's transparent color key, so everything we DON'T draw
        # is see-through and clicks land on the app beneath.
        self._canvas = tk.Canvas(
            root, highlightthickness=0, bd=0, bg=transparent_key,
        )
        self._canvas.pack(fill="both", expand=True)
        # Injected for tuning/tests; from_env() is the graceful neon fallback.
        self._style = style or OverlayStyle.from_env()

    @property
    def canvas(self) -> tk.Canvas:
        """The shared full-window canvas, exposed so the gliding PointerWidget can
        draw its arrow on the SAME canvas (Tk -transparentcolor keys at the window
        level, so the pointer and rectangle must share one canvas to composite).
        The pointer scopes its items by tag, so the two never clobber each other."""
        return self._canvas

    def draw(self, bbox: tuple[int, int, int, int], label_ar: str) -> None:
        """Replace whatever is shown with one glowing rectangle at PHYSICAL bbox
        plus an Arabic caption above its top-left corner."""
        self.clear()
        x1, y1, x2, y2 = bbox
        color = color_for(self._style, "highlight")
        for width, stroke in glow_strokes(self._style, color):
            self._canvas.create_rectangle(
                x1, y1, x2, y2, outline=stroke, width=width,
            )
        if label_ar:
            draw_caption_chip(
                self._canvas, x1, y1, label_ar, self._style, text_color=color,
            )

    def clear(self) -> None:
        """Erase the rectangle + caption (the hide()/ghosting path)."""
        self._canvas.delete("all")


__all__ = ["RectangleWidget"]
