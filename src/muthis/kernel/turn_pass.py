# src/muthis/kernel/turn_pass.py
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
from typing import Any, Callable, Optional

from ..cloud.protocol import TextDelta, ToolCall, TurnComplete, UserInput
from .draw_dispatch import DRAW_TOOLS, PendingDraw, next_draw
from ..file_reader import READ_FILE_TOOL, ReadFileFn
from .highlight_gate import HighlightGate, loop_tool_choice
from .core_router import build_core_router
from .tool_router import ToolRouter
from .turn import RUN_CODE_TOOL, TurnResult
from ..turn_voice import TurnVoice

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
    draw→speak sync point. Built once by the Orchestrator from its own
    injected seams; stateless between calls."""

    def __init__(
        self, *, reasoner, budget, overlay, voice,
        stream_tts: Optional[bool] = None,
        session_factory: Optional[Callable[[], object]] = None,
        read_file: Optional[ReadFileFn] = None,
        router: Optional[ToolRouter] = None,
        sandbox: Optional[Any] = None,
    ) -> None:
        self._reasoner = reasoner
        self._budget = budget
        self._overlay = overlay
        self._voice = voice
        # V2 Phase 0: the bespoke read seam generalized into the ToolRouter
        # (roadmap part 2 §1 — the one surgical change). The `read_file=`
        # kwarg contract is UNCHANGED: by default the router is built from
        # that same seam (production: FileReader().read; None degrades to the
        # Arabic unavailable note inside the router). An explicit `router`
        # wins — the Phase-1 broker's composition point. M1-3: the default
        # router feeds the per-plugin budget column when the injected budget
        # carries it (getattr: V1 fakes with only can_afford/record_turn
        # stay valid — accounting is additive, never a new requirement).
        self._router = router if router is not None else build_core_router(
            read_file=read_file,
            plugin_ledger=getattr(budget, "record_plugin_call", None))
        # v7: sentence streaming — flag-gated (default OFF). The factory seam
        # resolves lazily to the real TTS().open_speech_session on first
        # flag-ON use, so the buffered default path never imports the TTS layer.
        self._stream_tts = _stream_tts_from_env() if stream_tts is None else stream_tts
        self._session_factory = session_factory
        # T5: the plugin-domain sandbox servicer (gate + runner + kill), injected
        # at composition. None → run_code is unavailable (never offered anyway).
        self._sandbox = sandbox

    def new_turn_voice(self) -> TurnVoice:
        """A fresh per-turn voice (built by run_turn like the HighlightGate):
        ONE speech generation the whole turn feeds into. Flag OFF / no key →
        the TurnVoice simply routes everything through buffered speak().
        Also the per-turn setup hook: resets the sandbox run gate (T5)."""
        if self._sandbox is not None:
            self._sandbox.new_turn()  # fresh ≤3-runs/turn budget, like HighlightGate
        # DEC-16: arm the confirm gate's ONE look at this turn's transcript. It
        # rides the SAME turn-boundary hook as the sandbox gate on purpose —
        # DEC-19 forbids inventing a second one, and this hook is proven live.
        self._router.confirm_gate.new_turn()
        # DEC-37: the SAME hook, now serving two more consumers — the plugin-side
        # fetch cap (DEC-22) and the broker-side provenance collector (DEC-36).
        # The kernel fires OPAQUE callables and never learns what they reset; the
        # composition root registered each owner's own. Guarded like InterruptHooks
        # (a hook may not kill a turn, Law 11) but SYNCHRONOUS, not threaded: these
        # resets must be complete before the turn runs, whereas an F9 hook must
        # never block the silence. A raise is logged, never silently swallowed.
        for hook in self._router.turn_hooks:
            try:
                hook()
            except Exception:  # noqa: BLE001 — bookkeeping must never kill a turn
                logger.warning("[orchestrator] a turn-boundary hook raised — ignored")
        if self._stream_tts and self._session_factory is None:
            from ..tts import TTS  # lazy real default: only the flag-ON path pays
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
    ) -> tuple[Optional[TurnComplete], Optional[ToolCall],
               Optional[tuple[ToolCall, str]], Optional[tuple[ToolCall, str]]]:
        """Drain one provider turn into result. Returns (turn_complete,
        refresh_call, read_result): refresh_call is set iff the model asked
        for a new screenshot; read_result is (call, content) for the FIRST
        read_local_file of the pass, already serviced (v7 Phase 4) — the
        pipeline rides both into build_tool_result_message."""
        # DEC-16: the deterministic approval detector reads the RAW transcript
        # HERE, before the provider runs, because this is where the kernel
        # already hands it over — which is what keeps orchestrator.py
        # byte-identical (DEC-19 zero touch). The gate itself is one-shot per
        # turn, so the agentic loop's continuation passes (empty text, or the
        # refresh follow-up constant) cannot expire a pending approval inside
        # the very turn that asked for it. The model is never consulted.
        self._router.confirm_gate.observe(user_input.text)
        turn_complete: Optional[TurnComplete] = None
        refresh_call: Optional[ToolCall] = None
        read_call: Optional[ToolCall] = None
        run_call: Optional[ToolCall] = None  # T5: the pass's run_code (first wins)
        message_text = ""  # buffered mirror of the pass — the fallback source
        pending_draw: Optional[PendingDraw] = None  # first draw wins; applied at speak
        tool_choice = loop_tool_choice(gate)
        # Decision 13: stream mid-pass ONLY on a tool_choice="none" pass — the
        # API forbids tools there, so no draw can arrive mid-stream and the
        # Option-A draw-at-speak invariant is untouchable. Every "auto" pass
        # (draw pass, single-pass replies, refresh follow-ups) stays buffered
        # and reaches the ONE turn generation at the sync point below.
        streamed = tool_choice == "none" and await turn_voice.ensure_open()

        async for event in self._reasoner.run(user_input, screenshot, history, tool_choice=tool_choice):
            if isinstance(event, TextDelta):
                result.spoken_text += event.text
                message_text += event.text
                if streamed:
                    await turn_voice.push_stream(event.text)  # inline-await: no background consumer
            elif isinstance(event, ToolCall):
                if event.name in DRAW_TOOLS:
                    result.tool_calls.append(event)
                    # Circuit breaker: buffer only the FIRST draw (either tool); scaled in next_draw.
                    pending_draw = next_draw(gate, pending_draw, event, result.scale_x, result.scale_y)
                elif event.name == REFRESH_TOOL:
                    result.tool_calls.append(event)
                    refresh_call = event
                elif event.name == READ_FILE_TOOL:
                    # Phase 4: a perception tool like refresh — never gates the
                    # draw. First read of the pass wins; a repeat is answered by
                    # the pairing's already-read directive (turn.py, by name).
                    result.tool_calls.append(event)
                    if read_call is None:
                        read_call = event
                elif self._sandbox is not None and event.name == RUN_CODE_TOOL:
                    # T5: an EXECUTION tool, serviced after the sync point like a
                    # read — it NEVER gates the draw. First run of the pass wins.
                    result.tool_calls.append(event)
                    if run_call is None:
                        run_call = event
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
            return None, None, None, None

        result.input_tokens += turn_complete.input_tokens
        result.output_tokens += turn_complete.output_tokens
        result.cost_usd = round(result.cost_usd + turn_complete.cost_usd, 6)
        result.stop_reason = turn_complete.stop_reason
        # Cost recorded BEFORE speaking — the timeout must never cost us accounting.
        self._budget.record_turn(turn_complete)
        # Sync point: apply the ONE buffered draw, THEN speak. The auto-hide is
        # NOT armed here (v7.1 Fix F) — run_turn's finally arms it at SPEECH END,
        # so the rectangle survives the whole spoken explanation.
        # (A streamed pass is tool_choice="none": pending_draw is impossible.)
        if pending_draw is not None:
            await pending_draw.apply(self._overlay)
        if streamed:
            await turn_voice.end_stream()        # flush the tail into the generation
        else:
            # v7: an instant feed when the turn session is live — the ack no
            # longer blocks the loop, so the next pass's round-trip hides
            # BEHIND its playback (the measured 3.48s gap).
            await turn_voice.speak_or_feed(message_text)
        # Phase 4: service the pass's ONE read AFTER the audio is moving (local
        # I/O must never delay the spoken ack). Routed through the ToolRouter
        # (V2 Phase 0) at the SAME site with the same await discipline; the
        # router never raises — every failure is already an Arabic note.
        read_result: Optional[tuple[ToolCall, str]] = None
        if read_call is not None:
            outcome = await self._router.service(read_call.name, read_call.args)
            read_result = (read_call, outcome.result.text_ar)
            if outcome.taint and not result.taint:
                # §3.2: coarse turn-level taint — recorded here, enforced by
                # the high-impact gates when those tools exist (Phase 2).
                result.taint = True
                logger.info("[orchestrator] turn tainted by %s", outcome.provenance)
        # T5: service run_code AFTER the sync point too — bounded ≤3/turn by the
        # SandboxGate inside the servicer; the draw gate is never touched.
        run_result: Optional[tuple[ToolCall, str]] = None
        if run_call is not None and self._sandbox is not None:
            run_result = (run_call, await self._sandbox.run(run_call.args))
        # DEC-20/36: the badge, drawn by the KERNEL from the broker's own record.
        # HERE, at the very end of the pass: after the Option-A sync point and
        # after servicing, so it can neither reorder draw→speak nor delay the
        # audio. It is METADATA, not speech — its own bottom-left anchor, so the
        # caption's 2×60 budget is untouched, and it inherits the caption
        # lifecycle (clear_caption / the ghosting hide both wipe it), so no second
        # lifecycle exists. Redrawing each pass is idempotent, and an EMPTY record
        # draws NOTHING: "nothing fetched" must look like nothing, not a source.
        # DUCK-TYPED like every other optional overlay surface (the voice_out
        # caption seam, draw_dispatch's dim/shapes): a StubOverlay or an older
        # fake simply has no badge, and metadata must never crash a turn.
        badge = getattr(self._overlay, "show_domain_badge", None)
        if badge is not None:
            badge(self._router.fetched_domains())
        return turn_complete, refresh_call, read_result, run_result


__all__ = ["TurnPass", "REFRESH_TOOL", "STREAM_TTS_ENV"]
