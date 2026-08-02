# src/muthis_plugins/navigator/schema.py
"""The two Navigator tool schemas (DEC-65/DEC-66, T4). Byte-pinned by
tests/snapshots/look_tools_v6.json once mounted.

THE MODEL CARRIES NO MACHINE IDENTIFIER — DEC-71's ruling, applied PREVENTIVELY
here rather than after a live failure. `jump` takes the STEP NUMBER the user and
the model both already say aloud ("go back to step two"), and the KERNEL maps
that number to the step's stable id. A step id is a fact the kernel owns; routing
it through the model would make the model the carrier of a truth that is not its
own, which is the pattern this project has now rejected nine times."""

from __future__ import annotations

from typing import Any

NAVIGATOR_PLAN_SCHEMA: dict[str, Any] = {
    "name": "plan",
    "description": (
        "Start guiding the user through a multi-step task. Give the task a short "
        "title and the ordered steps, each one short and in the user's language. "
        "I keep the numbering; you never state a step number I did not give you. "
        "Call this once at the start of a walkthrough, not on every turn."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "A short title for the whole task.",
            },
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "The ordered steps, each one action the user performs."
                ),
            },
        },
        "required": ["title", "steps"],
    },
}

NAVIGATOR_STEP_SCHEMA: dict[str, Any] = {
    "name": "step",
    "description": (
        "Move within the walkthrough you already started: advance to the next "
        "step once the user has done the current one, go back one step, jump to "
        "a numbered step the user named, or finish. I decide whether the move is "
        "allowed and tell you what happened. Never assume it succeeded."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["advance", "back", "jump", "done"],
                "description": "What to do with the current position.",
            },
            "step_number": {
                "type": "integer",
                "description": (
                    "For action=jump only: the 1-based step number the user "
                    "named. Ignored for every other action."
                ),
            },
        },
        "required": ["action"],
    },
}

__all__ = ["NAVIGATOR_PLAN_SCHEMA", "NAVIGATOR_STEP_SCHEMA"]
