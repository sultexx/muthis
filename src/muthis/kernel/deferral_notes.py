# src/muthis/kernel/deferral_notes.py
"""
deferral_notes.py — WHAT THE ROUTED FAMILIES ARE, and what an UNSERVICED id is told.

Extracted from `tool_result_pairing.py` under the ≤300-line law (2026-08-02) — a
MOVE ONLY, proven by dumping every public symbol and every branch of
`build_tool_result_message` before and after and requiring the two byte-identical.

WHY THE T4-NAMED SEAM WAS NOT THE ONE TAKEN. That seam named a
`{tool_name: busy_note}` TABLE replacing the two structurally identical routed
arms. Its premise was that both arms are UNCONDITIONAL — serviced id gets the
content, every other id gets that family's ONE note. DEC-58 had already made the
doc arm CONDITIONAL, and the pending web fix makes the web arm conditional the same
way, so a flat table can express NEITHER. Measured at execution (DEC-56): the named
seam saves ~8 lines of a 30-line breach, because the cost is in the NOTES and the
table does not move them. The seam was NAMED at planning time and RE-MEASURED at
execution, which is exactly what DEC-52 and DEC-56 require.

THE SPLIT THAT IS ACTUALLY THERE: *which note an unserviced id receives* is a
different responsibility from *pair every tool_use with a tool_result*. The first
grows every milestone (+33 measured per capability); the second has been stable
since it was written. Separating them puts the growth in a module that exists to
hold it.

EVERY NOTE HERE OBEYS THE STANDING NOTE LAW (AGENTS.md, ruled in DEC-58): it states
what WAS accomplished, whether the condition is TERMINAL or TRANSIENT, and the valid
NEXT STEP. A refusal that reports only what did not happen produces a retry loop.

RE-EXPORTED from `tool_result_pairing.py`, so no importer changed: the dependency
runs pairing → notes and nothing cycles (the `router_surfaces.py` precedent;
contrast `core_router.py`, which could not be re-exported because its dependency
ran the other way). A LEAF module — it imports the protocol, the file-read surface
and the namespace helper, and never `turn` or `tool_result_pairing`.
"""

from __future__ import annotations

from typing import Any, Optional

from ..cloud.protocol import ToolCall
from ..file_reader import READ_FILE_TOOL
from .ack_scope import ACK_SCOPE_AR
from .step_verification import (
    EVIDENCE_ARG, FAIL_CLOSED_OUTCOME, RESULT_PROVEN, verification_from,
)
from .tool_router import namespaced_name

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
#
# T6 BLOCKING FIX — THE NOTE, NEVER THE SLOT. The one-serviced-call-per-pass
# bound STAYS: it protects the Phase-4 read bound and widening it is a design
# decision, not a reaction to a bug. What was broken was this note. `doc_rag` is
# the FIRST capability whose two tools form a MANDATORY SEQUENCE — you cannot
# query what you have not opened — so a model that plans BOTH in one message is
# behaving correctly. The old text said only "ask again in the next step" and
# said NOTHING about the open having succeeded, so a competent agent re-issued
# its WHOLE plan, open first: a full re-ingestion (18 s of silence, another index
# in RAM) per retry until the agentic cap fired. Measured live.
#
# So there are TWO notes, because the STATE ACHIEVED differs and the standing
# note law (AGENTS.md) requires each note to report the state it actually
# reached. One text claiming "the document was opened" when the serviced call was
# a QUERY would be a fresh instance of the very defect this fix closes.
DOC_OPENED_ASK_NEXT_AR = (
    "توجيه داخلي (لا يراه المستخدم): فُتح المستند بنجاح وهو جاهز الآن — "
    "لا تفتحه مرة أخرى، فإعادة الفتح تعيد الفهرسة كاملة بلا فائدة. "
    "أخدم طلب مستند واحدًا في كل خطوة تفكير، فأرسل استعلامك في الخطوة التالية "
    "مستخدماً المعرّف الذي أعطيتك إياه."
)

# The serviced doc call was NOT an open (a second query in the same step, or a
# read/web call took the step's one slot). Nothing was opened, so nothing claims
# it — the note states what DID happen, that the condition is TRANSIENT, and the
# one valid next move.
DOC_ONE_PER_PASS_AR = (
    "توجيه داخلي (لا يراه المستخدم): خدمت طلب مستند واحدًا في هذه الخطوة، "
    "وهذا الطلب لم يُنفَّذ بعد — ما صار فيه خطأ ولا تغيّر شي. "
    "أرسله مرة أخرى في الخطوة التالية كما هو."
)


def doc_deferral_note(serviced: Optional[ToolCall]) -> str:
    """WHICH deferral note an unserviced doc id receives, from what was SERVICED.

    The kernel already holds this fact — `read_result` carries the serviced call
    — so reporting it costs nothing and withholding it cost a full re-ingestion
    per retry. Fails SAFE: an unknown or absent serviced call gets the note that
    claims nothing."""
    if serviced is not None and serviced.name == DOC_OPEN_TOOL:
        return DOC_OPENED_ASK_NEXT_AR
    return DOC_ONE_PER_PASS_AR

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

# A PRECONDITION returns a CONFIRMATION, never content, so it CANNOT break the
# one-payload-bearing-result-per-pass invariant — and therefore does not consume
# the pass's slot (ruled 2026-07-31, after the loop bit LIVE three times).
#
# WHAT THE PHASE-4 BOUND ACTUALLY PROTECTED, corrected by measurement: a
# `read_local_file` and a `docs__query` each deliver up to 16,000 chars, while
# `docs__open` delivers 110-320. Expressing the bound as a CALL COUNT guarded the
# wrong quantity by ~100x; it was written that way only because every routed tool
# was payload-bearing at the time. Classifying by ROLE restores the invariant to
# what it always was.
#
# Role-scoped, not family-scoped, on purpose: a future capability with a prepare
# step (Phase 3's Navigator may carry sequences too) inherits this by declaring
# its tool here, with NO family table to maintain.
PRECONDITION_TOOLS = frozenset({DOC_OPEN_TOOL})

# T4: the two MODE verbs. **KERNEL-SERVICED** (DEC-73), so they are deliberately
# NOT in `ROUTER_SERVICED_TOOLS` — no router, no plugin and no capability is
# involved in their effect. But they MUST be answered BY NAME for exactly the
# reason every routed family above is: an id nobody answers falls through to the
# LOOK-only `else`, receives the POINTER ack, flips the per-turn draw gate and
# hard-terminates the turn. That is DEC-39, and it is the M2 bug this ordering
# rule was written from — which is why this constant and the arm that reads it
# land BEFORE the mount that makes the tools reachable.
NAV_PLAN_TOOL = namespaced_name("navigator", "plan")
NAV_STEP_TOOL = namespaced_name("navigator", "step")
# DEC-108 Gate 2A: the THIRD verb joins the set BEFORE the mount that makes it
# reachable — the same ordering as the two above, for the same reason, one
# milestone later. Gate 2B gave it the servicing arm below; the mount follows
# that arm, never the other way round.
NAV_VERIFY_TOOL = namespaced_name("navigator", "verify")
NAV_TOOLS = frozenset({NAV_PLAN_TOOL, NAV_STEP_TOOL, NAV_VERIFY_TOOL})

# ONE note for both verbs and every unserviced id: the state achieved is
# identical (nothing moved, nothing broke) and the valid next move is identical,
# so two wordings would be a distinction without a difference — DEC-70's
# reasoning rather than DEC-58's, and the test is which of those two applies,
# never the count of notes.
NAV_ONE_PER_PASS_AR = (
    "توجيه داخلي (لا يراه المستخدم): أخدم حركة مسار واحدة في كل خطوة تفكير، "
    "وهذه الحركة ما نُفِّذت وما تغيّر شي ولا صار خطأ. "
    "اطلبها مرة أخرى في الخطوة التالية كما هي. "
    f"{ACK_SCOPE_AR}."
)

# ─── DEC-108 Gate 2B: what a SERVICED `navigator__verify` is told ────────────
#
# THREE NOTES, AND THE COUNT IS THE ANSWER TO DEC-58-versus-DEC-70 RATHER THAN A
# PREFERENCE. The one-note ruling above applies when the state achieved AND the
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
    "DOC_ONE_PER_PASS_AR",
    "NAV_ONE_PER_PASS_AR",
    "NAV_PLAN_TOOL",
    "NAV_STEP_TOOL",
    "NAV_TOOLS",
    "NAV_VERIFY_TOOL",
    "VERIFY_NO_EVIDENCE_AR",
    "VERIFY_NO_STEP_AR",
    "VERIFY_READ_AR",
    "verification_note",
    "DOC_OPENED_ASK_NEXT_AR",
    "DOC_OPEN_TOOL",
    "DOC_QUERY_TOOL",
    "DOC_TOOLS",
    "PRECONDITION_TOOLS",
    "ROUTER_SERVICED_TOOLS",
    "RUN_CODE_ALREADY_AR",
    "RUN_CODE_TOOL",
    "RUN_CODE_UNAVAILABLE_AR",
    "WEB_FETCH_TOOL",
    "WEB_ONE_PER_PASS_AR",
    "WEB_SEARCH_TOOL",
    "WEB_TOOLS",
    "doc_deferral_note",
]
