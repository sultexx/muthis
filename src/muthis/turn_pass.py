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
import os
from typing import Any, Callable, List, Optional

from .cloud.protocol import TextDelta, ToolCall, TurnComplete, UserInput
from .draw_dispatch import DRAW_TOOLS, PendingDraw, next_draw
from .highlight_gate import HighlightGate, loop_tool_choice
from .speech_stream import SentenceSplitter
from .turn import TurnResult

# Kept on the orchestrator's logger: the log surface is unchanged by the split.
logger = logging.getLogger("muthis.orchestrator")

REFRESH_TOOL = "request_screen_refresh"

# C2 rollback flag: sentence streaming is OFF unless .env opts in.
STREAM_TTS_ENV = "MUTHIS_STREAM_TTS"


def _stream_tts_from_env() -> bool:
    raw = os.getenv(STREAM_TTS_ENV)
    return raw is not None and raw.strip().lower() in ("1", "true", "yes", "on")


class TurnPass:
    """ONE provider pass: run the reasoner, buffer text, gate draws, then the
    draw→auto-hide→speak sync point. Built once by the Orchestrator from its
    own injected seams; stateless between calls."""

    def __init__(
        self, *, reasoner, budget, overlay, auto_hide, voice,
        stream_tts: Optional[bool] = None,
        session_factory: Optional[Callable[[], object]] = None,
    ) -> None:
        self._reasoner = reasoner
        self._budget = budget
        self._overlay = overlay
        self._auto_hide = auto_hide
        self._voice = voice
        # C2: sentence streaming — flag-gated (default OFF) and ONLY for
        # tool_choice="none" passes. The factory seam resolves lazily to the
        # real TTS().open_speech_session on first flag-ON use, so the buffered
        # default path never imports the TTS layer.
        self._stream_tts = _stream_tts_from_env() if stream_tts is None else stream_tts
        self._session_factory = session_factory

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
        message_text = ""  # buffered mirror of the pass — the fallback source
        pending_draw: Optional[PendingDraw] = None  # first draw wins; applied at speak
        tool_choice = loop_tool_choice(gate)
        # C2 criterion (decision 13): stream ONLY a tool_choice="none" pass —
        # the API forbids tools there, so no draw can arrive mid-stream and the
        # Option-A draw-at-speak invariant is untouchable. Every "auto" pass
        # (draw pass, single-pass replies, refresh follow-ups) stays buffered.
        streamer = await self._open_streamer(tool_choice)

        async for event in self._reasoner.run(user_input, screenshot, history, tool_choice=tool_choice):
            if isinstance(event, TextDelta):
                result.spoken_text += event.text
                message_text += event.text
                if streamer is not None:
                    await streamer.push(event.text)  # inline-await: no background consumer
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
            if streamer is not None:
                await streamer.abandon()  # release the session; no fallback speak
            logger.error("[orchestrator] provider stream ended without TurnComplete")
            return None, None

        result.input_tokens += turn_complete.input_tokens
        result.output_tokens += turn_complete.output_tokens
        result.cost_usd = round(result.cost_usd + turn_complete.cost_usd, 6)
        result.stop_reason = turn_complete.stop_reason
        # Cost recorded BEFORE speaking — the timeout must never cost us accounting.
        self._budget.record_turn(turn_complete)
        # Sync point: apply the ONE buffered draw + arm auto-hide, THEN speak.
        # (A streamed pass is tool_choice="none": pending_draw is impossible.)
        if pending_draw is not None:
            await pending_draw.apply(self._overlay)
            self._auto_hide.schedule()
        if streamer is not None:
            await streamer.finish(message_text)  # flush + close; approved fallback
        else:
            await self._voice.speak(message_text)
        return turn_complete, refresh_call

    async def _open_streamer(self, tool_choice: str) -> Optional["_PassStreamer"]:
        """A streamer ONLY for a flag-ON `tool_choice="none"` pass. Any
        unavailability (rollback flag / no key / open failure) → None, and the
        pass silently stays on the proven buffered path."""
        if not (self._stream_tts and tool_choice == "none"):
            return None
        if self._session_factory is None:
            from .tts import TTS  # lazy real default: only the flag-ON path pays
            self._session_factory = TTS().open_speech_session
        session = self._session_factory()
        if session is None:
            return None
        try:
            await session.open()
        except Exception as exc:  # noqa: BLE001 — degrade, never break the turn
            logger.warning(
                "[orchestrator] speech session open failed (%s) — buffered pass", exc)
            return None
        return _PassStreamer(session, self._overlay, self._voice)


class _PassStreamer:
    """One streamed pass: SentenceSplitter → the persistent SpeechSession,
    inline-await only (no background consumer — the Batch-3 wedge is impossible
    by construction). The status light holds "speaking" across ALL sentences;
    any failure degrades per decision 15: the UNPLAYED remainder goes through
    ONE buffered speak() (which cascades to Gemini on its own)."""

    def __init__(self, session, overlay, voice) -> None:
        self._session = session
        self._overlay = overlay
        self._voice = voice
        self._splitter = SentenceSplitter()
        self._dead = False
        self._unplayed: List[str] = []

    async def push(self, fragment: str) -> None:
        for sentence in self._splitter.push(fragment):
            await self._feed(sentence)

    async def finish(self, full_text: str) -> None:
        """End of the pass: flush the tail, close the generation, then the
        approved fallback — NOTHING played → the whole reply through one
        buffered speak(); died mid-way → only the remainder."""
        for sentence in self._splitter.flush():
            await self._feed(sentence)
        close_error: Optional[Exception] = None
        try:
            await self._session.close()
        except Exception as exc:  # noqa: BLE001 — degrade, never crash the turn
            close_error = exc
        # close() drained the audio tail — the last sentence has finished
        # playing, so the caption leaves the screen with it (v6 C3).
        self._voice.clear_caption()
        self._overlay.set_state("thinking")
        if not self._session.got_audio:
            if close_error is not None:
                logger.warning(
                    "[orchestrator] speech session yielded no audio (%s) — speaking buffered",
                    close_error)
            await self._voice.speak(full_text)
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
        """Abnormal pass end (no TurnComplete): release the session quietly —
        the buffered path speaks nothing on that branch either."""
        try:
            await self._session.close()
        except Exception:  # noqa: BLE001 — already on the error path
            pass
        self._voice.clear_caption()  # never leave a caption from a dead pass
        self._overlay.set_state("thinking")

    async def _feed(self, sentence: str) -> None:
        if self._dead:
            self._unplayed.append(sentence)
            return
        self._overlay.set_state("speaking")  # held across sentences (idempotent)
        # Live captions (v6 C3): the bar tracks the sentence being fed to the
        # ONE persistent generation — flag-gated inside VoiceOut (its privacy
        # choke point), a no-op when captions are off.
        self._voice.show_caption(sentence)
        try:
            await self._session.feed(sentence)
        except Exception as exc:  # noqa: BLE001 — degrade to buffered
            logger.warning(
                "[orchestrator] speech session feed failed (%s) — buffering the rest", exc)
            self._dead = True
            # This sentence never played; the fallback speak() re-shows what
            # is ACTUALLY spoken — the bar must not freeze on a dead sentence.
            self._voice.clear_caption()
            self._unplayed.append(sentence)


__all__ = ["TurnPass", "REFRESH_TOOL", "STREAM_TTS_ENV"]
