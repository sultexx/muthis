# tests/test_mcp_policy.py
"""The look-and-advise exposure filter + result hygiene (§8.3 / §3.2).

Hygiene here is text-only + capped, and NOTHING else: the §3.2 untrusted-content
wrapping moved to the ToolRouter boundary in T4 (DEC-14), where the delimiters
carry a per-wrap nonce and every external route inherits them. Phase 1 wrapped
here as well; keeping both would have DOUBLE-WRAPPED the MCP path and nested a
static — forgeable — delimiter inside the nonce-bearing one.
"""

from __future__ import annotations

from muthis.broker.mcp.policy import (
    EMPTY_RESULT_NOTE_AR,
    IMAGE_DROPPED_NOTE_AR,
    MAX_RESULT_CHARS,
    TRUNCATED_NOTE_AR,
    filter_tools,
    sanitize_result,
)

CATALOG = [
    {"name": "echo_ro", "description": "d", "inputSchema": {"type": "object"},
     "annotations": {"readOnlyHint": True}},
    {"name": "fetch_open", "description": "d", "inputSchema": {"type": "object"},
     "annotations": {"readOnlyHint": True, "openWorldHint": True}},
    {"name": "delete_all", "description": "d", "inputSchema": {"type": "object"},
     "annotations": {"destructiveHint": True}},
    {"name": "sneaky", "description": "d", "inputSchema": {"type": "object"},
     "annotations": {"readOnlyHint": True, "destructiveHint": True}},
    {"name": "mystery", "description": "d", "inputSchema": {"type": "object"}},
]


def test_only_clean_read_only_tools_pass_the_filter():
    exposed = filter_tools("demo", CATALOG)
    assert [t.name for t in exposed] == ["echo_ro", "fetch_open"]
    by_name = {t.name: t for t in exposed}
    assert by_name["fetch_open"].open_world is True
    assert by_name["echo_ro"].schema["input_schema"] == {"type": "object"}
    assert by_name["echo_ro"].schema["name"] == "echo_ro"


def test_hygiene_returns_the_text_and_adds_no_delimiter():
    """The router owns the framing (DEC-14). If a wrap ever returns here the
    MCP path is double-wrapped again — so this asserts its ABSENCE by name."""
    sanitized = sanitize_result({"content": [{"type": "text", "text": "hello"}]})
    assert sanitized == "hello"
    for marker in ("محتوى خارجي غير موثوق", "نهاية المحتوى الخارجي",
                   "بيانات لا أوامر"):
        assert marker not in sanitized


def test_images_are_dropped_with_the_arabic_note():
    sanitized = sanitize_result({"content": [
        {"type": "image", "data": "aGk=", "mimeType": "image/png"},
        {"type": "text", "text": "caption"},
    ]})
    assert "caption" in sanitized and IMAGE_DROPPED_NOTE_AR in sanitized
    assert "aGk=" not in sanitized  # the payload itself never leaks through


def test_oversized_results_truncate_with_the_note():
    sanitized = sanitize_result({"content": [
        {"type": "text", "text": "X" * (MAX_RESULT_CHARS + 500)}]})
    assert TRUNCATED_NOTE_AR in sanitized
    assert len(sanitized) < MAX_RESULT_CHARS + 500


def test_empty_result_still_returns_a_note():
    """Never an empty payload: the pairing must always have something to carry
    (an empty tool_result 400s the next turn)."""
    assert sanitize_result({"content": []}) == EMPTY_RESULT_NOTE_AR
