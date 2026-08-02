# src/muthis/composition.py
"""
composition.py — the build helpers for the production graph.

Extracted from main.py under the ≤300-line law (DEC-19 / DEC-21 #2): a MOVE
ONLY of the component builders. main.py stays the composition ROOT and the
run-forever entry point; it imports these helpers and keeps the load-bearing
wiring SEQUENCE (Law 5.1 .env-first, sized coordinate space -> TLS warmup ->
hotkey -> run-forever, and the ordered shutdown).

No behavior change: the helpers are byte-identical to their main.py originals,
and the logger stays "muthis.main" so the log surface is unchanged (the
turn_pass.py precedent).
"""

from __future__ import annotations

import logging
import os
import pathlib
import subprocess

from .broker.broker import Broker
from .broker.grants import GrantsStore
from .broker.docs.service import DocumentService
from .broker.mcp.host import McpHost
from .broker.net import FetchedDomains, HardenedFetcher
from .broker.search import build_search_provider
# DEC-52's named extraction, EXECUTED (T4): the MOUNTS moved to
# composition_mounts.py when this file measured 320/300 with T4's mount. The
# re-export keeps every existing importer — main.py, the tests, the diag
# scripts — working unchanged (the turn.py precedent).
from .composition_mounts import mount_doc_rag, mount_web_research  # noqa: F401
from .cloud.claude_agent import ClaudeAgent
from .file_reader import FileReader, stage_file_gate
from .kernel.budget import Budget
from .kernel.frame_capture import FrameCapture
from .kernel.core_router import build_core_router
from .kernel.orchestrator import Orchestrator
from .kernel.session_taint import SessionTaint
from .kernel.tool_router import ToolRouter
from .trust.confirm_gate import ConfirmGate
from .kernel.turn import TurnResult
from .overlay import DEFAULT_POINTER_ANIM_MS, SidekickOverlay
from .stt import STT
from .tts import TTS
from .vision.downscale import (
    DEFAULT_VISION_MAX_WIDTH, compute_scale_factors, downscale_to_max_width,
)
from .vision.screen_capture import ScreenCapture, primary_monitor_size
from muthis_plugins.doc_rag.plugin import DocRagPlugin
from muthis_plugins.sandbox_exec.runner import SandboxRunner
from muthis_plugins.sandbox_exec.service import SandboxService
from muthis_plugins.web_research.plugin import WebResearchPlugin

# Kept on main's logger: the log surface is unchanged by the split (the
# turn_pass.py precedent — a mechanical extraction must not move log names).
logger = logging.getLogger("muthis.main")


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


class _BridgeAutoHide:
    """The broker's capture runs OUTSIDE any turn, so there is no pending
    auto-hide timer to cancel — a stale one firing later is harmless (hide
    is idempotent and every capture hides first anyway)."""

    def cancel(self) -> None:
        pass


def _build_broker_graph(
    budget: Budget, overlay: SidekickOverlay, reader: FileReader,
) -> tuple[ToolRouter, McpHost, HardenedFetcher, FetchedDomains]:
    """V2 Phase 1 (M1-7): the router + broker + MCP host composed at the
    root (roadmap part 2 §1). The bridge's screenshot rides the SAME
    hide→settle→capture chokepoint as every turn frame (§3.3); FileReader's
    gates guard the read seam for core plugin and bridge alike.

    V2 Phase 2 (T4, DEC-15): the session-sticky SessionTaint is built HERE — at
    the root, once per process — and injected into the router, the single
    chokepoint every tool result crosses. Built here rather than inside the
    router so its LIFETIME reads as what it is: the process's, not a per-turn
    object (contrast SandboxGate, rebuilt every turn). No orchestrator touch.

    V2 Phase 2 (T5, DEC-16): the ConfirmGate is built the SAME way and for the
    same reason — a pending approval must outlive the turn that asked for it,
    since it is answered in the NEXT one.

    V2 Phase 2 (T6, DEC-24): the HardenedFetcher — the EMBODIMENT of net.fetch
    (DEC-17) — is built here too, and injected into the Broker so a granted
    plugin's context carries the seam. ONE per process, deliberately: the
    per-domain rate limit and the RAM-only session LRU only mean anything when
    the whole session shares a single instance, and it owns a long-lived httpx
    client whose shutdown the root owns (the `agent.aclose()` precedent), which
    is why it is RETURNED rather than hidden inside the broker.

    V2 Phase 2 (T6b, DEC-37): the TURN-BOUNDARY hooks are registered here. The
    router carries them blindly; this root is the only place that knows both the
    plugin side (`FetchGate`, DEC-22) and the broker side (`FetchedDomains`,
    DEC-36), so each consumer resets through its own owner. The build order below
    is load-bearing for that reason alone — the collector, the fetcher, the broker
    and the web plugin all exist before the router that carries their resets."""
    bridge_frames = FrameCapture(
        overlay=overlay, screen_capture=ScreenCapture().capture,
        downscale=downscale_to_max_width, auto_hide=_BridgeAutoHide())

    async def bridge_capture():
        return await bridge_frames.capture(TurnResult())

    # DEC-20: the badge's provenance collector — built HERE and injected, the
    # SessionTaint shape, so its TURN lifetime is explicit rather than buried in
    # the fetcher beside process-scoped state (the LRU, the rate limiter). The
    # FETCHER records into it first-hand; no plugin ever touches the fact.
    fetched_domains = FetchedDomains()
    fetcher = HardenedFetcher(domains=fetched_domains)
    broker = Broker(grants=GrantsStore(), read_file=reader.read,
                    capture=bridge_capture, net_fetch=fetcher.fetch_readable,
                    fetched_domains=fetched_domains)
    # DEC-37: the web plugin is built HERE, one commit BEFORE it is mounted, and
    # the ordering is the point — its per-turn fetch cap must be LIVE before the
    # tool it bounds is reachable by the model, never the other way round.
    # DEC-18/27: the provider is INJECTED already-built — the plugin holds no key,
    # no client and no endpoint. A machine with nothing configured gets
    # NoSearchProvider, so the TOOL still exists everywhere and a missing key is
    # an ordinary Arabic note rather than a structural difference in the catalog.
    search_provider = build_search_provider()
    web_plugin = WebResearchPlugin(provider=search_provider)
    # THE TURN-BOUNDARY REGISTRATION (DEC-37). This is the ONE place that
    # legitimately knows both sides of the plugin boundary, so each consumer
    # resets through its OWN owner: the plugin owns its cap (DEC-22), the broker
    # owns the provenance collector's lifetime (DEC-36). The router only CARRIES
    # these callables and never learns what they do — so no kernel module names
    # a plugin or a broker record, and adding a third consumer later touches
    # this line alone.
    router = build_core_router(read_file=reader.read,
                               plugin_ledger=budget.record_plugin_call,
                               session_taint=SessionTaint(),
                               confirm_gate=ConfirmGate(),
                               turn_hooks=(web_plugin.new_turn, broker.new_turn),
                               # DEC-20: the badge's READER — the kernel draws
                               # from the collector the FETCHER writes, so the
                               # fact never passes through plugin code.
                               fetched_domains=fetched_domains.domains)
    # Three-strikes announcements log for now; the SPOKEN delivery joins the
    # voice line with Phase 2's first high-impact plugin (audio path sacred).
    host = McpHost(broker=broker,
                   announce=lambda note_ar: logger.warning(
                       "[main] mcp server disabled: %s", note_ar))
    return router, host, fetcher, web_plugin, search_provider


def _doc_model_dir() -> pathlib.Path:
    """Where the pinned encoder artifacts live. `MUTHIS_DOC_MODEL_DIR` overrides.

    Outside the repo by default: a 118 MB model is not source, and a cache under
    the user's home survives a reinstall — the sandbox image's pull-cache shape."""
    raw = os.getenv("MUTHIS_DOC_MODEL_DIR")
    if raw and raw.strip():
        return pathlib.Path(raw.strip()).expanduser()
    return pathlib.Path.home() / ".muthis" / "models" / "e5-small-int8"


def _build_doc_rag() -> tuple[DocumentService, DocRagPlugin]:
    """V2 Phase 2 (T4): the document servicer, and the plugin that is handed it.

    The SERVICE is built here and INJECTED already-built (DEC-27's shape, as the
    search provider is injected into `web_research`): it opens the user's private
    files and holds WHOLE documents, so it lives in the broker and the plugin can
    reach it only through two verbs.

    NO PER-TURN GATE, and that is measured rather than forgotten: `TurnPass`
    services ONE router call per pass and the agentic loop caps at
    MAX_AGENTIC_ITERATIONS, so document opens are already bounded at four per turn
    BY CONSTRUCTION. A second cap would bound nothing that is not already bounded
    — contrast the DEC-22 fetch cap, where one pass could otherwise chain
    redirects without limit.

    The ROOT keeps the service because it owns the teardown: the index is
    session-scoped and dies with the session (privacy law), so `clear()` belongs
    beside `agent.aclose()` in main's ordered shutdown, never inside a plugin."""
    # The TASK-1 doc_id observer is GONE with DEC-71, exactly as its own comment
    # promised: there is no round-trip left to observe. The model no longer
    # carries a document identifier, so the mismatch it instrumented is
    # unreachable rather than merely unlikely.
    service = DocumentService(model_dir=_doc_model_dir())
    return service, DocRagPlugin(service=service)


def _build_sandbox() -> SandboxService:
    """V2 Phase 2 (T5): the run_code servicer — a SandboxRunner (Docker CLI,
    DEC-9 stdin staging) behind the FileReader gates, wrapped in the ≤3/turn
    SandboxGate. The section 2.7 fallback engine is NOT built: a docker info
    failure surfaces the runner's honest Arabic note, never a silent degrade."""
    return SandboxService(runner=SandboxRunner(stage_gate=stage_file_gate))


def _log_docker_fallback_decision() -> None:
    """Honest startup logging (never silently degrade): whether Docker is up,
    and that the section 2.7 Job-Objects fallback is DEFERRED — at runtime a
    docker info failure surfaces the runner's Arabic note, not a silent swap."""
    try:
        ok = subprocess.run(["docker", "info"], capture_output=True,
                            timeout=10).returncode == 0
    except Exception:  # noqa: BLE001 — the probe must never crash startup
        ok = False
    if ok:
        logger.info("[main] docker available — sandbox__run_code is live")
    else:
        logger.warning("[main] docker unavailable — run_code refuses aloud; the "
                       "section 2.7 fallback engine is deferred (not built)")


def _build_orchestrator(
    agent: ClaudeAgent, budget: Budget, overlay: SidekickOverlay, mic_seam,
    router: ToolRouter, sandbox: SandboxService,
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
        router=router,                           # V2 Phase 1: the ONE injected seam
        sandbox=sandbox,                         # V2 Phase 2 (T5): the run_code servicer
    )
