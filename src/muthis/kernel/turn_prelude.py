# src/muthis/kernel/turn_prelude.py
"""
`TurnPrelude` — everything kernel-owned that decorates the RAW transcript before
a turn runs. Extracted from `orchestrator.py` (DEC-73, split 2).

ONE RESPONSIBILITY, SEVERAL SOURCES. Before this module the orchestrator applied
each directive source inline, and they had accumulated one at a time across three
milestones — verbosity in v5, the barge-in note in v7 Phase 3 — with no shared
name, so each new one looked like a small local addition rather than the fourth
member of a family. They are one job: TAKE THE USER'S WORDS AND HAND BACK WHAT
THE PROVIDER SHOULD SEE.

WHY THE ORCHESTRATOR HAD TO GIVE THIS UP, and the reason is not this feature.
`orchestrator.py` sat at 299/300 for three milestones, byte-identical through two
of them BY DESIGN. The P0 D-2 measurement found that the minimum cost of ANY new
injected seam there is three lines — one import, one constructor parameter, one
pass-through — against ONE line of headroom. So the file could not absorb the
next arrival whatever it was; `SessionMode` was merely next in the queue. This
seam is the room, and it is opened once, for a real responsibility, rather than
shaved to fit.

THE MODE FRAME IS THE THIRD SOURCE, AND ITS HOME IS NAMED HERE (DEC-65/DEC-66).
It is NOT built — T1 builds it — but this is where it lands, beside the two that
already exist, and `begin_turn` is the ONE call site it will join. Stub-first, the
AGENTS.md law: the fields are not built now, the shape that can receive them is.

ORDER IS PART OF THE CONTRACT. Verbosity detects a voice command in the RAW
transcript, so anything prepended BEFORE it would be inside the text it scans.
The barge-in note is prepended AFTER, where it cannot disturb that scan. A third
source must state where it sits and why, not simply be appended to the end.

Pure stdlib plus two sibling imports; importable in isolation. Holds no lifecycle,
no lock and no loop (Law 11) — it is state the ORCHESTRATOR owns across turns,
kept in one object so there is one lifetime rather than three.
"""

from __future__ import annotations

from typing import Optional

from .highlight_gate import INTERRUPTED_NOTE_AR
from .verbosity import VerbosityController


class TurnPrelude:
    """The turn's directive assembly. Built once by the Orchestrator, held ACROSS
    turns because verbosity's SHORT/DETAILED is sticky."""

    def __init__(self, *, verbosity: Optional[VerbosityController] = None) -> None:
        # Verbosity state lives ACROSS turns (sticky SHORT/DETAILED) — a real
        # default like the other seams, so main.py needs no wiring (v5 B3).
        self._verbosity = verbosity or VerbosityController()

    @property
    def verbosity(self) -> VerbosityController:
        """The controller itself, for callers that need the state rather than the
        assembly — kept read-only so the ONE mutation path stays `begin_turn`."""
        return self._verbosity

    def begin_turn(self, user_text: str, *, interrupted: bool = False) -> str:
        """The RAW transcript in, the provider's user text out.

        The caller clears its own interrupted flag; this method never writes to
        the orchestrator's state, which is what keeps the barge-in flag's single
        owner obvious after the extraction."""
        # Verbosity (option A): detect a voice command in the RAW transcript,
        # then attach the internal directive ONCE per utterance — never on the
        # agentic loop's continuations or the refresh follow-up.
        user_text = self._verbosity.begin_turn(user_text)
        if interrupted:  # barge-in context (v7 Phase 3)
            user_text = f"{INTERRUPTED_NOTE_AR}\n{user_text}"
        return user_text

    def end_turn(self) -> None:
        """Decay whatever is one-shot, at the end of the WHOLE utterance."""
        # Verbosity decay (B4): EXACT is one-shot per WHOLE utterance — decaying
        # any earlier would strip it before the tool_choice="none" explain pass.
        self._verbosity.end_turn()


__all__ = ["TurnPrelude"]
