# sdk/tests/test_mcp_runtime.py
"""PluginServer (the out-of-proc runtime) driven over REAL child processes
with the SDK's own wire utilities: catalog shape, profile negotiation, the
bridge-backed context, and polite degradation without the profile."""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path

from muthis_sdk.mcp import (
    MUTHIS_PROFILE,
    PROTOCOL_VERSION,
    notification,
    read_message,
    request,
    response,
    write_message,
)

FIXTURE = """
from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin, ToolResult

SCHEMA = {
    "name": "read_it",
    "description": "reads through the kernel",
    "input_schema": {"type": "object", "properties": {}},
}

class Fixture(ToolPlugin):
    def descriptors(self):
        return [ToolDescriptor(name="read_it", schema=SCHEMA, read_only=True)]

    async def execute(self, tool, args, ctx):
        if ctx.files is None:
            return ToolResult(text_ar="بلا مقدرة", is_error=True)
        return ToolResult(text_ar=await ctx.files.read({"path": "x"}))
"""


async def _spawn(tmp_path, offer_profile: bool):
    (tmp_path / "fixmod.py").write_text(textwrap.dedent(FIXTURE), encoding="utf-8")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "muthis_sdk.mcp_runtime", "fixmod:Fixture",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, cwd=str(tmp_path))
    experimental = {MUTHIS_PROFILE: {}} if offer_profile else {}
    await write_message(proc.stdin, request(1, "initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"experimental": experimental},
        "clientInfo": {"name": "test", "version": "0"}}))
    init = await read_message(proc.stdout)
    await write_message(proc.stdin, notification("notifications/initialized"))
    return proc, init


async def _finish(proc):
    proc.stdin.close()
    await asyncio.wait_for(proc.wait(), timeout=10)


def test_catalog_and_degradation_without_the_profile(tmp_path):
    async def go():
        proc, init = await _spawn(tmp_path, offer_profile=False)
        try:
            assert init["result"]["serverInfo"]["muthisProfile"] is False
            await write_message(proc.stdin, request(2, "tools/list"))
            listed = await read_message(proc.stdout)
            (tool,) = listed["result"]["tools"]
            assert tool["name"] == "read_it"
            assert tool["annotations"]["readOnlyHint"] is True
            await write_message(proc.stdin, request(
                3, "tools/call", {"name": "read_it", "arguments": {}}))
            called = await read_message(proc.stdout)
            assert called["result"]["isError"] is True
            assert called["result"]["content"][0]["text"] == "بلا مقدرة"
        finally:
            await _finish(proc)
    asyncio.run(go())


def test_profile_backed_context_bridges_to_the_client(tmp_path):
    async def go():
        proc, init = await _spawn(tmp_path, offer_profile=True)
        try:
            assert init["result"]["serverInfo"]["muthisProfile"] is True
            await write_message(proc.stdin, request(
                2, "tools/call", {"name": "read_it", "arguments": {}}))
            # The child now asks US (the kernel side) to read the file.
            bridge_req = await read_message(proc.stdout)
            assert bridge_req["method"] == "muthis/read_file"
            assert bridge_req["params"] == {"args": {"path": "x"}}
            await write_message(proc.stdin, response(
                bridge_req["id"], {"text": "١: سطر من النواة"}))
            called = await read_message(proc.stdout)
            assert called["id"] == 2
            assert called["result"]["content"][0]["text"] == "١: سطر من النواة"
            assert called["result"]["isError"] is False
        finally:
            await _finish(proc)
    asyncio.run(go())
