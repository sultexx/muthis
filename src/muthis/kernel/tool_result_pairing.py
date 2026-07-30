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
A LEAF module (imports highlight_gate / tool_router / file_reader / protocol,
never turn) so there is no import cycle. No behavior change — the DEC-21
serviced-results container is FEATURE work for a later commit, not this move.
"""

from __future__ import annotations

import base64
from typing import Any, Optional

from ..cloud.protocol import ToolCall
from ..file_reader import FILE_ALREADY_READ_AR, FILE_READ_ERROR_AR, READ_FILE_TOOL
from .highlight_gate import HighlightGate, draw_result_text
from .tool_router import namespaced_name

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


RUN_CODE_TOOL = namespaced_name("sandbox", "run_code")  # DEC-11: derived, not scattered
# Second / unserviced run_code ids in a pass keep Option-B pairing API-valid.
RUN_CODE_ALREADY_AR = "شغّلتَ الكود قبل قليل في هذه الجولة — استخدم نتيجته وأكمل."
RUN_CODE_UNAVAILABLE_AR = "التنفيذ المعزول غير متاح في هذه الجلسة."

# T6b: the web tools, derived from the ONE separator like run_code above. They are
# answered BY NAME for the reason `read_local_file` is — so a web call can NEVER
# fall through to the draw branch, where it would receive the pointer ack and flip
# the per-turn draw gate, silently terminating the agentic loop.
WEB_SEARCH_TOOL = namespaced_name("web", "search")
WEB_FETCH_TOOL = namespaced_name("web", "fetch")
WEB_TOOLS = frozenset({WEB_SEARCH_TOOL, WEB_FETCH_TOOL})

# ONE note covers both "a second web call this pass" and "a read was serviced
# instead": the model's next move is identical either way, so two wordings would
# be a distinction without a difference.
WEB_ONE_PER_PASS_AR = (
    "توجيه داخلي (لا يراه المستخدم): أخدم طلب ويب واحدًا في كل خطوة تفكير. "
    "اطلبه مرة أخرى في الخطوة التالية."
)

# T4: the doc tools, derived from the ONE separator like every namespaced name
# above. Answered BY NAME for the same reason, and DEC-39 makes the ORDER of that
# work a requirement rather than a preference: this branch and the servicing
# condition below land BEFORE the tools reach the catalog, because a
# MOUNTED-BUT-UNSERVICED tool bypasses every boundary (no DEC-14 wrap, no DEC-15
# taint raise, no DEC-16 confirm gate), then falls to the draw branch where it
# receives the POINTER ack, flips the per-turn draw gate and hard-terminates the
# turn. That is not a hypothetical: it is the M2 bug this ordering rule came from.
DOC_OPEN_TOOL = namespaced_name("docs", "open")
DOC_QUERY_TOOL = namespaced_name("docs", "query")
DOC_TOOLS = frozenset({DOC_OPEN_TOOL, DOC_QUERY_TOOL})

# Its OWN wording, not the web note reused. DEC-35's lesson is that a refusal
# misreporting its reason turns a terminal condition into a retryable one, and
# telling the model "I serve one WEB request per step" after it asked for a
# DOCUMENT is a smaller version of the same lie — the model would look for a web
# call it never made.
DOC_ONE_PER_PASS_AR = (
    "توجيه داخلي (لا يراه المستخدم): أخدم طلب مستند واحدًا في كل خطوة تفكير. "
    "اطلبه مرة أخرى في الخطوة التالية."
)

# EVERY tool the kernel services THROUGH THE ROUTER, as one name for one idea.
# `TurnPass` used to spell this as an or-chain (`== READ_FILE_TOOL or in
# WEB_TOOLS`) that each milestone lengthened by hand. The set is not a tidy-up:
# a routed tool MISSING from it falls through to the LOOK-only `else`, which
# means never serviced — so the DEC-14 wrap, the DEC-15 taint raise and the
# DEC-16 confirm gate are all bypassed — and then paired with the POINTER ack,
# flipping the draw gate and killing the turn (DEC-39). Naming the set puts that
# whole class of mistake in ONE place a test can pin, and makes the next routed
# tool cost `turn_pass.py` zero lines.
# T4 adds DOC_TOOLS here and NOWHERE ELSE: because `TurnPass` tests membership in
# this one set, the new routed family costs `turn_pass.py` exactly ZERO lines —
# which is what naming the set bought (measured at P0b, and now spent).
ROUTER_SERVICED_TOOLS = frozenset({READ_FILE_TOOL}) | WEB_TOOLS | DOC_TOOLS


def build_tool_result_message(
    assistant_content: list[dict[str, Any]],
    refresh_call: Optional[ToolCall] = None,
    fresh_screenshot: Optional[bytes] = None,
    gate: Optional[HighlightGate] = None,
    read_result: Optional[tuple[ToolCall, str]] = None,
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
    read_id = read_result[0].tool_use_id if read_result else None
    routed_name = read_result[0].name if read_result else None
    run_id = run_result[0].tool_use_id if run_result else None
    results: list[dict[str, Any]] = []
    for block in assistant_content:
        if block.get("type") != "tool_use":
            continue
        tool_use_id = block.get("id")
        if tool_use_id is not None and tool_use_id == refresh_id:
            results.append(_refresh_tool_result_block(tool_use_id, fresh_screenshot))
        elif block.get("name") == READ_FILE_TOOL:
            if tool_use_id is not None and tool_use_id == read_id:
                content = read_result[1]
            else:
                content = (FILE_ALREADY_READ_AR if routed_name == READ_FILE_TOOL
                           else FILE_READ_ERROR_AR)
            results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content,
            })
        elif block.get("name") in WEB_TOOLS:
            # BY NAME, exactly like the read above — never the draw branch.
            if tool_use_id is not None and tool_use_id == read_id:
                content = read_result[1]
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
            if tool_use_id is not None and tool_use_id == read_id:
                content = read_result[1]
            else:
                content = DOC_ONE_PER_PASS_AR
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
    "ROUTER_SERVICED_TOOLS",
    "build_tool_result_message",
]

# SEAM NAMED AT PLANNING TIME (the DEC-23 / DEC-52 posture, so a future
# contributor does not discover it mid-task): the web and doc arms of
# `build_tool_result_message` are now structurally IDENTICAL — serviced id gets the
# content, every other id gets that family's one-per-pass note. A FOURTH routed
# family should replace both with a single arm reading a `{tool_name: busy_note}`
# table, which then costs each later family one dict entry instead of eight lines.
# NOT done now, and the reason is the same one that made the `ROUTER_SERVICED_TOOLS`
# replacement land ALONE and BEFORE any doc_rag wiring: a refactor of two working
# security branches does not belong inside the feature commit that needed neither.
