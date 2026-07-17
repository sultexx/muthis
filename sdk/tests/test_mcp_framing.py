# sdk/tests/test_mcp_framing.py
"""The MCP wire slice: framing round-trips, EOF, broken frames, message shapes."""

from __future__ import annotations

import asyncio
import json

import pytest

from muthis_sdk.mcp import (
    MUTHIS_PROFILE,
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    error_response,
    is_notification,
    is_request,
    is_response,
    notification,
    request,
    response,
)
from muthis_sdk.mcp.framing import FramingError, encode_message, read_message


def _reader_with(data: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


def test_encode_is_one_line_utf8():
    line = encode_message(request(1, "tools/call", {"name": "قراءة"}))
    assert line.endswith(b"\n") and line.count(b"\n") == 1
    assert "قراءة" in line.decode("utf-8")


def test_round_trip_and_blank_line_tolerance():
    msgs = [request(1, "initialize"), notification("notifications/tools/list_changed")]
    data = encode_message(msgs[0]) + b"\n" + encode_message(msgs[1])
    async def go():
        reader = _reader_with(data)
        assert await read_message(reader) == msgs[0]
        assert await read_message(reader) == msgs[1]
        assert await read_message(reader) is None  # clean EOF
    asyncio.run(go())


def test_broken_frames_raise_framing_error():
    async def bad_json():
        await read_message(_reader_with(b"{not json}\n"))
    async def non_object():
        await read_message(_reader_with(b"[1,2]\n"))
    with pytest.raises(FramingError):
        asyncio.run(bad_json())
    with pytest.raises(FramingError):
        asyncio.run(non_object())


def test_message_shape_predicates():
    assert is_request(request(1, "m")) and not is_notification(request(1, "m"))
    assert is_notification(notification("m")) and not is_request(notification("m"))
    assert is_response(response(1, {})) and is_response(error_response(1, -32601, "x"))


def test_pinned_version_is_in_the_accept_set():
    assert PROTOCOL_VERSION in SUPPORTED_PROTOCOL_VERSIONS
    assert MUTHIS_PROFILE == "muthis-profile/1"
