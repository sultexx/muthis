# src/muthis/voice_out.py
"""
VoiceOut — the orchestrator's mouth (extracted under the ≤300-line law).

orchestrator.py sat at 299 lines and Phase B (v5) needed room there, so its two
SPOKEN surfaces moved here whole (the ≤300-line law: split, don't compress — the
same reason highlight_gate.py and draw_dispatch.py exist):

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
import os
from typing import Optional

from .kernel.budget import Budget
from .kernel.turn import BUDGET_REFUSAL_AR, Overlay, TtsFn, TurnResult

logger = logging.getLogger("muthis.orchestrator")

# v6 C rollback flag: live captions are ON by default (Sultan's release
# decision, 2026-07-15) — a falsey value is the one-env rollback, mirroring
# the MUTHIS_TRY_ELEVENLABS pattern.
CAPTIONS_ENV = "MUTHIS_CAPTIONS"


def _captions_from_env() -> bool:
    raw = os.getenv(CAPTIONS_ENV)
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off")


class VoiceOut:
    """The spoken output of a turn: TTS + status-light choreography + the
    budget refusal — and (v6 C) the CAPTION choke point: everything the bar
    ever shows passes through THIS class, so the privacy boundary (assistant
    speech only) covers the eyes exactly like the ears. Built by the
    Orchestrator from its own injected seams."""

    def __init__(self, tts: TtsFn, overlay: Overlay,
                 captions: Optional[bool] = None) -> None:
        self._tts = tts
        self._overlay = overlay
        self._captions = _captions_from_env() if captions is None else captions

    def show_caption(self, text: str, delay_s: float = 0.0) -> None:
        """Show `text` on the overlay's caption bar — flag-gated and
        duck-typed: an overlay without a caption bar (StubOverlay, older
        fakes) is a silent no-op. SYNC fire-and-forget (a thread-safe
        enqueue on the real overlay), so speech timing never waits on Tk.
        `delay_s` (v7 Phase 2 caption sync) defers the display to the
        sentence's estimated AUDIO start via the overlay's paced seam; an
        overlay without that seam shows immediately (the old behavior)."""
        if not (self._captions and text):
            return
        if delay_s > 0:
            later = getattr(self._overlay, "show_caption_later", None)
            if later is not None:
                later(text, round(delay_s * 1000))
                return
        show = getattr(self._overlay, "show_caption", None)
        if show is not None:
            show(text)

    def clear_caption(self) -> None:
        """Drop the caption (the audio for it has finished)."""
        if not self._captions:
            return
        clear = getattr(self._overlay, "clear_caption", None)
        if clear is not None:
            clear()

    async def speak(self, text: str) -> None:
        """Privacy boundary: ONLY assistant-authored Arabic may pass here —
        never the user transcript, never tool JSON. speak() never raises;
        a failed TTSResult is logged and the turn continues regardless.
        The caption shows WITH the speech start and clears when the audio
        finishes (TTS returns post-playback) — success or failure alike."""
        if not text:
            return
        self._overlay.set_state("speaking")  # neon green while the voice plays
        self.show_caption(text)
        try:
            tts_result = await self._tts(text)
        finally:
            self.clear_caption()
        if tts_result is not None:
            log = logger.info if tts_result.success else logger.warning
            log(
                "[orchestrator] tts provider=%s success=%s (%d chars)",
                tts_result.provider, tts_result.success, len(text),
            )
        self._overlay.set_state("thinking")  # back toward thinking; idle set at turn end

    async def refuse_for_budget(self, result: TurnResult, budget: Budget,
                                speak=None) -> None:
        """Refuse the turn out loud — no provider call is made. `speak` lets
        the caller route the refusal through the turn's continuous voice (v7)
        so it queues behind any audio already playing; default is self.speak."""
        result.budget_blocked = True
        logger.warning(
            "[orchestrator] budget gate closed (%.6f / %.2f USD spent) — "
            "turn refused, no provider call",
            budget.spent_today_usd(), budget.daily_limit_usd,
        )
        await (speak or self.speak)(BUDGET_REFUSAL_AR)


__all__ = ["VoiceOut", "CAPTIONS_ENV"]
