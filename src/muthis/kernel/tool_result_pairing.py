# src/muthis/kernel/tool_result_pairing.py
"""
tool_result_pairing.py — the Option-B tool_result pairing builder.

Extracted from turn.py under the ≤300-line law (DEC-19 / DEC-21 #3): a MOVE
ONLY of build_tool_result_message (+ _refresh_tool_result_block, the RUN_CODE
surfaces, and NO_SCREENSHOT_TOOL_RESULT_AR). turn.py re-exports the public
names, so every existing importer keeps working (the highlight_gate /
history_hygiene precedent).

The highest-traffic kernel seam: it pairs EVERY assistant tool_use with a
tool_result (Option B) — an orphan tool_use 400s the NEXT turn. Answered by
name: draw tools (gate-aware draw_result_text), request_screen_refresh (fresh
screenshot / the NO_SCREENSHOT note), read_local_file, and sandbox__run_code.
A LEAF module (imports highlight_gate / deferral_notes / file_reader / protocol,
never turn) so there is no import cycle. No behavior change — the DEC-21
serviced-results container is FEATURE work for a later commit, not this move.

SECOND EXTRACTION (2026-08-02): the routed-family NAMES, the deferral NOTES and
their selectors moved to `deferral_notes.py` and are RE-EXPORTED from here, so no
importer changed. This file kept the DISPATCH; the module that grows every
milestone is now the one that exists to hold it. See that module's docstring for
why the T4-named table seam was measured and NOT the shape taken.
"""

from __future__ import annotations

import base64
from typing import Any, Optional

from ..cloud.protocol import ToolCall
from ..file_reader import FILE_ALREADY_READ_AR, FILE_READ_ERROR_AR, READ_FILE_TOOL
from .highlight_gate import HighlightGate, draw_result_text

NO_SCREENSHOT_TOOL_RESULT_AR = "تعذّر التقاط لقطة شاشة جديدة."


def _refresh_tool_result_block(tool_use_id: str, screenshot: Optional[bytes]) -> dict[str, Any]:
    """The single tool_result block answering a request_screen_refresh: the
    fresh, already-downscaled payload COPY (a minimal PNG/JPEG sniff sets
    media_type so the SDK stack is NOT imported here), or an Arabic
    'no new screenshot' note when no fresh capture is available."""
    if screenshot:
        media_type = "image/png" if screenshot[:4] == b"\x89PNG" else "image/jpeg"
        inner: list[dict[str, Any]] = [{
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64.standard_b64encode(screenshot).decode("ascii"),
            },
        }]
    else:
        inner = [{"type": "text", "text": NO_SCREENSHOT_TOOL_RESULT_AR}]
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": inner}


from .deferral_notes import (
    DOC_ONE_PER_PASS_AR, DOC_OPENED_ASK_NEXT_AR, DOC_OPEN_TOOL, DOC_QUERY_TOOL,
    DOC_TOOLS, PRECONDITION_TOOLS, ROUTER_SERVICED_TOOLS, RUN_CODE_ALREADY_AR,
    RUN_CODE_TOOL, RUN_CODE_UNAVAILABLE_AR, WEB_FETCH_TOOL, WEB_ONE_PER_PASS_AR,
    WEB_SEARCH_TOOL, WEB_TOOLS, doc_deferral_note,
)


def build_tool_result_message(
    assistant_content: list[dict[str, Any]],
    refresh_call: Optional[ToolCall] = None,
    fresh_screenshot: Optional[bytes] = None,
    gate: Optional[HighlightGate] = None,
    read_results: Optional[list[tuple[ToolCall, str]]] = None,
    run_result: Optional[tuple[ToolCall, str]] = None,
) -> Optional[dict[str, Any]]:
    """ONE user message pairing a tool_result with EVERY tool_use block the
    assistant just emitted (Option B — full pairing). The refresh id (when
    refresh_call is given) is answered with the fresh screenshot — or a text
    note when fresh_screenshot is None (e.g. the follow-up limit was hit).

    read_local_file (v7 Phase 4) is answered by NAME so it can NEVER touch the
    draw gate: the serviced call (read_result = (call, content)) gets the file
    content; any OTHER read id in the same pass gets the already-read
    directive; a read id with NO servicing (legacy caller) gets the error note.

    Circuit breaker (hard backstop): every remaining id is a DRAW tool —
    highlight_target or draw_shapes. With a `gate`, the FIRST one of the turn
    gets its tool's "explain now" ack and flips `gate.drawn` (ONE gate, BOTH
    tools); every later one (this pass or a future one, either tool) gets its
    "already shown — don't redraw, explain" note — draw_result_text picks the
    wording by tool name. Without a gate (legacy) it always returns the ack.

    Returns None when the assistant turn carried no tool_use, so the caller
    appends NOTHING and never stores an empty message. Bundling all results
    into one message keeps them in the single user message that immediately
    follows the assistant turn — exactly what the API's pairing rule needs.
    Lives here (not in claude_agent.py) so the orchestrator stays importable
    without the SDK stack."""
    refresh_id = refresh_call.tool_use_id if refresh_call else None
    # `read_result` is the ROUTER-serviced call of the pass — a local read OR a
    # web call (T6b). Which one it was decides what the OTHER ids are told, so a
    # read id is never handed "already read" for a read that never happened.
    # EVERY serviced call of the pass, not one: a precondition no longer consumes
    # the slot, so `docs__open` and `docs__query` can both be serviced in one
    # pass. The lookup is a SET membership rather than an id comparison; the
    # deferral notes below are untouched and still fire for genuinely unserviced
    # ids (a second query, a second read).
    serviced = {call.tool_use_id: text for call, text in (read_results or ())}
    routed_names = {call.name for call, _ in (read_results or ())}
    last_serviced = read_results[-1][0] if read_results else None
    run_id = run_result[0].tool_use_id if run_result else None
    results: list[dict[str, Any]] = []
    for block in assistant_content:
        if block.get("type") != "tool_use":
            continue
        tool_use_id = block.get("id")
        if tool_use_id is not None and tool_use_id == refresh_id:
            results.append(_refresh_tool_result_block(tool_use_id, fresh_screenshot))
        elif block.get("name") == READ_FILE_TOOL:
            if tool_use_id in serviced:
                content = serviced[tool_use_id]
            else:
                content = (FILE_ALREADY_READ_AR if READ_FILE_TOOL in routed_names
                           else FILE_READ_ERROR_AR)
            results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content,
            })
        elif block.get("name") in WEB_TOOLS:
            # BY NAME, exactly like the read above — never the draw branch.
            if tool_use_id in serviced:
                content = serviced[tool_use_id]
            else:
                content = WEB_ONE_PER_PASS_AR
            results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content,
            })
        elif block.get("name") in DOC_TOOLS:
            # BY NAME, exactly like the read and the web calls above — never the
            # draw branch. A THIRD near-identical arm is deliberate here: folding
            # the routed families into one note table would edit two working
            # security branches inside a security milestone, and this file has the
            # room (see the seam noted below `__all__`).
            if tool_use_id in serviced:
                content = serviced[tool_use_id]
            else:
                # The note reports the state ACHIEVED, not only the deferral —
                # see `doc_deferral_note` and the standing note law.
                content = doc_deferral_note(last_serviced)
            results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content,
            })
        elif block.get("name") == RUN_CODE_TOOL:
            # T5: answered BY NAME (like read) so a run can NEVER hit the draw
            # branch. The serviced run gets its Arabic output; a second run_code
            # id in the same pass gets the already-ran note.
            if tool_use_id is not None and tool_use_id == run_id:
                content = run_result[1]
            else:
                content = RUN_CODE_ALREADY_AR if run_result else RUN_CODE_UNAVAILABLE_AR
            results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content,
            })
        else:
            results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": draw_result_text(gate, block.get("name", "")),
            })
    if not results:
        return None
    return {"role": "user", "content": results}


__all__ = [
    "NO_SCREENSHOT_TOOL_RESULT_AR",
    "RUN_CODE_TOOL", "RUN_CODE_ALREADY_AR", "RUN_CODE_UNAVAILABLE_AR",
    "WEB_SEARCH_TOOL", "WEB_FETCH_TOOL", "WEB_TOOLS", "WEB_ONE_PER_PASS_AR",
    "DOC_OPEN_TOOL", "DOC_QUERY_TOOL", "DOC_TOOLS", "DOC_ONE_PER_PASS_AR",
    "DOC_OPENED_ASK_NEXT_AR", "doc_deferral_note",
    "ROUTER_SERVICED_TOOLS",
    "build_tool_result_message",
]

# THE SEAM NAMED HERE AT PLANNING TIME IS SPENT — and it was NOT the shape taken,
# which is the part worth keeping. It named a `{tool_name: busy_note}` TABLE
# replacing the two structurally identical routed arms. Its premise was that both
# arms are UNCONDITIONAL; DEC-58 had already made the doc arm conditional, and the
# pending web-note fix makes the web arm conditional the same way, so a flat table
# expresses NEITHER. RE-MEASURED at execution as DEC-52 / DEC-56 require: the named
# seam saves ~8 lines of a 30-line breach, because the cost is in the NOTES and a
# table does not move them. The notes moved instead (`deferral_notes.py`, 2026-08-02),
# and this file went 298 → 193. A named seam is a hypothesis, not a plan.
#
# STILL TRUE, and it is why that extraction landed ALONE and mechanically: a
# refactor of two working security branches does not belong inside the feature
# commit that needed neither (the `ROUTER_SERVICED_TOOLS` precedent).
