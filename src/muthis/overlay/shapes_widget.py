# src/muthis/overlay/shapes_widget.py
"""
ShapesWidget — draws a LIST of geometric LOOK shapes (line / arrow / circle /
rectangle / numbered step badge, each with an optional Arabic caption) on the
overlay canvas it SHARES with the RectangleWidget and PointerWidget.

LOOK-ONLY: these are DRAWN graphics only — never the mouse, never a click,
never typing.

Pure VIEW on the Tk thread: draw() is handed ALREADY-PHYSICAL Shape objects
(shapes.scale_shapes_to_physical did the sent→physical multiply) and never
rescales. It owns ONLY its own items via SHAPES_TAG — mirroring PointerWidget —
so clearing shapes never disturbs the highlight rectangle or the pointer.

NEON LOOK (Batch 1): every style value — per-kind neon color, the glow layering,
the core width, the caption chip font/plate — comes from the injected
`OverlayStyle` (from `.env`, neon defaults). Each shape is drawn in TWO passes: a
dim outer HALO then a bright CORE (see style.glow_strokes), emulating a glow;
the caption rides a rounded semi-dark chip. Colors/glow only — the coordinates,
the SHAPES_TAG ghosting discipline, and the Tk-thread queue are untouched.

KNOWN interplay (accepted; highlight_target stays untouched): the highlight's
RectangleWidget clears with delete("all"), so a NEW highlight_target wipes any
drawn shapes — a fresh highlight means a fresh visual state. hide() clears
shapes explicitly (the ghosting rule — nothing survives into the next capture).

No tkinter import: the canvas is duck-typed (create_line / create_oval /
create_rectangle / create_polygon / create_text / bbox / tag_lower / delete), so
this module and its unit tests stay importable without a display.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ..shapes import Shape
from .style import OverlayStyle, color_for, draw_caption_chip, glow_strokes

# Tk arrowhead spec (d1, d2, d3): length along the line, overall length, flank
# width — sized to read clearly at 1080p. The halo pass scales it up with its
# width so the glow wraps the arrowhead too.
ARROW_SHAPE = (16, 20, 7)
# tk.LAST == "last"; the literal keeps tkinter out of this module.
ARROW_AT_END = "last"

# Every shape canvas item carries this tag, so shapes clear without disturbing
# the rectangle/pointer that share the canvas (never delete("all") here).
SHAPES_TAG = "muthis-shapes"

# User-facing numerals are Arabic-Indic (the language-split law: surfaces are Arabic).
ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def arabic_indic(number: int) -> str:
    """Render 1 → "١", 12 → "١٢" for the step badges."""
    return "".join(ARABIC_INDIC_DIGITS[int(d)] for d in str(number))


class ShapesWidget:
    """A tag-scoped multi-shape renderer on the shared overlay canvas."""

    def __init__(self, canvas, style: Optional[OverlayStyle] = None) -> None:
        self._canvas = canvas
        # Injected for tuning/tests; from_env() is the graceful neon fallback.
        self._style = style or OverlayStyle.from_env()

    def draw(self, shapes: Sequence[Shape]) -> None:
        """Replace any previously drawn shapes with this list (each at
        ALREADY-PHYSICAL coords, window at (0,0) → canvas coords == screen
        coords). An unknown kind is skipped quietly — the Tk thread must
        never die on bad data. Step badges are numbered here by their ORDER
        among the step shapes of the list (v6 B — the model sends no number;
        the render counts), so numbering restarts with every draw()."""
        self.clear()
        step_number = 0
        for shape in shapes:
            if shape.kind == "step":
                step_number += 1
                self._draw_step(shape, step_number)
            else:
                self._draw_one(shape)

    def clear(self) -> None:
        """Erase ONLY the shape items (the hide()/ghosting path). A no-op when
        nothing is drawn; the rectangle and pointer are never touched."""
        self._canvas.delete(SHAPES_TAG)

    def _draw_one(self, shape: Shape) -> None:
        x1, y1, x2, y2 = shape.points
        color = color_for(self._style, shape.kind)
        strokes = glow_strokes(self._style, color)  # [halo, core] (or [core])
        if shape.kind == "line":
            for width, stroke in strokes:
                self._canvas.create_line(
                    x1, y1, x2, y2,
                    fill=stroke, width=width, tags=SHAPES_TAG,
                )
        elif shape.kind == "arrow":
            for width, stroke in strokes:
                self._canvas.create_line(
                    x1, y1, x2, y2,
                    fill=stroke, width=width,
                    arrow=ARROW_AT_END, arrowshape=self._arrowshape(width),
                    tags=SHAPES_TAG,
                )
        elif shape.kind == "circle":
            # Unfilled like the highlight rectangle, so the circled element
            # stays fully visible underneath.
            for width, stroke in strokes:
                self._canvas.create_oval(
                    x1, y1, x2, y2,
                    outline=stroke, width=width, tags=SHAPES_TAG,
                )
        elif shape.kind == "rectangle":
            for width, stroke in strokes:
                self._canvas.create_rectangle(
                    x1, y1, x2, y2,
                    outline=stroke, width=width, tags=SHAPES_TAG,
                )
        else:
            return
        if shape.label_ar:
            draw_caption_chip(
                self._canvas, min(x1, x2), min(y1, y2), shape.label_ar,
                self._style, text_color=color, tags=SHAPES_TAG,
            )

    def _draw_step(self, shape: Shape, number: int) -> None:
        """One numbered badge (v6 B): an UNFILLED neon ring (the element under
        it stays visible — the highlight-rectangle philosophy) with the
        Arabic-Indic step numeral crisp at its center. Ring + numeral share the
        circle's neon color (MUTHIS_COLOR_CIRCLE — no new env, plan decision),
        and the optional caption chip rides below like every other kind."""
        x1, y1, x2, y2 = shape.points
        color = color_for(self._style, "circle")
        for width, stroke in glow_strokes(self._style, color):
            self._canvas.create_oval(
                x1, y1, x2, y2,
                outline=stroke, width=width, tags=SHAPES_TAG,
            )
        # ONE crisp bold numeral, sized to the badge so ١ and ١٢ both read
        # clearly; no halo pass — glowing text smears legibility.
        numeral_size = max(10, round(min(abs(x2 - x1), abs(y2 - y1)) * 0.5))
        self._canvas.create_text(
            (x1 + x2) / 2, (y1 + y2) / 2,
            text=arabic_indic(number), fill=color,
            font=(self._style.label_font_family, numeral_size, "bold"),
            tags=SHAPES_TAG,
        )
        if shape.label_ar:
            draw_caption_chip(
                self._canvas, min(x1, x2), min(y1, y2), shape.label_ar,
                self._style, text_color=color, tags=SHAPES_TAG,
            )

    def _arrowshape(self, width: float) -> tuple[int, int, int]:
        """Scale the arrowhead with the stroke width so the halo pass glows a
        proportionally larger head under the crisp core head."""
        scale = width / self._style.core_width if self._style.core_width else 1
        return tuple(round(v * scale) for v in ARROW_SHAPE)


__all__ = [
    "ShapesWidget", "SHAPES_TAG", "ARROW_AT_END", "ARROW_SHAPE", "arabic_indic",
]
