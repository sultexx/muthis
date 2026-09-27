"""
graph.py — the REAL production graph, assembled as `composition.py` and
`main.run()` assemble it, with only the edges outside the machine replaced.

Built fresh for EVERY scenario run, so no state crosses runs: a new router,
session taint, confirm gate, fetch collector, document index, sandbox gate and
session mode each time — exactly one app session per run. The mount ORDER is
production's (sandbox → web → docs → navigator → verify), and the catalogue
the model is handed is the router's own descriptors, which the preflight
hashes against the configuration's declared value.

WHAT DIFFERS FROM THE APP, AND WHY NONE OF IT REACHES THE MODEL'S INPUT:
  * the turn enters at `Orchestrator.run_turn(text)` — `handle_activation` is
    mic → STT → this same call, so a typed utterance stands in for a transcript;
  * the voice, overlay and screen are recorders and a fixed frame (`record.py`,
    `canned.py`); `stream_tts=False`, which selects the batch voice path and
    changes nothing the reasoner receives (`turn_pass.py`: TurnVoice only);
  * web search and the web itself are canned (`canned.py`);
  * no MCP host: its servers are mounted into the router AFTER the catalogue is
    taken and are "NOT offered to the model" (`main.py`), so nothing it adds is
    reachable by a model call;
  * the budget ledger is the harness's own file, never the app's;
  * for scenario S8 the sandbox runner's `exec_fn` raises FileNotFoundError, the
    fault the runner maps to DOCKER_UNAVAILABLE_AR (`runner.py`).
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any

from muthis.broker.broker import Broker
from muthis.broker.docs.service import DocumentService
from muthis.broker.grants import GrantsStore
from muthis.broker.net import FetchedDomains, HardenedFetcher
from muthis.composition_mounts import (mount_doc_rag, mount_navigator,
                                       mount_navigator_verify, mount_web_research)
from muthis.file_reader import FileReader, stage_file_gate
from muthis.kernel.budget import Budget
from muthis.kernel.core_router import build_core_router
from muthis.kernel.mode_surfaces import mode_indicator_text
from muthis.kernel.orchestrator import Orchestrator
from muthis.kernel.session_mode import SessionMode
from muthis.kernel.session_taint import SessionTaint
from muthis.trust.confirm_gate import ConfirmGate
from muthis.vision.downscale import downscale_to_max_width
from muthis_plugins.doc_rag.plugin import DocRagPlugin
from muthis_plugins.navigator import NavigatorPlugin
from muthis_plugins.navigator_verify import NavigatorVerifyPlugin
from muthis_plugins.sandbox_exec import SandboxExecPlugin
from muthis_plugins.sandbox_exec.runner import SandboxRunner
from muthis_plugins.sandbox_exec.service import SandboxService
from muthis_plugins.web_research.plugin import WebResearchPlugin

from harness import canned

DOC_MODEL_DIR = pathlib.Path.home() / ".muthis" / "models" / "e5-small-int8"


async def docker_missing(*args: Any, **kwargs: Any) -> Any:
    """The `exec_fn` fault for S8: the docker binary cannot be started."""
    raise FileNotFoundError("docker (harness fault: scenario S8)")


@dataclass
class Graph:
    router: Any
    sandbox: SandboxService
    doc_service: DocumentService
    fetcher: HardenedFetcher
    search: canned.CannedSearchProvider
    budget: Budget
    catalogue: list
    orchestrator: Any = None

    async def aclose(self) -> None:
        self.doc_service.clear()
        await self.fetcher.aclose()
        await self.search.aclose()


def build_router(*, runner: str, budget: Budget) -> Graph:
    """Everything below the orchestrator, in production's build order."""
    reader = FileReader()
    fetched = FetchedDomains()
    fetcher = HardenedFetcher(client_factory=canned.client_factory,
                              resolver=canned.resolver, domains=fetched)
    # capture=None: only an MCP server is ever granted perceive.screen
    # (`broker.py`), and there is no MCP host here.
    broker = Broker(grants=GrantsStore(), read_file=reader.read, capture=None,
                    net_fetch=fetcher.fetch_readable, fetched_domains=fetched)
    search = canned.CannedSearchProvider()
    web_plugin = WebResearchPlugin(provider=search)
    router = build_core_router(read_file=reader.read,
                               plugin_ledger=budget.record_plugin_call,
                               session_taint=SessionTaint(),
                               confirm_gate=ConfirmGate(),
                               turn_hooks=(web_plugin.new_turn, broker.new_turn),
                               fetched_domains=fetched.domains)
    if runner == "docker":
        sandbox_runner = SandboxRunner(stage_gate=stage_file_gate)
    elif runner == "docker_missing":
        sandbox_runner = SandboxRunner(stage_gate=stage_file_gate, exec_fn=docker_missing)
    else:
        raise ValueError(f"unknown runner {runner!r}")
    sandbox = SandboxService(runner=sandbox_runner)
    router.mount(SandboxExecPlugin(), namespace="sandbox", provenance="sandbox_exec")
    mount_web_research(router, web_plugin, fetcher)
    doc_service = DocumentService(model_dir=DOC_MODEL_DIR)
    mount_doc_rag(router, DocRagPlugin(service=doc_service))
    mount_navigator(router, NavigatorPlugin())
    mount_navigator_verify(router, NavigatorVerifyPlugin())
    catalogue = [descriptor.schema for descriptor in router.descriptors()]
    return Graph(router=router, sandbox=sandbox, doc_service=doc_service, fetcher=fetcher,
                 search=search, budget=budget, catalogue=catalogue)


def build_orchestrator(graph: Graph, *, reasoner: Any, overlay: Any, voice: Any,
                       png: bytes) -> Any:
    """The orchestrator over `graph`, wired through production's seams."""

    def redraw(mode: Any) -> None:            # the DEC-65 indicator seam's shape
        overlay.show_mode_indicator(mode_indicator_text(mode))

    orchestrator = Orchestrator(
        reasoner=reasoner, budget=graph.budget, tts=voice.speak,
        screen_capture=canned.fixed_capture(png), downscale=downscale_to_max_width,
        overlay=overlay, router=graph.router, sandbox=graph.sandbox,
        session_mode=SessionMode(on_change=redraw), stream_tts=False)
    orchestrator.add_interrupt_hook(graph.sandbox.kill_active)
    graph.orchestrator = orchestrator
    return orchestrator


def harness_budget(home: pathlib.Path, daily_limit_usd: float) -> Budget:
    """A ledger of the harness's own, beside its records — never the app's."""
    home.mkdir(parents=True, exist_ok=True)
    return Budget(daily_limit_usd=daily_limit_usd, budget_file=home / "harness_budget.json")


__all__ = ["DOC_MODEL_DIR", "Graph", "build_orchestrator", "build_router",
           "docker_missing", "harness_budget"]
