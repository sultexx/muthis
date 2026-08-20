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

from .ack_scope import ACK_SCOPE_AR
from .deferral_notes import NAV_PLAN_TOOL
from .step_verification import (
    EVIDENCE_ARG, FALLBACK, FAIL_CLOSED_OUTCOME, RESULT_PROVEN,
    StepVerification,
)

# ─── FIVE NOTES, AND THE COUNT IS DEC-58's TEST APPLIED ─────────────────────
#
# DEC-70's one-note ruling applies when the state achieved AND the valid next
# move are identical. Here there are five of each: the step ADVANCED · the step
# HELD · the step fell back to the USER's word · a PROVEN claim arrived with no
# evidence and was not licensed · and there was no active step to verify at all.
# Five states, five next moves, five notes.
#
# GATE 2C IS WHERE THEY GAINED CONSEQUENCES. At Gate 2B every outcome was read
# and answered and NOTHING followed, and the notes said exactly that, because a
# note that promised effects the machine did not yet have would be the "TRUE
# statement on a FALSE mechanism" this project has already paid for once. The
# machine exists now, so the notes report what it did — and the sentence that
# said the verification moves nothing is GONE rather than left to age.
VERIFY_ADVANCED_AR = (
    "توجيه داخلي (لا يراه المستخدم): أثبتّ نتيجة الخطوة، فقدّمت المسار خطوةً "
    "واحدة. اشرح الخطوة الجديدة كما هي عندي الآن، ولا تعيد شرح الخطوة السابقة "
    "ولا تعلن رقماً لم أعطك إياه. "
    f"{ACK_SCOPE_AR}."
)

# NOT PROVEN, and the UX ruling is inside the note: **the step explanation is
# NOT repeated.** DEC-106 ruled it, and the reason is that a repeat reads as
# "you did it wrong" when the honest state is "I have not seen it yet". The step
# stays active and the NEXT F9 attempts again — no timer, no nudge, no retry
# loop of our own making.
VERIFY_HOLDING_AR = (
    "توجيه داخلي (لا يراه المستخدم): ما ظهرت النتيجة بعد، فالخطوة باقية كما "
    "هي وما صار خطأ. **لا تعيد شرح الخطوة** ولا تسأل المستخدم هل أنهاها — "
    "أكمل إجابتك عادي، وسأعيد المحاولة في الدورة القادمة. "
    f"{ACK_SCOPE_AR}."
)

# UNOBSERVABLE — and this is the ONE note that asks the model to SPEAK, because
# DEC-106 ruled that the fallback is announced rather than silent. It carries
# the distinction the ruling is built on: **"I cannot verify this from this
# screen" is about MUT'HIS, and "your action failed" is about the USER** — a
# capability boundary reported as a user error is the failure this wording
# exists to prevent. It never quotes the expected result: that text is internal
# to the plan contract, the kernel never reads it (DEC-66), and a note cannot
# leak what the kernel never holds.
VERIFY_FALLBACK_AR = (
    "توجيه داخلي (لا يراه المستخدم): ما أقدر أتحقّق من هذه الخطوة من الشاشة "
    "الحالية — هذا حدّ في رؤيتي أنا، وليس معناه أن ما فعله المستخدم فشل. "
    "قل له ذلك بوضوح وبهذا الفرق، واطلب منه أن يخبرك حين ينتهي من الخطوة، "
    "ثم تابع عادي. لا تذكر النتيجة المتوقّعة نصّاً. "
    f"{ACK_SCOPE_AR}."
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


def verification_note(verification: StepVerification, *, state: str,
                      advanced: bool) -> str:
    """WHICH note a SERVICED `navigator__verify` receives (DEC-108 Gate 2C, P4).

    `doc_deferral_note`'s shape at the same seam: the kernel already holds every
    fact this needs, so reporting it costs nothing and withholding it costs a
    retry that repeats the same mistake.

    IT REPORTS WHAT HAPPENED, NEVER WHAT WAS ASKED FOR. `advanced` is what the
    AUTHORITY did, not what the outcome wanted — a proven last step is refused
    at the bound like any other advance, and its note is the authority's own.
    So the arm passes in the applied result and this function never guesses it.

    THE KERNEL VALIDATES REPRESENTATION, NOT TRUTH. The outcome was derived by
    `step_verification` from membership and presence alone; nothing here reads
    the expected result, parses the evidence or judges whether what the model
    described is what the screen showed. The one comparison made is
    STRUCTURAL — did the claim survive the derivation — and it exists so the
    fail-closed downgrade is spoken rather than silent."""
    if verification.claimed == RESULT_PROVEN and verification.outcome != RESULT_PROVEN:
        return VERIFY_NO_EVIDENCE_AR
    if advanced:
        return VERIFY_ADVANCED_AR
    if state == FALLBACK:
        return VERIFY_FALLBACK_AR
    return VERIFY_HOLDING_AR


__all__ = [
    "VERIFY_ADVANCED_AR",
    "VERIFY_FALLBACK_AR",
    "VERIFY_HOLDING_AR",
    "VERIFY_NO_EVIDENCE_AR",
    "VERIFY_NO_STEP_AR",
    "verification_note",
]
