# src/muthis/orchestrator.py
"""
Orchestrator — the heart of Mut'his v4.1.

Owns everything the wrappers are forbidden to own (Law 11): the single
asyncio event loop, the single event queue (Law 3.3), all locks, the session
lifecycle, and the conversation history. ClaudeAgent.run() is one blind
provider turn; Budget is an accounting gate; both are only ever *asked*.

STUB-FIRST BUILD: no real microphone, STT, TTS playback, or screen capture
is wired here yet. Every external dependency is an injected async callable;
the defaults below log in English and return canned data. The only real
integrations are the CloudReasoner protocol (cloud/protocol.py) and the
Budget gate (budget.py) — both stdlib-only, so this module stays importable
in isolation (no SDK imports).

Turn pipeline (run_turn):
    budget.can_afford()  ← BEFORE every provider call (Rule 10)
    → reasoner.run(user_input, screenshot, history)
    → TextDelta  → tts stub        (and accumulated into TurnResult)
    → ToolCall   → highlight_target → overlay stub (LOOK-only — nothing else
                   ever reaches the overlay); request_screen_refresh →
                   answered internally with a tool_result + fresh screenshot
    → TurnComplete → budget.record_turn(), history grows
    All bounded by the 90 s session timeout; cancelling the run_turn task
    propagates through the stream and closes the provider generator cleanly
    (the wrapper holds no state, so nothing leaks).
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from .budget import Budget
from .cloud.protocol import (
    CloudReasoner,
    TextDelta,
    ToolCall,
    TurnComplete,
    UserInput,
)
# STUB defaults — each is replaced by its real component in a later phase.
from .stubs import stub_overlay, stub_screen_capture, stub_stt, stub_tts

logger = logging.getLogger("muthis.orchestrator")


# ─── Session constants ────────────────────────────────────────────────────────

# Hard wall-clock bound for one whole turn, follow-ups included (v4.1 §9.3).
SESSION_TIMEOUT_S = 90.0

# One refresh follow-up is enough to un-stale a view; more is a model loop
# that would burn the budget.
MAX_REFRESH_FOLLOWUPS = 1

ALLOWED_OVERLAY_TOOL = "highlight_target"
REFRESH_TOOL = "request_screen_refresh"

# User-facing Arabic — the ONLY Arabic surfaces in this module (logs stay
# English, Law §17.5).
BUDGET_REFUSAL_AR = "عذراً، استهلكنا ميزانية اليوم كاملة. نكمل بكرة إن شاء الله."
REFRESH_FOLLOWUP_TEXT_AR = "هذه لقطة الشاشة المحدثة."
NO_SCREENSHOT_TOOL_RESULT_AR = "تعذّر التقاط لقطة شاشة جديدة."


# ─── Injected dependency signatures ───────────────────────────────────────────

SttFn = Callable[[], Awaitable[str]]
TtsFn = Callable[[str], Awaitable[None]]
ScreenCaptureFn = Callable[[], Awaitable[Optional[bytes]]]
OverlayFn = Callable[[ToolCall], Awaitable[None]]


# ─── Turn result ──────────────────────────────────────────────────────────────

@dataclass
class TurnResult:
    """Everything the caller needs to know about one completed turn."""
    spoken_text: str = ""                  # concatenated TextDelta stream
    tool_calls: list[ToolCall] = field(default_factory=list)  # executed only
    input_tokens: int = 0                  # summed across follow-ups
    output_tokens: int = 0
    cost_usd: float = 0.0
    budget_blocked: bool = False
    timed_out: bool = False
    stop_reason: Optional[str] = None      # last provider stop_reason


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class Orchestrator:
    """One per process. Owns loop, queue, history, and the turn pipeline."""

    def __init__(
        self,
        *,
        reasoner: CloudReasoner,
        budget: Budget,
        stt: SttFn = stub_stt,
        tts: TtsFn = stub_tts,
        screen_capture: ScreenCaptureFn = stub_screen_capture,
        overlay: OverlayFn = stub_overlay,
        session_timeout_s: float = SESSION_TIMEOUT_S,
    ) -> None:
        self._reasoner = reasoner
        self._budget = budget
        self._stt = stt
        self._tts = tts
        self._screen_capture = screen_capture
        self._overlay = overlay
        self._session_timeout_s = session_timeout_s

        # Conversation history, Claude message-dict format. Owned HERE and
        # nowhere else — the wrapper stores nothing between calls.
        self.history: list[dict[str, Any]] = []

        # The single event queue (Law 3.3). Placeholder until the hotkey
        # listener phase wires a real dispatcher through it.
        self.event_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()

    # ─────────────────────────── Public API ───────────────────────────

    async def handle_activation(self) -> TurnResult:
        """PTT entry point. # STUB — the real Ctrl+Shift+Space listener and
        mic capture arrive in the activation phase; for now STT is canned."""
        user_text = await self._stt()
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
        screenshot = await self._screen_capture()
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
            # screenshot — images are passed fresh per turn, never replayed
            # from history (replaying them would multiply token cost).
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

            # Answer request_screen_refresh: tool_result + FRESH screenshot,
            # then one more gated provider turn. The wrapper will append its
            # own user text message after this tool_result message; the API
            # merges consecutive user-role messages.
            fresh = await self._screen_capture()
            self.history.append(self._build_refresh_tool_result(refresh_call, fresh))
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

        async for event in self._reasoner.run(user_input, screenshot, list(self.history)):
            if isinstance(event, TextDelta):
                result.spoken_text += event.text
                await self._tts(event.text)
            elif isinstance(event, ToolCall):
                if event.name == ALLOWED_OVERLAY_TOOL:
                    result.tool_calls.append(event)
                    await self._overlay(event)
                elif event.name == REFRESH_TOOL:
                    result.tool_calls.append(event)
                    refresh_call = event
                else:
                    # LOOK-only hard boundary: action tools are never offered
                    # in the schema, so one arriving is a provider-contract
                    # violation. Never executed, never forwarded.
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
        self._budget.record_turn(turn_complete)
        return turn_complete, refresh_call

    # ───────────────────────── Helpers ─────────────────────────

    async def _refuse_for_budget(self, result: TurnResult) -> None:
        """Refuse the turn out loud — no provider call is made."""
        result.budget_blocked = True
        logger.warning(
            "[orchestrator] budget gate closed (%.6f / %.2f USD spent) — "
            "turn refused, no provider call",
            self._budget.spent_today_usd(), self._budget.daily_limit_usd,
        )
        await self._tts(BUDGET_REFUSAL_AR)

    @staticmethod
    def _build_refresh_tool_result(
        refresh_call: ToolCall,
        screenshot: Optional[bytes],
    ) -> dict[str, Any]:
        """User message carrying the tool_result for request_screen_refresh."""
        if screenshot:
            # Minimal PNG/JPEG sniff, deliberately NOT imported from
            # claude_agent: that module pulls in the SDK stack and this one
            # must stay importable in isolation.
            media_type = ("image/png" if screenshot[:4] == b"\x89PNG"
                          else "image/jpeg")
            inner: list[dict[str, Any]] = [{
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.standard_b64encode(screenshot).decode("ascii"),
                },
            }]
        else:
            inner = [{"type": "text", "text": NO_SCREENSHOT_TOOL_RESULT_AR}]
        return {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": refresh_call.tool_use_id,
                "content": inner,
            }],
        }


__all__ = [
    "Orchestrator",
    "TurnResult",
    "BUDGET_REFUSAL_AR",
    "SESSION_TIMEOUT_S",
    "MAX_REFRESH_FOLLOWUPS",
]
