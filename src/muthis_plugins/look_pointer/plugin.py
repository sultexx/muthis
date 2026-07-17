# src/muthis_plugins/look_pointer/plugin.py
"""LookPointerPlugin — highlight_target's declaration as an SDK plugin.

kernel_serviced: the pointing EXECUTION stays on the V1 kernel draw circuit
(draw_dispatch + HighlightGate + the tool_choice="none" terminator) letter
for letter — conflict ruling C-1. This plugin contributes the schema."""

from __future__ import annotations

from typing import Any

from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin, ToolResult

from ..common import KERNEL_SERVICED_AR
from .schema import HIGHLIGHT_TARGET_SCHEMA


class LookPointerPlugin(ToolPlugin):
    def descriptors(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="highlight_target",
                schema=HIGHLIGHT_TARGET_SCHEMA,
                read_only=True,
                kernel_serviced=True,
            )
        ]

    async def execute(self, tool: str, args: dict[str, Any], ctx: PluginContext) -> ToolResult:
        return ToolResult(text_ar=KERNEL_SERVICED_AR, is_error=True)
