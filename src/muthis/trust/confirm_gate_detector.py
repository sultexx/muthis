# src/muthis/trust/confirm_gate_detector.py
"""
The approval DETECTOR — what counts as the user's consent, and nothing else.

EXTRACTED from `trust/confirm_gate.py` under the ≤300-line law (DEC-136). That
file stood at 280/300 and the honest form of this gate's three rulings measured
+34, so the arrival met the pin exactly as the pin said it would: *"the next law
needs an EXTRACTION before it needs a sentence."* `confirm_gate.py` re-exports
every name below, so no import site outside this package changed — the
`file_reader_notes.py` / `confirm_gate_notes.py` precedent (DEC-113, DEC-131).

WHY THE SEAM IS HERE AND NOT SOMEWHERE CHEAPER. DEC-131 moved the SURFACE out
because the surface was what grew. This time the DETECTOR is what grew: ruling 1
changes the accepted set and ruling 2 makes that set the source the spoken
request is rendered from. A module whose whole job is "what counts as consent"
is the thing an auditor should be able to read end to end — the `high_impact.py`
shape, which is pure, stdlib-only and importable in isolation for the same
reason. DEC-42's *"the stronger property stays byte-identical while the weaker
one is worked on"* is not breached: it governs a NOTES change, and here the
stronger property is the one under the ruling.

THE DETECTOR IS THE SECURITY BOUNDARY, so its shape is deliberate:

  * STRIP, THEN ISOLATE. `turn_pass` hands over `user_input`, which by then is
    the transcript PLUS any kernel-authored directive lines the orchestrator
    prepended (the verbosity directive; `INTERRUPTED_NOTE_AR` after a barge-in).
    Whole-utterance isolation on THAT would refuse every approval spoken while
    sticky SHORT/DETAILED is on. So directive lines are dropped first — they all
    carry the `DIRECTIVE_MARKER_AR` family marker — and isolation then applies to
    the remainder, which is exactly the bare transcript. The user's ENTIRE
    utterance must be an approval word.
  * THE FAILURE IS ASYMMETRIC BY CONSTRUCTION. If a future directive ever omits
    the marker, its line survives the strip, the remainder no longer EQUALS an
    approval word, and the call is refused: a FALSE NEGATIVE (friction), never a
    FALSE POSITIVE (an authorization bypass). Every unknown lands on the safe
    side, and a test feeds an unstripped prefix to prove it.
  * THE WORD SET IS NARROW ON PURPOSE. Colloquial affirmatives («تمام», «أيه»,
    «زين», «نعم») occur constantly in unrelated speech; each one added is an
    accidental authorization waiting for a coincidence. Refusal words may be
    broader — a false refusal is friction. Narrowness is only humane because the
    request NAMES the words, so the user is told exactly what to say: low
    false-positives AND low friction.

    **THE OLD FORM OF THIS BULLET READ "and must not be widened", AND DEC-136
    ruling 1 SUPERSEDES THAT — with a test, not a preference.** The bound is
    stated with the set below, and «تم» / «أوكيه» are asserted ABSENT so the
    widening cannot creep.

HONEST LIMIT, AND IT IS THE ONE THAT DECIDES EVERY FUTURE WIDENING: the evidence
that would justify a wider set — how often a bare «نعم» is a COMPLETE utterance
in a turn that is not an approval — requires logging transcripts, which
DEC-17/DEC-28 forbid and `logging_policy.py` structurally refuses to make
durable. **The number cannot be obtained here, so widening is a judgement about
acceptable risk and can never be converted into a measurement** (DEC-135). Every
addition to the set below is therefore a RULING, and belongs to Sultan alone.

`normalize_ar` is imported from the kernel's verbosity module rather than
re-implemented: a second home for a security-relevant text transform is how the
two drift, and the STT tolerance it provides (tashkeel, hamza forms, tatweel,
Arabic-Indic digits, punctuation) is already pinned by `test_verbosity.py`.
"""

from __future__ import annotations

from typing import Optional

from ..kernel.verbosity import normalize_ar

# The family marker every kernel-authored directive line carries. It is the
# SHARED CORE of the family, not one member's exact opening: `DIRECTIVE_OPEN_AR`
# (verbosity) and `INTERRUPTED_NOTE_AR` (barge-in) word their openings
# differently, and matching either one exactly would leave the other in place. A
# test pins that both real constants contain this.
DIRECTIVE_MARKER_AR = "توجيه داخلي"

APPROVE = "approve"
REFUSE = "refuse"

# ─── THE ACCEPTED WORDS — AND EVERY ONE OF THEM IS SAID ALOUD ────────────────
#
# ONE TUPLE IS THE SOURCE (DEC-136 ruling 2). `_APPROVALS` normalizes it for
# matching and `confirm_gate_notes.render_words` renders it for speech, so a
# word cannot be ACCEPTED without being OFFERED. That asymmetry was a live
# defect, not a hypothetical: the detector accepted three words, the request
# named one, and a user told «أوافق» was refused three turns running — while
# «موافق», which he may well have said, had been accepted the whole time
# (DEC-135). A user refused for saying a word the system accepts is the same
# class as a note that invites a retry it cannot satisfy.
#
# «اعتمد» ADDED; «تم» AND «أوكيه» REFUSED (DEC-136 ruling 1, Sultan's). THE
# BOUND THAT DECIDES IT: whole-utterance matching already excludes a word
# occurring INSIDE a sentence, so the only question a candidate has to answer is
# whether its BARE form is a plausible COMPLETE utterance in a turn that is not
# an approval. «تم» and «أوكيه» are exactly that — they mean "understood", the
# ordinary acknowledgement of any statement at all, and a user who says one
# after hearing the request has acknowledged it rather than authorized it.
# «اعتمد» is an AUTHORIZATION verb: a bare «اعتمد» is not an utterance ordinary
# speech produces by accident. The distinction is INTENT-CARRYING, not
# frequency-based, which is why it survives a widening the frequency argument
# could not justify (see the module note on why frequency cannot be measured).
#
# Spelling is free: `normalize_ar` folds أ/إ/آ → ا, so «أعتمد» reaches «اعتمد»
# and «اوافق» reaches «أوافق» without either being listed twice.
APPROVAL_WORDS_AR = ("أوافق", "موافق", "وافق", "اعتمد")

# The LEAD word — what the request names first, and what every existing call
# site imports by this name (four test files and two diagnostic scripts).
APPROVAL_WORD_AR = APPROVAL_WORDS_AR[0]

# Written in natural spelling and normalized once at import — readable here,
# STT-tolerant at match time, and impossible to spell inconsistently.
_APPROVALS = frozenset(normalize_ar(word) for word in APPROVAL_WORDS_AR)
_REFUSALS = frozenset(normalize_ar(word) for word in ("ألغِ", "لا توافق", "لا"))


def strip_directive_lines(text: str) -> str:
    """Drop every kernel-authored directive line, leaving the bare transcript.

    Directives are always prepended as WHOLE lines by the orchestrator
    (`verbosity.attach` and the barge-in note both join with "\\n"), and neither
    constant contains a newline of its own, so a line-wise filter removes exactly
    them. A line the filter does not recognise SURVIVES, which is what makes the
    unknown case fail closed at the isolation step."""
    return "\n".join(line for line in text.splitlines()
                     if DIRECTIVE_MARKER_AR not in line)


def detect_confirmation(text: str) -> Optional[str]:
    """APPROVE / REFUSE / None for one raw transcript — pure, no state.

    Whole-utterance isolation: the normalized remainder must EQUAL a word in the
    set. An approval word inside a longer sentence is not an approval — the same
    rule that stops «أي ضلع أطول؟» from flipping verbosity, applied where the
    stakes are authorization rather than reply length.

    **None IS NOT "SILENCE" AND THE GATE DEPENDS ON THE DIFFERENCE** (DEC-136
    ruling 3). It means the user spoke and was not understood as either answer,
    which is the ONE state the retry surface is allowed to report; a REFUSE is
    deliberate and must never be answered with "that was not one of the words"."""
    utterance = normalize_ar(strip_directive_lines(text))
    if utterance in _APPROVALS:
        return APPROVE
    if utterance in _REFUSALS:
        return REFUSE
    return None


__all__ = [
    "APPROVAL_WORDS_AR",
    "APPROVAL_WORD_AR",
    "APPROVE",
    "DIRECTIVE_MARKER_AR",
    "REFUSE",
    "detect_confirmation",
    "strip_directive_lines",
]
