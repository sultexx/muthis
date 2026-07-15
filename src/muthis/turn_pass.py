# src/muthis/turn_pass.py
"""
TurnPass — drains ONE provider pass (extracted under the ≤300-line law).

orchestrator.py sat at 288 lines and Phase C (v5) needed room for the
buffer/stream branching, so the whole `_consume_stream` body moved here
UNCHANGED (Law §17.4: split, don't compress — the same reason voice_out.py
and highlight_gate.py exist): stream the reasoner's events, buffer the text,
gate the draws (first draw wins, unified over BOTH draw tools), then the
**Option-A SYNC POINT** — apply the ONE buffered draw → THEN speak — which
this module OWNS. (v7.1 Fix F: the auto-hide is NO LONGER armed here — a
draw-time timer was measured hiding the rectangle mid-explanation, draw+7 s
landing before speech end; run_turn's `finally` is now the ONLY arm site,
counting the 7 s from SPEECH END.) The orchestrator's agentic loop calls
`consume()` once per pass and keeps owning history, pairing, budget gating and
the loop itself (Law 11 untouched — TurnPass holds no lifecycle, no locks, no
loop; it is one pass, built once from the orchestrator's own injected seams).

**v7 continuous voice**: the per-pass `_PassStreamer` was replaced by the
turn-level `turn_voice.TurnVoice` (ONE speech generation for the WHOLE turn —
see that module for the measured 3.48s stop-and-go it removes). TurnPass stays
stateless: the orchestrator builds a fresh TurnVoice per turn through
`new_turn_voice()` (which owns the flag + the lazy real session factory) and
passes it into `consume()` like the HighlightGate. Decision 13 is unchanged:
mid-pass sentence streaming happens ONLY on `tool_choice="none"` passes (the
API forbids tools there, so no draw can arrive mid-stream); an "auto" pass's
text stays fully buffered and reaches the voice AT the sync point — now as an
instant `speak_or_feed()` so the ack no longer blocks the loop.

`REFRESH_TOOL` moved with the code; orchestrator re-exports it.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Optional

from .cloud.protocol import TextDelta, ToolCall, TurnComplete, UserInput
from .draw_dispatch import DRAW_TOOLS, PendingDraw, next_draw
from .highlight_gate import HighlightGate, loop_tool_choice
from .turn import TurnResult
from .turn_voice import TurnVoice

# Kept on the orchestrator's logger: the log surface is unchanged by the split.
logger = logging.getLogger("muthis.orchestrator")

# DIAG(v7): temporary timing probes for the stop-and-go / mid-sentence-pause
# investigation. Every [DIAG] line is removed once the audio work lands.
_diag = logging.getLogger("muthis.diag")

REFRESH_TOOL = "request_screen_refresh"

# C2 rollback flag: sentence streaming is OFF unless .env opts in.
STREAM_TTS_ENV = "MUTHIS_STREAM_TTS"


def _stream_tts_from_env() -> bool:
    raw = os.getenv(STREAM_TTS_ENV)
    return raw is not None and raw.strip().lower() in ("1", "true", "yes", "on")


class TurnPass:
    """ONE provider pass: run the reasoner, buffer text, gate draws, then the
    draw→speak sync point. Built once by the Orchestrator from its own
    injected seams; stateless between calls."""

    def __init__(
        self, *, reasoner, budget, overlay, voice,
        stream_tts: Optional[bool] = None,
        session_factory: Optional[Callable[[], object]] = None,
    ) -> None:
        self._reasoner = reasoner
        self._budget = budget
        self._overlay = overlay
        self._voice = voice
        # v7: sentence streaming — flag-gated (default OFF). The factory seam
        # resolves lazily to the real TTS().open_speech_session on first
        # flag-ON use, so the buffered default path never imports the TTS layer.
        self._stream_tts = _stream_tts_from_env() if stream_tts is None else stream_tts
        self._session_factory = session_factory

    def new_turn_voice(self) -> TurnVoice:
        """A fresh per-turn voice (built by run_turn like the HighlightGate):
        ONE speech generation the whole turn feeds into. Flag OFF / no key →
        the TurnVoice simply routes everything through buffered speak()."""
        if self._stream_tts and self._session_factory is None:
            from .tts import TTS  # lazy real default: only the flag-ON path pays
            self._session_factory = TTS().open_speech_session
        return TurnVoice(voice=self._voice, overlay=self._overlay,
                         session_factory=self._session_factory,
                         enabled=self._stream_tts)

    async def consume(
        self,
        user_input: UserInput,
        screenshot: Optional[bytes],
        history: list[dict[str, Any]],
        gate: HighlightGate,
        result: TurnResult,
        turn_voice: TurnVoice,
    ) -> tuple[Optional[TurnComplete], Optional[ToolCall]]:
        """Drain one provider turn into result. Returns (turn_complete,
        refresh_call); refresh_call is set iff the model asked for a new
        screenshot and the pipeline must answer it."""
        turn_complete: Optional[TurnComplete] = None
        refresh_call: Optional[ToolCall] = None
        message_text = ""  # buffered mirror of the pass — the fallback source
        pending_draw: Optional[PendingDraw] = None  # first draw wins; applied at speak
        tool_choice = loop_tool_choice(gate)
        # Decision 13: stream mid-pass ONLY on a tool_choice="none" pass — the
        # API forbids tools there, so no draw can arrive mid-stream and the
        # Option-A draw-at-speak invariant is untouchable. Every "auto" pass
        # (draw pass, single-pass replies, refresh follow-ups) stays buffered
        # and reaches the ONE turn generation at the sync point below.
        streamed = tool_choice == "none" and await turn_voice.ensure_open()
        _diag.info("[DIAG] pass start t=%.3f tool_choice=%s streamed=%s",
                   time.monotonic(), tool_choice, streamed)
        first_delta_at: Optional[float] = None

        async for event in self._reasoner.run(user_input, screenshot, history, tool_choice=tool_choice):
            if isinstance(event, TextDelta):
                if first_delta_at is None:
                    first_delta_at = time.monotonic()
                    _diag.info("[DIAG] pass first-delta t=%.3f", first_delta_at)
                result.spoken_text += event.text
                message_text += event.text
                if streamed:
                    await turn_voice.push_stream(event.text)  # inline-await: no background consumer
            elif isinstance(event, ToolCall):
                _diag.info("[DIAG] pass tool-call t=%.3f name=%s", time.monotonic(), event.name)
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
            # Abnormal pass end: the pipeline abandons the turn voice — this
            # branch never spoke on the buffered path either.
            logger.error("[orchestrator] provider stream ended without TurnComplete")
            return None, None

        result.input_tokens += turn_complete.input_tokens
        result.output_tokens += turn_complete.output_tokens
        result.cost_usd = round(result.cost_usd + turn_complete.cost_usd, 6)
        result.stop_reason = turn_complete.stop_reason
        # Cost recorded BEFORE speaking — the timeout must never cost us accounting.
        self._budget.record_turn(turn_complete)
        _diag.info("[DIAG] pass stream-end t=%.3f stop_reason=%s chars=%d",
                   time.monotonic(), turn_complete.stop_reason, len(message_text))
        # Sync point: apply the ONE buffered draw, THEN speak. The auto-hide is
        # NOT armed here (v7.1 Fix F) — run_turn's finally arms it at SPEECH END,
        # so the rectangle survives the whole spoken explanation.
        # (A streamed pass is tool_choice="none": pending_draw is impossible.)
        if pending_draw is not None:
            await pending_draw.apply(self._overlay)
            _diag.info("[DIAG] pass draw-applied t=%.3f", time.monotonic())
        if streamed:
            await turn_voice.end_stream()        # flush the tail into the generation
        else:
            # v7: an instant feed when the turn session is live — the ack no
            # longer blocks the loop, so the next pass's round-trip hides
            # BEHIND its playback (the measured 3.48s gap).
            await turn_voice.speak_or_feed(message_text)
        _diag.info("[DIAG] pass end t=%.3f", time.monotonic())
        return turn_complete, refresh_call


__all__ = ["TurnPass", "REFRESH_TOOL", "STREAM_TTS_ENV"]
