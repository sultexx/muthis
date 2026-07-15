# src/muthis/cloud/tool_schemas.py
"""
LOOK-only tool schemas (v4.1 §9.5, reduced to the LOOK subset).

Moved out of claude_agent.py — that file sits at the ≤300-line ceiling
(AGENTS.md §17.4: split, don't compress), so adding draw_shapes lives here.
claude_agent.py re-imports LOOK_ONLY_TOOLS, so every existing import path
(`from muthis.cloud.claude_agent import LOOK_ONLY_TOOLS`) keeps working.

LOOK-ONLY BUILD: highlight_target and draw_shapes only DRAW overlay graphics —
they never move the mouse, never click, never type. type_text / press_hotkey /
real_click DO NOT EXIST here — they arrive with Trust Modes in a later phase,
behind trust/confirm_gate.py. Do not add them here.

draw_shapes geometry mirrors shapes.Shape exactly: ONE uniform (x1, y1, x2, y2)
per kind — line/arrow endpoints (arrow head at x2,y2), rectangle corners, and
for a circle its ENCLOSING bounding box — so parsing stays a single code path
(shapes.parse_shapes_args) and one scale function covers every kind.
"""

from __future__ import annotations

from typing import Any

LOOK_ONLY_TOOLS: list[dict[str, Any]] = [
    {
        "name": "highlight_target",
        "description": (
            "Draw a cyan rectangle highlight around ONE UI element on the "
            "user's screen. This does NOT move or click the user's mouse and "
            "does NOT type anything — it only points. Coordinates are pixels "
            "in the provided screenshot, origin top-left."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "x1": {"type": "integer", "description": "Left edge"},
                "y1": {"type": "integer", "description": "Top edge"},
                "x2": {"type": "integer", "description": "Right edge"},
                "y2": {"type": "integer", "description": "Bottom edge"},
                "label_ar": {
                    "type": "string",
                    "description": "Short Arabic caption shown near the rectangle",
                },
            },
            "required": ["x1", "y1", "x2", "y2", "label_ar"],
        },
    },
    {
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
    },
    {
        "name": "request_screen_refresh",
        "description": (
            "Ask for a fresh screenshot when the current view is stale or "
            "missing. The orchestrator will answer with a tool_result that "
            "contains the new image."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]

__all__ = ["LOOK_ONLY_TOOLS"]
