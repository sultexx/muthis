# src/muthis/main.py
"""
main.py — the production composition root and run-forever entry point.

This is the FULL real graph, wired through the same DI seams the smoke script
and the tests use: real mic, real STT (Scribe, Arabic-pinned), real TTS (the
TTS() cascade — ElevenLabs is parked, Gemini carries the voice), real DPI-aware
screen capture, the real cyan overlay, the real ClaudeAgent with the Saudi
persona injected, and the sovereign Budget. It sizes the persona's coordinate
space ONCE at startup, warms TLS once, registers the global F9 hotkey, and then
runs forever until Ctrl+C — hands-free.

Activation flow (true push-to-talk: hold to talk, release to send):
    F9 DOWN (keyboard thread) → controller.on_press(): start the mic stream
      DIRECTLY on that thread (no loop crossing — it touches no asyncio state),
      unless a turn is running or a hold is already open.
    F9 UP   (keyboard thread) → loop.call_soon_threadsafe(controller.on_activate)
      → on_activate (loop thread): guarded by is_processing
        → asyncio.create_task(one full real turn)
          → orchestrator.handle_activation(): mic.stop() (flush + return the
            held audio) → STT → capture → Claude → TTS → overlay

mic.stop() IS the orchestrator's mic seam, so the turn's FIRST step ends the
hold. The stream keeps recording across the release→turn gap, which also closes
the concurrency window (is_recording stays True until the turn stops it) with no
extra flag.

CONCURRENCY: ActivationController owns BOTH guards — is_processing (a turn is in
flight) and, via the injected is_recording predicate, an open hold. A press is
refused while either is set; a release while a turn runs is dropped. The
Orchestrator stays clean and untouched. is_processing is reset in a finally so a
turn that RAISES never freezes activation — without it, one failed turn would
wedge F9 until restart.

PRIVACY: nothing here logs transcripts, audio, or screenshots. The orchestrator
keeps the transcript away from the TTS; main only ever prints/loges English
status and مطحس's own Arabic banner.
"""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv

# Law 5.1: .env loaded once, BEFORE the muthis imports/instantiations that read
# keys (ANTHROPIC/ELEVENLABS/GEMINI) — otherwise an override in .env is ignored.
load_dotenv()

from .budget import Budget  # noqa: E402
from .cloud.claude_agent import ClaudeAgent, LOOK_SYSTEM_PROMPT  # noqa: E402
from .earcons import EarconPlayer  # noqa: E402
from .hotkey import DEFAULT_HOTKEY, HotkeyListener  # noqa: E402
from .mic import Mic  # noqa: E402
from .orchestrator import Orchestrator  # noqa: E402
from .persona import resolve_system_prompt  # noqa: E402
from .stt import STT  # noqa: E402
from .tts import TTS  # noqa: E402
from .vision.downscale import (  # noqa: E402
    DEFAULT_VISION_MAX_WIDTH, compute_scale_factors, downscale_to_max_width,
)
from .vision.screen_capture import ScreenCapture, primary_monitor_size  # noqa: E402
from .overlay import DEFAULT_POINTER_ANIM_MS, SidekickOverlay  # noqa: E402

logger = logging.getLogger("muthis.main")


# ─── Activation controller (owns the concurrency guard) ────────────────────────

class ActivationController:
    """The single activation gate. Runs on the asyncio loop (plus on_press on the
    keyboard thread): it starts recording on key-down and bridges one key-up to
    exactly one turn, refusing overlaps on BOTH counts. Constructed with the
    orchestrator's handle_activation seam plus the mic's start / is_recording
    seams, so it is fully testable with fakes — it never imports the mic, Claude,
    or the keyboard."""

    def __init__(
        self,
        handle_activation,
        *,
        start_recording=None,
        is_recording=None,
        reset_mic=None,
        reset_hotkey=None,
        earcon=None,
        set_state=None,
    ) -> None:
        self._handle_activation = handle_activation
        # Mic seams, injected so the controller stays mic-agnostic and testable.
        # The defaults keep it usable for turn-only tests (no recording wired).
        self._start_recording = start_recording or (lambda: None)
        self._is_recording = is_recording or (lambda: False)
        # Fire-and-forget UI sound seam (default no-op; a fake in tests).
        self._earcon = earcon or (lambda name: None)
        # Status-light seam (2-B): SYNC fire-and-forget, safe from the keyboard thread.
        self._set_state = set_state or (lambda state: None)
        # Per-turn reset seams (the single source of truth): mic to idle + hotkey
        # debounce cleared. Injected; default no-ops keep turn-only tests simple.
        self._reset_mic = reset_mic or (lambda: None)
        self._reset_hotkey = reset_hotkey or (lambda: None)
        self._is_processing = False
        # Kept so a clean shutdown (and tests) can await the in-flight turn.
        self._task = None

    @property
    def is_processing(self) -> bool:
        return self._is_processing

    def on_press(self) -> None:
        """Key-DOWN. Runs DIRECTLY on the keyboard thread (start_recording only
        opens the audio stream — no asyncio). Refused while a turn is in progress;
        otherwise it ALWAYS opens a fresh stream — self-healing a leaked one."""
        if self._is_processing:
            logger.info("[main] hotkey press ignored — a turn is in progress")
            return
        if self._is_recording():
            # is_recording True with NO turn running == a leaked stream (a prior
            # hold whose turn never ran, e.g. a lost key-up). Heal it and reopen
            # fresh — never refuse forever, or F9 wedges. (A turn-owned hold was
            # already refused above by is_processing.)
            logger.warning("[main] stale recording with no turn — resetting mic")
            self._reset_mic()
        self._start_recording()
        # Confirm the stream actually opened before chirping (a failed start
        # leaves is_recording False → no false "listening" cue). Fire-and-forget.
        if self._is_recording():
            self._earcon("listening")
            self._set_state("listening")  # neon cyan dot — the mic is open

    def on_activate(self) -> None:
        """Key-UP, scheduled via call_soon_threadsafe — therefore runs on the
        LOOP thread, where asyncio.create_task is legal. Drops the release if a
        turn is already running; otherwise claims the flag and launches ONE turn
        (whose first step, mic.stop(), ends the hold and returns the audio)."""
        if self._is_processing:
            logger.info("[main] hotkey release ignored — a turn is already in progress")
            return
        self._is_processing = True
        self._earcon("processing")   # mask the think/answer latency (fire-and-forget)
        self._set_state("thinking")  # amber dot — the pipeline is starting
        self._task = asyncio.create_task(self._run_one_turn())

    async def _run_one_turn(self) -> None:
        try:
            await self._handle_activation()
        except Exception:  # one bad turn must not kill a run-forever app
            # No transcript/screenshot here — only the English failure + stack.
            logger.exception("[main] turn failed unexpectedly")
        finally:
            # ESSENTIAL: EVERY path (success, raise, cancel, timeout) fully resets
            # per-turn state together — mic to idle, hotkey debounce cleared, and
            # is_processing released — or F9 wedges. One source of truth.
            self.reset_turn_state()
            # Make the lock state observable in muthis_app.log: this line fires on
            # EVERY turn end (success or failure), pairing with the "ignored" logs.
            logger.info("[main] turn ended — state reset; F9 ready")

    def reset_turn_state(self) -> None:
        """The SINGLE per-turn reset (Regression B): mic to idle (close stream,
        clear frames, _recording False), hotkey debounce cleared, is_processing
        released — all together. The injected mic/hotkey resets never raise, so a
        bad one can't block the others; is_processing is cleared last regardless."""
        self._reset_mic()
        self._reset_hotkey()
        self._set_state("idle")      # dot dark — the true, single turn end
        self._is_processing = False


# ─── Composition root ──────────────────────────────────────────────────────────

def _size_sent_image() -> tuple[int, int]:
    """Size the persona's coordinate space ONCE: probe the primary monitor's
    physical resolution (geometry only, no pixels) and derive the EXACT dims of
    the downscaled COPY every turn will send. Falls back to a 16:9 frame at the
    configured max width on a headless host."""
    physical = primary_monitor_size()
    if physical is not None:
        sent_width, sent_height, _scale_x, _scale_y = compute_scale_factors(
            physical[0], physical[1], DEFAULT_VISION_MAX_WIDTH,
        )
        return sent_width, sent_height
    return DEFAULT_VISION_MAX_WIDTH, round(DEFAULT_VISION_MAX_WIDTH * 9 / 16)


def _pointer_anim_ms() -> int:
    """Glide duration (ms) for the overlay's animated pointer, sourced from
    MUTHIS_POINTER_ANIM_MS at the composition root (mirrors MUTHIS_HOTKEY /
    MUTHIS_OVERLAY_TIMEOUT_S). Falls back to the overlay's default on an
    empty/non-integer value — config never crashes a run-forever app."""
    raw = os.getenv("MUTHIS_POINTER_ANIM_MS")
    if raw is None:
        return DEFAULT_POINTER_ANIM_MS
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "[main] MUTHIS_POINTER_ANIM_MS=%r is not an integer — using default %d",
            raw, DEFAULT_POINTER_ANIM_MS,
        )
        return DEFAULT_POINTER_ANIM_MS


def _build_orchestrator(
    agent: ClaudeAgent, budget: Budget, overlay: SidekickOverlay, mic_seam,
) -> Orchestrator:
    """Wire the FULL production graph through the existing DI seams. Tests inject
    fakes through these very same seams — production just passes the real ones.
    `mic_seam` is Mic().stop: the turn ENDS the hold and gets the audio as its
    first step (the hotkey already started the stream on key-down)."""
    return Orchestrator(
        reasoner=agent,
        budget=budget,
        mic=mic_seam,                            # REAL mic (Mic().stop — ends the hold)
        stt=STT().transcribe,                    # REAL Scribe STT (Arabic-pinned)
        tts=TTS().speak,                         # REAL TTS cascade (Gemini voice)
        screen_capture=ScreenCapture().capture,  # REAL primary-monitor PNG (DPI-aware)
        downscale=downscale_to_max_width,        # REAL payload COPY (≤ max width)
        overlay=overlay,                         # REAL overlay (hidden before each capture)
    )


async def run() -> None:
    """Build the real graph, register the hotkey, run forever until interrupted."""
    sent_width, sent_height = _size_sent_image()

    # Persona resolved with the sent-image dims and injected through ClaudeAgent's
    # existing system_prompt seam. resolve_system_prompt falls back loudly to
    # LOOK_SYSTEM_PROMPT if the builder is empty/raises.
    persona_prompt = resolve_system_prompt(LOOK_SYSTEM_PROMPT, sent_width, sent_height)
    agent = ClaudeAgent(system_prompt=persona_prompt)  # reads ANTHROPIC_API_KEY
    await agent.warm_up_tls()  # warm the shared TLS session before the first call

    budget = Budget()
    # No hard exit when the budget is exhausted: the orchestrator gates every
    # provider call and SPEAKS the refusal (Rule 10), and the limit resets on the
    # UTC date rollover — a forever app must survive that, not die at startup.
    if not budget.can_afford():
        logger.warning("[main] daily budget already exhausted — turns will be refused aloud")

    overlay = SidekickOverlay(anim_duration_ms=_pointer_anim_ms())  # cyan rect + gliding pointer (DPI-aware, click-through)
    mic = Mic()                  # REAL streaming mic (hold to talk, release to send)
    earcons = EarconPlayer()     # pleasant lifecycle cues (MUTHIS_EARCONS, default on)
    orchestrator = _build_orchestrator(agent, budget, overlay, mic.stop)

    controller = ActivationController(
        orchestrator.handle_activation,
        start_recording=mic.start,                # key-down opens the stream
        is_recording=lambda: mic.is_recording,    # refuse a second overlapping hold
        earcon=earcons.play,                       # listening (mic open) + processing (turn start)
        set_state=overlay.set_state,               # status light: listening / thinking / idle
        reset_mic=mic.reset,                       # per-turn: force the mic idle
        # listener is built just below; late-bound so reset_turn_state (called only
        # during a turn) reaches the real listener.reset without a forward ref.
        reset_hotkey=lambda: listener.reset(),     # per-turn: clear hold debounce
    )
    loop = asyncio.get_running_loop()
    hotkey = os.getenv("MUTHIS_HOTKEY", DEFAULT_HOTKEY)
    listener = HotkeyListener(
        loop=loop,
        on_press=controller.on_press,       # key-down (direct): start recording
        on_release=controller.on_activate,  # key-up (bridged): run the turn
        hotkey=hotkey,
    )
    listener.start()

    print(f"مطحس جاهز. اضغط مع الاستمرار على {hotkey.upper()} وتكلّم بالعربية، ثم اترك الزر ليرد. (Ctrl+C للخروج)")

    # Run forever. KeyboardInterrupt (Ctrl+C) propagates out of the wait and into
    # the finally below, which tears everything down in order.
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        listener.stop()       # stop the keyboard thread first (no new turns)
        overlay.close()       # stop the overlay's Tk thread
        await agent.aclose()  # release the shared httpx client (root owns shutdown)
        logger.info("[main] shutdown complete")


def main() -> None:
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic on the Windows console
    except Exception:  # pragma: no cover - console quirk, non-fatal
        pass
    # English pipeline logs only. Transcript logging stays gated behind
    # MUTHIS_DEBUG inside the components — never enabled here.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nمع السلامة.")


if __name__ == "__main__":
    main()
