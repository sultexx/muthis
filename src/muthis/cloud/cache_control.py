"""
cache_control.py — request-time cache breakpoints, applied to COPIES.

ONE CONCERN: shaping a request so the static prefix is cacheable WITHOUT ever
touching an artifact that is pinned. Both halves of that concern live here
together on purpose (ruled 2026-07-31, Option A): the byte-pin rationale in
`cacheable_tools` is a SAFETY argument, and splitting it across two modules
would leave each reader holding half of it — a safety rationale with half
missing is one that gets overruled in good faith. Rationale lives where it is
read, the same instinct that keeps the SearXNG private-destination edge inside
`searxng.py` where an editor actually collides with it.

WHY CACHING AT ALL: the persona and the tool catalog are byte-identical across
every pass of every turn, which is exactly the cacheable shape. Measured on one
pass: 10,828 input tokens of which 10,785 (99.6%) is fixed overhead — the
persona alone 61%. Every milestone has grown both.

This module owns NO cost arithmetic (that is pricing.py) and NO transport.
"""

from __future__ import annotations

from typing import Any

# The one breakpoint kind this project uses. Named so the two call sites below
# can never drift apart, and never mutated after definition.
CACHE_BREAKPOINT = {"type": "ephemeral"}


def cacheable_system(system_prompt: str) -> list[dict[str, Any]]:
    """The system prompt as a BLOCK list carrying the cache breakpoint.

    Only the block form accepts `cache_control` — the SDK types `system` as
    `str | Iterable[TextBlockParam]` — so a plain string cannot be cached at
    all, no matter what else the request does. The prompt TEXT is unchanged
    here; it is only re-shaped, so the persona remains the persona.
    """
    return [{
        "type": "text",
        "text": system_prompt,
        "cache_control": CACHE_BREAKPOINT,
    }]


def cacheable_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The catalog with a breakpoint on the LAST tool, applied to a COPY.

    THE MOUNTED DESCRIPTORS ARE BYTE-PINNED to `tests/snapshots/look_tools_v4.json`,
    and `router.descriptors()` hands back the SAME dict objects on every call
    (asserted by identity — DEC-59 Q3). Writing `cache_control` into a mounted
    schema would therefore mutate the model-visible catalog IN PLACE, for the
    whole process, and fail that snapshot guard — correctly, because it IS a
    model-visible change.

    So only the LAST dict is shallow-copied and the breakpoint is written into
    the copy. The earlier dicts are shared by reference, which is safe precisely
    because nothing mutates them.

    THIS COPY DISCIPLINE IS THE ENTIRE SAFETY OF THE STEP. A future contributor
    who "simplifies" this to `tools[-1]["cache_control"] = CACHE_BREAKPOINT`
    silently edits the pinned catalog and changes what the model sees — the one
    class of change this project pins snapshots to prevent.

    It is the same discipline already applied to `_outcome_for`'s
    `dataclasses.replace` and to `tts.py`'s diacritized COPY: the shared, pinned
    artifact is never edited in place; the per-use variant is built beside it.
    """
    if not tools:
        return tools
    return [*tools[:-1], {**tools[-1], "cache_control": CACHE_BREAKPOINT}]
