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

from .schema import RUN_CODE_SCHEMA

# The pre-engine skeleton's user-facing note (T2 replaces this branch with the
# runner call). Honest: the tool is declared but the sandbox is not yet running.
SANDBOX_UNAVAILABLE_AR = "التنفيذ المعزول غير متاح في هذه الجلسة بعد."


class SandboxExecPlugin(ToolPlugin):
    """`run_code` over muthis-sdk. read_only w.r.t. the user's machine: execution
    is confined to a throwaway container (DEC-3 — execution is not control)."""

    def descriptors(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="run_code",
                schema=RUN_CODE_SCHEMA,
                read_only=True,
                kernel_serviced=False,
            )
        ]

    async def execute(self, tool: str, args: dict[str, Any], ctx: PluginContext) -> ToolResult:
        # T1 skeleton: the container engine lands in T2 (runner.py). Return a
        # polite Arabic note, never raise — the conformance golden and starved
        # runs exercise exactly this degradation contract.
        return ToolResult(text_ar=SANDBOX_UNAVAILABLE_AR, is_error=True)
