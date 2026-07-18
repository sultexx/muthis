# sdk/muthis_sdk/mcp/framing.py
"""
The stdio wire: newline-delimited UTF-8 JSON (one JSON-RPC message per
line, no embedded newlines — the MCP stdio transport).

Hard line cap: a peer that streams an unbounded line would balloon memory
on the reader; MAX_LINE_BYTES is the containment wall (oversized input is
a framing error, reported to the caller as such — never an allocation).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger("muthis_sdk.mcp.framing")

# 4 MiB: generous for tool results (the app caps CONTENT far lower), tight
# enough that a hostile peer cannot balloon the reader.
MAX_LINE_BYTES = 4 * 1024 * 1024


class FramingError(Exception):
    """A broken frame (oversized line / invalid JSON / non-object)."""


def encode_message(message: dict[str, Any]) -> bytes:
    """One message → one line. ensure_ascii=False keeps Arabic readable in
    logs and on the wire (UTF-8 both sides by contract)."""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


async def write_message(writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
    writer.write(encode_message(message))
    await writer.drain()


async def read_message(reader: asyncio.StreamReader) -> Optional[dict[str, Any]]:
    """The next message, or None on clean EOF. Raises FramingError on a
    broken frame — the session layer decides what a broken peer costs."""
    try:
        line = await reader.readuntil(b"\n")
    except asyncio.IncompleteReadError as exc:
        if not exc.partial:
            return None  # clean EOF
        raise FramingError("EOF inside a frame") from exc
    except asyncio.LimitOverrunError as exc:
        raise FramingError(f"line exceeds the reader limit: {exc}") from exc
    if len(line) > MAX_LINE_BYTES:
        raise FramingError(f"frame of {len(line)} bytes exceeds MAX_LINE_BYTES")
    text = line.decode("utf-8", errors="strict").strip()
    if not text:
        return await read_message(reader)  # tolerate blank keepalive lines
    try:
        message = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FramingError(f"invalid JSON frame: {exc}") from exc
    if not isinstance(message, dict):
        raise FramingError("frame is not a JSON object")
    return message


__all__ = ["FramingError", "MAX_LINE_BYTES", "encode_message", "read_message", "write_message"]
