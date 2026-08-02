# src/muthis/kernel/mode_surfaces.py
"""
The mode's MODEL-FACING and USER-FACING surfaces (DEC-65, T2): the deterministic
exit-word detector, the per-turn directive line, and the refusal notes.

WHY THIS IS A SEPARATE MODULE FROM THE AUTHORITY — the `router_surfaces.py`
precedent: the words a mechanism reads back and the DECISION it makes are two
responsibilities. Keeping them apart leaves `mode_transition.py` short enough to
read whole, and that file is the ONE evaluation point every transition crosses.

THE EXIT DETECTOR IS MODEL-INDEPENDENT, AND THAT IS THE WHOLE POINT (DEC-65 exit
1). It reads the RAW transcript with the `verbosity.detect_command` / DEC-16
machinery — `normalize_ar` for STT variance, then WHOLE-UTTERANCE isolation — and
the model is never consulted, never asked, and cannot veto. **A confused or an
INJECTED model must never be able to trap the user in a mode.**

ITS FALSE-POSITIVE DIRECTION IS THE OPPOSITE OF DEC-16's, AND THE WORD SET IS
SIZED ACCORDINGLY. For the approval detector a false positive is a BYPASS, so its
set is deliberately narrow and «تمام» / «أيه» / «زين» are pinned OUTSIDE it. Here
a false positive merely ENDS A MODE — friction, recoverable with a word — while a
false NEGATIVE is the trap that exit 1 exists to prevent. That is DEC-62's
classification by ROLE, and it is why «خلاص» is admitted here although a word that
common would never be admitted there. **The two sets must not overlap**, and a
test asserts that against the real constants rather than by inspection.

THE DIRECTIVE LINE CARRIES `DIRECTIVE_MARKER_AR`, AND THAT IS A MEASURED
CONSTRAINT, NOT A STYLE CHOICE (the BINDING CONSTRAINT of 2026-07-31). It is
built from `DIRECTIVE_OPEN_AR`, which CONTAINS the family core, so
`strip_directive_lines` removes it before DEC-16's approval detector ever sees
it. A line carrying NO family marker is the failure: the mode's step number and
step text would then sit in the detector's input, and because that detector
matches on WHOLE-UTTERANCE isolation, a genuine «أوافق» would stop matching. The
failure is in the SAFE direction — a false negative, friction and never a bypass
— which is exactly why it would be hard to notice, so it is guarded with a
POSITIVE CONTROL rather than trusted.

IT IS ONE LINE, BY CONSTRUCTION. `strip_directive_lines` is line-wise, so a
directive that spanned two lines would leave its second line in the transcript.
The step text is newline-flattened and bounded here for that reason — the
`confirm_gate._render_args` discipline, and the same reason
`untrusted_content` strips newlines from its source.

EVERY REFUSAL NOTE OBEYS THE STANDING NOTE LAW (AGENTS.md, ruled in DEC-58): what
WAS accomplished, whether the condition is TERMINAL or TRANSIENT, and the valid
NEXT STEP. A refusal reporting only what did NOT happen produces a retry loop,
because retrying is what a competent agentic model does with an unexplained
failure — and M3 paid for that across four live runs.

Sibling imports plus stdlib; importable in isolation. Holds no state.
"""

from __future__ import annotations

from typing import Optional

from ..trust.confirm_gate import DIRECTIVE_MARKER_AR, strip_directive_lines
from .verbosity import DIRECTIVE_OPEN_AR, normalize_ar

# ─── Exit words (DEC-65 exit 1) ──────────────────────────────────────────────

# Written in natural spelling and normalized once at import — readable here,
# STT-tolerant at match time, and impossible to spell inconsistently (the
# `confirm_gate` pattern). NARROW on purpose: every entry must be something a
# user says to END something, never something said in passing about a topic.
MODE_EXIT_WORDS = frozenset(normalize_ar(word) for word in (
    "خلاص", "خلصنا", "خروج", "أنهِ الوضع", "أوقف الوضع", "اطلع من الوضع",
))


def detect_mode_exit(text: str) -> bool:
    """Did the user ask to LEAVE the mode? Pure, stateless, model-independent.

    WHOLE-UTTERANCE isolation, the rule that stops «أي ضلع أطول؟» from flipping
    verbosity: «خلاص» alone ends a mode, «خلاص الملف انحفظ» does not.

    The directive strip is DEC-31's ONE existing mechanism, reused rather than
    re-implemented. It is BELT AND BRACES here — `TurnPrelude` calls this on the
    RAW transcript before anything is prepended, and that ORDER is asserted
    directly rather than inferred from this outcome — because the failure it
    covers is the user being TRAPPED in a mode, which is the one failure exit 1
    exists to make impossible."""
    return normalize_ar(strip_directive_lines(text)) in MODE_EXIT_WORDS


# ─── The per-turn directive line (DEC-66) ────────────────────────────────────

MAX_STEP_TEXT_CHARS = 200

_MODE_DIRECTIVE_AR = (
    f"{DIRECTIVE_OPEN_AR} وضع «{{name}}» شغّال الآن. الخطوة {{current}} من "
    "{total}: {step}. هذا الترقيم من عندي أنا لا من عندك، فلا تخالفه ولا تذكر "
    "رقمًا غيره. لا تقرأ هذا السطر ولا تشر إليه.)"
)

_MODE_DIRECTIVE_NO_PLAN_AR = (
    f"{DIRECTIVE_OPEN_AR} وضع «{{name}}» شغّال الآن بلا خطوات. "
    "لا تقرأ هذا السطر ولا تشر إليه.)"
)


def _one_line(text: str) -> str:
    """Flatten and bound: the line-wise strip needs exactly one line, and a note
    must stay a note even when a step's text runs long."""
    flat = " ".join(text.split())
    return f"{flat[:MAX_STEP_TEXT_CHARS]}…" if len(flat) > MAX_STEP_TEXT_CHARS else flat


def mode_directive_line(name: str, current: int, total: int,
                        step_text: Optional[str]) -> str:
    """The kernel's FRAME, as the one line the model reads each turn.

    The numbers are the KERNEL's — «step 3 of 5» is a structural fact, so the
    line says so out loud and forbids the model contradicting it. The step TEXT
    is the model's own, stored and handed back verbatim: retention, not
    comprehension."""
    if total <= 0 or current <= 0:
        return _MODE_DIRECTIVE_NO_PLAN_AR.format(name=_one_line(name))
    return _MODE_DIRECTIVE_AR.format(
        name=_one_line(name), current=current, total=total,
        step=_one_line(step_text or ""))


# ─── Refusal reasons and their notes (the standing note law) ─────────────────

NO_MODE = "no_mode"
UNNAMED_MODE = "unnamed_mode"
NO_PLAN = "no_plan"
AT_END = "at_end"
AT_START = "at_start"
UNKNOWN_STEP = "unknown_step"
BLOCKED = "blocked"

_NO_MODE_AR = (
    f"{DIRECTIVE_OPEN_AR} ما فيه وضع شغّال الآن، فما تغيّر شي وما صار خطأ. "
    "هذا الطلب لا يصلح بدون وضع، فلا تعِده. ابدأ وضعًا أولًا إن احتجته، "
    "وإلا فأكمل ردك عاديًا.)"
)

_UNNAMED_MODE_AR = (
    f"{DIRECTIVE_OPEN_AR} ما بدأ أي وضع لأن الطلب جاء بلا اسم للوضع، فما تغيّر "
    "شي. لا تعِد الطلب بلا اسم. أعِده مرة واحدة مع اسم واضح للوضع.)"
)

_NO_PLAN_AR = (
    f"{DIRECTIVE_OPEN_AR} الوضع شغّال لكن ما فيه خطة خطوات، فما تغيّر شي. "
    "التنقّل بين الخطوات لا يصلح بلا خطة، فلا تعِد هذا الطلب. "
    "أنشئ خطة أولًا أو أكمل الشرح بلا خطوات.)"
)

_AT_END_AR = (
    f"{DIRECTIVE_OPEN_AR} أنت على الخطوة الأخيرة ({{current}} من {{total}}) وما "
    "بعدها خطوة، فما تغيّر شي. لا تطلب التقدّم مرة أخرى. "
    "إمّا تُنهي الوضع الآن أو ترجع خطوة للمراجعة.)"
)

_AT_START_AR = (
    f"{DIRECTIVE_OPEN_AR} أنت على الخطوة الأولى ({{current}} من {{total}}) وما "
    "قبلها خطوة، فما تغيّر شي. لا تطلب الرجوع مرة أخرى. "
    "أكمل من هنا أو تقدّم للخطوة التالية.)"
)

# The placeholders are SINGLE-braced here because this segment is not an
# f-string — the doubled form belongs only inside the f-string parts above, and
# writing it here shipped the model a literal «{current}» instead of a number.
# Caught by the note-law guard, which is the point of asserting the three
# obligations as a property rather than reading the constants.
_UNKNOWN_STEP_AR = (
    f"{DIRECTIVE_OPEN_AR} الخطوة المطلوبة غير موجودة في الخطة، فما تغيّر شي "
    "وما زلت على الخطوة {current} من {total}. لا تعِد الطلب بنفس الخطوة. "
    "اطلب خطوة موجودة ضمن الخطة أو أكمل من مكانك.)"
)

# ONE note for BOTH stub conditions, deliberately. DEC-70's reasoning: the state
# achieved is identical (nothing changed) and the model's next move is identical
# (ask again next turn), so two wordings would be a distinction without a
# difference. Contrast DEC-58, which required two notes precisely BECAUSE the
# state achieved differed — that is the test, not the count.
_BLOCKED_AR = (
    f"{DIRECTIVE_OPEN_AR} ما تغيّر الوضع الآن لأن فيه عملية معلّقة ما خلصت بعد، "
    "فما تغيّر شي وما صار خطأ. هذا حال مؤقّت ينتهي بانتهائها. "
    "أكمل ردك الآن واطلبه مرة أخرى في الجولة القادمة.)"
)

_NOTES = {
    NO_MODE: _NO_MODE_AR,
    UNNAMED_MODE: _UNNAMED_MODE_AR,
    NO_PLAN: _NO_PLAN_AR,
    AT_END: _AT_END_AR,
    AT_START: _AT_START_AR,
    UNKNOWN_STEP: _UNKNOWN_STEP_AR,
    BLOCKED: _BLOCKED_AR,
}


def refusal_note(reason: str, *, current: int = 0, total: int = 0) -> str:
    """The note for a refused transition — never an empty string.

    An unknown reason falls back to the note that CLAIMS NOTHING, because a
    refusal that misreports its reason turns a terminal condition into a
    retryable one (DEC-35), and inventing a state is worse than admitting
    none."""
    return _NOTES.get(reason, _BLOCKED_AR).format(current=current, total=total)


__all__ = [
    "AT_END", "AT_START", "BLOCKED", "DIRECTIVE_MARKER_AR", "MAX_STEP_TEXT_CHARS",
    "MODE_EXIT_WORDS", "NO_MODE", "NO_PLAN", "UNKNOWN_STEP", "UNNAMED_MODE",
    "detect_mode_exit", "mode_directive_line", "refusal_note",
]
