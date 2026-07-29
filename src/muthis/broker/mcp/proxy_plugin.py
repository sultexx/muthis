# src/muthis/broker/mcp/proxy_plugin.py
"""
McpProxyPlugin — the ToolPlugin adapter the router mounts for ONE server.

The kernel's blindness rule (§8.1) is realized here: to the ToolRouter this
is an ordinary plugin with descriptors and an execute(); every MCP detail
(session, strikes, quarantine, hygiene) hides behind the HOST callable it
delegates to. Results come back is_error-or-not but NEVER as exceptions,
already policy-SANITIZED (text-only, capped). The router — not this proxy and
not the host — raises the taint flag from the taint=True mount and applies the
§3.2 untrusted-content wrapping on the way out (DEC-14): external server =
untrusted by definition (§8.5), and the framing is the kernel's to give.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin, ToolResult

from .policy import ExposedTool

# host-side: (tool_name, args) -> ToolResult (never raises)
HostCallFn = Callable[[str, dict[str, Any]], Awaitable[ToolResult]]


class McpProxyPlugin(ToolPlugin):
    def __init__(self, server_name: str, exposed: list[ExposedTool],
                 host_call: HostCallFn) -> None:
        self._server_name = server_name
        self._descriptors = [
            ToolDescriptor(
                name=tool.name,
                schema=tool.schema,
                read_only=True,          # only read-only tools pass the filter
                kernel_serviced=False,
            )
            for tool in exposed
        ]
        self._host_call = host_call

    def descriptors(self) -> list[ToolDescriptor]:
        return list(self._descriptors)

    async def execute(self, tool: str, args: dict[str, Any], ctx: PluginContext) -> ToolResult:
        return await self._host_call(tool, args)


__all__ = ["McpProxyPlugin"]
