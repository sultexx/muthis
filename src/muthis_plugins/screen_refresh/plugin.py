# src/muthis_plugins/screen_refresh/plugin.py
"""ScreenRefreshPlugin — request_screen_refresh's declaration as an SDK plugin.

kernel_serviced: the refresh EXECUTION is kernel state end-to-end — the
hide→settle→capture chokepoint, the physical↔sent scale bookkeeping, the
image-bearing tool_result, and the Bug-3 strip at turn end (conflict ruling
C-1). This plugin contributes the schema; Phase 1's broker may expose the
capture seam as perceive.screen for community plugins."""

from __future__ import annotations

from typing import Any

from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin, ToolResult

from ..common import KERNEL_SERVICED_AR
from .schema import SCREEN_REFRESH_SCHEMA


class ScreenRefreshPlugin(ToolPlugin):
    def descriptors(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="request_screen_refresh",
                schema=SCREEN_REFRESH_SCHEMA,
                read_only=True,
                kernel_serviced=True,
            )
        ]

    async def execute(self, tool: str, args: dict[str, Any], ctx: PluginContext) -> ToolResult:
        return ToolResult(text_ar=KERNEL_SERVICED_AR, is_error=True)
