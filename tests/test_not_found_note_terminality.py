# tests/test_not_found_note_terminality.py
"""`FILE_NOT_FOUND_AR` against DEC-58 ruling 3's three obligations.

THE DEFECT THIS GUARDS WAS NOT A MISSING OBLIGATION BUT AN INVERTED ONE. The old
note ended «واطلب القراءة من جديد» — *ask for the read again* — and its named
next step, «تأكد من المسار الكامل», addresses someone who can inspect a
filesystem, which the model cannot. So the only half the model could act on WAS
the retry. Measured live 2026-08-30: three identical not-found reads in one turn,
passes 1-3, pass 4 empty. `read_local_file` has no per-turn budget, so only the
agentic cap stopped it — the note is the whole brake.

THE GUARD IS A PREDICATE, NOT A STRING MATCH, AND THAT IS THE POINT. Asserting
the shipped sentence verbatim would pass for any wording at all and would pin the
prose instead of the property. So the obligations are expressed as a check, and
the check is then driven against THREE inputs:

  * the SHIPPED note                  -> must PASS
  * the HISTORICAL note that failed   -> must FAIL  (it would have caught the real defect)
  * an honest REWORDING               -> must PASS  (the negative control: the check
                                         tests the property, not this phrasing)

Without the second, the guard proves nothing about the defect it was written for.
Without the third, any rewrite of a correct note reddens the suite and the guard
becomes something to route around.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from muthis.file_reader import FileReader
from muthis.file_reader_notes import FILE_NOT_FOUND_AR

# The note as it stood before DEC-124 — the real defect, kept as the control.
HISTORICAL_NOTE = "ما لقيت الملف «{path}». تأكد من المسار الكامل واطلب القراءة من جديد."

# An honest rewording: different words, all three obligations intact.
HONEST_REWORDING = (
    "ما لقيت الملف «{path}» ولا قرأت منه شي. نفس المسار بيعطي نفس النتيجة "
    "دايماً فما ينفع تكراره. اسأل المستخدم وين يقع الملف بالضبط."
)

# An IMPERATIVE invitation to retry. Every one of these tells the model to do
# again the thing that just failed. The note may MENTION retrying in order to
# forbid it — «أي محاولة ثانية بنفس المسار ترجع نفس النتيجة» is the terminality
# clause, not an invitation — so the ban targets the imperative forms only.
RETRY_INVITATIONS = (
    "اطلب القراءة من جديد",
    "اطلب القراءة مرة ثانية",
    "جرّب مرة ثانية",
    "جرب مرة ثانية",
    "حاول مرة ثانية",
    "أعد المحاولة",
    "عاود المحاولة",
    "أعد القراءة",
)

# Next steps addressed to someone with a filesystem in front of them. The model
# has no shell, no browser and no directory listing; naming these leaves it with
# a step it cannot take, which is how the old note left the retry as the only
# available move.
#
# MATCHED AT A CLAUSE BOUNDARY, NOT AS A BARE SUBSTRING, and the distinction is
# load-bearing rather than fussy: the IMPERATIVE «تأكد من المسار» commands a
# check the model cannot run, while «لأتأكد من المسار بنفسي» is the note
# explaining, in the first person, why it CANNOT — the exact opposite, and it
# contains the other as a substring. A coarse ban rejects the honest reason
# clause and pushes the note toward saying less.
OPERATOR_ONLY_STEPS = (
    "تأكد من المسار",
    "تحقق من المسار",
    "تأكد من الصلاحيات",
)


def _commands(note: str, phrase: str) -> bool:
    """True when `phrase` appears as an IMPERATIVE — at a clause boundary rather
    than suffixed onto a longer word."""
    return bool(re.search(r"(?:^|[\s.،:؛«(])" + re.escape(phrase), note))


def _obligations(note: str) -> dict[str, bool]:
    """DEC-58's three, as checkable properties of one model-facing sentence."""
    return {
        # (1) THE STATE ACHIEVED — said, not implied.
        "state": ("ما قرأت شي" in note or "ولا قرأت" in note
                  or "ما فتحت شي" in note),
        # (2) TERMINAL, with the reason it cannot be retried away, and NO
        #     imperative invitation to do it again.
        "terminal": (("نفس النتيجة" in note or "نفس الجواب" in note)
                     and not any(bad in note for bad in RETRY_INVITATIONS)),
        # (3) A NEXT STEP THE MODEL CAN TAKE — and not one only an operator can.
        "next_step": ("اسأل المستخدم" in note
                      and not any(_commands(note, bad) for bad in OPERATOR_ONLY_STEPS)),
    }


# ───────────────────────── the three obligations hold ───────────────────────

@pytest.mark.parametrize("obligation", ["state", "terminal", "next_step"])
def test_the_shipped_note_satisfies_every_obligation(obligation):
    assert _obligations(FILE_NOT_FOUND_AR)[obligation], (
        f"FILE_NOT_FOUND_AR fails DEC-58 obligation '{obligation}'")


def test_no_retry_invitation_survives_anywhere_in_the_note():
    """The inversion itself. A mutation restoring ANY imperative retry — the
    shape that produced three identical failing reads in one turn — lands here."""
    for invitation in RETRY_INVITATIONS:
        assert invitation not in FILE_NOT_FOUND_AR, (
            f"the note invites a retry again: {invitation!r}")


def test_the_next_step_is_addressed_to_the_MODEL_not_an_operator():
    """«تأكد من المسار الكامل» is an instruction to inspect a filesystem. The
    model has no way to carry it out, so naming it leaves the retry as the only
    move it can actually make — which is exactly what it then made, three times."""
    assert "اسأل المستخدم" in FILE_NOT_FOUND_AR
    for step in OPERATOR_ONLY_STEPS:
        assert not _commands(FILE_NOT_FOUND_AR, step), (
            f"the note names a step only a filesystem operator can take: {step!r}")


def test_the_note_says_WHY_the_model_cannot_settle_it_alone():
    """DEC-58 wants the reason it cannot be retried away. Without it, "ask the
    user" reads as optional politeness beside a check the model might still try."""
    assert "ما أقدر" in FILE_NOT_FOUND_AR


# ───────── the controls: the check must catch the real defect, and only it ────

def test_the_check_would_have_CAUGHT_the_historical_note():
    """Without this the guard proves nothing: a predicate that passes everything
    passes the shipped note too."""
    verdict = _obligations(HISTORICAL_NOTE)
    assert not verdict["terminal"], "the check does not catch the inverted terminality"
    assert not verdict["next_step"], "the check does not catch the operator-only step"
    assert not verdict["state"], "the check does not catch the missing state"


def test_an_honest_REWORDING_is_not_flagged():
    """The negative control. A guard that only accepts today's exact sentence
    reddens on any correct rewrite and becomes something to route around."""
    assert all(_obligations(HONEST_REWORDING).values()), (
        "an honest rewording carrying all three obligations was rejected")


# ─────────────────── the mechanism: production returns THIS ─────────────────

def test_a_real_missing_path_returns_the_obliged_note(tmp_path):
    """The note must reach the model from the REAL reader, not merely exist as a
    constant — a fixed string nothing returns is not a brake on anything."""
    out = asyncio.run(FileReader().read({"path": str(tmp_path / "ghost.py")}))
    assert all(_obligations(out).values()), f"the served note fails an obligation: {out!r}"
    assert "ghost.py" in out, "the model cannot name the path back to the user"


def test_the_empty_path_case_is_served_the_same_obligations():
    """`file_reader.py` formats this note with `path=""` for a missing argument,
    so that branch must not degrade into a sentence with no next step."""
    out = asyncio.run(FileReader().read({}))
    assert all(_obligations(out).values())
