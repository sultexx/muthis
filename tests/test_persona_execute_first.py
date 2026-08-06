# tests/test_persona_execute_first.py
"""
EXECUTE FIRST, REPORT COMPLETION, EXPLAIN ONLY WHEN ASKED — the persona law, and
the conflict it is deliberately scoped around.

THE MEASURED DEFECT (DEC-96). Ten real-usage cases; eight carried
`verbosity_sufficient: false`; only THREE were interaction-shaped, and TWO of
those three were this ONE defect:

  * case 3 — asked to INDEX a document, it explained how indexing works and
    summarised the document unprompted, when what was expected was "tell me you
    indexed it, then wait";
  * case 9 — asked a direct question, it opened with a preamble instead of the
    answer.

The user is left waiting to find out whether the thing happened at all.

THE CONFLICT THIS LAW IS SHAPED AROUND, and it is why the law is written about
the OPENING of an answer rather than about length. A blanket brevity rule was
available and is refused: `SessionMode` walks the user through a task and
explains AT EVERY STEP by design, so "be brief" would strangle the Navigator.
**A rule that reads as a contradiction gets resolved by the model, unpredictably
(DEC-55/DEC-84), so the exception is stated IN the law rather than left to
inference.** Two exceptions, both asserted below: an explanation the user asked
for outright, and the per-step explanation of a walkthrough.

THE METHOD IS DEC-41'S, the same one that caught a live trap before:
  * `persona.py` BYTE-IDENTICAL, proven by git rather than asserted here;
  * the law is PURELY ADDITIVE — the composed prompt as it stood before it is a
    byte-exact PREFIX, so no pre-existing rule moved;
  * the new text is checked against the LIVE §3.2 delimiter constants, because a
    law the model READS must never resemble the untrusted-content boundary it
    reads INSIDE;
  * and the LAW is asserted, not its words — a substring assertion is a cutoff,
    the family M16 landed in at T5. Every check below is aimed at a PROPERTY the
    law must have; deleting the clause takes them RED, and so does rewording it
    into a blanket brevity rule.

Run:  set PYTHONDONTWRITEBYTECODE=1 && set PYTHONPATH=src && python -m pytest tests/test_persona_execute_first.py -q
"""

from __future__ import annotations

import hashlib
import pathlib
import re

from muthis.kernel.untrusted_content import WRAP_CLOSE_AR, WRAP_OPEN_AR
from muthis.persona import build_saudi_persona_prompt

SENT_W, SENT_H = 1280, 720

# The composed prompt immediately BEFORE this law — the baseline for the additive
# proof. Regenerate ONLY with a deliberate re-approval.
PROMPT_BEFORE_EXECUTE_FIRST_SHA256 = (
    "821dce120da2a94e564f0f6c0a03d6c17fe1194059eeaf5350aee8b97b9af7c5")
PROMPT_BEFORE_EXECUTE_FIRST_CHARS = 11397

# An anchor further back, at a different depth. An edit that mangled an earlier
# law AND re-pinned the baseline above in the same commit would slip past that
# check; it cannot slip past this one as well. Shared by value with the identity,
# doc, voice and web law tests.
PROMPT_AT_T4_SHA256 = "b8a505568adb5e90282a069c2ca2c3f9e7b36aa179e55194816582ef1c7bace3"
PROMPT_AT_T4_CHARS = 8569

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis"


def _prompt() -> str:
    return build_saudi_persona_prompt(SENT_W, SENT_H)


def _delta() -> str:
    return _prompt()[PROMPT_BEFORE_EXECUTE_FIRST_CHARS:]


# ─── Rule 2: the delta is an addition, not a mangle ─────────────────────────

def test_the_execute_first_law_is_purely_additive():
    """The composed prompt changed — the law was added — but every rule that
    existed before it is byte-identical, because it is APPENDED. A rewrite of any
    earlier rule fails HERE even if that rule's own test still passes."""
    prompt = _prompt()

    assert hashlib.sha256(prompt.encode()).hexdigest() != PROMPT_BEFORE_EXECUTE_FIRST_SHA256, (
        "the composed prompt did not change — the law never reached the model")
    baseline = prompt[:PROMPT_BEFORE_EXECUTE_FIRST_CHARS]
    assert hashlib.sha256(baseline.encode()).hexdigest() == PROMPT_BEFORE_EXECUTE_FIRST_SHA256, (
        "a PRE-EXISTING persona rule was modified — this law must only APPEND")
    assert len(prompt) > PROMPT_BEFORE_EXECUTE_FIRST_CHARS


def test_the_older_baseline_ALSO_still_holds():
    """An anchor further back, so a mangle-plus-rebase in one commit cannot pass."""
    assert hashlib.sha256(
        _prompt()[:PROMPT_AT_T4_CHARS].encode()).hexdigest() == PROMPT_AT_T4_SHA256


# ─── Rule 4: assert the LAW, not its words ──────────────────────────────────

def test_the_law_orders_the_ACTION_before_the_explanation():
    """THE LAW ITSELF. Do the thing, say it is done, stop.

    Three obligations, and the defect needed all three: case 3 performed the
    action and then buried the completion under an explanation nobody asked for,
    so 'execute' alone would not have caught it."""
    delta = _delta()

    assert "نفّذ أول" in delta, "the law no longer orders the action FIRST"
    assert "خلّصت" in delta, "the law no longer orders a COMPLETION report"
    assert "ولا تشرح إلا إذا طُلب" in delta, (
        "the law no longer withholds the explanation until it is asked for")


def test_the_law_bans_the_TWO_measured_openings():
    """The two shapes that were actually observed, banned by NAME.

    Case 3 opened with the mechanism and an unrequested summary; case 9 opened
    with a preamble. A law that banned only one of them would have left half the
    measured defect in place."""
    delta = _delta()

    assert "ممنوع تفتتح الإجابة بشرح آلية" in delta, (
        "explaining the mechanism of what was just done is permitted again (case 3)")
    assert "بتلخيص ما طلبه أحد" in delta, (
        "the unrequested summary is permitted again (case 3)")
    assert "بلا تمهيد" in delta, "the preamble is permitted again (case 9)"


def test_the_law_is_scoped_PER_ANSWER_and_is_TOOL_AGNOSTIC():
    """DEC-84's correction, applied on arrival instead of after a live failure.

    A rule written per tool family has to be RE-EARNED by the next capability —
    which is exactly how the ack gap arrived. The scope is the OPENING of an
    answer, whatever tools that answer happened to call."""
    delta = _delta()

    assert "افتتاح الإجابة وحدها" in delta, (
        "the law is no longer scoped to the OPENING of an answer — as a blanket "
        "rule it collides with every turn that is legitimately long")
    assert "مهما كانت الأدوات" in delta, (
        "the law is not tool-agnostic; a future capability would have to re-earn "
        "it, which is the DEC-84 defect being reintroduced")


def test_the_law_does_NOT_strangle_a_step_by_step_walkthrough():
    """THE CONFLICT GUARD, and it is the reason this law is not a brevity rule.

    `SessionMode` explains at every step BY DESIGN. Both exceptions are asserted
    together because a law carrying only one of them still reads as a
    contradiction in the case it omits — and a model resolving a contradiction
    picks one, unpredictably (DEC-55)."""
    delta = _delta()

    assert "خطوة خطوة" in delta, (
        "the walkthrough exception is gone — this law now contradicts the "
        "Navigator's whole purpose, which explains at every step by design")
    assert "الشرح في كل خطوة هو المطلوب" in delta, (
        "the walkthrough exception no longer says the per-step explanation is "
        "WANTED there; a bare mention is not an exception")
    assert "شرحاً طلبه المستخدم صراحةً" in delta, (
        "an explicitly requested explanation is no longer exempt — the law now "
        "overrides the user, which inverts the persona's priority order")


def test_the_expansion_is_OFFERED_and_never_started_unprompted():
    """The positive half. 'Do not explain' with no sanctioned alternative leaves
    the model no move and the helpful move is the wrong one — the DEC-49 shape,
    where a prohibition alone produced the behaviour it meant to stop."""
    delta = _delta()

    assert "بسؤال قصير واحد" in delta, "the law no longer sanctions OFFERING more"
    assert "ولا تبدأ فيها من نفسك" in delta, (
        "the law no longer forbids starting the expansion unprompted, which is "
        "the behaviour measured in cases 3 and 9")


def test_the_law_states_its_own_WHY():
    """Every persona law here carries its reason, because the reason is what
    stops a later edit from simplifying it back into the hole it closes."""
    assert "وليه:" in _delta(), "the law lost its stated reason"


# ─── The boundary and surface checks every persona law must pass ────────────

def test_the_law_does_not_resemble_the_untrusted_boundary():
    """DEC-14's rule, checked against the LIVE §3.2 constants so a future
    rewording of the delimiters re-runs this comparison automatically."""
    boundary = ((set(WRAP_OPEN_AR.split()) | set(WRAP_CLOSE_AR.split()))
                - {"—", "{source}", "{nonce}", "لا"})
    shared = boundary & set(_delta().split())
    assert not shared, (
        f"the execute-first law shares wording with the untrusted delimiters: "
        f"{sorted(shared)}")


def test_the_law_carries_no_formatting_syntax_and_no_urls():
    """The surface is TTS and a captions bar, never a markdown renderer."""
    delta = _delta()

    for token in ("**", "##", "`", "http://", "https://", "- [", "|"):
        assert token not in delta, f"the execute-first law carries {token!r}"
    assert not re.search(r"^\s*[*+]\s", delta, re.MULTILINE), "markdown bullets"


# ─── Rule 1: persona.py byte-identical, and the law has ONE home ────────────

def test_persona_py_is_untouched_and_no_clause_leaked_into_it():
    """`persona.py` holds the identity half and the composition; every LAW lives
    in `persona_laws.py`. A clause appearing in both is two copies of one fact."""
    persona = (SRC / "persona.py").read_text(encoding="utf-8")
    assert "نفّذ أول" not in persona, "the law leaked into persona.py"

    laws = (SRC / "persona_laws.py").read_text(encoding="utf-8")
    assert "نفّذ أول" in laws, "the law is not in persona_laws.py"

    holders = sorted(p.name for p in SRC.rglob("*.py")
                     if "افتتاح الإجابة وحدها" in p.read_text(encoding="utf-8"))
    assert holders == ["persona_laws.py"], (
        f"the execute-first scope is written out in {holders} — it must have "
        "exactly one home, or the two wordings drift apart")
