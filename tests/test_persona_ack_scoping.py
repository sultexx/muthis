# tests/test_persona_ack_scoping.py
"""
The persona's ack rules are ANSWER-scoped, and the contradiction is gone (DEC-84).

WHAT WAS WRONG, MEASURED AT T7. The persona held two rules in tension. At char
**2,378**: «كلمة التأكيد المنطوقة إلزامية في كل دور تأشير — ممنوع دور تأشير
صامت» — an ack is MANDATORY in EVERY pointing pass, a silent pointing pass is
FORBIDDEN. At char **9,788**, **7,410 characters and 54 newlines later**: the
scoping exception. **The model reads LINEARLY: the absolute came first and spoke
to exactly the framing a Navigator turn presents** — two consecutive
tool-capable passes that both look like pointing passes.

Fixing only the directives (the previous commit) would have closed the SYMPTOM
and left the CAUSE: a contradiction in the persona text that detonates at the
next feature opening a new pass gap. This project has refused that trade every
time, so both halves land.

**THE SCOPE IS PER ANSWER, NOT PER TOOL FAMILY.** The second clause used to read
"in the POINTING or DRAWING pass"; a capability that opened a new pass gap would
have had to re-earn it — which is how the gap arrived. It now covers whatever
tools a pass calls, so a future capability inherits it by existing.

THE METHOD IS DEC-41's, WHICH CAUGHT A LIVE TRAP BEFORE:
  * `persona.py` BYTE-IDENTICAL, proven by git rather than asserted here;
  * the composed prompt SNAPSHOT is hash-pinned, so the BASELINE cannot be
    quietly rewritten to make the delta test pass — a guard whose reference can
    be edited is checking nothing;
  * the DELTA is pinned as data: applying exactly two clause swaps to the
    snapshot must REBUILD the live prompt byte for byte, which is how "every
    pre-existing rule is unchanged" becomes a proof instead of a claim;
  * the new text is checked against the LIVE §3.2 delimiter constants, because a
    law the model READS must never resemble the untrusted-content boundary it
    reads INSIDE;
  * and the LAW is asserted, not its words — a substring assertion is a cutoff,
    the family M16 landed in at T5.

Run:  set PYTHONDONTWRITEBYTECODE=1 && set PYTHONPATH=src && python -m pytest tests/test_persona_ack_scoping.py -q
"""

from __future__ import annotations

import hashlib
import json
import pathlib

from muthis.cloud.claude_agent import LOOK_SYSTEM_PROMPT
from muthis.kernel.ack_scope import ACK_SCOPE_AR
from muthis.kernel.untrusted_content import WRAP_CLOSE_AR, WRAP_OPEN_AR
from muthis.persona import resolve_system_prompt

SNAPSHOTS = pathlib.Path(__file__).resolve().parent / "snapshots"
BEFORE_FILE = SNAPSHOTS / "persona_prompt_before_ack_scoping.txt"
DELTA_FILE = SNAPSHOTS / "persona_ack_scoping_delta.json"

# The composed prompt is dimension-injected, so the snapshot is taken at ONE
# fixed size and the test composes at the same one.
SENT_W, SENT_H = 1280, 720

# The snapshot's own hash. Pinning the BASELINE is the point: without it, a
# future edit could bring the snapshot into line with a changed prompt and the
# delta assertion below would pass while proving nothing.
BEFORE_SHA256 = "70a186e5b4ac12d94ba159fd5fb2e9a14812f4f8a7f0d1573345329988f4476d"

# Text APPENDED to the persona AFTER DEC-84, pinned by its own hash.
#
# WHY THIS EXISTS RATHER THAN A RE-SNAPSHOT. DEC-84's two clause swaps rebuild
# the persona exactly as it stood at that ruling. A law appended later is a
# DIFFERENT change under its own delta pin, and there were only three ways to
# absorb it: re-baseline `BEFORE_FILE` (forbidden — the docstring above says a
# guard whose reference can be edited is checking nothing), fold the append into
# `clauses` (which would misattribute a 2026-08-05 law to DEC-84's record), or
# pin it separately. The third keeps attribution honest AND keeps the check
# byte-total: the rebuild proves every byte up to the append point, this hash
# proves every byte after it. Nothing is unpinned, so the guarantee is the same
# one the `==` gave — only the accounting is now per-ruling.
#
# Contents: the identity law (2026-08-05) — Mut'his never identifies as any
# vendor's model. Its own additive proof lives in test_persona_identity_law.py.
# Verified before pinning, never pasted from a failure message: the tail was
# printed verbatim and is 741 characters — the SAME delta length the identity
# law's own prefix-hash proof measures independently — and contains that law and
# nothing else.
APPENDED_SINCE_DEC84_SHA256 = (
    "c5a73861200c1708ff59504fe1af68afb8a18031c6af903316552371b01de41b")


def _prompt() -> str:
    return resolve_system_prompt(LOOK_SYSTEM_PROMPT, SENT_W, SENT_H)


def test_the_snapshot_baseline_is_itself_unmodified():
    """THE REFERENCE, PINNED. A guard whose baseline can be edited is checking
    nothing — the same defect as a cutoff that admits zero, one layer earlier."""
    actual = hashlib.sha256(BEFORE_FILE.read_bytes()).hexdigest()
    assert actual == BEFORE_SHA256, (
        f"the pre-change persona snapshot has been modified ({actual}). It is "
        "the reference the delta below is measured against and must not move.")


def test_the_prompt_differs_from_the_snapshot_by_EXACTLY_the_pinned_clauses():
    """THE DELTA PIN — every pre-existing rule byte-identical, PROVEN.

    Applying exactly the two pinned clause swaps to the snapshot must rebuild
    the live prompt byte for byte. If any other rule changed, this fails; if a
    third clause were edited, this fails; if a swap were widened, this fails."""
    delta = json.loads(DELTA_FILE.read_text(encoding="utf-8"))["clauses"]
    assert len(delta) == 2, f"the pinned delta has {len(delta)} clauses, not 2"

    rebuilt = BEFORE_FILE.read_text(encoding="utf-8")
    for clause in delta:
        assert rebuilt.count(clause["old"]) == 1, (
            "a pinned clause is not uniquely locatable in the snapshot — the "
            "delta no longer describes this change")
        rebuilt = rebuilt.replace(clause["old"], clause["new"])

    live = _prompt()
    assert live.startswith(rebuilt), (
        "the composed prompt is NOT the snapshot plus exactly these two clause "
        "swaps — something else in the persona changed and is unaccounted for")

    # The remainder is laws APPENDED after DEC-84, pinned above. Between the two
    # assertions every byte of the live prompt is accounted for, which is what
    # the original equality guaranteed; an edit anywhere still fails one of them.
    tail = live[len(rebuilt):]
    assert hashlib.sha256(tail.encode()).hexdigest() == APPENDED_SINCE_DEC84_SHA256, (
        "text appended to the persona after DEC-84 has changed and is "
        "unaccounted for — update APPENDED_SINCE_DEC84_SHA256 deliberately, "
        "together with the appending law's own additive proof")


def test_no_unconditional_PER_PASS_ack_mandate_survives():
    """THE LAW, and it is a NEGATIVE because the defect was a contradiction.

    The clause that made an ack mandatory in EVERY pointing pass is what a model
    reading linearly obeyed. It must not exist in any form: not for pointing,
    not for drawing, not for a future tool."""
    prompt = _prompt()
    for forbidden in ("إلزامية في كل دور تأشير", "إلزامية في كل دور",
                      "في كل دور تأشير", "ممنوع دور تأشير صامت"):
        assert forbidden not in prompt, (
            f"an unconditional per-pass ack mandate is back: «{forbidden}». The "
            "model reads linearly and this outranks any exception stated later.")


def test_BOTH_ack_rules_are_scoped_to_the_ANSWER_and_are_tool_agnostic():
    """The positive half — the law says WHERE the ack belongs, and says it in a
    form no future capability has to re-earn.

    Asserted on BOTH occurrences, because the defect was precisely that one of
    the two was scoped and the other was not: checking either alone would have
    passed before the fix."""
    prompt = _prompt()
    assert prompt.count("أول دور من الإجابة") >= 2, (
        "fewer than two ANSWER-scoped statements — one of the pair is unscoped "
        "again, which is the exact shape of the original contradiction")
    assert prompt.count("مهما كانت الأدوات") >= 2, (
        "the tool-agnostic clause is missing from one of the two rules; a rule "
        "written per tool family must be re-earned by the next capability")


def test_the_mandatory_FIRST_ack_survives_the_rescoping():
    """The rule that must NOT have been lost. v7.1 Fix E banned a silent first
    pass — a measured chars=0 ack left the pass-2 round-trip unmasked — so the
    fix had to SCOPE the mandate, never delete it."""
    prompt = _prompt()
    assert "إلزامية في أول دور من الإجابة" in prompt, "the ack is no longer mandatory anywhere"
    assert "ممنوع أول دور صامت" in prompt, "a silent first pass is no longer banned"


def test_the_persona_ack_rules_do_not_resemble_the_untrusted_boundary():
    """DEC-14's rule, checked against the LIVE §3.2 constants so a future
    rewording of the delimiters re-runs this comparison automatically."""
    delta = json.loads(DELTA_FILE.read_text(encoding="utf-8"))["clauses"]
    boundary = ((set(WRAP_OPEN_AR.split()) | set(WRAP_CLOSE_AR.split()))
                - {"—", "{source}", "{nonce}", "لا"})
    for clause in delta:
        shared = boundary & set(clause["new"].split())
        assert not shared, (
            f"a rewritten persona clause shares wording with the untrusted "
            f"delimiters: {sorted(shared)}")


def test_the_persona_and_the_kernel_directives_say_the_SAME_law():
    """DEC-20's LAYERED pressure, and the layers must agree.

    The persona is layer ONE (carried into every turn) and `ack_scope.py` is
    layer TWO (the same law at the point of use). They are deliberately worded
    differently — a directive is not a copy of a persona rule — but a reader
    must be able to see they state one law, so the load-bearing terms match."""
    prompt = _prompt()
    for shared_term in ("الإجابة", "مهما كانت الأدوات"):
        assert shared_term in ACK_SCOPE_AR, f"the directive lost «{shared_term}»"
        assert shared_term in prompt, f"the persona lost «{shared_term}»"
