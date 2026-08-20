# tests/test_persona_step_result_law.py
"""
HOW TO WRITE `expected_result` — the authoring law (DEC-107, Gate 1), and the
enforcement boundary it sits on.

IT GUIDES; IT NEVER ENFORCES, and that division is the design rather than a
weakness. The kernel checks that the field is PRESENT and NON-EMPTY and nothing
more (DEC-66): it cannot count the ends of a sentence without reading it, and
reading it is the law it must not break. So an over-broad or two-ended result is
ALLOWED by the structural contract, and the only things standing where a
structure cannot are this law and measurement. That makes it load-bearing in
exactly the way DEC-57(a)'s «ما لقيت هذا في المستند» is load-bearing.

WHY THE LAW LIVES IN `persona_laws.py` AND NOT IN `persona_rules.py`, recorded
because the Gate 1 brief named the other file. `persona_rules.py` composes
`TOOL_AND_SAFETY_RULES = _CORE + MILESTONE_LAWS`, so a law added there lands in
the MIDDLE of the composed prompt and `after == before + delta` — DEC-41's
load-bearing half — stops being provable. Every milestone law since DEC-14 lives
here for that reason. The collision was stated and resolved in the direction the
mandated method requires (the DEC-63 standing rule), and it is Sultan's to
overrule.

ALL THREE CLAUSES ARE MEASURED, AND TWO OF THEM COME FROM THE SAME FIXTURE WITH
DIFFERENT MECHANISMS — which is why they are asserted separately below rather
than as one "phrase it well" check:

  1. RESULT, NOT ACTION — the timing fixture's rule 1. A step phrased around the
     CONTROL is genuinely SATISFIED mid-step (the radius IS set in the open
     dialog), turning a designed trap into a true positive.
  2. ONE OBSERVABLE END — DEC-106's binding constraint, earned from an answer
     that was not an error: "Move X from Source to Destination" has two ends
     with DIFFERENT observability, and a three-outcome contract has no label
     for half.
  3. NO VALUE A FRAME CANNOT SETTLE — the timing fixture's rule 2, whose
     mechanism is NOT rule 1's: naming a committed fillet radius fails
     verification for a reason unrelated to the step. It is emphatically NOT
     "no numbers", and the carve-out is asserted below, because this project's
     own category-3 fixture names 990 and 100 on purpose.

THE METHOD IS DEC-41'S:
  * `persona.py` BYTE-IDENTICAL, proven by git rather than asserted here;
  * the DELTA is pinned, not the prompt, with a SECOND anchor further back so a
    mangle-plus-rebase in one commit cannot pass both;
  * checked against the LIVE §3.2 delimiter constants, never a copy;
  * and the LAW is asserted, not its words — every anchor with `count(...) == 1`
    over the WHOLE prompt, plus a CONTROL proving the phrases a careless author
    would have reached for are genuinely ambiguous. M2's sixth guard hole was
    two words that occur elsewhere, so deleting a whole law stayed green.

Run:  set PYTHONDONTWRITEBYTECODE=1 && set PYTHONPATH=src && python -m pytest tests/test_persona_step_result_law.py -q
"""

from __future__ import annotations

import hashlib
import pathlib
import re

import pytest

from muthis.kernel.untrusted_content import WRAP_CLOSE_AR, WRAP_OPEN_AR
from muthis.persona import build_saudi_persona_prompt

SENT_W, SENT_H = 1280, 720

# The composed prompt immediately BEFORE this law — the baseline for the additive
# proof. Regenerate ONLY with a deliberate re-approval.
PROMPT_BEFORE_STEP_RESULT_SHA256 = (
    "363970749368bb888b4f03b69962daa74736dff36cb23f703b18d471e5df6a9a")
PROMPT_BEFORE_STEP_RESULT_CHARS = 12259

# An anchor further back, at a different depth, shared by value with the
# identity, doc, voice, web and execute-first law tests.
PROMPT_AT_T4_SHA256 = "b8a505568adb5e90282a069c2ca2c3f9e7b36aa179e55194816582ef1c7bace3"
PROMPT_AT_T4_CHARS = 8569

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis"

# Each anchor is a LOAD-BEARING fragment: delete the clause it belongs to and it
# disappears. Uniqueness is asserted, not assumed — see the control below.
ANCHORS = {
    "result_not_action": "صف المشهد اللي بيصير",
    "one_observable_end": "طرف واحد ملحوظ لكل خطوة",
    "no_unsettleable_value": "ما تقدر اللقطة تحسمها",
    "the_number_carve_out": "فاذكرها عادي",
    "authored_in_advance": "قبل أي تحقّق",
    "immutable": "ما تعدّلها ولا تعيد صياغتها",
    "the_why": "الشاشة هي السؤال والجواب",
}


def _prompt() -> str:
    return build_saudi_persona_prompt(SENT_W, SENT_H)


def _delta() -> str:
    return _prompt()[PROMPT_BEFORE_STEP_RESULT_CHARS:]


# ─── Rule 2: the delta is an addition, not a mangle ─────────────────────────

def test_the_step_result_law_is_purely_additive():
    """The composed prompt changed — the law was added — but every rule that
    existed before it is byte-identical, because it is APPENDED. A rewrite of
    any earlier rule fails HERE even if that rule's own test still passes; T5's
    M13 proved that scenario live rather than hypothetically."""
    prompt = _prompt()

    assert hashlib.sha256(prompt.encode()).hexdigest() != PROMPT_BEFORE_STEP_RESULT_SHA256, (
        "the composed prompt did not change — the law never reached the model")
    baseline = prompt[:PROMPT_BEFORE_STEP_RESULT_CHARS]
    assert hashlib.sha256(baseline.encode()).hexdigest() == PROMPT_BEFORE_STEP_RESULT_SHA256, (
        "a PRE-EXISTING persona rule was modified — this law must only APPEND")
    assert len(prompt) > PROMPT_BEFORE_STEP_RESULT_CHARS


def test_the_older_baseline_ALSO_still_holds():
    """Two anchors at different depths cannot both be re-based by accident."""
    assert hashlib.sha256(
        _prompt()[:PROMPT_AT_T4_CHARS].encode()).hexdigest() == PROMPT_AT_T4_SHA256


# ─── Rule 4: assert the LAW, not its words ──────────────────────────────────

@pytest.mark.parametrize("name", sorted(ANCHORS))
def test_every_anchor_is_UNIQUE_in_the_whole_prompt(name):
    """THE PRECONDITION FOR EVERY ASSERTION BELOW (the DEC-57 method). An
    anchor that already occurs elsewhere would keep a test green with the whole
    clause deleted — M2's sixth guard hole, exactly."""
    assert _prompt().count(ANCHORS[name]) == 1, (
        f"anchor {name!r} is not unique — it no longer proves the clause is here")


def test_the_uniqueness_rule_is_not_VACUOUSLY_satisfiable():
    """THE CONTROL. If any short Arabic phrase were unique, the rule above
    would be free. These are the words a careless author would have reached
    for, and every one of them is genuinely ambiguous in this prompt."""
    prompt = _prompt()
    for tempting in ("الخطوة", "النتيجة", "الشاشة", "خطوة", "وليه:"):
        assert prompt.count(tempting) > 1, (
            f"{tempting!r} is unique, so the uniqueness rule proves nothing")


def test_the_law_orders_a_RESULT_and_forbids_describing_the_ACTION():
    """CLAUSE 1, and its mechanism is the value-match one: a step phrased around
    the control is SATISFIED mid-step, so the law must name the scene rather
    than the doing."""
    delta = _delta()

    assert ANCHORS["result_not_action"] in delta, (
        "the law no longer orders a description of what will be SEEN")
    assert "مو \"اسحب الملف" in delta, (
        "the law lost its worked counter-example — a rule stating only the "
        "positive form is one a model satisfies with an action sentence")


def test_the_law_carries_DEC_106s_ONE_OBSERVABLE_END_constraint():
    """CLAUSE 2 — binding since DEC-106, and recorded there against the field
    `Step` did not yet have precisely so it would be honoured on arrival rather
    than rediscovered live. Both halves are asserted: the rule AND the banned
    two-ended form, because a rule without its counter-example reads as advice."""
    delta = _delta()

    assert ANCHORS["one_observable_end"] in delta, (
        "the one-observable-end constraint is gone — a two-ended step is HALF "
        "observable and the three-outcome contract has no label for half")
    assert "من المصدر إلى الوجهة" in delta, (
        "the measured two-ended example (C3_FILE r7) is no longer banned by name")


def test_clause_three_bans_UNSETTLEABLE_values_and_NOT_numbers():
    """CLAUSE 3, AND THE CARVE-OUT THAT KEEPS IT TRUE.

    The rule is "a value a frame cannot settle", never "no numbers". Written
    the second way it would be contradicted by this project's OWN category-3
    fixture, whose step texts name 990 and 100 on purpose — a cell's displayed
    contents ARE settleable from a frame; those frames simply do not contain
    the location. A law that shipped as "never name a number" would have been
    refuted by the measurement it came from."""
    delta = _delta()

    assert ANCHORS["no_unsettleable_value"] in delta, (
        "the law no longer bans values a frame cannot settle")
    assert ANCHORS["the_number_carve_out"] in delta, (
        "the carve-out is gone — the clause now reads as a ban on NUMBERS, "
        "which our own fixtures violate")
    for absolute in ("لا تذكر أي رقم", "ممنوع الأرقام", "بلا أرقام"):
        assert absolute not in delta, (
            f"the law hardened into a blanket number ban ({absolute!r})")


def test_the_law_binds_the_result_to_AUTHORING_TIME_and_forbids_rewording():
    """THE IMMUTABILITY HALF, and it is the clause the whole gate rests on.

    Without it "authored in advance" holds only until the first look: a model
    free to re-word the result afterwards brings it into agreement with what it
    just saw, and verification closes on itself one cycle late — with the field
    still present, still non-empty, and now matching the screen."""
    delta = _delta()

    assert ANCHORS["authored_in_advance"] in delta, (
        "the law no longer says the result is written BEFORE any verification")
    assert ANCHORS["immutable"] in delta, (
        "the law no longer forbids re-wording the result after a look — "
        "verification becomes circular and every measured rate an illusion")


def test_the_law_states_its_own_WHY():
    """Every persona law here carries its reason, because the reason is what
    stops a later edit from simplifying it back into the hole it closes."""
    assert ANCHORS["the_why"] in _delta(), "the law lost its stated reason"


# ─── The boundary and surface checks every persona law must pass ────────────

def test_the_law_does_not_resemble_the_untrusted_boundary():
    """DEC-14's rule, checked against the LIVE §3.2 constants so a future
    rewording of the delimiters re-runs this comparison automatically. The trap
    was live once: the natural Arabic phrasing of DEC-14 IS the delimiter's own
    wording, and the guard that catches it scans all of `src/`."""
    boundary = ((set(WRAP_OPEN_AR.split()) | set(WRAP_CLOSE_AR.split()))
                - {"—", "{source}", "{nonce}", "لا"})
    shared = boundary & set(_delta().split())

    assert not shared, (
        f"the step-result law shares wording with the untrusted delimiters: "
        f"{sorted(shared)}")


def test_the_law_carries_no_formatting_syntax_and_no_urls():
    """The surface is TTS and a captions bar, never a markdown renderer."""
    delta = _delta()

    for token in ("**", "##", "`", "http://", "https://", "- [", "|"):
        assert token not in delta, f"the step-result law carries {token!r}"
    assert not re.search(r"^\s*[*+]\s", delta, re.MULTILINE), "markdown bullets"


def test_the_law_never_orders_DRAWING_or_a_tool_call():
    """A persona law that reached for a tool would move a boundary from the
    prompt layer, which is where boundaries must never move. This one describes
    how to WRITE a field and touches no capability."""
    delta = _delta()

    for tool in ("highlight_target", "draw_shapes", "request_screen_refresh",
                 "read_local_file", "dim_screen"):
        assert tool not in delta, f"the step-result law reaches for {tool}"


# ─── Rule 1: persona.py byte-identical, and the law has ONE home ────────────

def test_persona_py_is_untouched_and_no_clause_leaked_into_it():
    """`persona.py` holds the identity half and the composition; every LAW
    lives in `persona_laws.py`. A clause appearing in both is two copies of one
    fact, and the two wordings drift apart."""
    persona = (SRC / "persona.py").read_text(encoding="utf-8")
    assert ANCHORS["one_observable_end"] not in persona, "the law leaked into persona.py"

    # DEC-108 Gate 2C moved this law to `persona_laws_navigator.py` under the
    # ≤300-line law — VERBATIM, with the composed prompt proven byte-identical.
    # The PROPERTY is unchanged and is still what is asserted: exactly ONE
    # holder, and never `persona.py`. Only the home's name moved.
    laws = (SRC / "persona_laws_navigator.py").read_text(encoding="utf-8")
    assert ANCHORS["one_observable_end"] in laws, (
        "the law is not in persona_laws_navigator.py")

    holders = sorted(p.name for p in SRC.rglob("*.py")
                     if ANCHORS["immutable"] in p.read_text(encoding="utf-8"))
    assert holders == ["persona_laws_navigator.py"], (
        f"the immutability clause is written out in {holders} — it must have "
        "exactly one home")
