# tests/test_persona_code_law.py
"""
THE CODE-EXECUTION LAWS — run it when reading cannot settle it, decline when
running cannot, and never present an extraction as the user's code (DEC-113).

THIS LAW PRESERVES BEHAVIOUR THAT WAS MEASURED HOLDING WITHOUT IT, which changes
what these tests are for. Under the real persona, the real catalogue at
`tool_choice="auto"` and the real `SandboxRunner`: 15/15 reached the sandbox where
reading could not settle the question and were correct 15/15; 18/18 declined where
execution could not settle it, reaching for the sandbox 0/18; and false claims of
having run something were 0 in 36, twice. So a green suite here does NOT prove the
law works — the behaviour predates it. What it proves is that the law is IN THE
PROMPT, says what was ruled, and has not acquired the one clause P0 forbade.

THE FORBIDDEN CLAUSE IS ASSERTED AS AN ABSENCE, AND IT IS THE POINT OF THIS FILE.
The measured zero false claims is a zero because the model NEVER CLAIMS — it
states results without narrating mechanism. An instruction to announce a run would
manufacture the one failure mode that cannot occur today: claiming a run that did
not happen. `test_the_law_does_NOT_instruct_the_model_to_ANNOUNCE_a_run` is what a
well-meaning future edit has to get past.

THE METHOD IS DEC-41'S: `persona.py` byte-identical with the law in ONE home; the
DELTA pinned with a second anchor further back; checked against the LIVE §3.2
constants; the LAW asserted with `count(...) == 1` per anchor plus a staleness
control.

AND THE PLACEMENT IS PART OF THE PROOF. `CODE_LAWS` is composed LAST, in
`persona_rules.py`, rather than appended inside `MILESTONE_LAWS` — that block is
concatenated BEFORE `NAVIGATOR_LAWS`, so a law added there lands MID-PROMPT and
re-bases four additive prefix-hash proofs at once. Composed last, every earlier
proof still points at the same bytes, and `test_EVERY_earlier_law_proof_still_
points_at_the_same_bytes` asserts exactly that.

Run:  set PYTHONDONTWRITEBYTECODE=1 && set PYTHONPATH=src && python -m pytest tests/test_persona_code_law.py -q
"""

from __future__ import annotations

import hashlib
import pathlib

import pytest

from muthis.kernel.untrusted_content import WRAP_CLOSE_AR, WRAP_OPEN_AR
from muthis.persona import build_saudi_persona_prompt
from muthis.persona_laws_code import CODE_LAWS

SENT_W, SENT_H = 1280, 720

# The composed prompt immediately BEFORE this law. Regenerate ONLY with a
# deliberate re-approval.
PROMPT_BEFORE_CODE_LAWS_SHA256 = (
    "540e52fb49fda79ec14389979a0a086b76848fb8dc2606b1ddfa00d2302be1b5")
PROMPT_BEFORE_CODE_LAWS_CHARS = 14822

# An anchor further back, at a different depth — the baseline the PASS-ECONOMY
# law was proven against, shared BY VALUE with that test.
PROMPT_BEFORE_PASS_ECONOMY_SHA256 = (
    "aad94e985d5260a1932989b8cfaedcd2ced415c24babc173576176b45d903f9f")
PROMPT_BEFORE_PASS_ECONOMY_CHARS = 14211

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis"

ANCHORS = {
    "run_when_reading_cannot": "فشغّله في الصندوق",
    "decline_when_running_cannot": "ما ينحسم بالتشغيل أصلاً",
    "declare_the_limit": "وحدودك تُقال كما هي",
    "probe_not_copy": "مِجَسّ لا نسخة",
    "never_as_their_code": "على أنه كوده",
    "the_why": "ينقلب خطأً صامتاً",
}

# Phrasings that would turn this into an instruction to ANNOUNCE a run. None may
# appear: today's zero false claims exists BECAUSE the model never claims, so
# this clause would create the failure mode rather than close it.
FORBIDDEN_ANNOUNCEMENTS = (
    "قل إنك شغّلت", "قل إنك نفّذت", "اذكر أنك شغّلت", "صرّح أنك شغّلت",
    "وقل إنك شغّلته", "قل إنك جرّبت", "بيّن أنك شغّلت",
)


def _prompt() -> str:
    return build_saudi_persona_prompt(SENT_W, SENT_H)


def _delta() -> str:
    return _prompt()[PROMPT_BEFORE_CODE_LAWS_CHARS:]


# ─── The delta is an ADDITION, not a mangle ─────────────────────────────────

def test_the_code_laws_are_purely_additive():
    """The composed prompt changed — the law reached the model — but every rule
    that existed before it is byte-identical, because it is APPENDED."""
    prompt = _prompt()

    assert hashlib.sha256(prompt.encode()).hexdigest() != PROMPT_BEFORE_CODE_LAWS_SHA256, (
        "the composed prompt did not change — the law never reached the model")
    baseline = prompt[:PROMPT_BEFORE_CODE_LAWS_CHARS]
    assert hashlib.sha256(baseline.encode()).hexdigest() == PROMPT_BEFORE_CODE_LAWS_SHA256, (
        "a PRE-EXISTING persona rule was modified — this law must only APPEND")


def test_EVERY_earlier_law_proof_still_points_at_the_same_bytes():
    """Two anchors at different depths cannot both be re-based by accident — and
    this one is the placement proof. Appended inside `MILESTONE_LAWS` the law
    would land BEFORE `NAVIGATOR_LAWS` and this assertion would fail."""
    assert hashlib.sha256(
        _prompt()[:PROMPT_BEFORE_PASS_ECONOMY_CHARS].encode()
    ).hexdigest() == PROMPT_BEFORE_PASS_ECONOMY_SHA256


def test_the_law_is_the_TAIL_of_the_prompt():
    """Composed LAST. If a later law is appended after it, that law owns the tail
    and re-pins from here — this assertion is what forces that to be noticed."""
    assert _prompt().endswith(CODE_LAWS)
    assert _delta() == CODE_LAWS


# ─── Assert the LAW, not its words ──────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(ANCHORS))
def test_every_anchor_is_UNIQUE_in_the_whole_prompt(name):
    """THE PRECONDITION FOR EVERY ASSERTION BELOW. An anchor that already occurs
    elsewhere would keep a test green with the whole clause deleted."""
    assert _prompt().count(ANCHORS[name]) == 1, (
        f"{name} is not unique — the assertion built on it proves nothing")


def test_the_law_says_to_RUN_where_reading_cannot_settle_the_question():
    """The measured regime: 15/15 reached, 15/15 correct, output tokens falling
    from a median of 11,179 to 404."""
    assert ANCHORS["run_when_reading_cannot"] in _delta()


def test_the_law_says_to_DECLINE_where_running_cannot_settle_the_question():
    """The other half, and it must sit in the SAME law. Split across two the
    model reads them linearly and the second reads as a retraction of the first
    — DEC-55's measured failure."""
    delta = _delta()

    assert ANCHORS["decline_when_running_cannot"] in delta
    assert delta.index(ANCHORS["run_when_reading_cannot"]) < delta.index(
        ANCHORS["decline_when_running_cannot"]), (
        "the decline clause reads before the permission it qualifies")


def test_the_law_requires_DECLARING_the_limit_rather_than_over_claiming():
    assert ANCHORS["declare_the_limit"] in _delta()


@pytest.mark.parametrize("phrase", FORBIDDEN_ANNOUNCEMENTS)
def test_the_law_does_NOT_instruct_the_model_to_ANNOUNCE_a_run(phrase):
    """THE RULED PROHIBITION, and the reason is counter-intuitive enough that it
    is written out here. Zero false execution claims were measured twice — and
    that zero exists BECAUSE the model never claims, not because it discriminates
    truthfully. Telling it to say it ran creates the failure mode P0 explicitly
    forbade. If this is ever wanted it is MEASURED AFTER IT LANDS, with the
    claim-marker detector and its 5/5 positive and 3/3 negative controls."""
    assert phrase not in _prompt(), (
        f"the law now instructs the model to announce a run ({phrase!r}) — the "
        "one fix P0 forbade")


# ─── The probe clause — the one thing measurement said was missing ──────────

def test_the_law_states_that_an_extraction_is_a_PROBE_not_a_COPY():
    """MEASURED, not anticipated: `MAX_STEP_CHARS` reached the sandbox as the
    literal `160` while the extraction itself was correct."""
    assert ANCHORS["probe_not_copy"] in _delta()


def test_the_law_FORBIDS_presenting_an_extraction_as_the_users_code():
    """The binding constraint in its operative form. Correct as a probe, a silent
    divergence the moment anyone treats it as the file."""
    assert ANCHORS["never_as_their_code"] in _delta()


def test_the_probe_clause_states_WHY_rather_than_only_what():
    """Every law here carries its reason: an inlined value does not move when the
    file moves, so a true probe becomes a silent error if read as the original."""
    assert ANCHORS["the_why"] in _delta()


# ─── Controls and the boundary it is read inside (§3.2) ─────────────────────

def test_the_CONTROL_the_obvious_phrasings_would_have_proven_nothing():
    """A careless author would have anchored on these, and each already occurs
    elsewhere — so a test built on them would pass with the law deleted."""
    prompt = _prompt()
    for ambiguous in ("الصندوق", "المستخدم", "الملف"):
        assert prompt.count(ambiguous) > 1, (
            f"{ambiguous!r} is no longer ambiguous — the control has gone stale")


def test_the_law_shares_no_wording_with_the_LIVE_untrusted_delimiters():
    """Checked against the LIVE constants, never a copy. A rule the model READS
    must never resemble the boundary it reads INSIDE."""
    delta = _delta()
    boundary_words = {word for word in (WRAP_OPEN_AR + " " + WRAP_CLOSE_AR).split()
                      if len(word) > 3}
    shared = sorted(word for word in boundary_words if word in delta)

    assert not shared, f"the law reproduces §3.2 delimiter wording: {shared}"


def test_the_law_does_not_collide_with_the_pinned_spoken_acks():
    """«شفت» and «زين» are the LIVE-MEASURED acks pinned by the voice law. A law
    containing either would make that guard read this text as an ack."""
    for ack in ("شفت", "زين"):
        assert ack not in CODE_LAWS


def test_persona_py_is_untouched_and_the_law_has_ONE_home():
    """`persona.py` holds the identity half and the composition; every LAW lives
    in a law module, and this one lives in exactly one."""
    persona = (SRC / "persona.py").read_text(encoding="utf-8")
    assert ANCHORS["probe_not_copy"] not in persona

    holders = sorted(p.name for p in SRC.rglob("*.py")
                     if ANCHORS["never_as_their_code"] in p.read_text(encoding="utf-8"))
    assert holders == ["persona_laws_code.py"], (
        f"the clause is written out in {holders} — it must have exactly one home")
