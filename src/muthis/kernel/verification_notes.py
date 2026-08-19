# src/muthis/kernel/verification_notes.py
"""
What a SERVICED `navigator__verify` is told — extracted from `deferral_notes.py`
under the ≤300-line law (DEC-108 Gate 2C), a MOVE ONLY.

WHY THE MOVE HAPPENED HERE AND NOT LATER. `deferral_notes.py` was pinned at
283/300 one commit earlier, on Sultan's ruling, and that pin's stated purpose was
to make the NEXT arrival meet a declared number rather than a green suite. This
is that next arrival: Gate 2C's state machine gives every outcome a real
consequence, so the notes must say what it is — and a note that reports a
consequence is longer than one that reports none. The pin did its job on the
first attempt to grow the file, which is the whole argument for pinning a module
that is DESIGNED to grow.

THE SEAM IS REAL, NOT A LINE BUDGET. `deferral_notes.py` answers *what an
UNSERVICED id is told* — the deferral families, one note each, chosen by which
call took the pass's one slot. This module answers *what a SERVICED verification
is told*, which is chosen by the OUTCOME the model represented and by the
transition that followed it. The two change for different reasons: the first
grows when a new tool family arrives, the second when the state machine's
consequences change.

EVERY NOTE HERE OBEYS THE STANDING NOTE LAW (AGENTS.md, ruled in DEC-58): what
WAS accomplished, whether it is TERMINAL or TRANSIENT, and the valid NEXT STEP.
A refusal that reports only what did not happen produces a retry loop.

AND EVERY ENUMERATION NAME IS DERIVED, never spelled: a note that hand-wrote
`RESULT_PROVEN` would drift from the enumeration it describes, and the drift
would be invisible — the model would read a name the kernel no longer knows.
"""

from __future__ import annotations

from typing import Any

from .ack_scope import ACK_SCOPE_AR
from .deferral_notes import NAV_PLAN_TOOL, NAV_STEP_TOOL
from .step_verification import (
    EVIDENCE_ARG, FAIL_CLOSED_OUTCOME, RESULT_PROVEN, verification_from,
)

# ─── DEC-108 Gate 2B: what a SERVICED `navigator__verify` is told ────────────
#
# THREE NOTES, AND THE COUNT IS THE ANSWER TO DEC-58-versus-DEC-70 RATHER THAN A
# PREFERENCE. DEC-70's one-note ruling applies when the state achieved AND the
# valid next move are identical; here neither is. A verification that was READ
# leaves the walkthrough where it was and the next move is the ordinary one; a
# PROVEN claim that carried no evidence was NOT licensed and the next move is to
# verify again WITH the evidence; and a verify with no active step applies to
# nothing at all and the next move is a different verb entirely. Three states,
# three next moves, three notes — DEC-58's test, applied and shown.
#
# NONE OF THEM REPORTS A CONSEQUENCE, because at Gate 2B there is none: the
# outcome is derived and answered, and NOTHING advances, holds or falls back.
# The state machine is Gate 2C's, and a note that promised its effects early
# would be the "TRUE statement on a FALSE mechanism" this project has already
# paid for once.
VERIFY_READ_AR = (
    "توجيه داخلي (لا يراه المستخدم): استلمت تحقّقك للخطوة الحالية وقرأته "
    "«{outcome}»، وما تغيّر شي ولا صار خطأ. "
    "التحقّق وحده لا يحرّك الخطوة — التقدّم يبقى عبر "
    f"«{NAV_STEP_TOOL}» كالمعتاد. {ACK_SCOPE_AR}."
)

# The FAIL-CLOSED downgrade, said OUT LOUD. `RESULT_PROVEN` with no evidence is
# unrepresentable (Gate 2A), so it becomes the recoverable outcome — and a
# downgrade the model is never told about is precisely the silent failure DEC-91
# measured a provider committing and DEC-107 refused to re-create in our own
# code. Every name in it is DERIVED from the kernel's own constants: a note that
# spelled them by hand would drift from the enumeration it describes.
VERIFY_NO_EVIDENCE_AR = (
    f"توجيه داخلي (لا يراه المستخدم): طلبت «{RESULT_PROVEN}» بلا دليل، فما "
    f"اعتمدته وقرأت الحالة «{FAIL_CLOSED_OUTCOME}». الخطوة ما تحرّكت ولا صار خطأ. "
    f"أعد التحقّق في الخطوة التالية واذكر في «{EVIDENCE_ARG}» الشيء الذي تراه "
    f"فعلاً على الشاشة ويثبت النتيجة المتوقّعة. {ACK_SCOPE_AR}."
)

VERIFY_NO_STEP_AR = (
    "توجيه داخلي (لا يراه المستخدم): ما في خطوة نشطة الآن، فالتحقّق ما ينطبق "
    "على شيء وما صار خطأ. "
    f"إن كان المستخدم في مهمة متعدّدة الخطوات فابدأ مساراً بـ«{NAV_PLAN_TOOL}»، "
    f"وإلا فأكمل إجابتك عادي بلا تحقّق. {ACK_SCOPE_AR}."
)


def verification_note(args: Any, *, has_active_step: bool) -> str:
    """WHICH note a SERVICED `navigator__verify` receives (DEC-108 Gate 2B, P4).

    `doc_deferral_note`'s shape at the same seam: the kernel already holds every
    fact this needs, so reporting it costs nothing and withholding it costs a
    retry that repeats the same mistake.

    THE KERNEL VALIDATES REPRESENTATION, NOT TRUTH. The outcome is derived by
    `step_verification` from membership and presence alone; nothing here reads
    the expected result, parses the evidence or judges whether what the model
    described is what the screen showed. The one comparison made is
    STRUCTURAL — did the claim survive the derivation — and it exists so the
    downgrade is spoken rather than silent.

    Fails SAFE in both directions: no active step claims nothing, and an
    unparseable payload arrives here already narrowed to the fail-closed
    outcome."""
    if not has_active_step:
        return VERIFY_NO_STEP_AR
    verification = verification_from(args)
    if verification.claimed == RESULT_PROVEN and verification.outcome != RESULT_PROVEN:
        return VERIFY_NO_EVIDENCE_AR
    return VERIFY_READ_AR.format(outcome=verification.outcome)


__all__ = [
    "VERIFY_NO_EVIDENCE_AR",
    "VERIFY_NO_STEP_AR",
    "VERIFY_READ_AR",
    "verification_note",
]
