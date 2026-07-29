# src/muthis/broker/mcp/policy.py
"""
The look-and-advise exposure policy + result hygiene (roadmap §8.3 / §3.2).

EXPOSURE (per server tool, from its MCP annotations):
  readOnlyHint == true                → EXPOSED to the router
  destructiveHint == true / no hints  → HIDDEN (manual enablement + voice
                                        confirm arrive with the first
                                        high-impact tool — Phase 2; hidden
                                        stays hidden in Phase 1)
  openWorldHint == true               → exposed IFF also read-only; its
                                        results are tainted like all MCP
                                        results (external = untrusted)

RESULT HYGIENE (every tools/call result, no exceptions):
  text-only (image/audio blocks DROPPED with an Arabic note — a visual
  injection channel deferred by design), then size-capped with a truncation
  note. That is ALL this module does.

The §3.2 untrusted-content WRAPPING is NOT here (DEC-14, T4): it happens
centrally at the ToolRouter.service() boundary, where the nonce-bearing
delimiters are a universal constant EVERY external route inherits — MCP,
web, and every future one — with the source named there. Phase 1 wrapped
here as well; keeping both would DOUBLE-WRAP the MCP path and leave the
inner delimiter static, i.e. forgeable by the very content it frames. Do
NOT re-add a wrap here: `tests/test_untrusted_wrap_guard.py` fails if the
delimiters ever live in more than one module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("muthis.broker.mcp.policy")

# Content cap AFTER extraction (chars) — mirrors read_local_file's scale.
MAX_RESULT_CHARS = 16_000

IMAGE_DROPPED_NOTE_AR = "(أسقطت النواة محتوى غير نصي من نتيجة الأداة — النص فقط يُمرَّر)"
TRUNCATED_NOTE_AR = "(اقتُطعت النتيجة لتجاوزها سقف الحجم — اطلب نطاقًا أضيق إن لزم)"
EMPTY_RESULT_NOTE_AR = "(أعادت الأداة نتيجة فارغة)"


@dataclass(frozen=True)
class ExposedTool:
    """One server tool that PASSED the filter, in router-descriptor shape."""
    name: str
    schema: dict[str, Any]
    open_world: bool


def _annotations(tool: dict[str, Any]) -> dict[str, Any]:
    ann = tool.get("annotations")
    return ann if isinstance(ann, dict) else {}


def filter_tools(server_name: str, tools: list[dict[str, Any]]) -> list[ExposedTool]:
    """The look-and-advise gate over a tools/list result."""
    exposed: list[ExposedTool] = []
    for tool in tools:
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            continue
        ann = _annotations(tool)
        read_only = ann.get("readOnlyHint") is True
        destructive = ann.get("destructiveHint") is True
        if not read_only or destructive:
            logger.info("[mcp-policy] %s.%s HIDDEN (readOnly=%s destructive=%s "
                        "— look-and-advise default)", server_name, name,
                        read_only, destructive)
            continue
        schema = {
            "name": name,
            "description": str(tool.get("description", "")),
            "input_schema": tool.get("inputSchema") or {"type": "object", "properties": {}},
        }
        exposed.append(ExposedTool(name=name, schema=schema,
                                   open_world=ann.get("openWorldHint") is True))
    logger.info("[mcp-policy] %s: %d/%d tools exposed", server_name,
                len(exposed), len(tools))
    return exposed


def extract_text(result: dict[str, Any]) -> tuple[str, bool]:
    """tools/call result → (joined text, dropped_nontext?). MCP shape:
    {"content": [{"type": "text", "text": ...} | {"type": "image", ...}]}."""
    blocks = result.get("content")
    if not isinstance(blocks, list):
        return ("", False)
    parts: list[str] = []
    dropped = False
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
        else:
            dropped = True
    return ("\n".join(part for part in parts if part), dropped)


def sanitize_result(result: dict[str, Any]) -> str:
    """The hygiene line: extract → cap. ALWAYS returns a non-empty Arabic
    payload the pairing can carry; the router adds the untrusted-content
    framing on the way out (DEC-14), so this never emits a delimiter."""
    text, dropped = extract_text(result)
    notes: list[str] = []
    if dropped:
        notes.append(IMAGE_DROPPED_NOTE_AR)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS]
        notes.append(TRUNCATED_NOTE_AR)
    if not text:
        text = EMPTY_RESULT_NOTE_AR
    return "\n".join([text, *notes]) if notes else text


__all__ = [
    "EMPTY_RESULT_NOTE_AR",
    "ExposedTool",
    "IMAGE_DROPPED_NOTE_AR",
    "MAX_RESULT_CHARS",
    "TRUNCATED_NOTE_AR",
    "extract_text",
    "filter_tools",
    "sanitize_result",
]
