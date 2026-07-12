# src/muthis/orchestrator.py
"""
Orchestrator — the heart of Mut'his v4.1.

Owns everything the wrappers are forbidden to own (Law 11): the single asyncio
loop, the event queue (Law 3.3), all locks, the session lifecycle, and the
conversation history. ClaudeAgent.run() is one blind provider turn; Budget is
an accounting gate; both are only ever *asked*.

STUB-FIRST BUILD: the hotkey is the last injected stub; mic/STT/TTS/screen/
downscale/overlay are REAL via injection (tests inject fakes through the same
seams). handle_activation: mic → STT → run_turn; mic/STT failures are spoken in
Arabic and end the turn EARLY (no provider call). Playback is buffer-then-speak
per assistant message. Contracts + TurnResult live in turn.py (≤300-line split).

Turn pipeline (run_turn, ≤ 90 s) is an AGENTIC LOOP of ≤ MAX_AGENTIC_ITERATIONS
run() calls while stop_reason == "tool_use", so Muthis explains AFTER pointing.
Per pass: budget gate; buffer + speak (Option B); apply the ONE buffered draw
(highlight_target OR draw_shapes — unified gate) at speak-time; pair EVERY
tool_use with a tool_result; hide before EVERY capture; Bug-3 strip at turn-end.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from .budget import Budget
from .cloud.protocol import (
    CloudReasoner,
    TextDelta,
    ToolCall,
    TurnComplete,
    UserInput,
)
# STUB defaults — each is replaced by its real component in a later phase.
from .stubs import (stub_downscale, stub_mic, stub_overlay, stub_screen_capture,
                    stub_stt, stub_tts)
# turn.py holds the contracts, Arabic strings, TurnResult, the tool_result builder.
from .draw_dispatch import DRAW_TOOLS, PendingDraw, next_draw
from .highlight_gate import HighlightGate, loop_tool_choice
from .turn import (
    AGENTIC_CAP_NOTE_AR, BUDGET_REFUSAL_AR, MIC_FAILED_AR, REFRESH_FOLLOWUP_TEXT_AR,
    STT_EMPTY_AR, DownscaleFn, MicFn, Overlay, ScreenCaptureFn, SttFn, TtsFn,
    TurnResult, build_tool_result_message, strip_images_from_history,
)
from .overlay_autohide import AutoHideController, DEFAULT_OVERLAY_TIMEOUT_S

logger = logging.getLogger("muthis.orchestrator")


# ─── Session constants ────────────────────────────────────────────────────────

# Hard wall-clock bound for one whole turn, follow-ups included (v4.1 §9.3).
SESSION_TIMEOUT_S = 90.0

# One follow-up un-stales a view; more is a model loop burning the budget.
MAX_REFRESH_FOLLOWUPS = 1

# Hard cap on agentic run() calls per utterance — bounds a never-ending tool_use.
MAX_AGENTIC_ITERATIONS = 4

ALLOWED_OVERLAY_TOOL = "highlight_target"
REFRESH_TOOL = "request_screen_refresh"

# Hide our rectangle, then yield this long before grabbing so the Tk thread has
# cleared it — Claude never sees a ghost of the previous highlight. 50 ms is ample.
OVERLAY_SETTLE_S = 0.05


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class Orchestrator:
    """One per process. Owns loop, queue, history, and the turn pipeline."""

    def __init__(
        self,
        *,
        reasoner: CloudReasoner,
        budget: Budget,
        mic: MicFn = stub_mic,
        stt: SttFn = stub_stt,
        tts: TtsFn = stub_tts,
        screen_capture: ScreenCaptureFn = stub_screen_capture,
        downscale: DownscaleFn = stub_downscale,
        overlay: Overlay = stub_overlay,
        session_timeout_s: float = SESSION_TIMEOUT_S,
        overlay_timeout_s: float = DEFAULT_OVERLAY_TIMEOUT_S,
    ) -> None:
        self._reasoner = reasoner
        self._budget = budget
        self._mic = mic
        self._stt = stt
        self._tts = tts
        self._screen_capture = screen_capture
        self._downscale = downscale
        self._overlay = overlay
        self._session_timeout_s = session_timeout_s
        self._auto_hide = AutoHideController(self._overlay, overlay_timeout_s)

        # Conversation history (Claude message-dict format). Owned HERE and
        # nowhere else — the wrapper stores nothing between calls.
        self.history: list[dict[str, Any]] = []

        # The single event queue (Law 3.3) — placeholder until hotkey phase.
        self.event_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()

    # ─────────────────────────── Public API ───────────────────────────

    async def handle_activation(self) -> TurnResult:
        """PTT entry point: mic → STT → run_turn. Mic/STT failures are
        spoken in Arabic and end the turn EARLY — no provider call, no
        budget burn. The transcript's ONLY consumer is run_turn → Claude;
        it must never be routed to the TTS (privacy boundary).
        # STUB — the real Ctrl+Shift+Space listener arrives in the hotkey
        phase; until then callers invoke this directly."""
        audio = await self._mic()
        if not audio:
            logger.warning("[orchestrator] mic capture failed — turn aborted")
            await self._speak(MIC_FAILED_AR)
            return TurnResult()

        user_text = (await self._stt(audio)).strip()
        if not user_text:
            logger.warning("[orchestrator] empty transcript — turn aborted")
            await self._speak(STT_EMPTY_AR)
            return TurnResult()

        return await self.run_turn(user_text)

    async def run_turn(self, user_text: str) -> TurnResult:
        """Execute one full (stubbed) turn. Never raises on timeout — the
        TurnResult reports what happened. Cancellation propagates normally."""
        result = TurnResult()
        try:
            async with asyncio.timeout(self._session_timeout_s):
                await self._run_turn_pipeline(user_text, result)
        except TimeoutError:
            result.timed_out = True
            logger.warning("[orchestrator] session bound (%.0fs) hit — turn truncated", self._session_timeout_s)
        self.history = strip_images_from_history(self.history)  # Bug 3: drop stale frame
        return result

    # ───────────────────────── Turn pipeline ─────────────────────────

    async def _run_turn_pipeline(self, user_text: str, result: TurnResult) -> None:
        user_input = UserInput(text=user_text)
        screenshot = await self._capture_downscaled(result)
        refresh_used = 0
        self._highlight_gate = HighlightGate()  # circuit breaker — fresh per turn

        # Agentic loop — ONE run() call per pass; the cap stops a model that, after
        # a tool_use, never says end_turn (point → explain normally needs ≤2 passes).
        for _iteration in range(MAX_AGENTIC_ITERATIONS):
            if not self._budget.can_afford():            # Rule 10, before EVERY call
                await self._refuse_for_budget(result)
                return
            turn_complete, refresh_call = await self._consume_stream(
                user_input, screenshot, result)
            if turn_complete is None:                    # stream died, no TurnComplete
                return

            # History grows here only. Utterance stored text-only (images never
            # replayed); a continuation has empty text → only assistant + pairing.
            if user_input.text:
                self.history.append(
                    {"role": "user", "content": [{"type": "text", "text": user_input.text}]})
            self.history.append(
                {"role": "assistant", "content": list(turn_complete.assistant_content)})

            # Option B: pair EVERY tool_use with a tool_result NOW — even at end_turn
            # — or the next turn 400s on an orphan (refresh→image, else ack).
            serviced_refresh = (
                refresh_call is not None and refresh_used < MAX_REFRESH_FOLLOWUPS)
            fresh = await self._capture_downscaled(result) if serviced_refresh else None
            pairing = build_tool_result_message(
                turn_complete.assistant_content, refresh_call, fresh, self._highlight_gate)
            if pairing is not None:
                self.history.append(pairing)
            refresh_used += int(serviced_refresh)

            # Continue ONLY while paused on a tool_use (deliver the explanation
            # planned AFTER pointing); end_turn/None or a past-limit refresh ends it.
            if turn_complete.stop_reason != "tool_use":
                if turn_complete.stop_reason is None:
                    logger.warning("[orchestrator] stop_reason=None — ending loop cleanly")
                return
            if refresh_call is not None and not serviced_refresh:
                logger.warning("[orchestrator] refresh limit reached — ignoring %s", refresh_call.tool_use_id)
                return
            user_input = (UserInput(text=REFRESH_FOLLOWUP_TEXT_AR)
                          if serviced_refresh else UserInput(text=""))
            # Keep the SAME frame for the explain pass (ephemeral; Bug 3 text-only).
            screenshot = None if serviced_refresh else screenshot

        logger.warning("[orchestrator] agentic cap (%d) hit — stopping cleanly", MAX_AGENTIC_ITERATIONS)
        await self._speak(AGENTIC_CAP_NOTE_AR)

    async def _consume_stream(
        self,
        user_input: UserInput,
        screenshot: Optional[bytes],
        result: TurnResult,
    ) -> tuple[Optional[TurnComplete], Optional[ToolCall]]:
        """Drain one provider turn into result. Returns (turn_complete,
        refresh_call); refresh_call is set iff the model asked for a new
        screenshot and the pipeline must answer it."""
        turn_complete: Optional[TurnComplete] = None
        refresh_call: Optional[ToolCall] = None
        message_text = ""  # buffer-then-speak: spoken once, after the stream
        pending_draw: Optional[PendingDraw] = None  # first draw wins; applied at speak

        async for event in self._reasoner.run(user_input, screenshot, list(self.history), tool_choice=loop_tool_choice(self._highlight_gate)):
            if isinstance(event, TextDelta):
                result.spoken_text += event.text
                message_text += event.text
            elif isinstance(event, ToolCall):
                if event.name in DRAW_TOOLS:
                    result.tool_calls.append(event)
                    # Circuit breaker: buffer only the FIRST draw (either tool); scaled in next_draw.
                    pending_draw = next_draw(self._highlight_gate, pending_draw, event, result.scale_x, result.scale_y)
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
        await self._speak(message_text)
        return turn_complete, refresh_call

    # ───────────────────────── Helpers ─────────────────────────

    async def _speak(self, text: str) -> None:
        """Privacy boundary: ONLY assistant-authored Arabic may pass here —
        never the user transcript, never tool JSON. speak() never raises;
        a failed TTSResult is logged and the turn continues regardless."""
        if not text:
            return
        self._overlay.set_state("speaking")  # neon green while the voice plays
        tts_result = await self._tts(text)
        if tts_result is not None:
            log = logger.info if tts_result.success else logger.warning
            log(
                "[orchestrator] tts provider=%s success=%s (%d chars)",
                tts_result.provider, tts_result.success, len(text),
            )
        self._overlay.set_state("thinking")  # back toward thinking; idle set at turn end

    async def _refuse_for_budget(self, result: TurnResult) -> None:
        """Refuse the turn out loud — no provider call is made."""
        result.budget_blocked = True
        logger.warning(
            "[orchestrator] budget gate closed (%.6f / %.2f USD spent) — "
            "turn refused, no provider call",
            self._budget.spent_today_usd(), self._budget.daily_limit_usd,
        )
        await self._speak(BUDGET_REFUSAL_AR)

    async def _capture_downscaled(self, result: TurnResult) -> Optional[bytes]:
        """Capture physical pixels → the downscaled COPY (the ONLY thing sent),
        recording the physical↔sent scale factors so highlight coords map back.
        Ghosting: clear the status dot + hide the rectangle BEFORE every grab —
        the one chokepoint for the initial capture AND each in-loop refresh; order
        is load-bearing (clear + hide → settle → capture)."""
        self._auto_hide.cancel()  # drop any stale auto-hide before the explicit hide
        self._overlay.clear_status_light()  # ghost the corner dot — Claude never sees it
        await self._overlay.hide()
        await asyncio.sleep(OVERLAY_SETTLE_S)
        sent = await self._downscale(await self._screen_capture())
        self._overlay.set_state("thinking")  # dot reappears (thinking) after the grab
        result.sent_width, result.sent_height = sent.sent_width, sent.sent_height
        result.scale_x, result.scale_y = sent.scale_x, sent.scale_y
        return sent.sent_bytes


__all__ = ["Orchestrator", "TurnResult", "BUDGET_REFUSAL_AR", "AGENTIC_CAP_NOTE_AR",
           "MIC_FAILED_AR", "STT_EMPTY_AR", "SESSION_TIMEOUT_S",
           "MAX_REFRESH_FOLLOWUPS", "MAX_AGENTIC_ITERATIONS", "OVERLAY_SETTLE_S"]
