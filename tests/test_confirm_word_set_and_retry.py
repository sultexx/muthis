# tests/test_confirm_word_set_and_retry.py
"""
DEC-136's three rulings, guarded — the accepted SET, the words the request
NAMES, and the second refusal that must not repeat the first.

WHY A NEW FILE RATHER THAN MORE OF `test_confirm_gate.py`. That file guards the
DEC-16 mechanism: the condition, the fingerprint, single-use, expiry, the strip.
None of that changed here. These three rulings are about WHICH WORDS COUNT and
WHAT THE USER IS TOLD, and they were bought by a live failure the mechanism
guards could not have seen — three turns of a byte-identical refusal after the
user had spoken (DEC-135). Keeping them together is what makes the reason
readable when someone later proposes widening the set again.

EVERYTHING HERE IS DRIVEN, NOT INSPECTED. The retry surface is reached by
running a real `ConfirmGate` through the real two-turn cycle — refuse, observe an
utterance, refuse again — because the defect being guarded is a SEQUENCE, and a
test that read the two constants side by side would pass even if nothing ever
selected the second one.
"""

from __future__ import annotations

import re

from muthis.kernel.verbosity import normalize_ar
from muthis.trust.confirm_gate import (
    APPROVAL_WORDS_AR, APPROVE, ConfirmGate, _APPROVALS, confirm_note,
    detect_confirmation,
)

TOOL = "web__search"
ARGS = {"query": "أسعار الذهب"}

# The note quotes each word it offers, and the tool name, in «guillemets». The
# assertions below only ever ask whether the ACCEPTED forms are among them, so
# the tool name riding along is harmless.
QUOTED = re.compile(r"«([^»]+)»")

# REFUSED at DEC-136 ruling 1, WITH THE REASON, because a bare list invites a
# future reader to "just add one more". THE BOUND: whole-utterance matching
# already excludes a word occurring inside a sentence, so the only question is
# whether the BARE form is a plausible COMPLETE utterance in a turn that is not
# an approval.
REFUSED_WITH_REASON = {
    "تم": "means «understood» — the ordinary acknowledgement of any statement, "
          "so a user who says it after hearing the request has acknowledged it "
          "rather than authorized it",
    "أوكيه": "the same acknowledgement, borrowed — it carries no authorizing "
             "intent and occurs constantly in unrelated speech",
}


def _refuse(gate: ConfirmGate) -> str:
    """One high-impact call under taint — the gate's whole external surface."""
    note = gate.refusal_for(TOOL, ARGS, high_impact=True, tainted=True)
    assert note is not None, "the gate stopped refusing — the fixture is void"
    return note


def _quoted_approvals(note: str) -> set[str]:
    return {normalize_ar(word) for word in QUOTED.findall(note)}


# ─── RULING 1 — the accepted set, pinned in both directions ──────────────────

def test_the_accepted_set_is_EXACTLY_these_four_words():
    """The pin. A word added here without a ruling fails LOUDLY, which is the
    whole reason the set is written down rather than derived."""
    assert APPROVAL_WORDS_AR == ("أوافق", "موافق", "وافق", "اعتمد")


def test_every_word_in_the_tuple_actually_APPROVES():
    """Offered ⇒ accepted. Driven through the detector, one word at a time, so a
    tuple entry that never matches (a typo, a stray space) cannot hide behind
    the set-identity assertion below."""
    for word in APPROVAL_WORDS_AR:
        assert detect_confirmation(word) == APPROVE, word


def test_اعتمد_approves_in_BOTH_spellings():
    """DEC-136 ruling 1's word, and the normalisation that makes listing it once
    enough: `normalize_ar` folds أ → ا, so the first-person «أعتمد» reaches the
    same form. Pinned because the ruling would be half-delivered otherwise."""
    for spelling in ("اعتمد", "أعتمد", "اعتمد.", "  اعتمد  "):
        assert detect_confirmation(spelling) == APPROVE, spelling


def test_the_words_REFUSED_at_DEC_136_stay_refused_and_the_reason_travels():
    """«تم» and «أوكيه» are ACKNOWLEDGEMENTS, not authorizations. This is the
    assertion a future widening has to argue with, so it carries the argument."""
    for word, reason in REFUSED_WITH_REASON.items():
        assert normalize_ar(word) not in _APPROVALS, f"{word} entered the set — {reason}"
        assert detect_confirmation(word) is None, f"{word} now authorises — {reason}"


def test_a_refused_word_does_not_sneak_in_through_normalisation():
    """The negative control for the test above: it must fail because the word is
    ABSENT, not because the exact spelling happened to miss."""
    for word in ("تم.", "تمّ", "أوكيه!", "اوكيه"):
        assert detect_confirmation(word) is None, word


# ─── RULING 2 — the request names every word the detector accepts ────────────

def test_the_tuple_the_request_RENDERS_FROM_is_the_set_the_detector_MATCHES():
    """THE PROPERTY, not a substring: one source, two consumers. If a word ever
    reaches `_APPROVALS` by a route that does not pass through the tuple the
    note renders, the gate can accept a word it never offered — the DEC-135
    defect, exactly."""
    assert {normalize_ar(word) for word in APPROVAL_WORDS_AR} == _APPROVALS


def test_the_REQUEST_names_every_word_the_detector_accepts():
    """Driven through the real gate, so it fails whether the shortfall is in the
    note's rendering or in what the gate hands it."""
    note = _refuse(ConfirmGate())
    missing = _APPROVALS - _quoted_approvals(note)
    assert not missing, (
        f"the request offers {len(_APPROVALS) - len(missing)} of {len(_APPROVALS)} "
        "accepted words — a user refused for saying a word the gate accepts is "
        "the defect DEC-136 ruling 2 closed")


def test_the_RETRY_request_names_them_too():
    """The second note is where naming them matters MOST — it is the one sent to
    a user who has already failed once."""
    gate = ConfirmGate()
    gate.new_turn()
    _refuse(gate)
    gate.new_turn()
    gate.observe("وش رايك في الجو اليوم")
    assert not (_APPROVALS - _quoted_approvals(_refuse(gate)))


# ─── RULING 3 — a failed attempt is not silence ──────────────────────────────

def test_the_SECOND_refusal_after_a_heard_non_approval_DIFFERS_from_the_first():
    """THE DEFECT THE LOG PROVED. Three live turns returned byte-identical text
    after the user had spoken, so nothing separated «that was not one of the
    words» from «I did not hear you» — and he cannot converge on a word he is
    never told he missed."""
    gate = ConfirmGate()
    gate.new_turn()
    first = _refuse(gate)
    gate.new_turn()
    gate.observe("ابحث لي عن أسعار الذهب")     # heard; neither answer
    second = _refuse(gate)
    assert second != first, (
        "the byte-identical directive came back after a failed attempt — this is "
        "the exact live loop DEC-135 measured across three turns")


def test_the_retry_note_STILL_names_the_tool_and_its_arguments():
    """DEC-16's bound (a) survives the shorter follow-up. The failed observation
    CLEARED the pending, so this refusal is binding a FRESH fingerprint over
    whatever the model is asking for NOW — an approval must never travel to a
    call the user never heard."""
    gate = ConfirmGate()
    gate.new_turn()
    _refuse(gate)
    gate.new_turn()
    gate.observe("لا أدري")
    second = _refuse(gate)
    assert TOOL in second, "the retry stopped naming the tool"
    assert "أسعار الذهب" in second, "the retry stopped naming the arguments"


def test_SILENCE_is_not_reported_as_a_failed_attempt():
    """THE FIRST NEGATIVE CONTROL, and it is what makes ruling 3 a distinction
    rather than a rewording. A turn that delivers no transcript neither approves
    nor fails — claiming otherwise would invent an utterance."""
    gate = ConfirmGate()
    gate.new_turn()
    first = _refuse(gate)
    gate.new_turn()                    # armed, but observe() never runs
    assert _refuse(gate) == first, (
        "a silent turn produced the retry note — the gate is claiming the user "
        "said something he never said")


def test_an_EXPLICIT_refusal_is_never_answered_with_you_were_not_understood():
    """THE SECOND NEGATIVE CONTROL. «لا» is a deliberate answer. Telling the user
    who declined that his words «did not match any approval word» is a false
    claim about his intent, and it is the one thing this surface must not do."""
    gate = ConfirmGate()
    gate.new_turn()
    first = _refuse(gate)
    gate.new_turn()
    gate.observe("لا")
    assert _refuse(gate) == first, "a deliberate refusal was answered as a miss"


def test_an_APPROVAL_clears_the_missed_state():
    """After the accept branch runs, a later refusal must open cleanly rather
    than accusing the user of a miss he already corrected."""
    gate = ConfirmGate()
    gate.new_turn()
    first = _refuse(gate)
    gate.new_turn()
    gate.observe("ياخي لا")                     # a miss: neither answer
    _refuse(gate)                               # rebinds, retry note
    gate.new_turn()
    gate.observe(APPROVAL_WORDS_AR[0])          # the user gets it right
    assert gate.refusal_for(TOOL, ARGS, high_impact=True, tainted=True) is None
    gate.new_turn()
    assert _refuse(gate) == first, "the miss outlived the approval that fixed it"


def test_the_two_notes_are_selected_by_the_flag_and_not_by_the_arguments():
    """`confirm_note` is the ONE chooser; the same call renders two texts purely
    on `missed`. Guards against a future edit that makes the retry depend on
    something incidental (an empty-args branch, a tool name)."""
    assert (confirm_note(TOOL, ARGS, APPROVAL_WORDS_AR, missed=True)
            != confirm_note(TOOL, ARGS, APPROVAL_WORDS_AR, missed=False))
