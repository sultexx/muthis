# src/muthis/cloud/luna_accounting.py
"""
luna_accounting.py — the END OF A TURN, for the second provider.

ONE CONCERN: turning this vendor's LAST stream event into a `TurnComplete`. It
holds no client, no key and no stream loop, and it is importable without either
SDK.

**THIS FILE EXISTS BECAUSE THREE OF THE FOUR MEASURED PROVIDER DIFFERENCES LAND
IN ONE PLACE.** It was extracted from `luna_agent.py` at 301/300 — the ≤300-line
law, split and never compress — and the extraction is the seam the measurements
had already drawn rather than a line count looking for a victim:

  ② `usage` ARRIVES ONLY AT THE LAST EVENT (DEC-88 ②). `claude_agent.py` reads
     it at `message_start`, the FIRST. So every token figure in this module comes
     from an object that does not exist until the stream ends, and a stream
     cancelled mid-flight — barge-in is exactly that — yields none of it.

  ③ THERE IS NO `stop_reason` FIELD, so the agentic loop's hard terminator is
     DERIVED here (`derive_stop_reason`).

  ④ THE COST MODEL IS INCLUSIVE, the exact inverse of DEC-60
     (`estimate_inclusive_cost_usd`, never `estimate_cost_usd`).

Everything is read with `getattr(..., None)` and coerced, deliberately: this is
the one point where a provider's response object meets a frozen dataclass the
ledger consumes, and a missing field must degrade to a recorded zero rather than
raise across the seam (Law 11 — no exception crosses a wrapper boundary).
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from .luna_messages import assistant_blocks
from .pricing import estimate_inclusive_cost_usd
from .protocol import ToolCall, TurnComplete

logger = logging.getLogger("muthis.cloud.luna")

# The last event of a stream, and the ONLY place `usage` appears (difference ②).
TERMINAL_EVENT_TYPES = ("response.completed", "response.incomplete", "response.failed")


def derive_stop_reason(status: str | None, saw_tool_call: bool) -> str | None:
    """The agentic loop's HARD terminator, RECONSTRUCTED — this provider has no
    `stop_reason` field at all (DEC-88 ②), so the scalar the orchestrator keys
    off is computed here.

    **THE TOOL-CALL TEST COMES FIRST, AND THE ORDER IS THE WHOLE FUNCTION.** A
    turn that calls a tool still reports `status == "completed"`, because the
    response DID complete — so testing status first would return `end_turn`, the
    orchestrator would stop at `stop_reason != "tool_use"`, and the explanation
    that is supposed to land AFTER the pointer would never be requested. The
    pointer would draw and Mut'his would fall silent. That is the LOOK-only
    product failing at its one job, from a two-line function nobody reads twice.

    `None` on an unknown or failed status is the honest answer and is already
    handled: the orchestrator logs `stop_reason=None` and ends the loop cleanly
    rather than looping on a turn it cannot classify.
    """
    if saw_tool_call:
        return "tool_use"
    if status == "completed":
        return "end_turn"
    if status == "incomplete":
        return "max_tokens"
    return None


def build_turn_complete(
    final: Any, text: str, tool_calls: Sequence[ToolCall], model: str
) -> TurnComplete:
    """The stream's terminal response → the one `TurnComplete` a turn may yield.

    `final` is None when the stream ended without a terminal event; every figure
    then degrades to zero and `stop_reason` to None, which the orchestrator
    already treats as "end the loop cleanly". A turn is never charged for tokens
    nobody reported.
    """
    usage = getattr(final, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    details = getattr(usage, "input_tokens_details", None)
    # MEASURED INCLUSIVE (DEC-88 ③): `cached_tokens` is a BREAKDOWN of
    # `input_tokens`, never an addition to it. `cache_write_tokens` is carried
    # for OBSERVABILITY only and is deliberately UNPRICED — the rate card
    # fetched at DEC-90 lists input, cached input and output, and no write
    # premium. If one ever appears, this is the line that needs a third rate.
    cache_read = getattr(details, "cached_tokens", None)
    cache_write = getattr(details, "cache_write_tokens", None)
    status = getattr(final, "status", None)
    if status == "incomplete":
        logger.warning("[luna] response incomplete: %s",
                       getattr(final, "incomplete_details", None))
    return TurnComplete(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_inclusive_cost_usd(
            model, input_tokens, output_tokens, cached_tokens=cache_read or 0),
        stop_reason=derive_stop_reason(status, bool(tool_calls)),
        model=model,
        assistant_content=assistant_blocks(text, tool_calls),
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_write,
    )


__all__ = ["TERMINAL_EVENT_TYPES", "derive_stop_reason", "build_turn_complete"]
