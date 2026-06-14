# src/muthis/overlay/rectangle_widget.py
"""
RectangleWidget — draws the single cyan highlight rectangle + a short Arabic
caption on a full-window Tk canvas.

Pure VIEW: it owns no coordinates and never scales. draw() is handed
ALREADY-PHYSICAL pixel coords by SidekickOverlay (which got them physical from
the orchestrator), and the window sits at (0,0) filling the primary monitor, so
canvas coords == screen coords and the bbox is used verbatim.

Lives on the Tk thread only (constructed and called from SidekickOverlay._run).
Split out of sidekick_window.py to keep each file single-responsibility and well
under the 300-line law. tkinter is imported here, never by the orchestrator.
"""

from __future__ import annotations

import tkinter as tk

# Cyan outline a few px wide so it reads over any UI. The interior is left
# unfilled (the transparent color key shows through) so the highlighted element
# stays fully visible underneath the rectangle.
RECTANGLE_COLOR = "#00FFFF"
RECTANGLE_WIDTH_PX = 3

# Caption: cyan text on a small dark plate for legibility over any background.
# Segoe UI ships with Win11 and renders Arabic glyphs.
CAPTION_FONT = ("Segoe UI", 14, "bold")
CAPTION_TEXT_COLOR = "#00FFFF"
CAPTION_PLATE_COLOR = "#002633"
CAPTION_PAD_PX = 6


class RectangleWidget:
    """A transparent full-window canvas showing one rectangle + caption."""

    def __init__(self, root: tk.Tk, transparent_key: str) -> None:
        # bg == the window's transparent color key, so everything we DON'T draw
        # is see-through and clicks land on the app beneath.
        self._canvas = tk.Canvas(
            root, highlightthickness=0, bd=0, bg=transparent_key,
        )
        self._canvas.pack(fill="both", expand=True)

    def draw(self, bbox: tuple[int, int, int, int], label_ar: str) -> None:
        """Replace whatever is shown with one rectangle at PHYSICAL bbox plus an
        Arabic caption above its top-left corner."""
        self.clear()
        x1, y1, x2, y2 = bbox
        self._canvas.create_rectangle(
            x1, y1, x2, y2,
            outline=RECTANGLE_COLOR, width=RECTANGLE_WIDTH_PX,
        )
        if label_ar:
            self._draw_caption(x1, y1, label_ar)

    def clear(self) -> None:
        """Erase the rectangle + caption (the hide()/ghosting path)."""
        self._canvas.delete("all")

    def _draw_caption(self, x: int, y: int, label_ar: str) -> None:
        """Caption just above the rectangle's top-left, on a small dark plate so
        the Arabic text stays legible over any desktop content."""
        text_id = self._canvas.create_text(
            x + CAPTION_PAD_PX, y - CAPTION_PAD_PX,
            text=label_ar, anchor="sw",
            fill=CAPTION_TEXT_COLOR, font=CAPTION_FONT,
        )
        # Draw the plate behind the text, then push it below the text.
        bounds = self._canvas.bbox(text_id)
        if bounds is not None:
            bx1, by1, bx2, by2 = bounds
            plate = self._canvas.create_rectangle(
                bx1 - CAPTION_PAD_PX, by1 - CAPTION_PAD_PX // 2,
                bx2 + CAPTION_PAD_PX, by2 + CAPTION_PAD_PX // 2,
                fill=CAPTION_PLATE_COLOR, outline=CAPTION_PLATE_COLOR,
            )
            self._canvas.tag_lower(plate, text_id)


__all__ = ["RectangleWidget"]
