# tests/test_persona_judgement_law.py
"""
HOW TO JUDGE a step's result — DEC-100's conservative instruction and DEC-105's
boundary, shipped into the persona at last.

THIS IS THE LAW EVERY MEASURED NUMBER IN THIS SERIES WAS OBTAINED WITH, AND IT
SHIPPED LAST. Gate 1 shipped how to WRITE an expected result; Gate 2C shipped
WHEN to verify and when to move; neither shipped how to JUDGE. Until this commit
the composed persona contained ZERO of this rule's load-bearing ideas, which
meant the build carried DEC-106's machine and not the judgement DEC-100
measured. A live false advance would then have read as a model failure when it
was a SHIPPING failure — which is why this landed before the live SOP rather
than after it.

WHAT IT CARRIES, in its measured terms rather than paraphrased:

  1. SETTLED AND COMMITTED — the neutral instruction failed T₁ at 43.3% (17 false
     advances in 30) and this rule took it to 100%, with T₂ and T₃ UNMOVED: the
     failure was REMOVED, not relocated. Reasoning tokens fell 17 → 2, so the
     rule is free.
  2. A PREVIEW IS NOT A RESULT — and this clause refuted a ceiling argument on
     the SAME FRAME. Asked neutrally: "the body visibly has rounded top edges",
     ten times out of ten. Asked this way: "the rounded geometry is only a live
     preview and the operation has not been confirmed", ten times out of ten.
     The model could always SEE the dialog; the missing piece was the rule.
  3. AN OPEN PANEL AWAITING CONFIRMATION IS NOT SETTLED, whatever the canvas
     shows behind it.
  4. THE ABSENCE OF A VISIBLE DISQUALIFIER DOES NOT ESTABLISH SETTLED — DEC-105's
     boundary, and the reason it is a clause rather than a flourish: Excel's
     cell-edit case failed 10/10 at confidence 99 with the model applying rule 3
     CORRECTLY. It looked for a disqualifier, found none, and concluded settled,
     which is what "no dialog is visible" instructs. The rule was STRUCTURALLY
     INCOMPLETE, not badly worded, and clause 4 is what fills it.

CLAUSES 2 AND 4 ARE SEPARATELY REQUIRED and are mutation-verified as such: they
answer different failures. Clause 2 catches a result that IS drawn and is not
committed; clause 4 catches a state that is NOT drawn at all. A build with only
one of them fails the other's measured case.

WHY THE LAW LIVES IN `persona_laws_navigator.py`, recorded because the brief
named `persona_laws.py`'s count. `persona_laws.py` composes `(… earlier laws …)
+ NAVIGATOR_LAWS`, so a law appended THERE lands in the MIDDLE of the composed
prompt and `after == before + delta` — DEC-41's load-bearing half — stops being
provable. This is Gate 1's collision exactly, one milestone on: stated, resolved
in the direction the mandated method requires, and Sultan's to overrule.

THE METHOD IS DEC-41'S: `persona.py` byte-identical with the law in ONE home; the
DELTA pinned, not the prompt, with a second anchor further back; checked against
the LIVE §3.2 constants; and the LAW asserted with `count(...) == 1` per anchor.

Run:  set PYTHONDONTWRITEBYTECODE=1 && set PYTHONPATH=src && python -m pytest tests/test_persona_judgement_law.py -q
"""

from __future__ import annotations

import hashlib
import pathlib

import pytest

from muthis.kernel.untrusted_content import WRAP_CLOSE_AR, WRAP_OPEN_AR
from muthis.persona import build_saudi_persona_prompt

SENT_W, SENT_H = 1280, 720

# The composed prompt immediately BEFORE this law — the baseline for the additive
# proof. Regenerate ONLY with a deliberate re-approval.
PROMPT_BEFORE_JUDGEMENT_SHA256 = (
    "19d22777ef61f6c55d86c8ad174cf9a0c8fdef8ca9f76a9009202452ff4d756e")
PROMPT_BEFORE_JUDGEMENT_CHARS = 13529

# An anchor further back, at a different depth — the baseline Gate 2C's
# verify-order law was proven against, shared BY VALUE with that test.
PROMPT_BEFORE_VERIFY_ORDER_SHA256 = (
    "22233972b9abb94021aa0d04f85d223f331450e04be483351fec4fabf21315ac")
PROMPT_BEFORE_VERIFY_ORDER_CHARS = 13163

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis"

# Each anchor is a LOAD-BEARING fragment of ONE clause: delete that clause and it
# disappears. Uniqueness is asserted, not assumed — see the control below.
ANCHORS = {
    "settled_and_committed": "حالة مستقرّة والنتيجة مثبَّتة",
    "preview_is_not_result": "المعاينة ليست نتيجة",
    "awaiting_confirmation": "تنتظر تأكيداً",
    "absence_proves_nothing": "غياب المانع الظاهر لا يثبت الاستقرار",
    "the_why": "لا أن تستنتجها من مجرى العمل",
}


def _prompt() -> str:
    return build_saudi_persona_prompt(SENT_W, SENT_H)


def _delta() -> str:
    return _prompt()[PROMPT_BEFORE_JUDGEMENT_CHARS:]


# ─── The delta is an ADDITION, not a mangle ─────────────────────────────────

def test_the_judgement_law_is_purely_additive():
    """The composed prompt changed — the law was added — but every rule that
    existed before it is byte-identical, because it is APPENDED. A rewrite of
    any earlier rule fails HERE even if that rule's own test still passes."""
    prompt = _prompt()

    assert hashlib.sha256(prompt.encode()).hexdigest() != PROMPT_BEFORE_JUDGEMENT_SHA256, (
        "the composed prompt did not change — the law never reached the model")
    baseline = prompt[:PROMPT_BEFORE_JUDGEMENT_CHARS]
    assert hashlib.sha256(baseline.encode()).hexdigest() == PROMPT_BEFORE_JUDGEMENT_SHA256, (
        "a PRE-EXISTING persona rule was modified — this law must only APPEND")


def test_the_older_baseline_ALSO_still_holds():
    """Two anchors at different depths cannot both be re-based by accident (the
    DEC-57 method). This one predates Gate 2C's verify-order law as well as this
    one, so a commit that mangled THAT law and re-approved THIS baseline fails
    here."""
    assert hashlib.sha256(
        _prompt()[:PROMPT_BEFORE_VERIFY_ORDER_CHARS].encode()
    ).hexdigest() == PROMPT_BEFORE_VERIFY_ORDER_SHA256


# ─── Assert the LAW, not its words ──────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(ANCHORS))
def test_every_anchor_is_UNIQUE_in_the_whole_prompt(name):
    """THE PRECONDITION FOR EVERY ASSERTION BELOW. An anchor that already occurs
    elsewhere would keep a test green with the whole clause deleted — M2's sixth
    guard hole, exactly."""
    assert _prompt().count(ANCHORS[name]) == 1, (
        f"{name} is not unique — the assertion built on it proves nothing")


def test_clause_1_requires_a_SETTLED_state_with_the_result_COMMITTED():
    """DEC-100's rule, in its measured terms. Without it the neutral reading
    stands, and the neutral reading failed T₁ seventeen times in thirty."""
    assert ANCHORS["settled_and_committed"] in _delta()


def test_clause_2_says_a_PREVIEW_IS_NOT_A_RESULT():
    """The clause that refuted the perceptual-ceiling argument on the same
    frame: the model could always see the dialog, and the rule is what changed
    the answer from yes ×10 to no ×10."""
    assert ANCHORS["preview_is_not_result"] in _delta()


def test_clause_3_disqualifies_an_open_panel_AWAITING_CONFIRMATION():
    """Whatever the canvas shows behind it. This is the disqualifier DEC-100
    validated and the one DEC-105 then proved insufficient ON ITS OWN."""
    assert ANCHORS["awaiting_confirmation"] in _delta()


def test_clause_4_says_ABSENCE_of_a_disqualifier_establishes_NOTHING():
    """DEC-105's boundary, and the case is exact: Excel failed 10/10 at
    confidence 99 with the model applying clause 3 CORRECTLY — it found no
    disqualifier and concluded settled. The rule was structurally incomplete;
    this clause is what fills it."""
    assert ANCHORS["absence_proves_nothing"] in _delta()


def test_clauses_2_and_4_are_SEPARATELY_required():
    """They answer DIFFERENT failures and neither implies the other. Clause 2
    catches a result that IS drawn and is not committed; clause 4 catches a state
    that is NOT drawn at all. A prompt carrying one and not the other fails the
    other's measured case, so both are asserted here as an explicit pair rather
    than left to two independent tests that could be deleted one at a time."""
    delta = _delta()

    assert ANCHORS["preview_is_not_result"] in delta
    assert ANCHORS["absence_proves_nothing"] in delta
    assert delta.index(ANCHORS["preview_is_not_result"]) != delta.index(
        ANCHORS["absence_proves_nothing"]), "the two clauses collapsed into one"


def test_the_law_states_WHY_rather_than_only_what():
    """Every milestone law here carries its own reason, because the reasoning is
    what stops a later edit from simplifying a law back into the hole it
    closes."""
    assert ANCHORS["the_why"] in _delta()


def test_the_CONTROL_the_obvious_phrasings_would_have_proven_nothing():
    """A careless author would have anchored on these, and each already occurs
    elsewhere — so a test built on them would pass with the law deleted."""
    prompt = _prompt()
    for ambiguous in ("الشاشة", "النتيجة", "الخطوة"):
        assert prompt.count(ambiguous) > 1, (
            f"{ambiguous!r} is no longer ambiguous — the control has gone stale")


# ─── The law never resembles the boundary it is read inside (§3.2) ──────────

def test_the_law_shares_no_wording_with_the_LIVE_untrusted_delimiters():
    """Checked against the LIVE constants, never a copy: a rule the model READS
    must not resemble the boundary it reads INSIDE. This law came close — the
    natural Arabic for "command panel" carries a §3.2 word — so the phrasing
    avoids it deliberately and this guard is what proves it stayed avoided."""
    delta = _delta()
    boundary_words = {word for word in (WRAP_OPEN_AR + " " + WRAP_CLOSE_AR).split()
                      if len(word) > 3}
    shared = sorted(word for word in boundary_words if word in delta)

    assert not shared, f"the law reproduces §3.2 delimiter wording: {shared}"


def test_persona_py_is_untouched_and_the_law_has_ONE_home():
    """`persona.py` holds the identity half and the composition; every LAW lives
    in the law modules. A clause in both is two copies of one fact."""
    persona = (SRC / "persona.py").read_text(encoding="utf-8")
    assert ANCHORS["preview_is_not_result"] not in persona

    holders = sorted(p.name for p in SRC.rglob("*.py")
                     if ANCHORS["absence_proves_nothing"] in p.read_text(encoding="utf-8"))
    assert holders == ["persona_laws_navigator.py"], (
        f"the clause is written out in {holders} — it must have exactly one home")


def test_the_law_is_NOT_in_persona_laws_py_because_that_would_land_it_MID_PROMPT():
    """THE PLACEMENT ARGUMENT, asserted rather than described. `persona_laws.py`
    composes `(… earlier …) + NAVIGATOR_LAWS`, so a law appended there lands
    BEFORE the navigator block and `after == before + delta` stops being
    provable — DEC-41's load-bearing half, and Gate 1's collision one milestone
    on."""
    earlier = (SRC / "persona_laws.py").read_text(encoding="utf-8")

    assert "NAVIGATOR_LAWS" in earlier, "the composition changed shape"
    assert ANCHORS["settled_and_committed"] not in earlier
    assert _prompt().endswith(_delta()), "the law is no longer the prompt's tail"
