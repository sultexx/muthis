# src/muthis_plugins/look_pointer/schema.py
"""The highlight_target tool schema — moved VERBATIM from cloud/tool_schemas.py
(V2 Phase 0 M4). The model-visible bytes are pinned by the frozen snapshot
tests/snapshots/look_tools_v1.json; any edit here fails that test on purpose."""

from __future__ import annotations

from typing import Any

HIGHLIGHT_TARGET_SCHEMA: dict[str, Any] = {
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
}

__all__ = ["HIGHLIGHT_TARGET_SCHEMA"]
