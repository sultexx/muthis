# src/muthis_plugins/file_read/schema.py
"""The read_local_file tool schema — moved VERBATIM from cloud/tool_schemas.py
(V2 Phase 0 M4). Pinned by the frozen snapshot tests/snapshots/look_tools_v1.json."""

from __future__ import annotations

from typing import Any

READ_LOCAL_FILE_SCHEMA: dict[str, Any] = {
    "name": "read_local_file",
    "description": (
        "READ the text content of ONE local file on the user's machine "
        "(code, SQL, config, data, notes) so your analysis is grounded "
        "in the REAL content instead of guessing from screenshot pixels. "
        "READ-ONLY and passive: it never writes, executes, clicks, or "
        "types anything. Use the exact path the user said or the path "
        "visible on screen (an editor tab/title bar); prefer an absolute "
        "Windows path. The tool_result returns the content with 1-based "
        "LINE NUMBERS so you can reference specific lines aloud and aim "
        "draw_shapes rectangles at them on screen. Large files are "
        "truncated — pass start_line/end_line to read a specific range. "
        "Secret-bearing files (.env, keys, credentials) are refused."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "The file's path — absolute preferred (e.g. "
                    "C:\\Users\\name\\project\\main.py)."
                ),
            },
            "start_line": {
                "type": "integer",
                "description": "Optional 1-based first line of the range.",
            },
            "end_line": {
                "type": "integer",
                "description": "Optional 1-based last line of the range.",
            },
        },
        "required": ["path"],
    },
}

__all__ = ["READ_LOCAL_FILE_SCHEMA"]
