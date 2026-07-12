# src/muthis/shapes.py
"""
Shapes — the geometric-drawing data model + sent→physical scaling (Phase A).

DRAW-ONLY, pure LOOK: a Shape is an overlay GRAPHIC — line / arrow / circle /
rectangle in cyan with an optional short Arabic label. Never the mouse, never a
click, never typing. Phase A is the visual foundation ONLY: this module is
exercised by the overlay and scripts/smoke_shapes.py; the Claude wiring (tool
schema + persona + agentic loop) is Phase B and does NOT exist yet.

HONEST LIMITATION (design for it, never promise around it): Claude localizes
REGIONS (a button, an icon, a field) reasonably well, but pixel-precise free
drawing on fine detail (a line exactly on a triangle's hypotenuse, a circle
exactly around one term in an equation) sits at the edge of model coordinate
accuracy — shapes may land slightly off on small targets. This model therefore
serves graceful region-level approximation, tolerant of small error; a
slightly-off shape is a model limit, not a rendering bug.

Coordinates: a Shape is authored in SENT-image space (the downscaled COPY the
model reasons in — vision/downscale.py) and mapped to PHYSICAL pixels by
scale_shape_to_physical, mirroring turn.scale_bbox_to_physical exactly: x
scales by scale_x, y by scale_y (PER-AXIS — the factors can differ by a hair),
each rounded. That function is the ONLY multiply site for shapes; the overlay
receives already-physical shapes and never rescales.

Separate from turn.py (at its 300-line ceiling) and from highlight_target,
which stays 100% untouched. stdlib only; importable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Literal, Protocol, Sequence, runtime_checkable

ShapeKind = Literal["line", "arrow", "circle", "rectangle"]

# The four drawable kinds in one place, so the widget and tests never retype them.
SHAPE_KINDS: tuple[ShapeKind, ...] = ("line", "arrow", "circle", "rectangle")


@dataclass(frozen=True)
class Shape:
    """ONE drawable overlay shape with a uniform 4-value geometry.

    `points` semantics per kind:
      * line / arrow: (x1, y1, x2, y2) endpoints — an arrow's HEAD is at (x2, y2).
      * rectangle:    (x1, y1, x2, y2) corners.
      * circle:       (x1, y1, x2, y2) — its ENCLOSING bbox (built from
        center+radius by circle_shape). One uniform 4-tuple keeps ONE scale
        function for every kind, and Tk draws circles from a bbox anyway
        (create_oval).

    Coordinates live in SENT-image space until scale_shape_to_physical maps
    them; the overlay is handed the physical result. `label_ar` is an optional
    short Arabic caption ("" = none).
    """
    kind: ShapeKind
    points: tuple[float, float, float, float]
    label_ar: str = ""


def circle_shape(
    center_x: float, center_y: float, radius: float, label_ar: str = "",
) -> Shape:
    """Build a circle Shape from center + radius, normalized AT CONSTRUCTION to
    the enclosing bbox (cx-r, cy-r, cx+r, cy+r) so circles share the uniform
    4-value geometry and the same per-axis scaling as every other kind. When
    scale_x and scale_y differ by a hair (sent_height rounds — see
    DownscaledImage) the circle becomes an imperceptibly flattened oval;
    accepted, and exactly how Tk renders circles anyway."""
    return Shape(
        kind="circle",
        points=(
            center_x - radius, center_y - radius,
            center_x + radius, center_y + radius,
        ),
        label_ar=label_ar,
    )


def scale_shape_to_physical(shape: Shape, scale_x: float, scale_y: float) -> Shape:
    """Map ONE shape's SENT-image points to PHYSICAL pixels — the exact mirror
    of turn.scale_bbox_to_physical: x1/x2 multiply by scale_x, y1/y2 by scale_y
    (PER-AXIS, never one factor for both), each rounded. This is the ONLY place
    the multiply happens; the overlay receives the result physical and never
    rescales. kind and label_ar pass through untouched."""
    x1, y1, x2, y2 = shape.points
    return replace(shape, points=(
        round(x1 * scale_x), round(y1 * scale_y),
        round(x2 * scale_x), round(y2 * scale_y),
    ))


def scale_shapes_to_physical(
    shapes: Iterable[Shape], scale_x: float, scale_y: float,
) -> tuple[Shape, ...]:
    """Map a whole shape list sent→physical in one call (order preserved) —
    the single entry point a Phase B caller will use before handing the list
    to the overlay."""
    return tuple(
        scale_shape_to_physical(shape, scale_x, scale_y) for shape in shapes
    )


def parse_shapes_args(args: dict[str, Any]) -> tuple[Shape, ...]:
    """Parse a draw_shapes tool call's args ({"shapes": [...]}) into SENT-space
    Shapes, DEFENSIVELY: a non-list payload, a non-dict entry, an unknown kind,
    or a missing/non-numeric coordinate drops THAT entry — never raises, because
    one malformed model item must not kill the turn (the call is still paired
    and gated upstream). Returns () when nothing valid survives, which the
    dispatcher treats as no-draw. label_ar defaults to ""."""
    raw = args.get("shapes")
    if not isinstance(raw, (list, tuple)):
        return ()
    parsed: list[Shape] = []
    for entry in raw:
        if not isinstance(entry, dict) or entry.get("kind") not in SHAPE_KINDS:
            continue
        try:
            points = (float(entry["x1"]), float(entry["y1"]),
                      float(entry["x2"]), float(entry["y2"]))
        except (KeyError, TypeError, ValueError):
            continue
        parsed.append(Shape(kind=entry["kind"], points=points,
                            label_ar=str(entry.get("label_ar") or "")))
    return tuple(parsed)


@runtime_checkable
class ShapesOverlay(Protocol):
    """The draw_shapes seam (SidekickOverlay in production; fakes in tests).

    Kept SEPARATE from turn.Overlay — extending that runtime_checkable protocol
    would fail isinstance checks for every existing overlay fake. Phase B types
    the orchestrator against THIS protocol. Implementations receive
    ALREADY-PHYSICAL shapes, draw only (LOOK), and never raise."""

    async def draw_shapes(self, shapes: Sequence[Shape]) -> None:
        ...


__all__ = [
    "ShapeKind", "SHAPE_KINDS", "Shape", "circle_shape", "parse_shapes_args",
    "scale_shape_to_physical", "scale_shapes_to_physical", "ShapesOverlay",
]
