# tests/test_persona_pass_economy_law.py
"""
VERIFY AND POINT IN ONE MESSAGE — the pass-economy clause (DEC-111), ruled from
the first live SOP.

THE COST IT REMOVES IS NOT STRUCTURAL, AND THAT IS WHY THE FIX IS A CLAUSE. The
kernel never asked for two passes: `turn_pass.py` keeps `pending_draw` and
`nav_call` as SEPARATE first-wins slots, so a navigator verb and a draw arriving
in ONE assistant message are BOTH serviced —
`test_advance_AND_point_in_one_pass_completes_in_TWO` has driven exactly that
since T5, and asserts the turn then ends in two passes with `tool_choice` going
`["auto", "none"]`. The model was choosing to spend a pass the machine did not
require.

WHAT IT COST LIVE. Three turns in the first SOP ended on `AGENTIC_CAP_NOTE_AR`
after a CORRECT draw, and the mechanism is provable from the loop rather than
inferred: once anything is drawn the next call is `tool_choice="none"` and the
turn ends, so the cap note is reachable ONLY if the draw landed on the fourth
pass. Three passes were spent before it where v1 spent none.

IT IS GUIDANCE, NOT A PROHIBITION, AND THE DISTINCTION WAS RULED. A model that
separates the two is not wrong — it is slower. A ban would forbid a shape the
kernel serves correctly, so the law says so out loud and this file asserts BOTH
halves: the permission must be present, and no prohibition may appear beside it.
A mutation that turns the clause into a ban goes RED here.

AND IT SCOPES THE CLAUSE ABOVE RATHER THAN CONTRADICTING IT. DEC-55's lesson was
MEASURED at T7: two rules that read as a conflict are resolved unpredictably,
because the model reads LINEARLY. So the pair each rule governs is named in this
law's own first line — verify + point BELONG TOGETHER, verify + move DO NOT —
and that naming is asserted below rather than left to inference.

THE METHOD IS DEC-41'S: `persona.py` byte-identical with the law in ONE home; the
DELTA pinned with a second anchor further back; checked against the LIVE §3.2
constants; the LAW asserted with `count(...) == 1` per anchor.

Run:  set PYTHONDONTWRITEBYTECODE=1 && set PYTHONPATH=src && python -m pytest tests/test_persona_pass_economy_law.py -q
"""

from __future__ import annotations

import hashlib
import pathlib

import pytest

from muthis.kernel.untrusted_content import WRAP_CLOSE_AR, WRAP_OPEN_AR
from muthis.persona import build_saudi_persona_prompt

SENT_W, SENT_H = 1280, 720

# The composed prompt immediately BEFORE this law. Regenerate ONLY with a
# deliberate re-approval.
PROMPT_BEFORE_PASS_ECONOMY_SHA256 = (
    "aad94e985d5260a1932989b8cfaedcd2ced415c24babc173576176b45d903f9f")
PROMPT_BEFORE_PASS_ECONOMY_CHARS = 14211

# An anchor further back, at a different depth — the baseline the JUDGEMENT law
# was proven against, shared BY VALUE with that test.
PROMPT_BEFORE_JUDGEMENT_SHA256 = (
    "19d22777ef61f6c55d86c8ad174cf9a0c8fdef8ca9f76a9009202452ff4d756e")
PROMPT_BEFORE_JUDGEMENT_CHARS = 13529

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis"

ANCHORS = {
    "combine_them": "فاجمعهما في رسالة واحدة",
    "separating_is_allowed": "وإن فصلتهما فما أخطأت",
    "the_two_pairs_named": "التحقّق والإشارة بابان",
    "not_a_contradiction": "مقصود ولا يناقضها",
    "the_why": "تصل للمستخدم وقتاً",
}

# Phrasings that would make this a PROHIBITION. None may appear: only guidance
# was ruled, and a ban would forbid a shape the kernel serves correctly.
FORBIDDEN_BANS = ("لا تفصلهما", "ممنوع تفصلهما", "لا تفرّقهما", "يجب أن تجمعهما")


def _prompt() -> str:
    return build_saudi_persona_prompt(SENT_W, SENT_H)


def _delta() -> str:
    return _prompt()[PROMPT_BEFORE_PASS_ECONOMY_CHARS:]


# ─── The delta is an ADDITION, not a mangle ─────────────────────────────────

def test_the_pass_economy_law_is_purely_additive():
    """The composed prompt changed — the law was added — but every rule that
    existed before it is byte-identical, because it is APPENDED."""
    prompt = _prompt()

    assert hashlib.sha256(prompt.encode()).hexdigest() != PROMPT_BEFORE_PASS_ECONOMY_SHA256, (
        "the composed prompt did not change — the law never reached the model")
    baseline = prompt[:PROMPT_BEFORE_PASS_ECONOMY_CHARS]
    assert hashlib.sha256(baseline.encode()).hexdigest() == PROMPT_BEFORE_PASS_ECONOMY_SHA256, (
        "a PRE-EXISTING persona rule was modified — this law must only APPEND")


def test_the_older_baseline_ALSO_still_holds():
    """Two anchors at different depths cannot both be re-based by accident."""
    assert hashlib.sha256(
        _prompt()[:PROMPT_BEFORE_JUDGEMENT_CHARS].encode()
    ).hexdigest() == PROMPT_BEFORE_JUDGEMENT_SHA256


# ─── Assert the LAW, not its words ──────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(ANCHORS))
def test_every_anchor_is_UNIQUE_in_the_whole_prompt(name):
    """THE PRECONDITION FOR EVERY ASSERTION BELOW. An anchor that already occurs
    elsewhere would keep a test green with the whole clause deleted."""
    assert _prompt().count(ANCHORS[name]) == 1, (
        f"{name} is not unique — the assertion built on it proves nothing")


def test_the_law_instructs_COMBINING_the_verification_with_the_pointing():
    """The ruled instruction. Without it the model keeps spending a pass the
    kernel never asked for, and a draw that lands on the fourth pass loses its
    explanation to the cap."""
    assert ANCHORS["combine_them"] in _delta()


def test_the_law_is_GUIDANCE_and_states_that_SEPARATING_IS_NOT_AN_ERROR():
    """HALF ONE OF THE RULED DISTINCTION. A model that separates them is not
    wrong, it is slower — and the law says so, so a later reader cannot mistake
    an economy for a rule."""
    assert ANCHORS["separating_is_allowed"] in _delta()


@pytest.mark.parametrize("ban", FORBIDDEN_BANS)
def test_the_law_is_NOT_a_prohibition(ban):
    """HALF TWO, and it is what a mutation turning guidance into a ban must hit.
    Only guidance was ruled; a prohibition would forbid a shape `turn_pass.py`
    services correctly, and it would contradict the permission above in the same
    breath — which is the DEC-55 failure this law is written to avoid."""
    assert ban not in _prompt(), (
        f"the clause became a PROHIBITION ({ban!r}) — only guidance was ruled")


def test_the_law_NAMES_the_two_pairs_rather_than_leaving_them_to_inference():
    """DEC-55's lesson, measured at T7: two rules that READ as a conflict get
    resolved unpredictably, because the model reads LINEARLY. Verify + point
    belong together; verify + move do not — and the law says which is which in
    its own first line."""
    delta = _delta()

    assert ANCHORS["the_two_pairs_named"] in delta
    assert ANCHORS["not_a_contradiction"] in delta


def test_the_EARLIER_verify_then_move_clause_is_still_there_and_unchanged():
    """The new law SCOPES it; it does not replace it. If a future edit deletes
    the earlier clause, this law's third bullet starts referring to a rule that
    is no longer in the prompt — a pointer into a rule that never existed, which
    fails quietly (the retired-doc lesson)."""
    prompt = _prompt()

    assert prompt.count("فلا تطلب التحقّق والانتقال") == 1, (
        "the verify-then-move clause is gone — this law scopes a rule that must "
        "still be in the prompt")
    assert prompt.index("فلا تطلب التحقّق والانتقال") < prompt.index(
        ANCHORS["the_two_pairs_named"]), (
        "the scoping clause now reads BEFORE the rule it scopes — the model "
        "reads linearly, which is the whole reason the pairs are named")


def test_the_law_states_WHY_rather_than_only_what():
    """Every law here carries its reason: the saved pass reaches the user as
    TIME, not as words."""
    assert ANCHORS["the_why"] in _delta()


def test_the_CONTROL_the_obvious_phrasings_would_have_proven_nothing():
    """A careless author would have anchored on these, and each already occurs
    elsewhere — so a test built on them would pass with the law deleted."""
    prompt = _prompt()
    for ambiguous in ("التحقّق", "الخطوة", "المستخدم"):
        assert prompt.count(ambiguous) > 1, (
            f"{ambiguous!r} is no longer ambiguous — the control has gone stale")


# ─── The law never resembles the boundary it is read inside (§3.2) ──────────

def test_the_law_shares_no_wording_with_the_LIVE_untrusted_delimiters():
    """Checked against the LIVE constants, never a copy."""
    delta = _delta()
    boundary_words = {word for word in (WRAP_OPEN_AR + " " + WRAP_CLOSE_AR).split()
                      if len(word) > 3}
    shared = sorted(word for word in boundary_words if word in delta)

    assert not shared, f"the law reproduces §3.2 delimiter wording: {shared}"


def test_persona_py_is_untouched_and_the_law_has_ONE_home():
    """`persona.py` holds the identity half and the composition; every LAW lives
    in the law modules."""
    persona = (SRC / "persona.py").read_text(encoding="utf-8")
    assert ANCHORS["combine_them"] not in persona

    holders = sorted(p.name for p in SRC.rglob("*.py")
                     if ANCHORS["separating_is_allowed"] in p.read_text(encoding="utf-8"))
    assert holders == ["persona_laws_navigator.py"], (
        f"the clause is written out in {holders} — it must have exactly one home")
