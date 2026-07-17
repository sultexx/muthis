# src/muthis_plugins/file_read/plugin.py
"""FileReadPlugin — read_local_file as the fully ROUTED core plugin.

The archetype every community perception plugin follows: declare the schema,
then a STATELESS execute() over the kernel-granted capability seam. The
safety gates (secret names on raw+resolved path, binary sniff, size bounds)
live in the KERNEL's FileReader behind ctx.files.read — never here (roadmap
§3.3: the refusal-by-name is not delegated). The seam never raises; neither
do we."""

from __future__ import annotations

from typing import Any

from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin, ToolResult

from ..common import FILES_CAPABILITY_ABSENT_AR
from .schema import READ_LOCAL_FILE_SCHEMA


class FileReadPlugin(ToolPlugin):
    def descriptors(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="read_local_file",
                schema=READ_LOCAL_FILE_SCHEMA,
                read_only=True,
                kernel_serviced=False,
            )
        ]

    async def execute(self, tool: str, args: dict[str, Any], ctx: PluginContext) -> ToolResult:
        if ctx.files is None:
            # Kit/bare-context degradation. The production no-seam path is
            # ruled earlier, kernel-side, with the V1 note (single-sourced).
            return ToolResult(text_ar=FILES_CAPABILITY_ABSENT_AR, is_error=True)
        return ToolResult(text_ar=await ctx.files.read(args))
