# src/muthis_plugins/sandbox_exec/schema.py
"""The sandbox `run_code` tool contract + data-model bounds (Roadmap §2.1).

The bare tool name is `run_code`; the ToolRouter namespaces it to
`sandbox.run_code` at mount time (T5, `mount(namespace="sandbox")`) — the
plugin stays free of the dotted name the manifest name regex forbids anyway.

The bounds below are the SINGLE SOURCE for both the model-facing schema text
and the T2 runner that enforces them (default/hard-cap timeout, total file
size). Declaring them here keeps the description and the enforcement in sync."""

from __future__ import annotations

from typing import Any

# Data-model bounds (Roadmap §2.1). Enforced runner-side in T2; declared here once.
LANGUAGES: tuple[str, ...] = ("python", "node", "bash", "sqlite")
DEFAULT_TIMEOUT_S = 20
MAX_TIMEOUT_S = 60
MAX_TOTAL_FILE_BYTES = 1_000_000  # 1 MB across all files[] (Roadmap §2.1 / §2.4)

RUN_CODE_SCHEMA: dict[str, Any] = {
    "name": "run_code",
    "description": (
        "Run a short snippet of code in an ISOLATED, throwaway sandbox and get "
        "the REAL output back, so you can hand the user code you have actually "
        "executed instead of guessing. The sandbox has NO network by default, "
        "NO access to the user's files, system, mouse, keyboard, or clipboard, "
        "runs as an unprivileged user, and is destroyed after the run. Use it "
        "to verify code before you present it, to reproduce an error the user "
        "hit, or to compute a concrete result. Give the language and the code; "
        "you may optionally stage input files and pipe stdin. Staged files are "
        "READ-ONLY; /work is the only writable directory (write any output "
        "there, and to modify an input copy it into /work first). The "
        "tool_result returns the exit code with stdout/stderr, so you can read "
        "the output and, if it failed, fix and re-run (a few attempts per turn)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": list(LANGUAGES),
                "description": "The runtime for `code`: python, node, bash, or sqlite.",
            },
            "code": {
                "type": "string",
                "description": "The source to run. Keep it self-contained.",
            },
            "files": {
                "type": "array",
                "description": (
                    "Optional input files staged READ-ONLY for the code to read. "
                    "Total size across all files must stay under 1 MB."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "File name (no directory)."},
                        "content": {"type": "string", "description": "The file's text content."},
                    },
                    "required": ["name", "content"],
                },
            },
            "stdin": {
                "type": "string",
                "description": "Optional standard input piped to the program.",
            },
            "timeout_s": {
                "type": "integer",
                "description": (
                    "Optional wall-clock timeout in seconds (default 20, hard cap 60). "
                    "The run is killed if it exceeds this."
                ),
            },
        },
        "required": ["language", "code"],
    },
}

__all__ = [
    "RUN_CODE_SCHEMA",
    "LANGUAGES",
    "DEFAULT_TIMEOUT_S",
    "MAX_TIMEOUT_S",
    "MAX_TOTAL_FILE_BYTES",
]
