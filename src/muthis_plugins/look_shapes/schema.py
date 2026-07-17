# src/muthis_plugins/look_shapes/schema.py
"""The draw_shapes tool schema — moved VERBATIM from cloud/tool_schemas.py
(V2 Phase 0 M4). The model-visible bytes are pinned by the frozen snapshot
tests/snapshots/look_tools_v1.json; any edit here fails that test on purpose."""

from __future__ import annotations

from typing import Any

DRAW_SHAPES_SCHEMA: dict[str, Any] = {
    "name": "draw_shapes",
    "description": (
        "Draw one or MORE geometric overlay graphics (line / arrow / "
        "circle / rectangle / step) on the user's screen to illustrate "
        "or annotate what you are explaining. This does NOT move or "
        "click the user's mouse and does NOT type anything — it only "
        "draws. ONE call may carry SEVERAL shapes together (e.g. a line "
        "+ a circle + an arrow) and that is the expected way to draw a "
        "composite illustration. Coordinates are pixels in the provided "
        "screenshot, origin top-left. Every kind uses the same four "
        "values: line/arrow endpoints (the arrow HEAD is at x2,y2), "
        "rectangle corners, and for a circle the ENCLOSING bounding box "
        "of the circle. A 'step' is a small NUMBERED badge circle (its "
        "ENCLOSING bounding box, ~30-50px in screenshot pixels) placed "
        "ON a UI element to mark one step of a sequential how-to; steps "
        "are numbered AUTOMATICALLY 1, 2, 3... by their order in the "
        "shapes list, so send them in execution order. Set "
        "dim_screen=true for WHITEBOARD mode: the whole screen fades "
        "dark like a classroom blackboard behind your drawing while you "
        "explain — use it when illustrating a CONCEPT or abstract idea; "
        "leave it false/absent when annotating the user's own content "
        "(code, UI, documents) that they must keep seeing in full."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "dim_screen": {
                "type": "boolean",
                "description": (
                    "Whiteboard mode: dim the whole screen behind the "
                    "shapes for a concept explanation (default false)."
                ),
            },
            "shapes": {
                "type": "array",
                "minItems": 1,
                "description": "All shapes to draw, together in ONE call.",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["line", "arrow", "circle",
                                     "rectangle", "step"],
                        },
                        "x1": {"type": "integer"},
                        "y1": {"type": "integer"},
                        "x2": {"type": "integer"},
                        "y2": {"type": "integer"},
                        "label_ar": {
                            "type": "string",
                            "description": (
                                "Optional short Arabic caption shown near "
                                "the shape"
                            ),
                        },
                    },
                    "required": ["kind", "x1", "y1", "x2", "y2"],
                },
            },
        },
        "required": ["shapes"],
    },
}

__all__ = ["DRAW_SHAPES_SCHEMA"]
