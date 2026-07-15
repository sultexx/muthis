# src/muthis/turn_voice.py
"""
TurnVoice — ONE continuous speech generation for the WHOLE turn (v7 audio fix).

WHY: the measured stop-and-go (diag 2026-07-15) — pass 1 spoke its ack through
a BLOCKING buffered speak(), then the agentic loop paid a full second provider
round-trip (WS open 0.51s + TTFT 1.93s + first sentence 0.77s = a 3.48s silent
gap) before pass 2's streamed explanation started in a SECOND generation. This
module replaces the per-pass `_PassStreamer` with a session that lives for the
TURN: the ack is FED (an instant WebSocket send — audio plays on the player's
existing worker thread) instead of awaited, so the loop proceeds immediately
and the round-trip hides BEHIND the ack playback; pass 2's sentences join the
SAME generation, so prosody never restarts and the status light never flickers
back to "thinking" mid-speech.

NOT the Batch-3 wedge: every feed is an inline await (no background consumer).
The only concurrent parts remain the ones that already exist — the PCM player
worker and the session's bounded internal reader — and `finish()` (called from
run_turn's `finally`) closes both deterministically every turn.

Option A is untouched: the pass's sync point still runs draw → arm auto-hide →
THEN hand the text here. Decision 13 is untouched: mid-pass streaming happens
only on `tool_choice="none"` passes; an "auto" pass's text arrives WHOLE at the
sync point via speak_or_feed().

Degradation (decision 15, generalized from pass to turn): streaming disabled /
no key / open failed → every text goes through the proven buffered
`VoiceOut.speak()` exactly as before. A session that DIES mid-turn defers the
unplayed remainder to finish() — spoken in ONE buffered call AFTER close()
drains the already-playing tail (never overlapping audio). `got_audio` remains
the double-speak guard: nothing played → the whole turn's text is re-spoken.

Per-turn state like HighlightGate: built fresh by `TurnPass.new_turn_voice()`
each turn, never reused. Sibling + stdlib imports; importable in isolation.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, List, Optional

from .speech_stream import SentenceSplitter

# The orchestrator's logger: this is turn-pipeline speech plumbing, and the log
# surface should read as one component (same choice as turn_pass/voice_out).
logger = logging.getLogger("muthis.orchestrator")

# DIAG(v7): temporary timing probe for the audio investigation.
_diag = logging.getLogger("muthis.diag")


class TurnVoice:
    """The turn's mouth-stream: open lazily on first speech, feed sentences
    from EVERY pass into one generation, close once at turn end."""

    def __init__(
        self,
        *,
        voice,                      # VoiceOut: buffered speak + caption choke point
        overlay,                    # status light (set_state), duck-typed
        session_factory: Optional[Callable[[], object]] = None,
        enabled: bool = False,
    ) -> None:
        self._voice = voice
        self._overlay = overlay
        self._factory = session_factory
        self._enabled = enabled and session_factory is not None
        self._session = None
        self._open_failed = False   # one open attempt per turn — no retry storm
        self._dead = False          # a feed raised: defer the rest to finish()
        self._closed = False
        self._splitter = SentenceSplitter()
        self._fed: List[str] = []
        self._unplayed: List[str] = []

    # ─────────────────────────────── Speaking ───────────────────────────────

    async def ensure_open(self) -> bool:
        """True iff the ONE turn session is (now) open and alive. At most one
        open attempt per turn; failure logs and leaves the turn buffered."""
        if self._session is not None:
            return not self._dead
        if not self._enabled or self._open_failed or self._closed:
            return False
        session = self._factory()
        if session is None:                      # factory says: streaming unavailable
            self._open_failed = True
            return False
        try:
            await session.open()
        except Exception as exc:  # noqa: BLE001 — degrade, never break the turn
            logger.warning(
                "[orchestrator] speech session open failed (%s) — buffered turn", exc)
            self._open_failed = True
            return False
        self._session = session
        return True

    async def speak_or_feed(self, text: str) -> None:
        """A pass's BUFFERED text at its sync point (the pass-1 ack, refresh
        follow-ups, single-pass replies, spoken notes). Session alive → an
        INSTANT feed (audio plays while the loop moves on — the master fix);
        never opened → the proven blocking VoiceOut.speak(); died mid-turn →
        deferred to finish() so fallback audio can never overlap the tail."""
        if not text:
            return
        if self._dead:
            self._unplayed.append(text)
            return
        if await self.ensure_open():
            await self._feed(text)
        else:
            await self._voice.speak(text)

    async def push_stream(self, fragment: str) -> None:
        """Streamed-pass deltas (tool_choice="none" only): sentences feed the
        instant their boundary arrives."""
        for sentence in self._splitter.push(fragment):
            await self._feed(sentence)

    async def end_stream(self) -> None:
        """A streamed pass ended: flush the splitter tail into the generation.
        The session stays OPEN — a later pass may keep speaking."""
        for sentence in self._splitter.flush():
            await self._feed(sentence)

    # ─────────────────────────────── Lifecycle ───────────────────────────────

    async def finish(self) -> None:
        """Turn end (run_turn's finally): close the generation, drain the tail,
        then the decision-15 fallback — nothing played → the WHOLE turn's text
        in one buffered speak(); died mid-way → only the unplayed remainder;
        close failed after audio → log only (re-speaking would duplicate)."""
        if self._closed:
            return
        self._closed = True
        if self._session is None:
            return                               # buffered turn: nothing to drain
        close_error: Optional[Exception] = None
        try:
            await self._session.close()
        except Exception as exc:  # noqa: BLE001 — degrade, never crash the turn
            close_error = exc
        _diag.info("[DIAG] turn-voice finish t=%.3f fed=%d unplayed=%d",
                   time.monotonic(), len(self._fed), len(self._unplayed))
        # close() drained the audio tail — the caption leaves with the voice.
        self._voice.clear_caption()
        self._overlay.set_state("thinking")
        if not self._session.got_audio:
            if close_error is not None:
                logger.warning(
                    "[orchestrator] speech session yielded no audio (%s) — speaking buffered",
                    close_error)
            whole_turn = " ".join(self._fed + self._unplayed).strip()
            if whole_turn:
                await self._voice.speak(whole_turn)
            return
        if self._unplayed:
            logger.warning(
                "[orchestrator] speech session died mid-turn — speaking the remainder buffered")
            await self._voice.speak(" ".join(self._unplayed))
        elif close_error is not None:
            # Audio already played; re-speaking would duplicate — log only.
            logger.warning(
                "[orchestrator] speech session close failed after audio (%s)", close_error)

    async def abandon(self) -> None:
        """Abnormal turn end (a pass died without TurnComplete): release the
        generation quietly — that branch never spoke on the buffered path
        either, so no fallback speak."""
        if self._closed:
            return
        self._closed = True
        if self._session is None:
            return
        try:
            await self._session.close()
        except Exception:  # noqa: BLE001 — already on the error path
            pass
        self._voice.clear_caption()              # never leave a caption from a dead turn
        self._overlay.set_state("thinking")

    # ─────────────────────────────── Internals ───────────────────────────────

    async def _feed(self, sentence: str) -> None:
        if self._dead:
            self._unplayed.append(sentence)
            return
        self._overlay.set_state("speaking")      # held across sentences (idempotent)
        # Live captions: the bar tracks what the generation is being fed —
        # flag-gated inside VoiceOut (the privacy choke point).
        self._voice.show_caption(sentence)
        try:
            await self._session.feed(sentence)
            self._fed.append(sentence)
        except Exception as exc:  # noqa: BLE001 — degrade to buffered-at-finish
            logger.warning(
                "[orchestrator] speech session feed failed (%s) — buffering the rest", exc)
            self._dead = True
            # This sentence never played; the bar must not freeze on it.
            self._voice.clear_caption()
            self._unplayed.append(sentence)


__all__ = ["TurnVoice"]
