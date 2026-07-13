# src/muthis/voice_out.py
"""
VoiceOut — the orchestrator's mouth (extracted under the ≤300-line law).

orchestrator.py sat at 299 lines and Phase B (v5) needed room there, so its two
SPOKEN surfaces moved here whole (Law §17.4: split, don't compress — the same
reason highlight_gate.py and draw_dispatch.py exist):

  * `speak()` — the PRIVACY BOUNDARY: only assistant-authored Arabic may pass
    here — never the user transcript, never tool JSON. It also choreographs the
    status light (speaking while the voice plays, back toward thinking after);
    it never raises — a failed TTSResult is logged and the turn continues.
  * `refuse_for_budget()` — the Rule-10 refusal, spoken out loud with NO
    provider call, flagging the TurnResult.

Behavior is UNCHANGED from the orchestrator methods this replaces. The Option-A
sync point (apply the buffered draw → arm auto-hide → THEN speak) stays in the
orchestrator — this module only receives the speak CALL, never reorders it.
The logger keeps the "muthis.orchestrator" name so log surfaces are unchanged.
Sibling + stdlib imports only; importable in isolation.
"""

from __future__ import annotations

import logging

from .budget import Budget
from .turn import BUDGET_REFUSAL_AR, Overlay, TtsFn, TurnResult

logger = logging.getLogger("muthis.orchestrator")


class VoiceOut:
    """The spoken output of a turn: TTS + status-light choreography + the
    budget refusal. Built by the Orchestrator from its own injected seams."""

    def __init__(self, tts: TtsFn, overlay: Overlay) -> None:
        self._tts = tts
        self._overlay = overlay

    async def speak(self, text: str) -> None:
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

    async def refuse_for_budget(self, result: TurnResult, budget: Budget) -> None:
        """Refuse the turn out loud — no provider call is made."""
        result.budget_blocked = True
        logger.warning(
            "[orchestrator] budget gate closed (%.6f / %.2f USD spent) — "
            "turn refused, no provider call",
            budget.spent_today_usd(), budget.daily_limit_usd,
        )
        await self.speak(BUDGET_REFUSAL_AR)


__all__ = ["VoiceOut"]
