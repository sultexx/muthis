# src/muthis/kernel/history_hygiene.py
"""
History hygiene — the Bug-3 stale-frame strip, extracted WHOLE from turn.py
(v7 Phase 4: that file sat at 298/300 and the read_local_file pairing branch
needed room; Law §17.4: split, don't compress — the same reason
highlight_gate.py and voice_out.py exist). turn.py re-exports both public
names, so every existing import keeps working. Pure stdlib; importable in
isolation.

Replaces a request_screen_refresh screenshot in STORED history once its turn
is over. The fresh frame already reached the model inside its tool_result for
the iteration that needed it; persisting the pixels would replay a now-stale
view on the NEXT user turn — the app-switch hallucination (still "seeing" a
since-closed app). A fresh frame is captured every turn, so nothing of value
is lost; the id and the pairing stay intact, only the image bytes are dropped.
"""

from __future__ import annotations

from typing import Any

# The swap-in placeholder. Not a spoken surface.
STALE_SCREENSHOT_NOTE_AR = "(لقطة شاشة من دور سابق غير مرفقة)"


def _tool_result_has_image(block: dict[str, Any]) -> bool:
    """True iff `block` is a tool_result whose content list carries an image."""
    inner = block.get("content")
    return (
        block.get("type") == "tool_result"
        and isinstance(inner, list)
        and any(b.get("type") == "image" for b in inner)
    )


def _strip_tool_result_images(block: dict[str, Any]) -> dict[str, Any]:
    """Return a COPY of one tool_result with every image block swapped for a short
    text note (the original — already sent this turn — is never mutated). Anything
    that is not an image-bearing tool_result is returned unchanged (same object)."""
    if not _tool_result_has_image(block):
        return block
    note = {"type": "text", "text": STALE_SCREENSHOT_NOTE_AR}
    stripped = [note if b.get("type") == "image" else b for b in block["content"]]
    return {**block, "content": stripped}


def strip_images_from_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return `history` with every request_screen_refresh screenshot dropped from
    its tool_result. Called ONCE per turn, AFTER the turn ends: the frame already
    did its job for the iteration that needed it, and keeping it leaks a stale view
    into the NEXT user turn (Bug 3 — the app-switch hallucination).

    Structure is preserved EXACTLY — same messages, roles, and tool_use_ids — so
    every tool_use/tool_result pairing stays valid and no message becomes empty.
    New dicts are built ONLY for changed blocks; the originals (already handed to
    earlier run() calls this turn) are never mutated, and an image-free history is
    returned unchanged (same object)."""
    def _has_image(message: dict[str, Any]) -> bool:
        content = message.get("content")
        return isinstance(content, list) and any(
            _tool_result_has_image(block) for block in content)

    if not any(_has_image(message) for message in history):
        return history
    sanitized: list[dict[str, Any]] = []
    for message in history:
        content = message.get("content")
        if not isinstance(content, list):
            sanitized.append(message)
            continue
        new_content = [_strip_tool_result_images(block) for block in content]
        sanitized.append(
            message if new_content == content
            else {**message, "content": new_content})
    return sanitized


__all__ = ["STALE_SCREENSHOT_NOTE_AR", "strip_images_from_history"]
