# sdk/muthis_sdk/mcp/__init__.py
"""
Minimal MCP-over-stdio plumbing (V2 Phase 1, decision Q-1.1: hand-rolled
stdlib — the SDK's zero-dependency law is absolute, and the security layer
above this wants low-level control, not a framework).

Scope is the NARROW slice Mut'his needs and nothing more: JSON-RPC 2.0
framed as newline-delimited UTF-8 JSON over stdio; initialize / tools/list /
tools/call; notifications (tools/list_changed); and the experimental
`muthis-profile/1` capability. No HTTP/SSE transport, no resources, no
prompts, no sampling (refused by policy at the client).

Lives in the SDK so BOTH sides import ONE implementation: the app's broker
(client side) and mcp_runtime (server side, M1-6) — the app→sdk import
direction is the legal one.
"""

from .framing import MAX_LINE_BYTES, read_message, write_message
from .messages import (
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

__all__ = [
    "MAX_LINE_BYTES",
    "MUTHIS_PROFILE",
    "PROTOCOL_VERSION",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "error_response",
    "is_notification",
    "is_request",
    "is_response",
    "notification",
    "read_message",
    "request",
    "response",
    "write_message",
]
