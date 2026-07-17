# sdk/muthis_sdk/mcp/messages.py
"""
JSON-RPC 2.0 message shapes + the MCP constants Mut'his pins.

The protocol version is PINNED (roadmap §8.2): we speak one dated revision
and accept the known-compatible set — an unknown server version is a clean
handshake refusal, never a silent guess. The version-compat matrix ships in
the docs (§8.7 promise).
"""

from __future__ import annotations

from typing import Any, Optional

# The revision we request; the accept-set covers the wire-compatible ones.
PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2024-11-05", "2025-03-26", "2025-06-18"})

# The experimental capability community plugins negotiate to reach kernel
# powers through the broker (roadmap §8.4). Version 1 carries read_file +
# capture; annotate is deliberately deferred (decision Q-1.2).
MUTHIS_PROFILE = "muthis-profile/1"

# JSON-RPC error codes (the standard set + the range servers may use).
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def request(msg_id: int | str, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def notification(method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def response(msg_id: int | str, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def error_response(msg_id: int | str | None, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def is_request(msg: dict[str, Any]) -> bool:
    return "method" in msg and "id" in msg


def is_notification(msg: dict[str, Any]) -> bool:
    return "method" in msg and "id" not in msg


def is_response(msg: dict[str, Any]) -> bool:
    return "id" in msg and ("result" in msg or "error" in msg)


__all__ = [
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "MUTHIS_PROFILE",
    "PARSE_ERROR",
    "PROTOCOL_VERSION",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "error_response",
    "is_notification",
    "is_request",
    "is_response",
    "notification",
    "request",
    "response",
]
