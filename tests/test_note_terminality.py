# tests/test_note_terminality.py
"""DEC-58 ruling 3's three obligations, as ONE check over EVERY note ruled to carry them.

THE DEFECT THIS FAMILY PRODUCES IS AN INVERSION, NOT AN OMISSION. Both notes
guarded here used to END by inviting the operation that had just failed —
«واطلب القراءة من جديد», «جرّب مرة ثانية» — while naming a next step only
someone sitting at the machine can take («تأكد من المسار الكامل», «تأكد من
الصلاحيات»). So the single move left to the model WAS the retry, and it retried:
measured live 2026-08-30, three identical not-found reads in one turn, passes
1-3, pass 4 empty. `read_local_file` has no per-turn budget, so only the agentic
cap stopped it — the note is the whole brake.

ONE CHECK, NOT TWO, AND THE REGISTRY IS THE POINT. A second copy of this
predicate would drift from the first, and the third note would get neither. Here
a note is audited BY CONSTRUCTION the moment it joins `GOVERNED` — which is also
the honest limit of the property: it is scoped to that tuple, not to the module.
The notes deliberately OUTSIDE it are listed in `EXEMPT` with the reason, so the
scope is a recorded decision rather than whatever happened to be added.

EVERY OBLIGATION IS A SET OF ACCEPTED PHRASINGS, AND THE TWO CONTROLS ARE WHAT
KEEP THAT HONEST. Widening a check to fit a second note could widen it into
uselessness, so each HISTORICAL note must still FAIL (the predicate really does
catch the defect it was written for) and each honest REWORDING must still PASS
(it tests the property, not one sentence). Without the first the guard proves
nothing; without the second any correct rewrite reddens the suite and the guard
becomes something to route around.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from muthis.file_reader import FileReader
from muthis.file_reader_notes import FILE_NOT_FOUND_AR, FILE_READ_ERROR_AR

# ─────────────────────────── the accepted phrasings ─────────────────────────

# ① what was achieved — stated, never left to inference.
STATE = ("ما قرأت شي", "ما فتحت شي", "ولا قرأت", "ما رجع لي منه شي", "ما وصلني")
# ② terminal, with the reason it cannot be retried away.
TERMINAL = ("نفس النتيجة", "نفس الجواب", "ما تغيّر النتيجة", "ما تتغيّر النتيجة")
# ③ a next step the MODEL can take — it can talk to the user, and that is all.
NEXT_STEP = ("اسأل المستخدم", "خبّر المستخدم")
# and the reason the model cannot settle it alone, or "ask the user" reads as
# optional politeness beside a check it might still try.
WHY = ("ما أقدر",)

# An IMPERATIVE invitation to redo what just failed. A note may MENTION repeating
# in order to FORBID it — «أي محاولة ثانية بنفس المسار ترجع نفس النتيجة» is the
# terminality clause — so only imperative forms are banned.
RETRY_INVITATIONS = (
    "اطلب القراءة من جديد", "اطلب القراءة مرة ثانية", "جرّب مرة ثانية",
    "جرب مرة ثانية", "حاول مرة ثانية", "أعد المحاولة", "عاود المحاولة",
    "أعد القراءة",
)

# Steps addressed to someone with a filesystem in front of them. The model has no
# shell, no browser and no directory listing.
#
# MATCHED AT A CLAUSE BOUNDARY, NOT AS A BARE SUBSTRING, and the distinction is
# load-bearing rather than fussy: the IMPERATIVE «تأكد من المسار» commands a check
# the model cannot run, while «لأتأكد من المسار بنفسي» is the note explaining, in
# the first person, why it CANNOT — the exact opposite, and it contains the other
# as a substring. The first version of this guard rejected the honest reason
# clause. A coarse ban pushes a note toward saying LESS, which is the direction
# this whole family of defects already travels.
OPERATOR_ONLY_STEPS = ("تأكد من المسار", "تحقق من المسار",
                       "تأكد من الصلاحيات", "تحقق من الصلاحيات")


def _commands(note: str, phrase: str) -> bool:
    """True when `phrase` appears as an IMPERATIVE — at a clause boundary rather
    than suffixed onto a longer word."""
    return bool(re.search(r"(?:^|[\s.،:؛«(])" + re.escape(phrase), note))


def obligations(note: str) -> dict[str, bool]:
    """DEC-58's three, as checkable properties of one model-facing sentence."""
    return {
        "state": any(p in note for p in STATE),
        "terminal": (any(p in note for p in TERMINAL)
                     and not any(bad in note for bad in RETRY_INVITATIONS)),
        "next_step": (any(p in note for p in NEXT_STEP)
                      and not any(_commands(note, bad) for bad in OPERATOR_ONLY_STEPS)),
        "why": any(p in note for p in WHY),
    }


# ─────────────────────────────── the registry ───────────────────────────────

# The notes RULED to carry all three, each with the text it replaced. The
# historical column is not decoration: it is the control that proves the check
# catches the real defect.
GOVERNED = (
    ("FILE_NOT_FOUND_AR", FILE_NOT_FOUND_AR,
     "ما لقيت الملف «{path}». تأكد من المسار الكامل واطلب القراءة من جديد."),
    ("FILE_READ_ERROR_AR", FILE_READ_ERROR_AR,
     "صار خطأ أثناء قراءة الملف، جرّب مرة ثانية أو تأكد من الصلاحيات."),
)

# Deliberately OUTSIDE the registry, recorded so the scope is a decision:
#   FILE_NAME_NOT_BARE_AR, TRUNCATION_NOTE_AR — a retry there is a genuinely
#     DIFFERENT operation (a bare name; a line range), so inviting it is correct.
#   FILE_BLOCKED_AR, FILE_NOT_TEXT_AR, FILE_READ_UNAVAILABLE_AR — they lack
#     obligation ③ but none INVITES the failed operation; reported in DEC-124 and
#     not yet ruled.
#   FILE_IS_DOCUMENT_AR, FILE_ALREADY_READ_AR, FILE_TOO_LARGE_AR — already carry
#     all three in their own wording, which this predicate's phrase sets do not
#     happen to spell; adding them would mean widening the sets to fit rather
#     than because the property changed.
EXEMPT = 8

# Honest rewordings: different words, all obligations intact. The negative control.
REWORDINGS = (
    "ما لقيت الملف «{path}» ولا قرأت منه شي. نفس المسار يعطي نفس النتيجة "
    "دايماً فما ينفع تكراره. اسأل المستخدم وين يقع الملف، لأني ما أقدر أشوف جهازه.",
    "ما رجع لي منه شي أبداً. إعادة الطلب ما تغيّر النتيجة داخل هذي الجولة. "
    "خبّر المستخدم إن القراءة فشلت، لأني ما أقدر أعرف السبب من عندي.",
)


# ────────────────────── every governed note carries all four ─────────────────

@pytest.mark.parametrize("name,note,_hist", GOVERNED)
@pytest.mark.parametrize("obligation", ["state", "terminal", "next_step", "why"])
def test_every_governed_note_satisfies_every_obligation(obligation, name, note, _hist):
    assert obligations(note)[obligation], f"{name} fails DEC-58 obligation '{obligation}'"


@pytest.mark.parametrize("name,note,_hist", GOVERNED)
def test_no_retry_invitation_survives(name, note, _hist):
    """The inversion itself — the shape that produced three identical failing
    reads in one turn. A mutation restoring ANY imperative retry lands here."""
    for invitation in RETRY_INVITATIONS:
        assert invitation not in note, f"{name} invites a retry again: {invitation!r}"


@pytest.mark.parametrize("name,note,_hist", GOVERNED)
def test_the_next_step_is_addressed_to_the_MODEL_not_an_operator(name, note, _hist):
    """«تأكد من المسار الكامل» and «تأكد من الصلاحيات» instruct a check the model
    cannot run, leaving the retry as the only move it can actually make."""
    assert any(p in note for p in NEXT_STEP), f"{name} names no step the model can take"
    for step in OPERATOR_ONLY_STEPS:
        assert not _commands(note, step), (
            f"{name} names a step only a filesystem operator can take: {step!r}")


def test_the_catch_all_note_invents_no_CAUSE():
    """`FILE_READ_ERROR_AR` is the `except Exception` arm, so the cause is by
    definition unknown. The old text asserted one — «تأكد من الصلاحيات» — which
    sends the model, and through it the user, at the wrong thing. A note that
    names a mechanism it does not have is the quietest defect in this project."""
    for invented in ("الصلاحيات", "permissions", "مقفل", "محذوف"):
        assert invented not in FILE_READ_ERROR_AR, (
            f"the catch-all note asserts a cause it cannot know: {invented!r}")


# ───────── the controls: catches the real defect, and only the defect ────────

@pytest.mark.parametrize("name,_note,historical", GOVERNED)
def test_the_check_would_have_CAUGHT_each_historical_note(name, _note, historical):
    """Widening the phrase sets to fit a second note could widen them into
    uselessness. Each historical text must still fail, or the registry grew at
    the cost of the property."""
    verdict = obligations(historical)
    assert not verdict["terminal"], f"{name}: inverted terminality no longer caught"
    assert not verdict["next_step"], f"{name}: operator-only step no longer caught"
    assert not verdict["state"], f"{name}: missing state no longer caught"


@pytest.mark.parametrize("rewording", REWORDINGS)
def test_an_honest_REWORDING_is_not_flagged(rewording):
    """A guard that only accepts today's exact sentences reddens on any correct
    rewrite and becomes something to route around."""
    assert all(obligations(rewording).values()), (
        f"an honest rewording carrying every obligation was rejected: {rewording!r}")


def test_the_registry_and_the_exemptions_account_for_every_note():
    """The scope is a recorded decision, not whatever happened to be added. If a
    note is introduced or moved between the two lists, this count moves with it."""
    from muthis import file_reader_notes as notes
    governed_names = {name for name, _, _ in GOVERNED}
    all_notes = {n for n in notes.__all__ if n.endswith("_AR")}
    assert governed_names <= all_notes
    assert len(all_notes) - len(governed_names) == EXEMPT, (
        "a note was added or removed without deciding whether DEC-58 governs it")


# ─────────────────── the mechanism: production returns THESE ────────────────

def test_a_real_missing_path_returns_the_obliged_note(tmp_path):
    out = asyncio.run(FileReader().read({"path": str(tmp_path / "ghost.py")}))
    assert all(obligations(out).values()), f"the served note fails an obligation: {out!r}"
    assert "ghost.py" in out, "the model cannot name the path back to the user"


def test_the_empty_path_case_is_served_the_same_obligations():
    """`file_reader.py` formats the not-found note with `path=""` for a missing
    argument, so that branch must not degrade into a sentence with no next step."""
    assert all(obligations(asyncio.run(FileReader().read({}))).values())


def test_the_catch_all_arm_is_reachable_and_returns_the_obliged_note():
    """A non-dict `args` makes `_read_blocking` raise, which is the `except
    Exception` wall — the arm `FILE_READ_ERROR_AR` actually serves. A constant
    nothing returns is not a brake on anything."""
    out = asyncio.run(FileReader().read("not-a-dict"))
    assert out == FILE_READ_ERROR_AR
    assert all(obligations(out).values())
