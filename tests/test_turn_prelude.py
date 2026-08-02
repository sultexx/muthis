# tests/test_turn_prelude.py
"""
The DEC-73 split-2 extraction: everything kernel-owned that decorates the RAW
transcript, in one object.

WHAT THIS DEFENDS THAT NOTHING ELSE DOES. Before the extraction the two directive
sources were applied inline in `run_turn`, and their ORDER was implicit in the
statement sequence — nothing asserted it. Verbosity detects a voice command in
the RAW transcript, so a note prepended BEFORE it would be inside the text it
scans, and a STANDALONE command like «اختصر» would stop being detected while the
barge-in note is present. That is a FALSE NEGATIVE — the user's command silently
ignored — which is exactly the kind that looks like the user mis-speaking rather
than a broken guard (the T2 BINDING CONSTRAINT's lesson, in a second place).

The extraction is where that order could have been lost, so it is asserted here
against the real `VerbosityController` and the real `INTERRUPTED_NOTE_AR`, not
against fakes: the whole property is about how two real strings compose.

AND THE CHOICE OF COMMAND IS ITSELF LOAD-BEARING — measured, not assumed. The
first version used an ANYWHERE phrase, which matches as a substring wherever it
sits, so the order-inverting mutation SURVIVED it. Only a `_STANDALONE_WORDS`
entry, which must be the whole utterance, can tell the two orders apart.

DEC-65's mode frame is the THIRD source and lands here at T1. It is not built and
is not tested here — but the ordering rule it must satisfy now has a home and a
guard, which is the point of naming a seam before it is needed.
"""

from __future__ import annotations

from muthis.kernel.highlight_gate import INTERRUPTED_NOTE_AR
from muthis.kernel.turn_prelude import TurnPrelude
from muthis.kernel.verbosity import NORMAL, SHORT, VerbosityController


def test_a_plain_utterance_passes_through_unchanged():
    """The common case: no command, no interrupt, nothing prepended."""
    prelude = TurnPrelude()

    assert prelude.begin_turn("وش هذا الزر") == "وش هذا الزر"


def test_the_barge_in_note_is_prepended_only_when_the_last_turn_was_INTERRUPTED():
    prelude = TurnPrelude()

    assert INTERRUPTED_NOTE_AR not in prelude.begin_turn("كمل")
    assert prelude.begin_turn("كمل", interrupted=True).startswith(INTERRUPTED_NOTE_AR)


def test_VERBOSITY_reads_the_RAW_transcript_BEFORE_the_barge_in_note_is_added():
    """THE ORDER, which was implicit in a statement sequence and is now a contract.

    THE DISCRIMINATING CASE IS A STANDALONE WORD, and finding that out cost a
    surviving mutation. The first version of this test used «باختصار», which is an
    ANYWHERE phrase — a substring match that hits wherever it sits — so it
    survives either order and proves nothing: the mutation that swaps the two
    lines PASSED against it.

    «اختصر» is in `_STANDALONE_WORDS` and triggers ONLY when the normalized WHOLE
    utterance is the word. Prepending the note first therefore destroys it, and
    the user's command is silently ignored for exactly the turns that follow an
    interruption — a false negative that reads as the user mis-speaking."""
    prelude = TurnPrelude()

    out = prelude.begin_turn("اختصر", interrupted=True)

    assert INTERRUPTED_NOTE_AR in out
    assert prelude.verbosity.level == SHORT, (
        "the barge-in note was prepended BEFORE verbosity scanned the transcript")


def test_the_same_STANDALONE_command_is_detected_WITHOUT_an_interruption_too():
    """The positive control. Without it, a prelude that detected NOTHING in
    either case would still satisfy the ordering test above by failing both."""
    prelude = TurnPrelude()

    prelude.begin_turn("اختصر")

    assert prelude.verbosity.level == SHORT


def test_an_ANYWHERE_phrase_is_order_INDEPENDENT_which_is_why_it_cannot_guard_this():
    """Recorded so the choice above is not undone by someone 'simplifying' it.

    An anywhere phrase survives the note either way. That is correct behaviour —
    and it is precisely what makes it useless as evidence about ordering."""
    prelude = TurnPrelude()

    prelude.begin_turn("باختصار وش هذا", interrupted=True)

    assert prelude.verbosity.level == SHORT


def test_the_controller_is_HELD_ACROSS_turns_because_SHORT_is_sticky():
    """v5 B3: the prelude's lifetime is the orchestrator's, not the turn's. A
    rebuilt-per-turn prelude would reset SHORT/DETAILED every utterance."""
    prelude = TurnPrelude()

    prelude.begin_turn("باختصار وش هذا")
    level = prelude.verbosity.level
    prelude.end_turn()
    prelude.begin_turn("وش هذا")

    assert prelude.verbosity.level == level, "a sticky level did not survive"


def test_an_INJECTED_controller_is_used_rather_than_a_fresh_one():
    """The seam the Orchestrator's `verbosity=` parameter rides on. If the
    prelude ignored it and built its own, a test or a composition that injected
    a configured controller would be silently overridden."""
    injected = VerbosityController()

    prelude = TurnPrelude(verbosity=injected)

    assert prelude.verbosity is injected


def test_end_turn_decays_the_ONE_SHOT_level_but_not_the_sticky_one():
    """B4: EXACT is one-shot per WHOLE utterance; SHORT is not. Decaying either
    one earlier would strip it before the tool_choice="none" explain pass."""
    prelude = TurnPrelude()

    prelude.begin_turn("جاوبني بخمس كلمات")
    exact = prelude.verbosity.level
    prelude.end_turn()

    assert exact != prelude.verbosity.level, "the one-shot level never decayed"
