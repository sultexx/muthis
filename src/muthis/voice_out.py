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
from .speech_stream import SentenceSplitter
from .turn_voice import ARABIC_TTS_CHARS_PER_SEC

logger = logging.getLogger("muthis.orchestrator")

# v6 C rollback flag: live captions are ON by default (Sultan's release
# decision, 2026-07-15) — a falsey value is the one-env rollback, mirroring
# the MUTHIS_TRY_ELEVENLABS pattern.
CAPTIONS_ENV = "MUTHIS_CAPTIONS"


# ROLLING CAPTIONS (DEC-128, shape C1). The BUFFERED path hands this class the
# WHOLE answer in ONE call, so the bar showed a single truncated block for a turn
# that speaks for minutes — MEASURED at 117 of 1,159 chars — and the fraction
# FALLS as the answer grows, because the bar's cap is absolute while the answer
# is not (10.1% at 1,159 chars, 3.4% at 3,479). Below this length the one block
# is already most of the answer and rolling buys nothing worth the churn; 240 is
# twice the 2x60 budget the bar carried when this was written.
#
# DELIBERATELY NOT derived from caption_bar's constants: this module is "sibling
# + stdlib imports only, importable in isolation" (module docstring), and the
# overlay package pulls the Tk window in through its __init__.
ROLLING_MIN_CHARS = 240


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
        if self._roll_caption(text, delay_s):
            return
        if delay_s > 0:
            later = getattr(self._overlay, "show_caption_later", None)
            if later is not None:
                later(text, round(delay_s * 1000))
                return
        show = getattr(self._overlay, "show_caption", None)
        if show is not None:
            show(text)

    def _roll_caption(self, text: str, delay_s: float) -> bool:
        """Shape C1: split a long BUFFERED answer into sentence captions and
        schedule each at its ESTIMATED audio start, so the bar follows the voice
        instead of freezing on the opening 117 characters for the whole turn.

        Returns False — leaving the single-caption behaviour EXACTLY as it was —
        when the overlay has no paced seam (StubOverlay, older fakes) or when the
        text is short (a streamed sentence, an ack). That floor is what keeps the
        STREAMED path untouched: its sentences arrive one at a time, well under
        it. The `len(pieces) < 2` check below is DEFENSIVE and not reachable
        today — the splitter's soft valve cuts any run past `MAX_BUFFER_CHARS`
        (200) and the floor here is 240 — kept so those constants can move
        without this method silently changing shape.

        ORDERING IS NOT TOUCHED. This runs at the caption choke point, after the
        Option-A sync point has already decided when to speak; it changes what
        the bar shows, never when the voice commits.

        The rate is IMPORTED, not copied — one source of truth, and
        `turn_voice.py` is pinned at 300 with ZERO headroom, so it must not grow
        a line to hand the constant over. Pacing is therefore open-loop: the
        buffered path feeds ONCE, so there is a single clock reading for the
        whole answer and nothing to re-anchor against. MEASURED live over
        151-167 s: 10.87 ch/s against the shipped 11.5, stable across duration
        (-0.1% from ~82 s to ~165 s), which puts the last caption of an
        eleven-caption answer ~5 s AHEAD of its audio and loses none of them."""
        later = getattr(self._overlay, "show_caption_later", None)
        if later is None or len(text) <= ROLLING_MIN_CHARS:
            return False
        splitter = SentenceSplitter()
        pieces = splitter.push(text) + splitter.flush()
        if len(pieces) < 2:
            return False
        fed = 0
        for piece in pieces:
            later(piece, round((delay_s + fed / ARABIC_TTS_CHARS_PER_SEC) * 1000))
            fed += len(piece)
        return True

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
