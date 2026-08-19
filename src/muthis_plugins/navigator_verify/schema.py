# src/muthis_plugins/navigator_verify/schema.py
"""The Navigator's THIRD verb — `verify` (DEC-108 Gate 2A, catalog v8).

THREE VERBS, THREE RESPONSIBILITIES (DEC-108 ruling ③): `plan` defines the plan
and each step's expected result · `verify` ESTABLISHES THE RESULT'S STATE ·
`step` advances. This is a SEPARATE TOOL rather than new semantics on `step`,
because "did it happen" and "move me on" are two questions and a tool that
answered both would let the second be reached without the first.

THE ENUMERATION IS SPELLED HERE A SECOND TIME, AND THAT IS THE LAYERING LAW
RATHER THAN A DUPLICATE. `muthis_plugins/` imports `muthis_sdk` and the stdlib
ONLY — never `muthis.*` — so this package cannot import the kernel's
`step_verification.OUTCOMES`, and a test pins the two lists EQUAL instead. The
drift that guard exists for is silent: a value the schema offers and the kernel
does not recognise fails CLOSED, which turns every genuine advance into a retry
with nothing anywhere reporting it.

WHAT IS DELIBERATELY NOT HERE. How to JUDGE — a preview is not a result, absence
of a disqualifier is not settled, one observable end per step — is a PERSONA law
(DEC-100, DEC-105, DEC-106) and is not restated in this file: two copies of one
rule drift apart, and the schema's job is to make the three answers available
and the evidence unskippable, not to teach the judgement.
"""

from __future__ import annotations

from typing import Any

NAVIGATOR_VERIFY_SCHEMA: dict[str, Any] = {
    "name": "verify",
    "description": (
        "Report whether the CURRENT step's expected result is visible on the "
        "screen you were just shown. Answer about the expected result you wrote "
        "with the plan — not about what you think the user did. I never advance "
        "a step you did not prove, and I never treat a retry as a failure."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "string",
                "enum": [
                    "RESULT_PROVEN",
                    "RESULT_NOT_PROVEN_OBSERVABLE",
                    "RESULT_UNOBSERVABLE",
                ],
                "description": (
                    "RESULT_PROVEN: you can SEE what the expected result "
                    "described. RESULT_NOT_PROVEN_OBSERVABLE: this screen "
                    "WOULD show it and it is not there yet — say this and I "
                    "keep the user on the same step. RESULT_UNOBSERVABLE: this "
                    "screen cannot settle it at all, whatever the user did."
                ),
            },
            "evidence": {
                "type": "string",
                "description": (
                    "REQUIRED with RESULT_PROVEN: the one thing you can see "
                    "that establishes the expected result. Without it I cannot "
                    "record an advance at all. Leave it out for the other two "
                    "outcomes — neither of them asks you to point at anything."
                ),
            },
        },
        "required": ["outcome"],
    },
}

__all__ = ["NAVIGATOR_VERIFY_SCHEMA"]
