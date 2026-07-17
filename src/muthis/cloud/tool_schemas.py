# src/muthis/cloud/tool_schemas.py
"""
LOOK-only tool schemas — the ASSEMBLY point (V2 Phase 0 M4).

The four schema dicts moved VERBATIM into their core plugin packages
(src/muthis_plugins/*/schema.py — the dogfood re-founding, roadmap §3.1);
this module re-assembles LOOK_ONLY_TOOLS in the EXACT V1 order so
claude_agent.py and every existing importer keep working unchanged. The
model-visible bytes are pinned by tests/snapshots/look_tools_v1.json
(byte-equality test in tests/test_core_plugins.py): editing a schema in a
plugin package intentionally fails that snapshot.

LOOK-ONLY BUILD: highlight_target and draw_shapes only DRAW overlay graphics —
they never move the mouse, never click, never type. type_text / press_hotkey /
real_click DO NOT EXIST here — they arrive with Trust Modes in a later phase,
behind trust/confirm_gate.py. Do not add them here (and the muthis-sdk
capability enum has no member they could ever request — golden rule §1.1).

draw_shapes geometry mirrors shapes.Shape exactly: ONE uniform (x1, y1, x2, y2)
per kind — line/arrow endpoints (arrow head at x2,y2), rectangle corners, and
for a circle its ENCLOSING bounding box — so parsing stays a single code path
(shapes.parse_shapes_args) and one scale function covers every kind.
"""

from __future__ import annotations

from typing import Any

from muthis_plugins.file_read.schema import READ_LOCAL_FILE_SCHEMA
from muthis_plugins.look_pointer.schema import HIGHLIGHT_TARGET_SCHEMA
from muthis_plugins.look_shapes.schema import DRAW_SHAPES_SCHEMA
from muthis_plugins.screen_refresh.schema import SCREEN_REFRESH_SCHEMA

# The V1 order is load-bearing (the model-visible catalog): pointer, shapes,
# refresh, read — exactly as v1.0.0 shipped it.
LOOK_ONLY_TOOLS: list[dict[str, Any]] = [
    HIGHLIGHT_TARGET_SCHEMA,
    DRAW_SHAPES_SCHEMA,
    SCREEN_REFRESH_SCHEMA,
    READ_LOCAL_FILE_SCHEMA,
]

__all__ = ["LOOK_ONLY_TOOLS"]
