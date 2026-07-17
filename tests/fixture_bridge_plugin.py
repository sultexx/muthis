# tests/fixture_bridge_plugin.py
"""A capability-USING out-of-proc fixture plugin (NOT a pytest module): its
tool reads a file THROUGH ctx.files — which the SDK runtime backs with a
muthis/read_file bridge request to the kernel. The full-circle subject of
tests/test_mcp_bridge.py. Degrades politely when the capability is absent."""

from __future__ import annotations

from typing import Any

from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin, ToolResult

SCHEMA: dict[str, Any] = {
    "name": "read_via_kernel",
    "description": "Read a file through the kernel's gated seam (read-only).",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
}


class BridgePlugin(ToolPlugin):
    def descriptors(self) -> list[ToolDescriptor]:
        return [ToolDescriptor(name="read_via_kernel", schema=SCHEMA, read_only=True)]

    async def execute(self, tool: str, args: dict[str, Any], ctx: PluginContext) -> ToolResult:
        if ctx.files is None:
            return ToolResult(text_ar="قراءة الملفات غير متاحة لهذه الإضافة.",
                              is_error=True)
        return ToolResult(text_ar=await ctx.files.read({"path": args.get("path", "")}))
