# tests/test_missed_lifetime.py
"""
DEC-147 ③ — A MISS CANNOT OUTLIVE ITS TURN.

DEC-145 ⑨ CONFIRMED the defect on the real gate. After a missed approval, `missed`
stayed set across turns, because `observe()` returned before touching it whenever
nothing was pending. So the NEXT refusal — any call, any number of turns later — came
back in the RETRY form, telling the model the user's LAST words matched no approval
word although nobody had asked the user anything. The note's own precondition
(`confirm_gate_notes.py`) is a miss heard WHILE A PENDING EXISTED; a look that finds
nothing pending now clears the flag.

It could never release a call — `missed` selects a NOTE and nothing else (DEC-136) —
but it was a false statement, reachable right after Session 1's pattern. The designed
case, a miss followed by a refusal in the SAME turn, is what the retry note exists for
and is guarded here too, so a fix that silenced the note would go RED as well.

Run:  set PYTHONPATH=src && python -m pytest tests/test_missed_lifetime.py -q
"""

from __future__ import annotations

from muthis.kernel.tool_router import namespaced_name
from muthis.trust.confirm_gate import CONFIRM_RETRY_AR, ConfirmGate

SEARCH = namespaced_name("web", "search")
RETRY_CLAIM = "لم يطابق أي كلمة من كلمات الإذن"   # the retry note's own claim
NOT_A_WORD = "أوافق ابحث عنها الحين"              # heard, and not a bare accepted word
UNRELATED = ("وش هذا الملف؟", "اشرح لي الكود", "طيب شكراً")


def _refuse(gate, query="q"):
    return gate.refusal_for(SEARCH, {"query": query}, high_impact=True, tainted=True)


def _turn(gate, said):
    gate.new_turn()
    gate.observe(said)


def test_the_claim_this_file_looks_for_IS_the_retry_notes():
    """The positive control: without it, every "not in" below would pass on a
    rewording of the note while examining nothing."""
    assert RETRY_CLAIM in CONFIRM_RETRY_AR


def test_a_miss_does_NOT_reach_an_unrelated_refusal_turns_later():
    """DEC-145 ⑨'s reproduction, now the guard: a miss in turn 2, three unrelated
    turns with nothing pending, a NEW refusal in turn 5 — the first-refusal form."""
    gate = ConfirmGate()
    _refuse(gate)
    gate.take_spoken_request()
    _turn(gate, NOT_A_WORD)                  # turn 2: heard, not an answer, pending cleared
    for said in UNRELATED:                   # turns 3-5: nothing pending, nothing asked
        _turn(gate, said)
    assert RETRY_CLAIM not in _refuse(gate, "شي جديد"), (
        "a miss three turns back selected the retry note for a call nobody asked about")


def test_the_explicit_refusal_control_never_selects_the_retry_note():
    """DEC-145 ⑨'s «لا» control — the negative test, green before the fix and after."""
    gate = ConfirmGate()
    _refuse(gate)
    gate.take_spoken_request()
    _turn(gate, "لا")
    for said in UNRELATED:
        _turn(gate, said)
    assert RETRY_CLAIM not in _refuse(gate, "شي جديد")


def test_a_miss_STILL_selects_the_retry_note_in_its_own_turn():
    """The designed case survives: a miss, then the model re-issuing in the SAME turn,
    is exactly what the retry note exists for (DEC-136 ruling 3)."""
    gate = ConfirmGate()
    _refuse(gate)
    gate.take_spoken_request()
    _turn(gate, NOT_A_WORD)
    assert RETRY_CLAIM in _refuse(gate), "the retry note no longer follows a real miss"


def test_every_look_that_finds_a_pending_still_decides_the_flag():
    """A pending re-placed in the missed turn is looked at in the next one, and a
    second miss is a miss again — the fix clears the flag only when nothing waits."""
    gate = ConfirmGate()
    _refuse(gate)
    _turn(gate, NOT_A_WORD)                  # a miss: the pending is cleared
    _refuse(gate)                            # re-issued in the same turn: retry, pending placed
    _turn(gate, NOT_A_WORD)                  # a pending exists, so the look decides: missed
    assert RETRY_CLAIM in _refuse(gate)
