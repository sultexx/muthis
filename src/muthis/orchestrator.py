# src/muthis/orchestrator.py
"""
Orchestrator — the heart of Mut'his v4.1.

Owns everything the wrappers are forbidden to own (Law 11): the single
asyncio event loop, the single event queue (Law 3.3), all locks, the session
lifecycle, and the conversation history. ClaudeAgent.run() is one blind
provider turn; Budget is an accounting gate; both are only ever *asked*.

STUB-FIRST BUILD: the hotkey is the last injected stub. Mic, STT, TTS, screen
capture, downscale, and the cyan-rectangle overlay are REAL via injection —
production wires Orchestrator(mic=Mic().record, ..., overlay=SidekickOverlay());
tests inject fakes through the same seams. handle_activation: mic → STT
(Scribe, Arabic-pinned) → run_turn, with mic/STT failures spoken in Arabic
and ending the turn EARLY (no provider call, no budget burn). Playback is
buffer-then-speak per assistant message (per-delta synthesis would produce
choppy half-word audio). TODO(follow-up): sentence-by-sentence streaming
playback — deliberately NOT built yet. Contracts + TurnResult live in
turn.py (≤300-line split); this module stays importable in isolation.

Turn pipeline (run_turn), bounded by the 90 s session timeout (audio
playback included; cancellation closes the provider generator cleanly):
    budget.can_afford() BEFORE every provider call (Rule 10)
    → reasoner.run() → TextDelta accumulated into the message buffer;
      highlight_target → coords scaled sent→physical → overlay.show (LOOK-only,
        nothing else reaches it; the overlay is hidden before each capture);
      request_screen_refresh → answered with a tool_result + fresh screenshot
    → TurnComplete → budget.record_turn(), speak the buffered message via
      the injected TTS, history grows.
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
# Contracts, Arabic surface strings, TurnResult, and the refresh tool_result
# builder live in turn.py (≤300-line split); re-exported below so existing
# imports keep working.
from .turn import (
    BUDGET_REFUSAL_AR, MIC_FAILED_AR, REFRESH_FOLLOWUP_TEXT_AR, STT_EMPTY_AR,
    DownscaleFn, MicFn, Overlay, ScreenCaptureFn, SttFn, TtsFn, TurnResult,
    build_refresh_tool_result, scale_bbox_to_physical,
)
from .overlay_autohide import AutoHideController, DEFAULT_OVERLAY_TIMEOUT_S

logger = logging.getLogger("muthis.orchestrator")


# ─── Session constants ────────────────────────────────────────────────────────

# Hard wall-clock bound for one whole turn, follow-ups included (v4.1 §9.3).
SESSION_TIMEOUT_S = 90.0

# One follow-up un-stales a view; more is a model loop burning the budget.
MAX_REFRESH_FOLLOWUPS = 1

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
            logger.warning(
                "[orchestrator] session bound (%.0fs) hit — turn truncated",
                self._session_timeout_s,
            )
        return result

    # ───────────────────────── Turn pipeline ─────────────────────────

    async def _run_turn_pipeline(self, user_text: str, result: TurnResult) -> None:
        user_input = UserInput(text=user_text)
        screenshot = await self._capture_downscaled(result)
        followups_left = MAX_REFRESH_FOLLOWUPS

        while True:
            # Rule 10: the budget is sovereign. Consulted before EVERY
            # provider call — the initial turn and each follow-up alike.
            if not self._budget.can_afford():
                await self._refuse_for_budget(result)
                return

            turn_complete, refresh_call = await self._consume_stream(
                user_input, screenshot, result,
            )
            if turn_complete is None:
                return

            # History grows here and only here. User text WITHOUT the
            # screenshot — images are never replayed (token-cost multiplier).
            self.history.append({
                "role": "user",
                "content": [{"type": "text", "text": user_input.text}],
            })
            self.history.append({
                "role": "assistant",
                "content": list(turn_complete.assistant_content),
            })

            if refresh_call is None:
                return
            if followups_left <= 0:
                logger.warning(
                    "[orchestrator] refresh follow-up limit reached — "
                    "ignoring %s", refresh_call.tool_use_id,
                )
                return
            followups_left -= 1

            # Answer request_screen_refresh: tool_result + FRESH (downscaled)
            # screenshot, then one more gated provider turn.
            fresh = await self._capture_downscaled(result)
            self.history.append(build_refresh_tool_result(refresh_call, fresh))
            user_input = UserInput(text=REFRESH_FOLLOWUP_TEXT_AR)
            screenshot = None  # the fresh image rides inside the tool_result

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

        async for event in self._reasoner.run(user_input, screenshot, list(self.history)):
            if isinstance(event, TextDelta):
                result.spoken_text += event.text
                message_text += event.text
            elif isinstance(event, ToolCall):
                if event.name == ALLOWED_OVERLAY_TOOL:
                    result.tool_calls.append(event)
                    # Scale sent→physical HERE; the overlay never rescales.
                    bbox = scale_bbox_to_physical(
                        event.args, result.scale_x, result.scale_y)
                    await self._overlay.show(bbox, event.args.get("label_ar", ""))
                    self._auto_hide.schedule()  # arm auto-hide (cancel-and-replace)
                elif event.name == REFRESH_TOOL:
                    result.tool_calls.append(event)
                    refresh_call = event
                else:
                    # LOOK-only hard boundary: an action tool arriving is a
                    # provider-contract violation. Never executed/forwarded.
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
        # Cost recorded BEFORE speaking — playback takes seconds and the
        # session timeout must never cancel the accounting.
        self._budget.record_turn(turn_complete)
        await self._speak(message_text)
        return turn_complete, refresh_call

    # ───────────────────────── Helpers ─────────────────────────

    async def _speak(self, text: str) -> None:
        """Privacy boundary: ONLY assistant-authored Arabic may pass here —
        never the user transcript, never tool JSON. speak() never raises;
        a failed TTSResult is logged and the turn continues regardless."""
        if not text:
            return
        tts_result = await self._tts(text)
        if tts_result is not None:
            log = logger.info if tts_result.success else logger.warning
            log(
                "[orchestrator] tts provider=%s success=%s (%d chars)",
                tts_result.provider, tts_result.success, len(text),
            )

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
        """Capture physical pixels, then build the downscaled COPY that is the
        ONLY thing sent to the provider, and record the physical↔sent scale
        factors on the turn so highlight coords can be mapped back. Physical
        pixels stay the source of truth; only the COPY leaves here.

        Ghosting fix: hide our rectangle BEFORE every grab — the single
        chokepoint for the initial capture AND each refresh recapture. Order is
        load-bearing: hide → settle → capture."""
        self._auto_hide.cancel()  # drop any stale auto-hide before the explicit hide
        await self._overlay.hide()
        await asyncio.sleep(OVERLAY_SETTLE_S)
        sent = await self._downscale(await self._screen_capture())
        result.sent_width, result.sent_height = sent.sent_width, sent.sent_height
        result.scale_x, result.scale_y = sent.scale_x, sent.scale_y
        return sent.sent_bytes


__all__ = ["Orchestrator", "TurnResult", "BUDGET_REFUSAL_AR",
           "MIC_FAILED_AR", "STT_EMPTY_AR",
           "SESSION_TIMEOUT_S", "MAX_REFRESH_FOLLOWUPS", "OVERLAY_SETTLE_S"]
