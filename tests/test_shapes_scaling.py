"""
test_shapes_scaling.py — the shapes data model + sent→physical scaling
(muthis.shapes), pure and deterministic (no Tk, no screen, no network).

Proves every shape kind's points map sent→physical PER-AXIS (x by scale_x, y by
scale_y, rounded) exactly like turn.scale_bbox_to_physical — the highlight rule
the shapes path mirrors — and that circle_shape normalizes center+radius to the
enclosing bbox at construction.

Run:  set PYTHONPATH=src && python -m pytest tests/test_shapes_scaling.py -q
"""

from __future__ import annotations

from muthis.shapes import (
    SHAPE_KINDS,
    Shape,
    circle_shape,
    scale_shape_to_physical,
    scale_shapes_to_physical,
)
from muthis.turn import scale_bbox_to_physical


# ───────────────────────────── The model ─────────────────────────────


def test_the_four_shape_kinds_are_exactly_line_arrow_circle_rectangle():
    assert SHAPE_KINDS == ("line", "arrow", "circle", "rectangle")


def test_circle_shape_normalizes_center_radius_to_the_enclosing_bbox():
    circle = circle_shape(100, 80, 40, label_ar="دائرة")
    assert circle.kind == "circle"
    assert circle.points == (60, 40, 140, 120)
    assert circle.label_ar == "دائرة"


def test_label_defaults_to_empty():
    assert Shape(kind="line", points=(0, 0, 1, 1)).label_ar == ""


# ─────────────────────── Per-kind sent→physical ───────────────────────


def test_line_scales_per_point_at_1_5():
    line = Shape(kind="line", points=(100, 100, 200, 200), label_ar="خط")
    scaled = scale_shape_to_physical(line, 1.5, 1.5)
    assert scaled.points == (150, 150, 300, 300)
    assert scaled.kind == "line"
    assert scaled.label_ar == "خط"          # label rides through untouched


def test_arrow_scales_each_axis_independently():
    # scale_x != scale_y — x multiplies by 1.5 ONLY, y by 2.0 ONLY.
    arrow = Shape(kind="arrow", points=(10, 20, 110, 220))
    assert scale_shape_to_physical(arrow, 1.5, 2.0).points == (15, 40, 165, 440)


def test_circle_bbox_scales_per_axis_like_every_other_kind():
    circle = circle_shape(100, 80, 40)      # bbox (60, 40, 140, 120)
    assert scale_shape_to_physical(circle, 1.5, 1.5).points == (90, 60, 210, 180)


def test_rectangle_scaling_rounds_each_coordinate():
    # 1.4 gives unambiguous fractions (no .5 half-even cases): 141.4→141,
    # 46.2→46, 709.8→710, 589.4→589.
    rect = Shape(kind="rectangle", points=(101, 33, 507, 421))
    scaled = scale_shape_to_physical(rect, 1.4, 1.4)
    assert scaled.points == (141, 46, 710, 589)


def test_identity_scale_keeps_the_points():
    line = Shape(kind="line", points=(12, 34, 56, 78))
    assert scale_shape_to_physical(line, 1.0, 1.0).points == (12, 34, 56, 78)


def test_rectangle_rule_is_the_exact_mirror_of_scale_bbox_to_physical():
    # The shapes multiply must NEVER drift from the highlight's proven rule.
    args = {"x1": 101, "y1": 33, "x2": 507, "y2": 421}
    scale_x, scale_y = 1.5, 1.5039
    expected = scale_bbox_to_physical(args, scale_x, scale_y)
    shape = Shape(kind="rectangle", points=(101, 33, 507, 421))
    assert scale_shape_to_physical(shape, scale_x, scale_y).points == expected


def test_scaling_returns_a_new_shape_and_never_mutates_the_original():
    line = Shape(kind="line", points=(100, 100, 200, 200))
    scaled = scale_shape_to_physical(line, 1.5, 1.5)
    assert scaled is not line
    assert line.points == (100, 100, 200, 200)


# ───────────────────────────── The list ─────────────────────────────


def test_scale_shapes_to_physical_maps_the_whole_list_in_order():
    shapes = [
        Shape(kind="line", points=(100, 100, 200, 200)),
        circle_shape(100, 80, 40),
    ]
    scaled = scale_shapes_to_physical(shapes, 1.5, 1.5)
    assert [s.points for s in scaled] == [(150, 150, 300, 300), (90, 60, 210, 180)]
    assert [s.kind for s in scaled] == ["line", "circle"]


def test_scaling_an_empty_list_yields_an_empty_tuple():
    assert scale_shapes_to_physical([], 1.5, 1.5) == ()
