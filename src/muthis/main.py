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

CONCURRENCY: ActivationController (extracted to activation.py — this file sat
AT 299/300; re-exported here) owns BOTH guards — is_processing and the open
hold. A release while a turn runs is dropped; a PRESS while a turn is SPEAKING
is the v7 Phase 3 BARGE-IN: the turn is silenced + cancelled and the fresh
recording captures the user's interruption (flag MUTHIS_BARGE_IN, default ON).
is_processing is reset in a finally so a turn that RAISES never freezes
activation.

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

from .activation import ActivationController  # noqa: E402,F401 — re-export: old imports keep working
from .broker.docs.zones import assert_zone_invariant  # noqa: E402
from .kernel.budget import Budget  # noqa: E402
from .cloud.claude_agent import ClaudeAgent, LOOK_SYSTEM_PROMPT  # noqa: E402
from .composition import (  # noqa: E402 — build helpers extracted (≤300 law, DEC-21 #2)
    _build_broker_graph, _build_doc_rag, _build_orchestrator, _build_sandbox,
    _log_docker_fallback_decision, _pointer_anim_ms, _size_sent_image,
    mount_doc_rag, mount_navigator, mount_web_research,
)
from .earcons import EarconPlayer  # noqa: E402
from .file_reader import FileReader  # noqa: E402
from muthis_plugins.navigator import NavigatorPlugin  # noqa: E402
from muthis_plugins.sandbox_exec import SandboxExecPlugin  # noqa: E402
from .hotkey import DEFAULT_HOTKEY, HotkeyListener  # noqa: E402
from .logging_policy import configure_logging  # noqa: E402
from .mic import Mic  # noqa: E402
from .persona import resolve_system_prompt  # noqa: E402
from .overlay import SidekickOverlay  # noqa: E402

logger = logging.getLogger("muthis.main")


# ─── Composition root ──────────────────────────────────────────────────────────

async def run() -> None:
    """Build the real graph, register the hotkey, run forever until interrupted."""
    sent_width, sent_height = _size_sent_image()

    budget = Budget()
    # No hard exit when the budget is exhausted: the orchestrator gates every
    # provider call and SPEAKS the refusal (Rule 10), and the limit resets on the
    # UTC date rollover — a forever app must survive that, not die at startup.
    if not budget.can_afford():
        logger.warning("[main] daily budget already exhausted — turns will be refused aloud")

    overlay = SidekickOverlay(anim_duration_ms=_pointer_anim_ms())  # cyan rect + gliding pointer (DPI-aware, click-through)
    mic = Mic()                  # REAL streaming mic (hold to talk, release to send)
    earcons = EarconPlayer()     # pleasant lifecycle cues (MUTHIS_EARCONS, default on)
    reader = FileReader()
    # `fetcher` is the ONE net.fetch embodiment (DEC-17/DEC-24) — the root owns
    # its shutdown because it owns a long-lived httpx client (see the finally).
    # `search` is the DEC-18 provider: the root owns its shutdown too, because it
    # holds the THIRD long-lived httpx client (key-bearing, separate by law from
    # the zero-credential fetcher). `web_plugin` is built there so its per-turn
    # cap is already LIVE; it is MOUNTED below, after the sandbox.
    router, mcp_host, fetcher, web_plugin, search = _build_broker_graph(
        budget, overlay, reader)
    # V2 Phase 2 (T5): mount run_code (namespaced) into the catalog + build its
    # servicer. The v2 model catalog is the router's descriptors — the FIRST
    # model-visible change since Phase 1 (byte-pinned to look_tools_v2.json).
    sandbox = _build_sandbox()
    router.mount(SandboxExecPlugin(), namespace="sandbox", provenance="sandbox_exec")
    # V2 Phase 2 (T6b): web__search + web__fetch join the catalog — the THIRD
    # model-visible change in the project's history (byte-pinned to
    # look_tools_v3.json). Mounted AFTER the sandbox so v3 is v2 with two tools
    # APPENDED, and every boundary is already on their path: the servicing branch
    # (DEC-39), the wrap and taint raise, the confirm gate, the per-turn cap and
    # the provenance badge all landed BEFORE the model could call them.
    mount_web_research(router, web_plugin, fetcher)
    # V2 Phase 2 (T4): docs__open + docs__query join the catalog — the FOURTH
    # model-visible change in the project's history (byte-pinned to
    # look_tools_v4.json). Mounted AFTER the web tools so v4 is v3 with two tools
    # APPENDED, and — DEC-39's REQUIREMENT, not a preference — the SERVICING branch
    # in tool_result_pairing.py landed BEFORE this line, because a mounted-but-
    # unserviced tool bypasses the wrap, the taint raise and the confirm gate, then
    # takes the pointer ack and hard-terminates the turn.
    doc_service, doc_plugin = _build_doc_rag()
    mount_doc_rag(router, doc_plugin)
    # Phase 3 (T4): navigator__plan + navigator__step join the catalog — the
    # FIFTH model-visible change (v6), and the first that EXTENDS again after
    # v5's revision. Mounted AFTER the doc tools so the diff stays additive,
    # and AFTER the servicing branch + the answer-by-name arm landed, which
    # is DEC-39's REQUIREMENT: a mounted-but-unserviced tool takes the
    # POINTER ack and hard-terminates the turn.
    mount_navigator(router, NavigatorPlugin())
    model_tools = [descriptor.schema for descriptor in router.descriptors()]
    _log_docker_fallback_decision()

    # Persona resolved with the sent-image dims and injected through ClaudeAgent's
    # existing system_prompt seam. resolve_system_prompt falls back loudly to
    # LOOK_SYSTEM_PROMPT if the builder is empty/raises.
    persona_prompt = resolve_system_prompt(LOOK_SYSTEM_PROMPT, sent_width, sent_height)
    agent = ClaudeAgent(system_prompt=persona_prompt, tools=model_tools)  # reads ANTHROPIC_API_KEY
    await agent.warm_up_tls()  # warm the shared TLS session before the first call

    orchestrator = _build_orchestrator(agent, budget, overlay, mic.stop, router, sandbox)
    orchestrator.add_interrupt_hook(sandbox.kill_active)  # F9 kills the live container (T4 seam)

    loop = asyncio.get_running_loop()
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
        # Barge-in (v7 Phase 3): a press during playback silences the turn.
        interrupt_turn=orchestrator.interrupt_turn,
        schedule_on_loop=loop.call_soon_threadsafe,
    )
    hotkey = os.getenv("MUTHIS_HOTKEY", DEFAULT_HOTKEY)
    listener = HotkeyListener(
        loop=loop,
        on_press=controller.on_press,       # key-down (direct): start recording
        on_release=controller.on_activate,  # key-up (bridged): run the turn
        hotkey=hotkey,
    )
    listener.start()

    # V2 Phase 1: mount trusted plugins.d servers (read-only tools only) into
    # the router. NOT offered to the model in this phase — the model-visible
    # catalog stays the byte-pinned V1 four; router-level mounting is the
    # Phase-1 gate, the model merge is Phase 2's designed change.
    mounted = await mcp_host.mount_all(router)
    if mounted:
        logger.info("[main] mcp servers mounted: %s", ", ".join(mounted))

    print(f"مطحس جاهز. اضغط مع الاستمرار على {hotkey.upper()} وتكلّم بالعربية، ثم اترك الزر ليرد. (Ctrl+C للخروج)")

    # Run forever. KeyboardInterrupt (Ctrl+C) propagates out of the wait and into
    # the finally below, which tears everything down in order.
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        listener.stop()       # stop the keyboard thread first (no new turns)
        await mcp_host.shutdown()  # terminate MCP children before the UI goes
        overlay.close()       # stop the overlay's Tk thread
        doc_service.clear()   # drop every open document: session-scoped by law
        await fetcher.aclose()  # release the net.fetch client (DEC-17: a SEPARATE pool)
        await search.aclose()   # release the key-bearing search client (DEC-18)
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
    # This ALSO applies the privacy policy that holds the third-party HTTP
    # loggers at WARNING: httpx logs the FULL request URL at INFO on every
    # request, which would put a fetched page's query string — and a GET search
    # provider's QUERY, i.e. what the user asked while looking at their screen —
    # into this app's log, defeating DEC-17, DEC-20 and the first privacy law.
    # See logging_policy.py; it is a deliberate control, not boilerplate.
    configure_logging()
    # THE ZONE INVARIANT (DEC-49 ruling 4), checked HERE — after logging is
    # configured so the failure is legible, and before the event loop opens so a
    # broken configuration stops the process instead of surfacing later as one
    # strange document. The derived ingestion maximum MUST EXCEED
    # MUTHIS_DOC_INJECT_LIMIT or zone 2 is EMPTY: every document large enough to
    # need an index is already too large to build one, and the three-zone design
    # is incoherent rather than degraded. P0 measured that inversion happening
    # under the rejected encoder, so it is a real configuration, not a
    # hypothetical. It RAISES; it does not warn.
    assert_zone_invariant()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nمع السلامة.")


if __name__ == "__main__":
    main()
