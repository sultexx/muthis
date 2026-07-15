"""
test_shapes_widget.py — ShapesWidget drawing on a FAKE canvas (no Tk, no
display), mirroring test_pointer_widget.py, now for the NEON look (Batch 1):

  * each of the four kinds draws its Tk primitive at the given PHYSICAL coords
    (line → create_line, arrow → create_line with an arrowhead, circle →
    create_oval, rectangle → create_rectangle), all tag-scoped,
  * GLOW LAYERING — every shape emits TWO passes, a dim outer HALO then a bright
    CORE (style.glow_strokes), the core carrying that kind's neon color,
  * an Arabic label draws a caption on a rounded chip (smooth polygon) above the
    shape; an empty label draws none,
  * draw() replaces by clearing ONLY the shapes tag (never delete-all), so the
    highlight rectangle/pointer sharing the canvas are never disturbed,
  * an unknown kind is skipped quietly (the Tk thread must never die).

Env is cleared by conftest, so ShapesWidget's from_env() fallback yields the
documented neon defaults deterministically.

Run:  set PYTHONPATH=src && python -m pytest tests/test_shapes_widget.py -q
"""

from __future__ import annotations

from muthis.overlay.shapes_widget import (
    ARROW_AT_END,
    SHAPES_TAG,
    ShapesWidget,
    arabic_indic,
)
from muthis.overlay.style import OverlayStyle, dim
from muthis.shapes import Shape, circle_shape

# The deterministic neon defaults the widget's from_env() fallback resolves to
# (conftest clears the MUTHIS_* overlay env), used to assert exact colors.
DEFAULTS = OverlayStyle()


# ──────────────────────────────── Fake canvas ────────────────────────────────


class FakeCanvas:
    """Records every draw primitive; bbox() returns a plausible text bounds."""

    def __init__(self):
        self.lines = []          # (coords, kwargs)
        self.ovals = []
        self.rectangles = []
        self.polygons = []       # the rounded caption chip lands here
        self.texts = []
        self.deleted = []        # tags handed to delete()
        self.lowered = []
        self._next_id = 0

    def _new_id(self):
        self._next_id += 1
        return self._next_id

    def create_line(self, *coords, **kwargs):
        self.lines.append((coords, kwargs))
        return self._new_id()

    def create_oval(self, *coords, **kwargs):
        self.ovals.append((coords, kwargs))
        return self._new_id()

    def create_rectangle(self, *coords, **kwargs):
        self.rectangles.append((coords, kwargs))
        return self._new_id()

    def create_polygon(self, *coords, **kwargs):
        self.polygons.append((coords, kwargs))
        return self._new_id()

    def create_text(self, *coords, **kwargs):
        self.texts.append((coords, kwargs))
        return self._new_id()

    def bbox(self, item_id):
        return (100, 100, 160, 120)

    def tag_lower(self, lower, upper):
        self.lowered.append((lower, upper))

    def delete(self, tag):
        self.deleted.append(tag)


# ──────────────────────────────── Tests ────────────────────────────────


def test_each_kind_draws_its_primitive_at_the_physical_coords():
    canvas = FakeCanvas()
    ShapesWidget(canvas).draw([
        Shape(kind="line", points=(10, 20, 30, 40)),
        Shape(kind="arrow", points=(50, 60, 70, 80)),
        circle_shape(200, 200, 50),
        Shape(kind="rectangle", points=(300, 300, 400, 350)),
    ])

    # Two create_line per line-like shape (halo + core): line ×2, arrow ×2.
    assert len(canvas.lines) == 4
    # line: both passes at the SAME physical coords; only the CORE (2nd) is neon.
    assert canvas.lines[0][0] == (10, 20, 30, 40)
    assert canvas.lines[1][0] == (10, 20, 30, 40)
    assert canvas.lines[1][1]["fill"] == DEFAULTS.colors["line"]
    assert canvas.lines[0][1]["width"] > canvas.lines[1][1]["width"]  # halo wider
    assert "arrow" not in canvas.lines[0][1]                          # plain line
    # arrow: passes 3 & 4, each carrying the arrowhead; core in neon green.
    assert canvas.lines[2][0] == (50, 60, 70, 80)
    assert canvas.lines[2][1]["arrow"] == ARROW_AT_END
    assert canvas.lines[3][1]["fill"] == DEFAULTS.colors["arrow"]
    # circle draws the enclosing bbox as an oval; rectangle is verbatim — each
    # with 2 passes, the neon core last.
    assert len(canvas.ovals) == 2 and canvas.ovals[0][0] == (150, 150, 250, 250)
    assert canvas.ovals[1][1]["outline"] == DEFAULTS.colors["circle"]
    assert len(canvas.rectangles) == 2 and canvas.rectangles[0][0] == (300, 300, 400, 350)
    assert canvas.rectangles[1][1]["outline"] == DEFAULTS.colors["rectangle"]


def test_glow_emits_a_dim_halo_under_a_bright_core():
    # The halo is the neon color dimmed by glow_intensity, drawn first (under);
    # the core is the full neon color, drawn second (on top).
    canvas = FakeCanvas()
    ShapesWidget(canvas).draw([Shape(kind="line", points=(0, 0, 100, 0))])

    halo, core = canvas.lines[0][1], canvas.lines[1][1]
    assert core["fill"] == DEFAULTS.colors["line"]
    assert halo["fill"] == dim(DEFAULTS.colors["line"], DEFAULTS.glow_intensity)
    assert halo["width"] == DEFAULTS.core_width + 2 * DEFAULTS.glow_width
    assert core["width"] == DEFAULTS.core_width


def test_glow_can_be_disabled_leaving_a_single_crisp_core():
    canvas = FakeCanvas()
    ShapesWidget(canvas, OverlayStyle(glow_enabled=False)).draw(
        [Shape(kind="rectangle", points=(1, 2, 3, 4))]
    )
    # One pass only — the crisp neon core, no halo underneath.
    assert len(canvas.rectangles) == 1
    assert canvas.rectangles[0][1]["outline"] == DEFAULTS.colors["rectangle"]


def test_every_item_is_scoped_to_the_shapes_tag():
    canvas = FakeCanvas()
    ShapesWidget(canvas).draw([
        Shape(kind="line", points=(0, 0, 1, 1), label_ar="خط"),
        Shape(kind="rectangle", points=(2, 2, 3, 3)),
    ])

    every_kwargs = [
        kwargs
        for group in (canvas.lines, canvas.ovals, canvas.rectangles,
                      canvas.polygons, canvas.texts)
        for _, kwargs in group
    ]
    assert every_kwargs, "nothing was drawn"
    assert all(kwargs.get("tags") == SHAPES_TAG for kwargs in every_kwargs)


def test_a_label_draws_a_caption_chip_and_an_empty_label_draws_none():
    canvas = FakeCanvas()
    ShapesWidget(canvas).draw([
        Shape(kind="line", points=(10, 20, 30, 40), label_ar="خط"),
        Shape(kind="rectangle", points=(50, 60, 70, 80)),   # no label
    ])

    assert len(canvas.texts) == 1
    assert canvas.texts[0][1]["text"] == "خط"
    assert canvas.texts[0][1]["fill"] == DEFAULTS.colors["line"]   # per-shape text
    # The caption rides ONE rounded chip (a smooth polygon), pushed below its text.
    assert len(canvas.polygons) == 1
    assert canvas.polygons[0][1].get("smooth") is True
    assert canvas.polygons[0][1]["fill"] == DEFAULTS.label_plate
    assert len(canvas.lowered) == 1


def test_draw_replaces_by_clearing_only_the_shapes_tag():
    canvas = FakeCanvas()
    widget = ShapesWidget(canvas)

    widget.draw([Shape(kind="line", points=(0, 0, 1, 1))])
    widget.draw([Shape(kind="rectangle", points=(2, 2, 3, 3))])
    widget.clear()

    # Three clears (one per draw + the explicit one), ALL by tag — never "all",
    # so the highlight rectangle/pointer on the shared canvas survive.
    assert canvas.deleted == [SHAPES_TAG, SHAPES_TAG, SHAPES_TAG]


def test_an_unknown_kind_is_skipped_quietly():
    canvas = FakeCanvas()
    bogus = Shape(kind="triangle", points=(0, 0, 1, 1), label_ar="مثلث")  # type: ignore[arg-type]

    ShapesWidget(canvas).draw([bogus])

    assert canvas.lines == [] and canvas.ovals == [] and canvas.rectangles == []
    assert canvas.polygons == [] and canvas.texts == []   # not even the caption


# ─────────────────────── Numbered step badges (v6 B2) ───────────────────────


def test_a_step_draws_a_ring_with_a_centered_arabic_indic_numeral():
    canvas = FakeCanvas()
    ShapesWidget(canvas).draw([Shape(kind="step", points=(100, 100, 140, 140))])

    # Ring: two glow passes (halo + core) as ovals at the physical bbox,
    # in the CIRCLE's neon color (MUTHIS_COLOR_CIRCLE — no new env).
    assert len(canvas.ovals) == 2
    assert canvas.ovals[0][0] == (100, 100, 140, 140)
    assert canvas.ovals[1][1]["outline"] == DEFAULTS.colors["circle"]
    assert canvas.ovals[0][1]["width"] > canvas.ovals[1][1]["width"]
    # ONE crisp numeral at the badge center, Arabic-Indic, badge-scaled bold.
    assert len(canvas.texts) == 1
    coords, kwargs = canvas.texts[0]
    assert coords == (120.0, 120.0)
    assert kwargs["text"] == "١"
    assert kwargs["fill"] == DEFAULTS.colors["circle"]
    assert kwargs["font"] == (DEFAULTS.label_font_family, 20, "bold")
    assert kwargs["tags"] == SHAPES_TAG


def test_steps_are_numbered_by_list_order_counting_steps_only():
    canvas = FakeCanvas()
    ShapesWidget(canvas).draw([
        Shape(kind="step", points=(10, 10, 40, 40)),
        Shape(kind="arrow", points=(50, 50, 90, 90)),   # not a step: no number
        Shape(kind="step", points=(100, 100, 130, 130)),
        Shape(kind="step", points=(200, 200, 230, 230)),
    ])

    numerals = [kwargs["text"] for _, kwargs in canvas.texts]
    assert numerals == ["١", "٢", "٣"]


def test_step_numbering_restarts_on_every_draw():
    canvas = FakeCanvas()
    widget = ShapesWidget(canvas)
    widget.draw([Shape(kind="step", points=(10, 10, 40, 40))])
    widget.draw([Shape(kind="step", points=(50, 50, 80, 80))])

    # Each draw() is a fresh map: the second list starts again at ١.
    numerals = [kwargs["text"] for _, kwargs in canvas.texts]
    assert numerals == ["١", "١"]


def test_a_labeled_step_gets_a_caption_chip_and_arabic_indic_handles_two_digits():
    canvas = FakeCanvas()
    ShapesWidget(canvas).draw([
        Shape(kind="step", points=(10, 10, 40, 40), label_ar="افتح القائمة"),
    ])
    chip_texts = [kwargs.get("text") for _, kwargs in canvas.texts]
    assert "افتح القائمة" in chip_texts
    assert arabic_indic(12) == "١٢"
