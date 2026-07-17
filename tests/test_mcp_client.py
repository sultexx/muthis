# tests/test_mcp_client.py
"""McpSession against the independent fake server (real child processes) +
direct dispatch units for the peer-request door."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from muthis.broker.mcp.client import McpSession, McpSessionError

FAKE = str(Path(__file__).parent / "fake_mcp_server.py")


def _entry(mode="standard"):
    return f'"{sys.executable}" "{FAKE}" {mode}'


def test_handshake_list_call_and_clean_close():
    async def go():
        session = McpSession("fake", _entry())
        await session.start()
        try:
            assert session.server_info.get("name") == "fake-foreign-server"
            listed = await session.call("tools/list")
            assert {t["name"] for t in listed["tools"]} >= {"echo_ro", "delete_all"}
            result = await session.call(
                "tools/call", {"name": "echo_ro", "arguments": {"text": "سلام"}})
            assert result["content"][0]["text"] == "echo:سلام"
        finally:
            await session.close()
    asyncio.run(go())


def test_unknown_protocol_version_is_refused():
    async def go():
        session = McpSession("fake", _entry("badversion"))
        with pytest.raises(McpSessionError, match="unsupported protocol"):
            await session.start()
    asyncio.run(go())


def test_call_timeout_raises_session_error():
    async def go():
        session = McpSession("fake", _entry("hang"), call_timeout_s=0.5)
        await session.start()
        try:
            with pytest.raises(McpSessionError, match="timed out"):
                await session.call("tools/call", {"name": "echo_ro", "arguments": {}})
        finally:
            await session.close()
    asyncio.run(go())


def test_peer_request_door_refuses_sampling_and_unknown_methods():
    """Direct dispatch unit: no bridge wired → METHOD_NOT_FOUND for everything;
    sampling refused by name even before the bridge check."""
    sent = []

    async def go():
        session = McpSession("fake", _entry())
        async def collect(message):
            sent.append(message)
        session._send = collect  # the dispatch unit under test, no child needed
        await session._serve_peer_request(
            {"jsonrpc": "2.0", "id": 7, "method": "sampling/createMessage"})
        await session._serve_peer_request(
            {"jsonrpc": "2.0", "id": 8, "method": "muthis/read_file", "params": {}})
        await session._serve_peer_request(
            {"jsonrpc": "2.0", "id": 9, "method": "anything/else"})
    asyncio.run(go())
    assert [m["id"] for m in sent] == [7, 8, 9]
    assert all(m["error"]["code"] == -32601 for m in sent)
    assert "sampling" in sent[0]["error"]["message"]


def test_bridge_seam_services_profile_methods():
    sent = []

    async def bridge(method, params):
        return {"served": method, "path": params.get("path")}

    async def go():
        session = McpSession("fake", _entry(), bridge=bridge)
        async def collect(message):
            sent.append(message)
        session._send = collect
        await session._serve_peer_request(
            {"jsonrpc": "2.0", "id": 1, "method": "muthis/read_file",
             "params": {"path": "x.py"}})
    asyncio.run(go())
    assert sent[0]["result"] == {"served": "muthis/read_file", "path": "x.py"}
