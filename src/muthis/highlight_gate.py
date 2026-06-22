# src/muthis/highlight_gate.py
"""
Highlight circuit breaker — ONE highlight_target draw per user turn.

Keeping the screenshot attached across the agentic loop (the previous fix) made
Claude re-see its own target, forget it already pointed, and call
highlight_target again and again until the budget cap — never explaining. This
is the HARD backstop, belt-and-suspenders with the persona / tool_result
directive (turn.py): the FIRST highlight of a turn draws; every later one is
suppressed (no redraw) and its tool_result tells Claude to stop pointing and
explain now.

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
    """Per-user-turn control flag for the highlight circuit breaker. Distinct
    from TurnResult (what happened) — this is the loop's control state.

    `drawn` flips True once the first highlight_target of the turn has been
    answered; while it is True the overlay is never redrawn and every further
    highlight_target is answered with the 'already shown — explain now' note."""

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
    "كلمة بدون أي مقدمة أو تأكيد (لا \"أبشر\"، ولا \"أشرت لك\"، ولا \"تم\")."
)
# Sent for the SECOND+ highlight_target of a turn (hard backstop): the overlay
# was NOT redrawn — forbid re-pointing AND force the explanation now (same as
# the ack: start with the information, no completion framing).
HIGHLIGHT_ALREADY_SHOWN_AR = (
    "المؤشّر معروض على العنصر. لا تستدعِ highlight_target مرة أخرى — قدّم شرحك "
    "الآن مباشرةً بالمعلومة (ما هو وما وظيفته ولماذا) بدون أي مقدمة أو تأكيد."
)


def highlight_result_text(gate: Optional[HighlightGate]) -> str:
    """Pick a highlight_target tool_result text and advance the gate: the first
    highlight of the turn gets the 'explain now' ack (and flips gate.drawn), the
    rest get the 'already shown' note. No gate → always the ack (legacy)."""
    if gate is None:
        return HIGHLIGHT_ACK_TEXT_AR
    if gate.drawn:
        return HIGHLIGHT_ALREADY_SHOWN_AR
    gate.drawn = True
    return HIGHLIGHT_ACK_TEXT_AR


def loop_tool_choice(gate: HighlightGate) -> str:
    """The HARD loop terminator: once a highlight has been drawn this turn
    (gate.drawn), the NEXT agentic run() is made with tool_choice="none" so
    Claude CANNOT call a tool and MUST emit its explanation as text →
    stop_reason becomes end_turn → the loop ends. "auto" until then, so the
    first point AND any request_screen_refresh still work (a refresh never sets
    gate.drawn). This is the API-enforced brake; the draw-suppression in
    next_highlight is the belt-and-suspenders."""
    return "none" if gate.drawn else "auto"


__all__ = [
    "HighlightGate", "HIGHLIGHT_ACK_TEXT_AR", "HIGHLIGHT_ALREADY_SHOWN_AR",
    "highlight_result_text", "loop_tool_choice",
]
