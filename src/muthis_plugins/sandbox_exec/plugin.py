# src/muthis_plugins/sandbox_exec/plugin.py
"""SandboxExecPlugin — the `run_code` tool contract (V2 Phase 2, M1, T1).

The plugin skeleton over muthis-sdk: it DECLARES the sandbox `run_code`
contract and stays stateless. The execution ENGINE (the Docker container
lifecycle + DEC-8 read-only staging) is T2's `runner.py`; until it is wired,
execute() degrades to a short Arabic note and NEVER raises (Law 11 / the
FileReader pattern). Imports muthis_sdk + stdlib only (layering law)."""

from __future__ import annotations

from typing import Any

from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin, ToolResult

from ..common import KERNEL_SERVICED_AR
from .schema import RUN_CODE_SCHEMA


class SandboxExecPlugin(ToolPlugin):
    """`run_code` over muthis-sdk — a DECLARATION plugin (like the LOOK tools):
    it contributes the model-visible schema, but execution is KERNEL-serviced
    (T5: the kernel's turn_pass dispatches it to the plugin-domain SandboxService
    after the sync point). read_only w.r.t. the user's machine — execution is
    confined to a throwaway container (DEC-3 — execution is not control)."""

    def descriptors(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="run_code",
                schema=RUN_CODE_SCHEMA,
                read_only=True,
                kernel_serviced=True,  # serviced by the kernel path, not the router
            )
        ]

    async def execute(self, tool: str, args: dict[str, Any], ctx: PluginContext) -> ToolResult:
        # Kernel-serviced: production never reaches here (turn_pass dispatches to
        # SandboxService). This is the last defensive wall — a polite Arabic
        # refusal, never a raise (what the conformance golden run observes).
        return ToolResult(text_ar=KERNEL_SERVICED_AR, is_error=True)
