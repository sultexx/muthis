# examples/hello_world/plugin.py
"""HelloWorldPlugin — the smallest honest Mut'his plugin.

What a community author writes: ONE ToolPlugin subclass. No MCP, no
process plumbing, no protocol — `muthis_sdk.mcp_runtime` turns this class
into a full stdio server, and the Mut'his broker mounts it read-only.
Stateless execute, Arabic user-facing text, returns — never raises."""

from __future__ import annotations

from typing import Any

from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin, ToolResult

SAY_HELLO_SCHEMA: dict[str, Any] = {
    "name": "say_hello",
    "description": (
        "Say a warm Arabic hello. Pass an optional 'name' to greet someone "
        "specific. Read-only: it only talks."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Who to greet (optional)."},
        },
    },
}


class HelloWorldPlugin(ToolPlugin):
    def descriptors(self) -> list[ToolDescriptor]:
        return [ToolDescriptor(name="say_hello", schema=SAY_HELLO_SCHEMA,
                               read_only=True)]

    async def execute(self, tool: str, args: dict[str, Any], ctx: PluginContext) -> ToolResult:
        who = str(args.get("name", "")).strip()
        greeting = f"أهلًا وسهلًا يا {who}!" if who else "أهلًا وسهلًا من إضافة الترحيب!"
        return ToolResult(text_ar=greeting)
