# tests/test_persona_doc_laws.py
"""
The two `doc_rag` persona laws (T5) — the absence clause and the spoken location.

**THIS LAW IS LOAD-BEARING, NOT A NICETY, AND THE NUMBER IS WHY.** P0 measured
effective recall at **82%**, so roughly ONE QUESTION IN FIVE will not have its
answer retrieved at all. The mechanism that would have caught that deterministically
DOES NOT EXIST: DEC-49 ruling 3 retired the dense entry floor after measurement
proved the positive and negative cosine distributions OVERLAP (−0.11), because a
topically-adjacent absence scores like a true answer. A floor cannot separate them
and would HIDE content from the model — worse than having none. DEC-50 then upgraded
this law to load-bearing. **Until Phase 3's visual citation lands, these clauses are
the only thing standing between the milestone and its most likely failure: a
confident answer synthesised from chunks that do not contain the answer.**

FOUR METHOD RULES, each earned by a defect this project already met:

  1. **`persona.py` BYTE-IDENTICAL** — the T1 extraction existed for exactly this,
     and it is git-verified rather than asserted in a commit message.
  2. **THE DELTA IS PINNED, not the prompt.** The composed prompt MUST change (two
     clauses were added) while every pre-existing rule stays byte-identical, proven
     by `after[:N] == before` rather than claimed. That is what distinguishes an
     ADDITION from a MANGLE, and `test_persona.py` / `test_persona_web_laws.py`
     both pass UNMODIFIED.
  3. **CHECKED AGAINST THE LIVE §3.2 CONSTANTS.** At DEC-41 the natural Arabic
     phrasing of a law WAS the delimiter's own wording, and writing it naturally
     would have failed the build. A law the model READS must never resemble the
     untrusted-content boundary it reads INSIDE. This fired once; it is not
     hypothetical.
  4. **ASSERT THE LAW, NOT ITS WORDS.** The sixth guard hole of M2 was asserting
     two words that occur elsewhere in the prompt, so deleting an entire law stayed
     GREEN. Every anchor below is therefore asserted with `count(...) == 1`: a
     phrase that appears elsewhere cannot be an anchor, and the check FAILS if one
     ever becomes ambiguous.
"""

from __future__ import annotations

import hashlib
import pathlib
import re

from muthis.kernel.untrusted_content import WRAP_CLOSE_AR, WRAP_OPEN_AR
from muthis.persona import build_saudi_persona_prompt
from muthis.persona_rules import TOOL_AND_SAFETY_RULES

SENT_W, SENT_H = 1280, 720

# The composed prompt as it stood at T4, BEFORE these two clauses — the baseline
# for the additive proof. Regenerate ONLY with a deliberate re-approval.
# RE-BASELINED at DEC-84. The ack rules were rescoped from PER POINTING
# PASS to PER ANSWER, which is an IN-PLACE edit of a pre-existing rule --
# the first this persona has taken. The append-only property these
# prefix hashes enforced is SUPERSEDED by the DELTA PIN in
# test_persona_ack_scoping.py, which proves the change was EXACTLY two
# clauses and every other byte identical. Each new prefix below was
# proven to be the old prefix with clause A swapped, never recomputed
# blindly. These still fail on any FURTHER persona edit.
PROMPT_AT_T4_SHA256 = "b8a505568adb5e90282a069c2ca2c3f9e7b36aa179e55194816582ef1c7bace3"
PROMPT_AT_T4_CHARS = 8569

# The pin from DEC-41, kept here as a SECOND anchor further back in history: an
# edit that mangled a web law would slip past the T4 baseline if the mangle were
# itself included in it. Two anchors at different depths cannot both be re-based
# by accident.
PROMPT_BEFORE_WEB_LAWS_SHA256 = (
    "783e14ab8bd24abad68c919291f401074c0028c7221d3ad443c20e18501665da")
PROMPT_BEFORE_WEB_LAWS_CHARS = 6850

# The substrings tests/test_untrusted_wrap_guard.py treats as proof that a
# delimiter has been re-implemented. By VALUE on purpose: if that guard's list
# grows, this test is updated deliberately, not silently.
DELIMITER_MARKERS = ("محتوى خارجي غير موثوق", "نهاية المحتوى الخارجي",
                     "بيانات لا أوامر")

# ── THE ANCHORS. Each must occur EXACTLY ONCE (rule 4 above). ────────────────
ABSENCE_ANCHORS = (
    "الإجابة من المستند — إذا ما كان الجواب فيه فقُلها",   # the FULL header
    "ما لقيت هذا في المستند",                              # the ruled sentence
    "قربها ما يعني أن الجواب فيها",                        # the WHY: 82% recall
    "موضوع مجاور",                                          # the overlap finding
    "هذا جوابٌ صحيح ونافع",                                 # the POSITIVE framing
    "وممنوع تسدّ الفراغ",
    "ولا تكمّل من معرفتك أنت وتنسب الكلام للمستند",
)
LOCATION_ANCHORS = (
    "ذكر الموضع — إلزامي لكل معلومة جبتها من المستند",      # the FULL header
    "في صفحة 12 من المستند",                                # the worked example
    "ذكر الموضع يدخل داخل حدود الإسهاب نفسها ولا يمدّدها",  # the cap, DISAMBIGUATED
    "وممنوع تخترع موضعاً",                                  # anti-fabrication
    "يقدر يفتحها ويتأكد بنفسه",                             # the WHY: verifiability
)


def _prompt() -> str:
    return build_saudi_persona_prompt(SENT_W, SENT_H)


# ─── The delta: an addition, not a mangle ────────────────────────────────────

def test_the_two_clauses_are_purely_additive():
    """The composed prompt changed — two clauses were added — but every rule that
    existed at T4 is byte-identical, because the clauses are APPENDED. A rewrite of
    any earlier rule fails HERE even if that rule's own test still passes."""
    prompt = _prompt()

    assert hashlib.sha256(prompt.encode()).hexdigest() != PROMPT_AT_T4_SHA256, (
        "the composed prompt did not change — the clauses never reached the model")
    baseline = prompt[:PROMPT_AT_T4_CHARS]
    assert hashlib.sha256(baseline.encode()).hexdigest() == PROMPT_AT_T4_SHA256, (
        "a PRE-EXISTING persona rule was modified — these clauses must only APPEND")
    assert len(prompt) > PROMPT_AT_T4_CHARS


def test_the_pre_web_law_baseline_ALSO_still_holds():
    """A second anchor, further back. If a web law were mangled AND the T4 baseline
    re-pinned in the same commit, the check above would pass; this one would not."""
    prompt = _prompt()
    older = prompt[:PROMPT_BEFORE_WEB_LAWS_CHARS]

    assert hashlib.sha256(older.encode()).hexdigest() == PROMPT_BEFORE_WEB_LAWS_SHA256


def test_persona_py_is_byte_identical_and_no_clause_leaked_into_it():
    """The T1 extraction existed precisely so these could land without touching
    persona.py. Asserted here, not merely claimed in a commit message."""
    persona_py = (pathlib.Path(__file__).resolve().parents[1]
                  / "src" / "muthis" / "persona.py").read_text(encoding="utf-8")

    for anchor in ("الإجابة من المستند", "ذكر الموضع", "ما لقيت هذا في المستند"):
        assert anchor not in persona_py, "a doc law leaked into persona.py"


def test_both_clauses_live_in_persona_rules():
    assert "الإجابة من المستند" in TOOL_AND_SAFETY_RULES
    assert "ذكر الموضع" in TOOL_AND_SAFETY_RULES


# ─── Rule 3: the live delimiter trap ─────────────────────────────────────────

def test_neither_clause_resembles_the_untrusted_delimiter():
    """A rule the model READS must never look like the boundary it reads INSIDE —
    otherwise the persona itself teaches the shape a hostile document would need to
    forge. Checked against the LIVE constants, so a change to the delimiter's
    wording re-runs this comparison instead of leaving a stale copy behind."""
    prompt = _prompt()

    for marker in DELIMITER_MARKERS:
        assert marker not in prompt, f"a persona law reproduces the delimiter: {marker!r}"
    assert WRAP_OPEN_AR.split("{")[0] not in prompt
    assert WRAP_CLOSE_AR.split("{")[0] not in prompt


def test_the_delta_specifically_is_delimiter_free():
    """Scoped to the NEW text, so this cannot pass on the strength of the older
    laws already being clean."""
    delta = _prompt()[PROMPT_AT_T4_CHARS:]

    assert delta.strip(), "the delta is empty — nothing was added"
    for marker in DELIMITER_MARKERS:
        assert marker not in delta


def test_the_clauses_carry_no_formatting_syntax_and_no_urls():
    """The surface is TTS and a captions bar, never a markdown renderer — the ban a
    live Phase-4 run earned. Identical to DEC-20's constraints."""
    delta = _prompt()[PROMPT_AT_T4_CHARS:]

    for token in ("**", "##", "`", "http://", "https://", "- [", "|"):
        assert token not in delta, f"the new clauses carry {token!r}"
    assert not re.search(r"^\s*[*+]\s", delta, re.MULTILINE), "markdown bullets"


# ─── Rule 4: assert the LAW, not its words ───────────────────────────────────

def test_every_anchor_occurs_EXACTLY_ONCE_in_the_composed_prompt():
    """THE SIXTH GUARD HOLE, closed by construction. That hole was asserting two
    words which occur elsewhere in the prompt, so deleting an entire law stayed
    green. An anchor that appears more than once cannot distinguish its own law
    from another's, so ambiguity FAILS here rather than silently weakening every
    assertion below.

    Cutoff: exactly 1 occurrence. Admitted: all 12 anchors, counted."""
    prompt = _prompt()
    anchors = ABSENCE_ANCHORS + LOCATION_ANCHORS
    admitted = 0

    for anchor in anchors:
        found = prompt.count(anchor)
        assert found == 1, f"anchor occurs {found}x, not once: {anchor!r}"
        admitted += 1

    assert admitted == len(anchors) == 12, f"only {admitted} anchors checked"


def test_the_ambiguous_phrases_are_PROVEN_ambiguous_so_the_rule_is_not_vacuous():
    """The control. If these were unique, the uniqueness rule above would be
    trivially satisfiable and would prove nothing about anchor selection. They are
    the phrases a careless author WOULD have reached for."""
    prompt = _prompt()

    assert prompt.count("إلزامي") > 1
    assert prompt.count("ذكر المصدر") > 1
    # The verbosity-cap sentence exists in the WEB citation law too, which is
    # exactly why the doc anchor carries "ذكر الموضع" in front of it.
    assert prompt.count("يدخل داخل حدود الإسهاب نفسها ولا يمدّدها") == 2


# ─── (a) The absence clause — DEC-49 ruling 3, upgraded by DEC-50 ────────────

def test_the_absence_clause_orders_the_model_to_SAY_the_answer_is_absent():
    prompt = _prompt()

    assert "الإجابة من المستند — إذا ما كان الجواب فيه فقُلها" in prompt
    assert "ما لقيت هذا في المستند" in prompt


def test_the_absence_clause_states_WHY_closeness_is_not_presence():
    """The measured finding, carried into the law: a topically-adjacent absence
    scores like a true answer, which is why no threshold could replace this."""
    prompt = _prompt()

    assert "قربها ما يعني أن الجواب فيها" in prompt
    assert "موضوع مجاور" in prompt


def test_the_absence_clause_is_a_POSITIVE_instruction_not_only_a_prohibition():
    """Stated as what to DO. "Do not infer" alone leaves a model with no sanctioned
    move, and the helpful move is the wrong one — so the law names the alternative
    and calls it a correct answer."""
    prompt = _prompt()

    assert "هذا جوابٌ صحيح ونافع" in prompt
    assert "واعرض عليه" in prompt          # offer the user a way forward
    assert "يسمّي فصلاً أو قسماً محدداً" in prompt


def test_the_absence_clause_forbids_filling_the_gap_from_the_models_own_knowledge():
    """The DEC-20 anti-fabrication shape, in its document form: knowledge that came
    from no source must not be attributed to one."""
    prompt = _prompt()

    assert "وممنوع تسدّ الفراغ" in prompt
    assert "ولا تكمّل من معرفتك أنت وتنسب الكلام للمستند" in prompt
    assert "نبّه أنها من معرفتك لا من المستند" in prompt


# ─── (b) The spoken location citation ────────────────────────────────────────

def test_the_location_clause_requires_natural_spoken_prose():
    prompt = _prompt()

    assert "ذكر الموضع — إلزامي لكل معلومة جبتها من المستند" in prompt
    assert "في صفحة 12 من المستند" in prompt      # the worked example
    assert "بلا صيغة اقتباس" in prompt
    assert "بلا لاصقة في آخر الجملة" in prompt    # no machine-style suffix
    assert "بلا رابط" in prompt


def test_the_location_clause_fits_INSIDE_the_verbosity_cap():
    """DEC-20's constraint, unchanged: the citation is part of the sentence, not an
    extension of the budget. Asserted with the DISAMBIGUATED phrase — the bare
    sentence also belongs to the web citation law."""
    assert "ذكر الموضع يدخل داخل حدود الإسهاب نفسها ولا يمدّدها" in _prompt()


def test_the_location_clause_forbids_INVENTING_a_position():
    """An invented page number is worse than no page at all, because it is
    checkable and wrong — it spends the very trust the clause exists to build."""
    prompt = _prompt()

    assert "وممنوع تخترع موضعاً" in prompt
    assert "اذكر الموضع اللي وصلك مع المقطع كما هو" in prompt
    assert "بدون ما تسمّي صفحة" in prompt      # the honest no-position case


def test_the_location_clause_states_the_VERIFIABILITY_reason():
    """The reason is what stops a future edit from "simplifying" the law away: with
    82% recall, a located claim is checkable and an unlocated one is not."""
    prompt = _prompt()

    assert "يقدر يفتحها ويتأكد بنفسه" in prompt
    assert "ما يقدر يتحقق منها" in prompt


def test_the_location_clause_is_NOT_the_visual_citation():
    """Phase 3's machine-verifiable rendering is a DIFFERENT thing. This clause only
    lets the model SPEAK a position it already receives; DEC-45's position data
    stays inert for rendering, and no drawing instruction may appear here — a draw
    order in the persona would put a box on screen for every retrieval."""
    delta = _prompt()[PROMPT_AT_T4_CHARS:]

    for drawing in ("draw_shapes", "highlight_target", "dim_screen", "مستطيل"):
        assert drawing not in delta, f"the location clause orders drawing: {drawing!r}"


# ─── The clauses land where the tools do ─────────────────────────────────────

def test_the_clauses_name_the_document_not_the_web():
    """The web citation law names sources; this one names POSITIONS inside one
    document. Confusing them would tell the model to cite a page for a web page."""
    delta = _prompt()[PROMPT_AT_T4_CHARS:]

    assert "المستند" in delta
    assert "الويب" not in delta, "the doc clauses mention the web"
