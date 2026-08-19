# src/muthis/kernel/step_verification.py
"""
The THREE-WAY OUTCOME, and NOTHING ELSE (DEC-106's contract, DEC-108 Gate 2A).

DEC-106 ruled three outcomes — `RESULT_PROVEN` advances, `RESULT_NOT_PROVEN_
OBSERVABLE` holds for the next cycle, `RESULT_UNOBSERVABLE` falls back — and
DEC-108 ruled where the machine lives: HERE, in its own module, producing that
outcome from its inputs and nothing else. **It grants itself no mode-transition
authority and no plan advancement.** Transition authority stays in
`mode_transition.py`; `session_mode.py` stores and never interprets.

AND THE LIMIT IS STRUCTURAL RATHER THAN PROMISED — the `navigator_service.py`
asymmetry, applied a second time. That module cannot bypass the single
evaluation point because it is HANDED NO MUTATOR TO CALL. This one is handed
less still: **it takes a mapping and returns a value.** No authority, no mode,
no plan, no frame, no clock and no router crosses this boundary, so "it cannot
advance a step" is not a rule anyone here has to keep — there is nothing here to
advance a step WITH. Every guard below asserts that as an ABSENCE OF MEANS.

THE KERNEL VALIDATES REPRESENTATION, NOT TRUTH (DEC-108 ruling ③). The MODEL
looked at the frame and made the judgement; it returns that judgement through
`navigator__verify`. What this module asks is not *"is that true?"* — it cannot
know — but *"is this a well-formed representation of one of the three outcomes?"*
Two questions and no more: **is the claimed outcome a member of the closed
enumeration, and is the field the strongest outcome requires actually there.**
`expected_result` is never read here, the evidence is never parsed, and no word
of either is compared to anything: DEC-66's law is that the kernel STORES,
NUMBERS and BOUNDS-CHECKS and never INTERPRETS TEXT, and a verifier that read
prose would break it at the one place it would be most tempting to.

FAIL-CLOSED, AND THE FORM IS THE POINT: **`RESULT_PROVEN` IS UNREPRESENTABLE
WITHOUT EVIDENCE — not rejected by a check.** `StepVerification` HAS NO
`outcome` FIELD. There is no slot to put `RESULT_PROVEN` in, so an
evidence-free advance is not a bad value this module refuses; it is a value this
module CANNOT HOLD. `outcome` is DERIVED from the two fields that do exist, and
**inside every function body in this file the name `RESULT_PROVEN` appears only
as a comparison operand — never returned, never assigned** — so the single path
by which it can leave this module is `return self.claimed`, which both checks
run in front of. That is the `SessionMode` precedent — nesting was
made impossible to EXPRESS rather than blocked, because a guard that rejects a
bad write is a guard someone can forget to call — and DEC-107 Gate 4's, one
milestone later.

THE FAIL-CLOSED DESTINATION IS `RESULT_NOT_PROVEN_OBSERVABLE`, AND IT IS ONE
NAMED CONSTANT SO THAT CHOICE CAN BE OVERRULED IN ONE LINE. Both non-advancing
outcomes would satisfy "never advance", so the choice between them is real:
`RESULT_UNOBSERVABLE` is DEC-106's declared CAPABILITY BOUNDARY — a statement
about the VIEWPOINT — and its state has exactly one exit, the user's own
declaration, and never returns to verifying for that step (invariant ⑤). A
malformed payload says nothing whatever about the viewpoint; it is a
representation failure, and spending an unrecoverable fallback on one would
answer a question nobody asked. `RESULT_NOT_PROVEN_OBSERVABLE` holds the step
and retries at the next F9, which is the recoverable non-advancing outcome and
the only one that matches what actually went wrong.

TOTAL BY CONSTRUCTION. Every input — a missing key, a list where a string
belongs, an outcome spelled wrong, an integer, `None`, no mapping at all —
yields one of the three outcomes and never an exception. `navigator_service.py`
NEVER RAISES for the same reason and it is the same reason again: these are
model-authored JSON arguments and may be anything.

Pure stdlib; importable in isolation.
"""

from __future__ import annotations

import dataclasses
from typing import Any

# ─── The CLOSED enumeration (DEC-106) ────────────────────────────────────────
# The model-facing spellings. `muthis_plugins/` may not import `muthis.*` (the
# layering law), so the tool schema spells these a second time and a test pins
# the two lists EQUAL — a drift would make the kernel fail-close every genuine
# advance in silence, which is the quietest failure this contract has.
RESULT_PROVEN = "RESULT_PROVEN"
RESULT_NOT_PROVEN_OBSERVABLE = "RESULT_NOT_PROVEN_OBSERVABLE"
RESULT_UNOBSERVABLE = "RESULT_UNOBSERVABLE"

OUTCOMES = (RESULT_PROVEN, RESULT_NOT_PROVEN_OBSERVABLE, RESULT_UNOBSERVABLE)

# Where anything malformed lands. See the module docstring: one constant, one
# line to overrule, and the reasoning recorded beside it rather than inferred
# from the value.
FAIL_CLOSED_OUTCOME = RESULT_NOT_PROVEN_OBSERVABLE

# The model-facing argument names. Named rather than spelled at the two use
# sites, because the schema and the reader must agree and one home is how they
# stay agreed.
OUTCOME_ARG = "outcome"
EVIDENCE_ARG = "evidence"

# Bounds on model-authored text, the `navigator_service.MAX_STEP_CHARS` shape.
# The evidence is a sentence about what is on screen, not a transcript; the
# claimed outcome is one enumeration member and anything longer is already not
# one. Neither value is read — they are BOUNDED, which is what DEC-66 permits.
MAX_EVIDENCE_CHARS = 300
MAX_CLAIM_CHARS = 60


def _narrowed(raw: Any, limit: int) -> str:
    """A model-authored string, collapsed to ONE bounded line — or empty.

    `navigator_service._one_line`'s shape, and DELIBERATELY NOT IMPORTED FROM
    IT: this module's whole property is that it imports nothing that could act,
    and reaching into the servicing layer for one expression would trade that
    for a saved line. The duplication is the cheaper half of the trade and is
    recorded here so it reads as a decision rather than an oversight."""
    return " ".join(raw.split())[:limit] if isinstance(raw, str) else ""


@dataclasses.dataclass(frozen=True)
class StepVerification:
    """ONE verification, as REPRESENTED by the model.

    TWO FIELDS, AND NEITHER OF THEM IS THE OUTCOME. `claimed` is what the model
    said; `evidence` is what it offered for the one outcome that requires an
    offer. The outcome is a FUNCTION of the two, computed on read, so there is
    no assignment anywhere — in this module or in any future caller — that can
    set `RESULT_PROVEN` beside an empty evidence field.

    `claimed` is kept rather than discarded on purpose: a caller that wants to
    know the model asked for an advance it could not license (for a note, for a
    measurement, for the Gate 3 observation) reads it here instead of
    re-deriving it from a payload the kernel has already narrowed."""

    claimed: str
    evidence: str

    @property
    def outcome(self) -> str:
        """The three-way outcome — the ONLY value the rest of the kernel acts on.

        Two questions, in the order that makes the second meaningful: is this a
        member of the closed enumeration, and — for the one outcome that
        advances a step — did the evidence the representation requires actually
        arrive? Anything else is the fail-closed outcome."""
        if self.claimed not in OUTCOMES:
            return FAIL_CLOSED_OUTCOME
        if self.claimed == RESULT_PROVEN and not self.evidence:
            return FAIL_CLOSED_OUTCOME
        return self.claimed


def verification_from(args: Any) -> StepVerification:
    """ONE `navigator__verify` payload, narrowed. Never raises.

    `Any` rather than a mapping type, and the annotation is honest: these are
    model-authored JSON arguments and may be anything at all, so the coercion
    below is the contract rather than a courtesy — `navigator_service.py`'s
    `args if isinstance(args, dict) else {}`, at the same boundary, for the
    same reason."""
    fields = args if isinstance(args, dict) else {}
    return StepVerification(
        claimed=_narrowed(fields.get(OUTCOME_ARG), MAX_CLAIM_CHARS),
        evidence=_narrowed(fields.get(EVIDENCE_ARG), MAX_EVIDENCE_CHARS),
    )


__all__ = [
    "EVIDENCE_ARG",
    "FAIL_CLOSED_OUTCOME",
    "MAX_CLAIM_CHARS",
    "MAX_EVIDENCE_CHARS",
    "OUTCOMES",
    "OUTCOME_ARG",
    "RESULT_NOT_PROVEN_OBSERVABLE",
    "RESULT_PROVEN",
    "RESULT_UNOBSERVABLE",
    "StepVerification",
    "verification_from",
]
