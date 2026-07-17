# sdk/muthis_sdk/plugin.py
"""
The ToolPlugin base class — the one thing a plugin author implements.

Contract (V2_ROADMAP.md §3.2, extending V1 Law 11 to plugins): execution is
STATELESS. No loops, no locks, no retries, no conversation memory inside the
plugin — the kernel alone owns lifecycles, history, budget gating and the
agentic loop. A plugin that needs a kernel capability (file read, screen,
overlay) asks through the injected PluginContext; it never grabs an OS handle
of its own (§3.3 — the broker principle).

Failure discipline: every failure is RETURNED as a short Arabic note in a
ToolResult (is_error=True), never raised — the generalized FileReader pattern.
The conformance kit treats a raising execute() as an automatic FAIL.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .context import PluginContext
from .types import ToolDescriptor, ToolResult


class ToolPlugin(ABC):
    """Base class for every Mut'his plugin (native core and, later, MCP)."""

    @abstractmethod
    def descriptors(self) -> list[ToolDescriptor]:
        """The tools this plugin offers the model.

        Must be deterministic and side-effect free: the kernel may call it
        at mount time and again when assembling the per-turn schema list.
        """

    @abstractmethod
    async def execute(
        self, tool: str, args: dict[str, Any], ctx: PluginContext
    ) -> ToolResult:
        """Service ONE tool call. Stateless; must never raise.

        `tool` is the descriptor name being invoked (one plugin may declare
        several). `args` is the model-provided input, already JSON-decoded.
        Kernel-serviced descriptors (draw tools, screen refresh) are
        intercepted by the kernel BEFORE dispatch ever reaches here; their
        execute() exists only to satisfy the contract and must return a
        polite Arabic refusal if ever called directly.
        """
