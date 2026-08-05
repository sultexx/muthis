# src/muthis/cloud/luna_messages.py
"""
luna_messages.py — the message-shape translation, in BOTH directions.

ONE CONCERN: converting between the KERNEL's conversation vocabulary and this
vendor's item vocabulary. It holds no client, no key, no stream and no cost
arithmetic, and it is importable with neither SDK present.

WHY THE KERNEL'S SHAPE IS THE ANTHROPIC BLOCK SHAPE, AND WHY THAT IS NOT A LEAK.
`Orchestrator` stores `{"role": ..., "content": [block, ...]}` and
`build_tool_result_message` pairs every `tool_use` with a `tool_result` by
reading `type` / `id` / `name` (`tool_result_pairing.py`), while
`history_hygiene.py` strips a stale frame by reading `type` / `content`. That
vocabulary is the KERNEL's, and it predates the second provider by a year. So
the direction of the fix is fixed too: **the WRAPPER translates, the kernel does
not learn a second vocabulary** — DEC-88's finding that every difference lands
in the wrapper, applied to the one place it actually costs code.

THE TWO DIRECTIONS:
  · `to_vendor_input`  — kernel history + this turn's new content → the vendor's
    FLAT input item list.
  · `assistant_blocks` — this turn's streamed text and tool calls → the kernel
    blocks `TurnComplete.assistant_content` must carry, so the pairing, the
    hygiene strip and the agentic loop all work unchanged.

FLAT IS THE WHOLE DIFFERENCE. Anthropic nests a `tool_result` inside a user
message and enforces strict role alternation, which is why `claude_agent.run()`
FOLDS this turn's content into a trailing user message. Here `function_call` and
`function_call_output` are TOP-LEVEL items, so there is no consecutive-user-
message problem and NO FOLD IS NEEDED — the same history produces correctly
ordered items on its own. That fold is an Anthropic pairing rule, not a shared
one, and reproducing it here would be cargo.

THE `reasoning` OUTPUT ITEM IS NOT ROUND-TRIPPED, and this is a DECLARED limit
rather than an oversight (DEC-88 ② recorded it as UNMEASURED). Carrying it would
require the wrapper to hold state between passes, which LAW 11 forbids, or to
put a provider-specific opaque item into kernel history, which is exactly the
second vocabulary the paragraph above refuses. DEC-90 then drove a real
two-pass turn end to end without it: the tool_use → tool_result round trip
closed and the loop terminated correctly at `end_turn`. It is recorded as a
LIVE-RUN question, not as a settled property — a 3-4 pass turn was never driven.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from .protocol import ToolCall


def to_vendor_input(
    history: list[dict[str, Any]],
    screenshot: bytes | None,
    user_text: str,
    image_media_type: str = "image/png",
    image_b64: str = "",
) -> list[dict[str, Any]]:
    """Kernel history + this turn's new content → the vendor's input items.

    The caller does the base64 work (it owns the media-type sniff), so this
    module never touches image BYTES — only the already-encoded string.
    """
    items: list[dict[str, Any]] = []
    for message in history:
        items.extend(_items_for(message))
    parts: list[dict[str, Any]] = []
    if screenshot and image_b64:
        # Image FIRST, then text — the order `claude_agent.run()` uses and the
        # order the DEC-88 pointing measurement was taken in.
        parts.append(_image_part(image_media_type, image_b64))
    if user_text:
        parts.append({"type": "input_text", "text": user_text})
    if parts:
        items.append({"role": "user", "content": parts})
    return items


def assistant_blocks(text: str, tool_calls: Sequence[ToolCall]) -> list[dict[str, Any]]:
    """This turn's output → the KERNEL blocks. Emitted in the kernel's
    vocabulary because the kernel reads them: `id` and `name` are what
    `build_tool_result_message` pairs on, and a block missing either becomes an
    orphan `tool_use` that 400s the NEXT turn on the Anthropic path too."""
    blocks: list[dict[str, Any]] = []
    if text:
        blocks.append({"type": "text", "text": text})
    for call in tool_calls:
        blocks.append({
            "type": "tool_use",
            "id": call.tool_use_id,
            "name": call.name,
            "input": call.args,
        })
    return blocks


# ── one kernel message → zero or more vendor items ────────────────────────


def _items_for(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Order is preserved EXACTLY: accumulated content parts are FLUSHED before
    every top-level item, so a tool call never overtakes the text that preceded
    it. The kernel builds pure-text and pure-pairing messages today; translating
    faithfully costs the same as assuming it always will."""
    role = message.get("role", "user")
    content = message.get("content")
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return []
    items: list[dict[str, Any]] = []
    parts: list[dict[str, Any]] = []

    def flush() -> None:
        if parts:
            items.append({"role": role, "content": list(parts)})
            parts.clear()

    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "tool_use":
            flush()
            items.append({
                "type": "function_call",
                "call_id": block.get("id"),
                "name": block.get("name"),
                # The vendor takes arguments as a JSON STRING, the same form it
                # streams them in. `default=str` never raises on an exotic value
                # — dropping a whole tool call to a serialization error would
                # orphan it, which is the failure this pairing exists to prevent.
                "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False,
                                        default=str),
            })
        elif kind == "tool_result":
            flush()
            items.append({
                "type": "function_call_output",
                "call_id": block.get("tool_use_id"),
                "output": _output_for(block.get("content")),
            })
        elif kind == "text":
            parts.append(_text_part(role, block.get("text", "")))
        elif kind == "image":
            source = block.get("source") or {}
            parts.append(_image_part(source.get("media_type", "image/png"),
                                     source.get("data", "")))
    flush()
    return items


def _output_for(content: Any) -> Any:
    """A tool_result's payload → the vendor's `output`.

    A plain string stays a string. A BLOCK LIST becomes the vendor's content-part
    list, which is what keeps a `request_screen_refresh` frame INSIDE its own
    tool result rather than re-attached as a loose user message: the fresh frame
    must sit where the model asked for it, or the pairing stops meaning what it
    says.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "image":
            source = block.get("source") or {}
            parts.append(_image_part(source.get("media_type", "image/png"),
                                     source.get("data", "")))
        else:
            parts.append({"type": "input_text", "text": block.get("text", "")})
    return parts


def _text_part(role: str, text: str) -> dict[str, Any]:
    """Text in a message item is `output_text` when the ASSISTANT said it and
    `input_text` when anyone else did — the one place the vendor's vocabulary
    splits a single kernel block type by role."""
    return {"type": "output_text" if role == "assistant" else "input_text", "text": text}


def _image_part(media_type: str, data_b64: str) -> dict[str, Any]:
    """A data: URI, exactly the form the DEC-88 pointing run measured. No
    `detail` field is sent, because none was sent in that measurement and the
    23/25 result is only transferable if the request shape is."""
    return {"type": "input_image", "image_url": f"data:{media_type};base64,{data_b64}"}


__all__ = ["to_vendor_input", "assistant_blocks"]
