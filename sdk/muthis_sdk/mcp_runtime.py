# sdk/muthis_sdk/mcp_runtime.py
"""
The out-of-process plugin runtime (V2 Phase 1 M1-6, roadmap §8.4):

    python -m muthis_sdk.mcp_runtime <module:Class>

runs any ToolPlugin as an MCP stdio SERVER — the community author writes the
same simple class the in-proc core plugins use; every MCP detail lives here.

muthis-profile/1: when the CLIENT (the Mut'his broker) offers the
experimental capability at initialize, the plugin's PluginContext seams are
backed by server→client requests the broker services INSIDE the kernel with
its own gates: ctx.files.read → muthis/read_file, ctx.screen.capture →
muthis/capture (annotate deferred — decision Q-1.2). A client that never
offered the profile (any generic MCP client) yields a context with those
capabilities ABSENT, and a contract-conformant plugin degrades politely.

Deliberately SYNCHRONOUS stdio (the fake-server pattern): Windows asyncio
stdin pipes are a known swamp, and a child process serving one kernel needs
no concurrency — requests are handled in arrival order; client requests
that interleave a pending bridge wait are backlogged and served right
after. Each execute() runs under its own asyncio.run (the plugin API is
async; the transport is not). Zero third-party deps, stdlib only.
"""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
import sys
from collections import deque
from typing import Any, Optional

from .context import FilesCapability, PluginContext, ScreenCapability
from .mcp.messages import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    MUTHIS_PROFILE,
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
)
from .plugin import ToolPlugin
from .types import ToolResult

_RUNTIME_VERSION = "1.0"


class _Stdio:
    """Blocking line transport over the real stdio (UTF-8 both ways).

    The runtime OWNS its wire encoding: Windows pipes default to the locale
    codepage (cp1256 on Arabic systems — the live bug this guards), so both
    streams are reconfigured to strict UTF-8 at construction, never left to
    the environment."""

    def __init__(self) -> None:
        for stream in (sys.stdin, sys.stdout):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                reconfigure(encoding="utf-8")

    def read(self) -> Optional[dict[str, Any]]:
        while True:
            line = sys.stdin.readline()
            if line == "":
                return None  # EOF — the client is gone
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue  # a broken frame from the client is skipped
            if isinstance(message, dict):
                return message

    def send(self, message: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        sys.stdout.flush()


class PluginServer:
    def __init__(self, plugin: ToolPlugin, io: Optional[_Stdio] = None) -> None:
        self._plugin = plugin
        self._io = io or _Stdio()
        self._profile = False
        self._req_id = 0
        self._backlog: deque[dict[str, Any]] = deque()

    # ─────────────────────── The profile-backed context ───────────────────────

    def _bridge(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """One server→client request, blocking until ITS response. Client
        requests that arrive meanwhile are backlogged, not lost."""
        self._req_id += 1
        msg_id = f"srv-{self._req_id}"
        self._io.send({"jsonrpc": "2.0", "id": msg_id, "method": method,
                       "params": params})
        while True:
            message = self._io.read()
            if message is None:
                raise EOFError("client vanished mid-bridge")
            if message.get("id") == msg_id and (
                    "result" in message or "error" in message):
                if "error" in message:
                    return {}
                result = message.get("result")
                return result if isinstance(result, dict) else {}
            self._backlog.append(message)

    def _context(self) -> PluginContext:
        if not self._profile:
            return PluginContext()  # generic MCP client: no kernel powers

        async def read(args: dict[str, Any]) -> str:
            reply = self._bridge("muthis/read_file", {"args": args})
            return str(reply.get("text", ""))

        async def capture() -> Optional[bytes]:
            reply = self._bridge("muthis/capture", {})
            encoded = reply.get("image_base64")
            return base64.b64decode(encoded) if encoded else None

        return PluginContext(files=FilesCapability(read=read),
                             screen=ScreenCapability(capture=capture))

    # ─────────────────────────── The serve loop ───────────────────────────

    def serve_forever(self) -> None:
        while True:
            message = self._backlog.popleft() if self._backlog else self._io.read()
            if message is None:
                return
            if "method" in message and "id" in message:
                self._io.send(self._handle(message))
            # notifications and stray responses need no reply

    def _handle(self, message: dict[str, Any]) -> dict[str, Any]:
        method = message.get("method", "")
        msg_id = message.get("id")
        try:
            if method == "initialize":
                return self._on_initialize(msg_id, message.get("params") or {})
            if method == "tools/list":
                return {"jsonrpc": "2.0", "id": msg_id,
                        "result": {"tools": self._tool_catalog()}}
            if method == "tools/call":
                return self._on_call(msg_id, message.get("params") or {})
            return _error(msg_id, METHOD_NOT_FOUND, f"no method {method}")
        except Exception as exc:  # noqa: BLE001 — the runtime wall
            return _error(msg_id, INTERNAL_ERROR, repr(exc))

    def _on_initialize(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        version = params.get("protocolVersion")
        if version not in SUPPORTED_PROTOCOL_VERSIONS:
            version = PROTOCOL_VERSION  # answer with ours; the client decides
        experimental = (params.get("capabilities") or {}).get("experimental") or {}
        self._profile = MUTHIS_PROFILE in experimental
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": type(self._plugin).__name__,
                "version": _RUNTIME_VERSION,
                "muthisProfile": self._profile,
            },
        }}

    def _tool_catalog(self) -> list[dict[str, Any]]:
        catalog = []
        for descriptor in self._plugin.descriptors():
            catalog.append({
                "name": descriptor.name,
                "description": str(descriptor.schema.get("description", "")),
                "inputSchema": descriptor.schema.get(
                    "input_schema", {"type": "object", "properties": {}}),
                "annotations": {"readOnlyHint": bool(descriptor.read_only)},
            })
        return catalog

    def _on_call(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str):
            return _error(msg_id, INVALID_PARAMS, "tools/call needs a name")
        result = asyncio.run(self._plugin.execute(
            name, params.get("arguments") or {}, self._context()))
        if not isinstance(result, ToolResult):
            return _error(msg_id, INTERNAL_ERROR,
                          "plugin returned a non-ToolResult (contract breach)")
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "content": [{"type": "text", "text": result.text_ar}],
            "isError": bool(result.is_error),
        }}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id,
            "error": {"code": code, "message": message}}


def load_plugin(spec: str) -> ToolPlugin:
    """'package.module:ClassName' → a constructed ToolPlugin."""
    module_name, _, class_name = spec.partition(":")
    if not module_name or not class_name:
        raise SystemExit(f"usage: python -m muthis_sdk.mcp_runtime module:Class "
                         f"(got {spec!r})")
    if "" not in sys.path and "." not in sys.path:
        sys.path.insert(0, "")  # the child's cwd — where plugin repos live
    plugin_cls = getattr(importlib.import_module(module_name), class_name)
    if not (isinstance(plugin_cls, type) and issubclass(plugin_cls, ToolPlugin)):
        raise SystemExit(f"{spec} is not a ToolPlugin subclass")
    return plugin_cls()


def main(argv: Optional[list[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m muthis_sdk.mcp_runtime <module:Class>",
              file=sys.stderr)
        return 2
    PluginServer(load_plugin(args[0])).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
