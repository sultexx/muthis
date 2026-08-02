# src/muthis/kernel/orchestrator.py
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
from typing import Any, Callable, Optional

from .budget import Budget
from ..cloud.protocol import CloudReasoner, UserInput
from .draw_dispatch import DRAW_SHAPES_TOOL, DRAW_TOOLS
from ..file_reader import ReadFileFn
# STUB defaults — each is replaced by its real component in a later phase.
from ..stubs import (stub_downscale, stub_mic, stub_overlay, stub_read_file,
                     stub_screen_capture, stub_stt, stub_tts)
# turn.py holds the contracts, Arabic strings, TurnResult, the tool_result builder.
from .frame_capture import FrameCapture
from .highlight_gate import HighlightGate
from .interrupt_hooks import InterruptHooks
from .tool_router import ToolRouter
from .turn_pass import REFRESH_TOOL, TurnPass
from .turn import (
    AGENTIC_CAP_NOTE_AR, BUDGET_REFUSAL_AR, MIC_FAILED_AR, REFRESH_FOLLOWUP_TEXT_AR,
    STT_EMPTY_AR, DownscaleFn, MicFn, Overlay, ScreenCaptureFn, SttFn, TtsFn,
    TurnResult, build_tool_result_message, strip_images_from_history,
)
from ..overlay_autohide import AutoHideController, DEFAULT_OVERLAY_TIMEOUT_S
from .turn_prelude import TurnPrelude
from .verbosity import VerbosityController
from ..voice_out import VoiceOut

logger = logging.getLogger("muthis.orchestrator")


# ─── Session constants ────────────────────────────────────────────────────────

# Hard wall-clock bound for one whole turn, follow-ups included (AGENTS.md).
SESSION_TIMEOUT_S = 90.0

# One follow-up un-stales a view; more is a model loop burning the budget.
MAX_REFRESH_FOLLOWUPS = 1

# Hard cap on agentic run() calls per utterance — bounds a never-ending tool_use.
MAX_AGENTIC_ITERATIONS = 4

ALLOWED_OVERLAY_TOOL = "highlight_target"
# REFRESH_TOOL moved to turn_pass.py with the pass-draining code (re-exported
# via the import above so existing references keep working). OVERLAY_SETTLE_S
# moved to frame_capture.py with the capture chokepoint (M1-2 extraction).


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
        read_file: ReadFileFn = stub_read_file,
        router: Optional[ToolRouter] = None,
        sandbox: Optional[Any] = None,
        session_timeout_s: float = SESSION_TIMEOUT_S,
        overlay_timeout_s: float = DEFAULT_OVERLAY_TIMEOUT_S,
        verbosity: Optional[VerbosityController] = None,
        stream_tts: Optional[bool] = None,
        speech_session_factory: Optional[Callable[[], object]] = None,
    ) -> None:
        self._reasoner = reasoner
        self._budget = budget
        self._mic = mic
        self._stt = stt
        self._overlay = overlay
        # The spoken surfaces (privacy boundary + status choreography + budget
        # refusal) live in voice_out.py — the ≤300-line split, like highlight_gate.
        self._voice = VoiceOut(tts, overlay)
        # Every kernel-owned directive that decorates the raw transcript lives
        # in ONE object (DEC-73 split 2): verbosity, the barge-in note, and — at
        # T1 — DEC-65's mode frame. Held ACROSS turns; the rationale moved WITH
        # the code rather than being compressed out of it (DEC-30).
        self._prelude = TurnPrelude(verbosity=verbosity)
        self._session_timeout_s = session_timeout_s
        self._auto_hide = AutoHideController(self._overlay, overlay_timeout_s)
        # The hide→settle→capture chokepoint lives in frame_capture.py — the
        # M1-2 extraction that makes the router seam fit under the 300 law.
        self._frames = FrameCapture(overlay=overlay, screen_capture=screen_capture,
                                    downscale=downscale, auto_hide=self._auto_hide)
        # Pass-draining (incl. the draw→auto-hide→speak sync point) lives in
        # turn_pass.py — the ≤300-line split; built from the same seams. The
        # C2 streaming seams (flag + session factory) ride through untouched.
        self._pass = TurnPass(
            reasoner=reasoner, budget=budget, overlay=overlay, voice=self._voice,
            stream_tts=stream_tts, session_factory=speech_session_factory,
            read_file=read_file,  # v7 Phase 4: the read_local_file seam
            router=router,  # V2 Phase 1: the ONE injected seam (roadmap §1)
            sandbox=sandbox,  # V2 Phase 2 (T5): the run_code servicer
        )
        # Barge-in (v7 Phase 3): the live turn's voice + the next-turn note flag.
        self._active_turn_voice = None
        self._interrupted_last_turn = False
        # DEC-3-C: the GENERIC F9 hook seam — fired on interrupt; the kernel
        # stays blind to what a hook does (a plugin registers its own).
        self._interrupts = InterruptHooks()

        # Conversation history (Claude message-dict format). Owned HERE and
        # nowhere else — the wrapper stores nothing between calls.
        self.history: list[dict[str, Any]] = []

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
            await self._voice.speak(MIC_FAILED_AR)
            return TurnResult()

        user_text = (await self._stt(audio)).strip()
        if not user_text:
            logger.warning("[orchestrator] empty transcript — turn aborted")
            await self._voice.speak(STT_EMPTY_AR)
            return TurnResult()

        return await self.run_turn(user_text)

    async def interrupt_turn(self) -> None:
        """Barge-in (v7 Phase 3): clear the UI, silence the active voice
        (finish() then no-ops — no fallback re-speak), and mark the NEXT
        turn's interrupted-context directive. The caller cancels the turn
        task AFTER this returns. Safe no-op when no turn is active.

        DEC-3-C: F9 also fires the generic interrupt hooks — fire-and-forget
        on their own threads, PARALLEL to the silence, never blocking it."""
        turn_voice = self._active_turn_voice  # captured pre-await (race armor)
        if turn_voice is not None:
            self._interrupts.fire()  # generic F9 side effects, alongside the silence
        # UI first: the instant hide wipes board/shapes/captions/dim ~10 ms
        # in, while the audio abort pays its ~130 ms WS close behind it.
        self._auto_hide.cancel()
        await self._overlay.hide()
        if turn_voice is not None:
            await turn_voice.interrupt()
            self._interrupted_last_turn = True

    def add_interrupt_hook(self, hook: Callable[[], None]) -> None:
        """Register a fire-and-forget F9 hook (DEC-3-C) — fired on its own thread."""
        self._interrupts.add(hook)

    async def run_turn(self, user_text: str) -> TurnResult:
        """Execute one full (stubbed) turn. Never raises on timeout — the
        TurnResult reports what happened. Cancellation propagates normally."""
        user_text = self._prelude.begin_turn(
            user_text, interrupted=self._interrupted_last_turn)
        self._interrupted_last_turn = False
        result = TurnResult()
        # Per-turn state (fresh by construction): the draw gate and the ONE
        # continuous speech generation every pass feeds into (v7). The gate is
        # also rebuilt at the pipeline top; this early build keeps the finally
        # below safe on any pre-pipeline exit.
        self._highlight_gate = HighlightGate()
        turn_voice = self._pass.new_turn_voice()
        self._active_turn_voice = turn_voice  # visible to interrupt_turn
        turn_voice.begin_open()  # Fix G: the WS handshake overlaps the vision pass
        try:
            async with asyncio.timeout(self._session_timeout_s):
                await self._run_turn_pipeline(user_text, result, turn_voice)
        except TimeoutError:
            result.timed_out = True
            logger.warning("[orchestrator] session bound (%.0fs) hit — turn truncated", self._session_timeout_s)
        finally:
            # v1.0-RC2 (UAT 1): the barge-in window stays OPEN through the drain.
            try:
                # Outside the timeout scope, so the drain can await safely: close
                # the turn's generation (decision-15 fallbacks live inside) …
                await turn_voice.finish()
                # … then the WHITEBOARD lights come back on (v7 Phase 2): a
                # dim_screen draw fades out AT speech end — the un-dim is
                # synchronized with the voice; the shapes keep the 7 s grace
                # below. Duck-typed: stubs/old fakes without it no-op.
                if any(call.name == DRAW_SHAPES_TOOL and call.args.get("dim_screen")
                       for call in result.tool_calls):
                    undim = getattr(self._overlay, "undim_screen", None)
                    if undim is not None:
                        undim()
                # … and arm the auto-hide — the ONLY arm site (v7.1 Fix F: a
                # draw-time timer hid the rectangle mid-explanation). finish()
                # returns at SPEECH END, so the 7 s count from here. Keyed on the
                # RECEIVED draw calls, not gate.drawn (the gate flips only at the
                # pairing, which a fake or mid-turn failure may never reach).
                if any(call.name in DRAW_TOOLS for call in result.tool_calls):
                    self._auto_hide.schedule()
            finally:
                self._active_turn_voice = None  # the barge-in window closes here
        self.history = strip_images_from_history(self.history)  # Bug 3: drop stale frame
        self._prelude.end_turn()   # decay whatever is one-shot (B4)
        return result

    # ───────────────────────── Turn pipeline ─────────────────────────

    async def _run_turn_pipeline(self, user_text: str, result: TurnResult,
                                 turn_voice) -> None:
        user_input = UserInput(text=user_text)
        screenshot = await self._frames.capture(result)
        refresh_used = 0
        self._highlight_gate = HighlightGate()  # circuit breaker — fresh per turn

        # Agentic loop — ONE run() call per pass; the cap stops a model that, after
        # a tool_use, never says end_turn (point → explain normally needs ≤2 passes).
        for _iteration in range(MAX_AGENTIC_ITERATIONS):
            if not self._budget.can_afford():            # Rule 10, before EVERY call
                # Spoken through the turn voice: audio from an earlier pass may
                # still be playing — the refusal must queue behind it, never overlap.
                await self._voice.refuse_for_budget(
                    result, self._budget, speak=turn_voice.speak_or_feed)
                return
            turn_complete, refresh_call, serviced = await self._pass.consume(
                user_input, screenshot, list(self.history),
                self._highlight_gate, result, turn_voice)
            if turn_complete is None:                    # stream died, no TurnComplete
                await turn_voice.abandon()               # release the generation quietly
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
            fresh = await self._frames.capture(result) if serviced_refresh else None
            pairing = build_tool_result_message(
                turn_complete.assistant_content, refresh_call, fresh,
                self._highlight_gate, serviced)
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
        await turn_voice.speak_or_feed(AGENTIC_CAP_NOTE_AR)  # queues behind playing audio

__all__ = ["Orchestrator", "TurnResult", "BUDGET_REFUSAL_AR", "AGENTIC_CAP_NOTE_AR",
           "MIC_FAILED_AR", "STT_EMPTY_AR", "SESSION_TIMEOUT_S",
           "MAX_REFRESH_FOLLOWUPS", "MAX_AGENTIC_ITERATIONS"]
