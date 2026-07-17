# src/muthis_plugins/screen_refresh/schema.py
"""The request_screen_refresh tool schema — moved VERBATIM from
cloud/tool_schemas.py (V2 Phase 0 M4). Pinned by the frozen snapshot
tests/snapshots/look_tools_v1.json."""

from __future__ import annotations

from typing import Any

SCREEN_REFRESH_SCHEMA: dict[str, Any] = {
    "name": "request_screen_refresh",
    "description": (
        "Ask for a fresh screenshot when the current view is stale or "
        "missing. The orchestrator will answer with a tool_result that "
        "contains the new image."
    ),
    "input_schema": {"type": "object", "properties": {}},
}

__all__ = ["SCREEN_REFRESH_SCHEMA"]
