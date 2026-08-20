# tests/test_persona_verify_order_law.py
"""
WHEN TO VERIFY AND WHEN TO MOVE — DEC-108 Gate 2C's two persona clauses, and
the ruling that put them here instead of in the kernel.

TWO CLAUSES, TWO HOMES, AND THE SPLIT IS THE POINT.

  (a) THE DIRECTIVE LINE NAMES THE VERB when an active step exists. This is Gate
      2B item 3 RELOCATED by ruling after the measurement refuted its premise:
      gating what the model is OFFERED would have meant varying the tool
      catalogue per turn, and `tools` is the FIRST element of the cached prefix,
      so that costs a CloudReasoner protocol change AND invalidates the persona
      behind it. Naming the verb in the per-turn directive costs NOTHING — the
      directive is in the user message, not the cached prefix — and it is built
      only when a mode is running, on numbers the prelude has already read.

  (b) THE AUTHORING CLAUSE FOR FIRST-WINS. The kernel must NOT enforce an
      ordering between two verbs — that is a semantic judgement about turn
      shape, and `pass_servicing.py` is pinned as holding no ordering state —
      so the model carries it. The failure mode if it does not is ONE WASTED
      PASS inside the cap of 4, which is why guidance suffices here where a
      STRUCTURE was required for the evidence (Gate 2A).

THE METHOD IS DEC-41'S, unchanged:
  * `persona.py` BYTE-IDENTICAL, and the law has exactly ONE home;
  * the DELTA is pinned, not the prompt, with a SECOND anchor further back so a
    mangle-plus-rebase in one commit cannot pass both;
  * checked against the LIVE §3.2 delimiter constants, never a copy;
  * and the LAW is asserted, not its words — every anchor with `count(...) == 1`,
    plus a control proving the phrases a careless author would have reached for
    are genuinely ambiguous.

Run:  set PYTHONDONTWRITEBYTECODE=1 && set PYTHONPATH=src && python -m pytest tests/test_persona_verify_order_law.py -q
"""

from __future__ import annotations

import hashlib
import pathlib

import pytest

from muthis.kernel.deferral_notes import NAV_VERIFY_TOOL
from muthis.kernel.mode_surfaces import mode_directive_line
from muthis.kernel.untrusted_content import WRAP_CLOSE_AR, WRAP_OPEN_AR
from muthis.persona import build_saudi_persona_prompt

SENT_W, SENT_H = 1280, 720

# The composed prompt immediately BEFORE this law — the baseline for the
# additive proof. Regenerate ONLY with a deliberate re-approval.
PROMPT_BEFORE_VERIFY_ORDER_SHA256 = (
    "22233972b9abb94021aa0d04f85d223f331450e04be483351fec4fabf21315ac")
PROMPT_BEFORE_VERIFY_ORDER_CHARS = 13163

# An anchor further back, at a different depth — the baseline DEC-107 Gate 1's
# law was proven against, shared BY VALUE with that test.
PROMPT_BEFORE_STEP_RESULT_SHA256 = (
    "363970749368bb888b4f03b69962daa74736dff36cb23f703b18d471e5df6a9a")
PROMPT_BEFORE_STEP_RESULT_CHARS = 12259

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis"

# Each anchor is a LOAD-BEARING fragment of one clause: delete the clause and it
# disappears. Uniqueness is asserted, not assumed — see the control below.
ANCHORS = {
    "one_move_per_pass": "فلا تطلب التحقّق والانتقال",
    "a_proof_advances_itself": "فأنا أقدّم المسار بنفسي",
    "another_move_goes_next": "رجوع، أو قفزة، أو إنهاء",
}


def _prompt() -> str:
    return build_saudi_persona_prompt(SENT_W, SENT_H)


def _delta() -> str:
    return _prompt()[PROMPT_BEFORE_VERIFY_ORDER_CHARS:]


# ─── The delta is an ADDITION, not a mangle ─────────────────────────────────

def test_the_verify_order_law_is_purely_additive():
    """The composed prompt changed — the law was added — but every rule that
    existed before it is byte-identical, because it is APPENDED. A rewrite of
    any earlier rule fails HERE even if that rule's own test still passes."""
    prompt = _prompt()

    assert hashlib.sha256(prompt.encode()).hexdigest() != PROMPT_BEFORE_VERIFY_ORDER_SHA256, (
        "the composed prompt did not change — the law never reached the model")
    baseline = prompt[:PROMPT_BEFORE_VERIFY_ORDER_CHARS]
    assert hashlib.sha256(baseline.encode()).hexdigest() == PROMPT_BEFORE_VERIFY_ORDER_SHA256, (
        "a PRE-EXISTING persona rule was modified — this law must only APPEND")
    assert len(prompt) > PROMPT_BEFORE_VERIFY_ORDER_CHARS


def test_the_older_baseline_ALSO_still_holds():
    """Two anchors at different depths cannot both be re-based by accident (the
    DEC-57 method). This one predates DEC-107 Gate 1's law as well as this one,
    so a commit that mangled THAT law and re-approved THIS baseline fails here."""
    assert hashlib.sha256(
        _prompt()[:PROMPT_BEFORE_STEP_RESULT_CHARS].encode()
    ).hexdigest() == PROMPT_BEFORE_STEP_RESULT_SHA256


def test_the_extraction_that_preceded_this_law_left_the_prompt_untouched():
    """`persona_laws_navigator.py` was carved out of `persona_laws.py` in its own
    mechanical commit, and the composed prompt was proven byte-identical across
    it. The deeper baseline above is what proves it here: it predates the split,
    and it still matches."""
    composed = _prompt()

    assert composed.count(ANCHORS["one_move_per_pass"]) == 1
    assert PROMPT_BEFORE_STEP_RESULT_CHARS < PROMPT_BEFORE_VERIFY_ORDER_CHARS < len(composed)


# ─── Assert the LAW, not its words ──────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(ANCHORS))
def test_every_anchor_is_UNIQUE_in_the_whole_prompt(name):
    """THE PRECONDITION FOR EVERY ASSERTION BELOW. An anchor that already occurs
    elsewhere would keep a test green with the whole clause deleted — M2's sixth
    guard hole, exactly."""
    assert _prompt().count(ANCHORS[name]) == 1, (
        f"{name} is not unique — the assertion built on it proves nothing")


def test_the_law_states_ONE_MOVE_PER_THINKING_STEP():
    """First-wins is the KERNEL's existing behaviour and the kernel must not
    grow an ordering rule for it, so the model is told instead."""
    assert ANCHORS["one_move_per_pass"] in _delta()


def test_the_law_states_that_a_PROOF_ADVANCES_BY_ITSELF():
    """Without this the model cannot know that a proven step advances on its
    own, and it would spend its next pass asking for the advance it already
    earned — which the plan's edge would then refuse."""
    assert ANCHORS["a_proof_advances_itself"] in _delta()


def test_the_law_sends_ANY_OTHER_MOVE_to_the_next_thinking_step():
    """`back`, `jump` and `done` are unaffected by verification and still cost
    the pass's one navigator slot."""
    assert ANCHORS["another_move_goes_next"] in _delta()


def test_the_CONTROL_the_obvious_phrasings_would_have_proven_nothing():
    """A careless author would have anchored on these, and each already occurs
    in the prompt or occurs nowhere — so a test built on them would pass with
    the law deleted, or fail for the wrong reason."""
    prompt = _prompt()
    for ambiguous in ("الخطوة", "التحقّق", "المسار"):
        assert prompt.count(ambiguous) > 1, (
            f"{ambiguous!r} is no longer ambiguous — the control has gone stale "
            "and the anchors above should be re-examined")


# ─── The law never resembles the boundary it is read inside (§3.2) ──────────

def test_the_law_shares_no_wording_with_the_LIVE_untrusted_delimiters():
    """Checked against the LIVE constants, never a copy: a rule the model READS
    must not resemble the boundary it reads INSIDE, or a page could imitate one
    by quoting the other."""
    delta = _delta()
    boundary_words = {word for word in (WRAP_OPEN_AR + " " + WRAP_CLOSE_AR).split()
                      if len(word) > 3}
    shared = sorted(word for word in boundary_words if word in delta)

    assert not shared, f"the law reproduces §3.2 delimiter wording: {shared}"


def test_persona_py_is_untouched_and_the_law_has_ONE_home():
    """`persona.py` holds the identity half and the composition; every LAW lives
    in the law modules. A clause in both is two copies of one fact."""
    persona = (SRC / "persona.py").read_text(encoding="utf-8")
    assert ANCHORS["a_proof_advances_itself"] not in persona

    holders = sorted(p.name for p in SRC.rglob("*.py")
                     if ANCHORS["one_move_per_pass"] in p.read_text(encoding="utf-8"))
    assert holders == ["persona_laws_navigator.py"], (
        f"the clause is written out in {holders} — it must have exactly one home")


# ─── Clause (a): the DIRECTIVE names the verb, at zero cache cost ───────────

def test_the_directive_NAMES_the_verb_when_an_active_step_exists():
    """Item 3, relocated. The kernel does not gate what is OFFERED; it names the
    verb exactly when there is a step to verify, and the MODEL still decides
    whether to call it — the half of ruling ③ that survived the measurement."""
    line = mode_directive_line("توصيل الشبكة", 1, 3, "افتح الإعدادات")

    assert NAV_VERIFY_TOOL in line
    assert "\n" not in line, "the directive must stay ONE line"


def test_a_mode_with_NO_STEPS_is_not_invited_to_verify():
    """A mode without a plan has nothing to verify, so naming the verb would
    invite a call that can only be answered "there is no active step"."""
    assert NAV_VERIFY_TOOL not in mode_directive_line("review", 0, 0, None)


def test_the_verb_name_is_DERIVED_in_the_directive_and_never_SPELLED():
    """DEC-11's rule reaches the persona surfaces too: the separator lives in
    ONE place, and a hand-typed name is how a dot reached the provider once."""
    source = (SRC / "kernel" / "mode_surfaces.py").read_text(encoding="utf-8")

    assert "NAV_VERIFY_TOOL" in source
    assert "navigator__verify" not in source, (
        "the namespaced form is spelled out — it must be DERIVED")


def test_the_directive_is_NOT_in_the_cached_prefix_which_is_why_it_is_free():
    """THE MEASUREMENT THAT MOVED THE RULING, made testable. The persona is the
    cached prefix and the directive is not part of it — so naming the verb per
    turn invalidates no cache, where varying the TOOL CATALOGUE would have
    invalidated the persona behind it at every walkthrough boundary."""
    prompt = _prompt()

    assert NAV_VERIFY_TOOL not in prompt, (
        "the verb's name reached the CACHED prefix — the whole point of the "
        "relocation is that the directive is per-turn and the persona is not")
    assert "الخطوة {current} من" not in prompt, "a directive template leaked into the persona"
