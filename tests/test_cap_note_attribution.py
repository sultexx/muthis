# tests/test_cap_note_attribution.py
"""
WHO ENDED THE TURN — `AGENTIC_CAP_NOTE_AR`'s attribution (DEC-111 ①, executed).

THE DEFECT WAS MEASURED LIVE AND IT WAS A LIE ABOUT THE AGENT. Sultan saw a
CORRECT draw land and then heard «اكتفيت بهذا القدر» — «I have had enough of
this much» — three times in one SOP, with `agentic cap (4) hit` ×3 in the log.
The note was written for a model that would not stop; his case is the INVERSE.
The mechanism admits no other shape: once anything is drawn the next call is
`tool_choice="none"` and the turn ends, so the cap note is reachable ONLY if the
draw landed on the FOURTH pass — the model was mid-answer and the LOOP cut it.

THIS IS DEC-58'S CLASS, AND IT FAILS THE FIRST OBLIGATION BEFORE THE OTHER TWO
MATTER. The standing note law requires every note to state the STATE ACHIEVED,
whether the condition is TERMINAL or TRANSIENT, and the VALID NEXT STEP. The old
text carried a next step («اسألني من جديد») and still reported the wrong state,
because a note that names the wrong agent has already misreported what happened.
So this file asserts BOTH halves and proves each against the shipped defect:
the three obligations must be PRESENT, and no wording that hands the ending to
Mut'his — or to the user — may appear.

THE CAP ITSELF IS NOT TOUCHED. DEC-111 ruled `MAX_AGENTIC_ITERATIONS` stays at 4
and the ruling is not reopened here; this is a MESSAGE-layer fix, which is
exactly the line the note law draws (it never licenses moving a bound to make a
note easier to write).

THE SCANNERS CARRY CONTROLS IN BOTH DIRECTIONS, because a ban list that flags
nothing and a ban list that flags everything fail identically in a green run:
the shipped defect and five plausible rewordings must be FLAGGED, and an honest
alternative wording must NOT be — otherwise the guard cries wolf and gets read
as noise the first time someone rewords the note legitimately.

Run:  set PYTHONDONTWRITEBYTECODE=1 && set PYTHONPATH=src && python -m pytest tests/test_cap_note_attribution.py -q
"""

from __future__ import annotations

import pathlib

import pytest

from muthis.kernel import orchestrator
from muthis.kernel.turn import AGENTIC_CAP_NOTE_AR

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis"

# The text that SHIPPED and was heard live. Kept here as the positive control —
# every scanner below must reject it, or the scanner is examining nothing.
THE_SHIPPED_DEFECT = "اكتفيت بهذا القدر الآن، إذا تبي أكمل اسألني من جديد."

# ─── The three obligations, one anchor group each ────────────────────────────

# (1) THE STATE: cut short by a limit rather than completed. Two anchors, because
# "the answer is incomplete" without a named cause reads as a failure, and "a
# limit was reached" without the incompleteness reads as a status line.
CUT_BY_A_LIMIT = ("انقطع الجواب قبل ما يكمل", "وصلت للحد المسموح به")

# (2) TERMINAL or TRANSIENT — and a transient condition must say WHAT CHANGES,
# so «مؤقت» alone is not enough.
TRANSIENT = ("حد مؤقت", "يبدأ من جديد مع كل سؤال")

# (3) THE VALID NEXT STEP, named — asking again for the REMAINDER specifically,
# not a bare "ask again" that invites the whole turn to be re-issued.
NEXT_STEP = ("اسألني عن الباقي", "وأكمله لك")

# ─── The bans — three families, three different lies ─────────────────────────

# Mut'his DECIDED to stop. This is the shipped defect and its neighbours.
SELF_ATTRIBUTION_BANS = ("اكتف", "أكتف", "كفاية", "قررت", "اخترت", "ما ودي", "بس كذا")

# The USER caused it. VERIFY_FALLBACK_AR's precedent, one note over: a limit on
# Mut'his's side must say so and must not become a statement about the user.
USER_BLAME_BANS = ("بسببك", "سؤالك", "طلبك طويل", "قصّرت", "غلطت", "ما وريتني", "تأخرت")

# The condition is TERMINAL. It is not: the next turn resets the loop.
TERMINAL_BANS = ("لا تحاول مرة أخرى", "ما أقدر أكمل", "انتهت الجلسة", "ما فيه فايدة")


def _hits(text: str, bans: tuple[str, ...]) -> list[str]:
    """Every banned phrasing present in `text`. A LIST, not a bool, so a failure
    names which lie it caught rather than only that one was caught."""
    return [ban for ban in bans if ban in text]


def _missing(text: str, anchors: tuple[str, ...]) -> list[str]:
    return [anchor for anchor in anchors if anchor not in text]


# ─── The obligations are PRESENT ─────────────────────────────────────────────

def test_the_note_says_the_turn_was_cut_by_a_limit_not_completed():
    """Obligation (1). The state achieved is: the answer did NOT finish, and a
    limit is why — both halves, because either alone misreports it."""
    assert not _missing(AGENTIC_CAP_NOTE_AR, CUT_BY_A_LIMIT), (
        "the note no longer says the turn was cut short by a limit — "
        f"missing {_missing(AGENTIC_CAP_NOTE_AR, CUT_BY_A_LIMIT)}")


def test_the_note_is_transient_and_says_what_changes():
    """Obligation (2). Transient, and the thing that changes is named: the limit
    starts over with the next question."""
    assert not _missing(AGENTIC_CAP_NOTE_AR, TRANSIENT), (
        f"the note lost its transience: missing {_missing(AGENTIC_CAP_NOTE_AR, TRANSIENT)}")
    assert not _hits(AGENTIC_CAP_NOTE_AR, TERMINAL_BANS), (
        f"the note now reads as TERMINAL: {_hits(AGENTIC_CAP_NOTE_AR, TERMINAL_BANS)}")


def test_the_note_names_the_valid_next_step():
    """Obligation (3). Ask for THE REMAINDER — the DEC-57 positive-instruction
    argument applied to notes: a note with no sanctioned move gets guessed at."""
    assert not _missing(AGENTIC_CAP_NOTE_AR, NEXT_STEP), (
        f"the next step is no longer named: {_missing(AGENTIC_CAP_NOTE_AR, NEXT_STEP)}")


# ─── The attribution is HONEST — the defect this file exists for ─────────────

def test_the_note_never_attributes_the_ending_to_muthis():
    """THE RULING. The loop ended the turn, not Mut'his. A wording that hands the
    ending back to Mut'his goes RED here — mutation-verified against the text
    that actually shipped (see the positive control below)."""
    assert not _hits(AGENTIC_CAP_NOTE_AR, SELF_ATTRIBUTION_BANS), (
        "the note claims Mut'his chose to stop — the LOOP stopped it: "
        f"{_hits(AGENTIC_CAP_NOTE_AR, SELF_ATTRIBUTION_BANS)}")


def test_the_note_never_blames_the_user():
    """The opposite lie, and the one a rewrite reaches for next: moving the
    ending off Mut'his by putting it on the user."""
    assert not _hits(AGENTIC_CAP_NOTE_AR, USER_BLAME_BANS), (
        f"the note blames the user: {_hits(AGENTIC_CAP_NOTE_AR, USER_BLAME_BANS)}")


# ─── The controls — the scanners are neither blind nor indiscriminate ────────

def test_the_scanner_flags_the_SHIPPED_defect():
    """POSITIVE CONTROL. The exact text Sultan heard must be caught, or every
    green assertion above is a scan over a ban list that matches nothing."""
    assert _hits(THE_SHIPPED_DEFECT, SELF_ATTRIBUTION_BANS) == ["اكتف"]


def test_the_shipped_defect_ALSO_fails_the_state_obligation():
    """POSITIVE CONTROL for the presence half — and the finding itself: the old
    note DID name a next step and still misreported what happened, so the
    obligations are not interchangeable and (1) fails on its own."""
    assert not _missing(THE_SHIPPED_DEFECT, ("اسألني",)), (
        "the old note did name a next step — that is the point of this control")
    assert _missing(THE_SHIPPED_DEFECT, CUT_BY_A_LIMIT) == list(CUT_BY_A_LIMIT)


@pytest.mark.parametrize("regression", [
    "قررت أوقف هنا، اسألني عن الباقي وأكمله لك.",
    "أكتفي بهذا القدر، اسألني عن الباقي وأكمله لك.",
    "كفاية كذا الحين، اسألني عن الباقي وأكمله لك.",
    "ما ودي أكمل أكثر، اسألني عن الباقي وأكمله لك.",
    "اخترت أوقف عند هذا الحد، اسألني عن الباقي وأكمله لك.",
])
def test_the_scanner_flags_plausible_rewordings_that_restore_the_defect(regression):
    """Each of these carries a CORRECT next step and still names the wrong agent
    — which is precisely how the defect returns quietly."""
    assert _hits(regression, SELF_ATTRIBUTION_BANS), (
        f"a self-attributing rewording passed the scan: {regression!r}")


def test_the_scanner_does_NOT_flag_an_honest_alternative_wording():
    """NEGATIVE CONTROL. A ban list that rejects every rewrite is a ban list that
    gets deleted the first time the note is legitimately reworded."""
    honest = "توقف الشرح عند حد الجولة عندي، وهو حد مؤقت. اسألني عن الباقي وأكمله لك."
    assert not _hits(honest, SELF_ATTRIBUTION_BANS + USER_BLAME_BANS + TERMINAL_BANS)


# ─── The guard is scanning the string the USER actually hears ────────────────

def test_the_scanned_constant_is_the_one_spoken_at_the_cap():
    """The instrument's own mechanism check: every assertion above is worthless
    if the cap speaks a different literal. The orchestrator must import THIS
    object and speak it BY NAME — a copied literal would drift in silence."""
    assert orchestrator.AGENTIC_CAP_NOTE_AR is AGENTIC_CAP_NOTE_AR

    source = (SRC / "kernel" / "orchestrator.py").read_text(encoding="utf-8")
    assert "speak_or_feed(AGENTIC_CAP_NOTE_AR)" in source, (
        "the cap no longer speaks the constant this file guards")
    assert "اكتفيت" not in source, "a copy of the old note reappeared in the loop"
