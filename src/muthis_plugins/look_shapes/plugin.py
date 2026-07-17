# src/muthis_plugins/look_shapes/plugin.py
"""LookShapesPlugin — draw_shapes' declaration as an SDK plugin.

kernel_serviced: the drawing EXECUTION (shapes parsing/scaling, whiteboard
dim, the unified HighlightGate) stays on the V1 kernel draw circuit letter
for letter — conflict ruling C-1. This plugin contributes the schema."""

from __future__ import annotations

from typing import Any

from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin, ToolResult

from ..common import KERNEL_SERVICED_AR
from .schema import DRAW_SHAPES_SCHEMA


class LookShapesPlugin(ToolPlugin):
    def descriptors(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="draw_shapes",
                schema=DRAW_SHAPES_SCHEMA,
                read_only=True,
                kernel_serviced=True,
            )
        ]

    async def execute(self, tool: str, args: dict[str, Any], ctx: PluginContext) -> ToolResult:
        return ToolResult(text_ar=KERNEL_SERVICED_AR, is_error=True)
