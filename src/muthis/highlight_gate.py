# src/muthis/highlight_gate.py
"""
Draw circuit breaker — ONE draw per user turn, UNIFIED over BOTH draw tools
(highlight_target AND draw_shapes).

Keeping the screenshot attached across the agentic loop (the previous fix) made
Claude re-see its own target, forget it already pointed, and call
highlight_target again and again until the budget cap — never explaining. This
is the HARD backstop, belt-and-suspenders with the persona / tool_result
directive (turn.py): the FIRST draw of a turn — whichever tool asked — draws;
every later draw call is suppressed (no redraw) and its tool_result tells
Claude to stop drawing and explain now. Because both tools flip the SAME
gate.drawn, loop_tool_choice forces tool_choice="none" on the pass after ANY
draw — Claude cannot draw again with either tool and must explain in text.

State is per-turn and resets BY CONSTRUCTION — the orchestrator builds a fresh
HighlightGate at the top of every _run_turn_pipeline, so there is nothing to
reset by hand and no state can leak between user turns. Lives in its own module
(pure stdlib) because orchestrator.py is at the ≤300-line ceiling and turn.py is
near it — split, don't compress (AGENTS.md §17.4).
"""

from __future__ import annotations

from dataclasses import dataclass


from typing import Optional


@dataclass
class HighlightGate:
    """Per-user-turn control flag for the draw circuit breaker — ONE gate
    covering BOTH draw tools. Distinct from TurnResult (what happened) — this
    is the loop's control state.

    `drawn` flips True once the first draw of the turn (highlight_target OR
    draw_shapes) has been answered; while it is True the overlay is never
    redrawn and every further draw call — same tool or the other — is answered
    with its 'already shown — explain now' note."""

    drawn: bool = False


# ─── The two tool_result surfaces (user-invisible API transcript, never TTS) ──
#
# A highlight_target id MUST be answered with a tool_result or the next provider
# turn 400s on an orphan. These carry NO screenshot (the cyan rectangle is
# already on the user's real screen) and are never spoken — they live only in
# the transcript to steer Claude.
#
# Circuit breaker (prompt half) — this is the FIRST thing Claude reads on the
# forced-text pass 2, so it is a COMMAND to explain NOW, NOT a status report.
# Any completion lead ("تم وضع المؤشّر …", let alone "بنجاح") read as task-done
# and produced a bare ack ("أبشر، أشرت لك"); instead we open by naming it an
# INTERNAL directive the user never hears, then order the explanation to START
# with the actual information (no "تم"-style lead of its own).
HIGHLIGHT_ACK_TEXT_AR = (
    "توجيه داخلي (لا يراه المستخدم): المؤشّر صار ظاهراً على العنصر. الآن قدّم "
    "شرحك مباشرةً — ما هو هذا العنصر وما وظيفته ولماذا — وابدأ بالمعلومة من أول "
    "كلمة بدون أي مقدمة أو تأكيد (لا \"أبشر\"، ولا \"أشرت لك\"، ولا \"تم\"). "
    # v1.0-RC2 (UAT bug 2, measured live): pass 2 sometimes came back as the
    # pass-1 ack VERBATIM and nothing else — name the failure and its cost.
    "وممنوع أن تكرر كلمات تأكيدك السابقة (\"أبشر، شوف\" ونحوها): ردّ هذا الدور "
    "هو الشرح نفسه لا غير، وإن لم تقل الشرح الآن فلن يسمع المستخدم شرحاً أبداً."
)
# Sent for the SECOND+ highlight_target of a turn (hard backstop): the overlay
# was NOT redrawn — forbid re-pointing AND force the explanation now (same as
# the ack: start with the information, no completion framing).
HIGHLIGHT_ALREADY_SHOWN_AR = (
    "المؤشّر معروض على العنصر. لا تستدعِ highlight_target مرة أخرى — قدّم شرحك "
    "الآن مباشرةً بالمعلومة (ما هو وما وظيفته ولماذا) بدون أي مقدمة أو تأكيد."
)
# draw_shapes twins of the two texts above — same philosophy: an INTERNAL
# directive ordering the explanation NOW, never a completion report.
SHAPES_ACK_TEXT_AR = (
    "توجيه داخلي (لا يراه المستخدم): الرسم صار ظاهراً على الشاشة. الآن قدّم "
    "شرحك مباشرةً — ما الذي يوضّحه الرسم ولماذا — وابدأ بالمعلومة من أول كلمة "
    "بدون أي مقدمة أو تأكيد (لا \"أبشر\"، ولا \"رسمت لك\"، ولا \"تم\"). "
    "وممنوع أن تكرر كلمات تأكيدك السابقة (\"أبشر، شوف\" ونحوها): ردّ هذا الدور "
    "هو الشرح نفسه لا غير، وإن لم تقل الشرح الآن فلن يسمع المستخدم شرحاً أبداً."
)
SHAPES_ALREADY_SHOWN_AR = (
    "الرسم معروض على الشاشة. لا تستدعِ draw_shapes أو highlight_target مرة "
    "أخرى — قدّم شرحك الآن مباشرةً بالمعلومة بدون أي مقدمة أو تأكيد."
)


def draw_result_text(gate: Optional[HighlightGate], tool_name: str) -> str:
    """Pick the tool_result text for EITHER draw tool and advance the ONE
    per-turn gate: the first draw of the turn — whichever tool — gets its
    'explain now' ack and flips gate.drawn; every later draw call (same tool
    or the other, this pass or a future one) gets its 'already shown' note.
    This is what makes the gate UNIFIED: both tools read and flip the same
    `drawn` flag. No gate → always the ack (legacy)."""
    ack, already = (
        (SHAPES_ACK_TEXT_AR, SHAPES_ALREADY_SHOWN_AR)
        if tool_name == "draw_shapes"
        else (HIGHLIGHT_ACK_TEXT_AR, HIGHLIGHT_ALREADY_SHOWN_AR)
    )
    if gate is None:
        return ack
    if gate.drawn:
        return already
    gate.drawn = True
    return ack


def highlight_result_text(gate: Optional[HighlightGate]) -> str:
    """highlight_target-only wrapper kept for existing callers/tests —
    delegates to draw_result_text (the unified gate)."""
    return draw_result_text(gate, "highlight_target")


def loop_tool_choice(gate: HighlightGate) -> str:
    """The HARD loop terminator: once ANYTHING has been drawn this turn
    (gate.drawn — set by the first highlight_target OR draw_shapes pairing),
    the NEXT agentic run() is made with tool_choice="none" so Claude CANNOT
    call a tool and MUST emit its explanation as text → stop_reason becomes
    end_turn → the loop ends. "auto" until then, so the first draw AND any
    request_screen_refresh still work (a refresh never sets gate.drawn). This
    is the API-enforced brake; the draw-suppression in turn.next_highlight /
    draw_dispatch.next_draw is the belt-and-suspenders."""
    return "none" if gate.drawn else "auto"


# v7 Phase 3 (barge-in): the next-turn context note — an INTERNAL directive
# (the persona's v5-B3 rule: obeyed, never read aloud or quoted) telling the
# model its previous reply was cut off MID-SPEECH by the user, so it neither
# assumes the explanation was heard nor takes offense at the interruption.
INTERRUPTED_NOTE_AR = (
    "(توجيه داخلي من النظام، ليس من كلام المستخدم ولا يراه: قاطعك المستخدم "
    "قبل اكتمال نطق ردّك السابق — لبِّ طلبه الجديد مباشرة، واعلم أنه لم "
    "يسمع شرحك السابق كاملاً.)"
)


__all__ = [
    "HighlightGate", "HIGHLIGHT_ACK_TEXT_AR", "HIGHLIGHT_ALREADY_SHOWN_AR",
    "SHAPES_ACK_TEXT_AR", "SHAPES_ALREADY_SHOWN_AR", "INTERRUPTED_NOTE_AR",
    "draw_result_text", "highlight_result_text", "loop_tool_choice",
]
