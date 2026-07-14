# src/muthis/turn_pass.py
"""
TurnPass — drains ONE provider pass (extracted under the ≤300-line law).

orchestrator.py sat at 288 lines and Phase C (v5) needs room for the
buffer/stream branching, so the whole `_consume_stream` body moved here
UNCHANGED (Law §17.4: split, don't compress — the same reason voice_out.py
and highlight_gate.py exist): stream the reasoner's events, buffer the text,
gate the draws (first draw wins, unified over BOTH draw tools), then the
**Option-A SYNC POINT** — apply the ONE buffered draw → arm auto-hide → THEN
speak. This module now OWNS that sync point; the orchestrator's agentic loop
calls `consume()` once per pass and keeps owning history, pairing, budget
gating and the loop itself (Law 11 untouched — TurnPass holds no lifecycle,
no locks, no loop; it is one pass, built once from the orchestrator's own
injected seams).

Phase C2 adds the flag-gated sentence-streaming branch HERE (tool_choice
"none" passes only — never "auto") so the orchestrator never grows for it.

`REFRESH_TOOL` moved with the code; orchestrator re-exports it.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .cloud.protocol import TextDelta, ToolCall, TurnComplete, UserInput
from .draw_dispatch import DRAW_TOOLS, PendingDraw, next_draw
from .highlight_gate import HighlightGate, loop_tool_choice
from .turn import TurnResult

# Kept on the orchestrator's logger: the log surface is unchanged by the split.
logger = logging.getLogger("muthis.orchestrator")

REFRESH_TOOL = "request_screen_refresh"


class TurnPass:
    """ONE provider pass: run the reasoner, buffer text, gate draws, then the
    draw→auto-hide→speak sync point. Built once by the Orchestrator from its
    own injected seams; stateless between calls."""

    def __init__(self, *, reasoner, budget, overlay, auto_hide, voice) -> None:
        self._reasoner = reasoner
        self._budget = budget
        self._overlay = overlay
        self._auto_hide = auto_hide
        self._voice = voice

    async def consume(
        self,
        user_input: UserInput,
        screenshot: Optional[bytes],
        history: list[dict[str, Any]],
        gate: HighlightGate,
        result: TurnResult,
    ) -> tuple[Optional[TurnComplete], Optional[ToolCall]]:
        """Drain one provider turn into result. Returns (turn_complete,
        refresh_call); refresh_call is set iff the model asked for a new
        screenshot and the pipeline must answer it."""
        turn_complete: Optional[TurnComplete] = None
        refresh_call: Optional[ToolCall] = None
        message_text = ""  # buffer-then-speak: spoken once, after the stream
        pending_draw: Optional[PendingDraw] = None  # first draw wins; applied at speak

        async for event in self._reasoner.run(user_input, screenshot, history, tool_choice=loop_tool_choice(gate)):
            if isinstance(event, TextDelta):
                result.spoken_text += event.text
                message_text += event.text
            elif isinstance(event, ToolCall):
                if event.name in DRAW_TOOLS:
                    result.tool_calls.append(event)
                    # Circuit breaker: buffer only the FIRST draw (either tool); scaled in next_draw.
                    pending_draw = next_draw(gate, pending_draw, event, result.scale_x, result.scale_y)
                elif event.name == REFRESH_TOOL:
                    result.tool_calls.append(event)
                    refresh_call = event
                else:
                    # LOOK-only hard boundary: an action tool is a contract violation.
                    logger.error(
                        "[orchestrator] LOOK-only violation: refusing tool %r",
                        event.name,
                    )
            elif isinstance(event, TurnComplete):
                turn_complete = event

        if turn_complete is None:
            logger.error("[orchestrator] provider stream ended without TurnComplete")
            return None, None

        result.input_tokens += turn_complete.input_tokens
        result.output_tokens += turn_complete.output_tokens
        result.cost_usd = round(result.cost_usd + turn_complete.cost_usd, 6)
        result.stop_reason = turn_complete.stop_reason
        # Cost recorded BEFORE speaking — the timeout must never cost us accounting.
        self._budget.record_turn(turn_complete)
        # Sync point: apply the ONE buffered draw + arm auto-hide, THEN speak.
        if pending_draw is not None:
            await pending_draw.apply(self._overlay)
            self._auto_hide.schedule()
        await self._voice.speak(message_text)
        return turn_complete, refresh_call


__all__ = ["TurnPass", "REFRESH_TOOL"]
