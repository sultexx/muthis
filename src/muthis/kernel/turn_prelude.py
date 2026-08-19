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

THE MODE FRAME IS THE THIRD SOURCE, AND IT IS NOW LIVE (DEC-65/DEC-66). T1 gave
the injected `SessionMode` a home here; **T2 made it a directive** — one internal
line per turn carrying the kernel's frame, under the BINDING CONSTRAINT of
2026-07-31: it MUST carry `DIRECTIVE_MARKER_AR`, or the mode's step text flows
into the DEC-16 approval detector's input and a genuine «أوافق» stops matching.

`begin_turn` IS ALSO WHERE TWO OF THE THREE EXITS ARE EVALUATED, and that is not
a convenience — it is the only place in the turn that holds the RAW transcript at
the moment the turn starts. The lazy idle expiry needs the turn's start; the
deterministic exit word needs the raw text. DEC-73 measured design C against
`new_turn_voice()` and `consume()` because THIS MODULE DID NOT YET EXIST; split 2
created a carrier that serves both needs at once, which is why the mode reaches
neither `turn_pass.py` nor `orchestrator.py` at all — both are byte-identical
through T2.

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
from .mode_surfaces import detect_mode_exit, mode_directive_line
from .mode_transition import (
    EXIT_WORD, EXPIRE, ModeAuthority, TransitionRequest, is_idle_expired,
)
from .session_mode import SessionMode
from .verbosity import VerbosityController


class TurnPrelude:
    """The turn's directive assembly. Built once by the Orchestrator, held ACROSS
    turns because verbosity's SHORT/DETAILED is sticky."""

    def __init__(self, *, verbosity: Optional[VerbosityController] = None,
                 session_mode: Optional[SessionMode] = None) -> None:
        # Verbosity state lives ACROSS turns (sticky SHORT/DETAILED) — a real
        # default like the other seams, so main.py needs no wiring (v5 B3).
        self._verbosity = verbosity or VerbosityController()
        # DEC-65 (T1): the mode frame's third source. A REAL default, never
        # None, for the reason `SessionTaint` defaults to a real instance and
        # `PassServiced` to an empty record — a consumer must never have to
        # branch on absence, because that branch is where the two worlds drift.
        self._session_mode = session_mode or SessionMode()
        # T2: the authority is built OVER the injected mode rather than beside
        # it, so "the authority and the frame disagree about which mode" is not
        # a state that exists. Its condition seam is the stub (DEC-65 names the
        # conditions; T4/T5 wire the real facts) and it costs the composition
        # root and the orchestrator ZERO lines.
        self._authority = ModeAuthority(mode=self._session_mode)

    @property
    def verbosity(self) -> VerbosityController:
        """The controller itself, for callers that need the state rather than the
        assembly — kept read-only so the ONE mutation path stays `begin_turn`."""
        return self._verbosity

    @property
    def session_mode(self) -> SessionMode:
        """The injected mode, read-only. T3's indicator draws the FRAME from
        here; the ONE mutation path is the authority below."""
        return self._session_mode

    @property
    def authority(self) -> ModeAuthority:
        """The single transition authority, read-only. T4's model-facing verbs
        route their requests through THIS object rather than building a second
        one over the same frame."""
        return self._authority

    def begin_turn(self, user_text: str, *, interrupted: bool = False) -> str:
        """The RAW transcript in, the provider's user text out.

        The caller clears its own interrupted flag; this method never writes to
        the orchestrator's state, which is what keeps the barge-in flag's single
        owner obvious after the extraction.

        ORDER IS A CONTRACT, and it has three clauses now. The idle expiry is
        evaluated FIRST so an expired mode never decorates the turn that
        discovers it. The exit word is read SECOND, from the RAW transcript,
        BEFORE anything is prepended. Verbosity runs THIRD because it too scans
        raw text, and everything prepended below sits outside what those two
        read."""
        # EXIT 3 (DEC-65) — the inactivity timeout, evaluated LAZILY at the
        # start of a turn and NEVER by a background timer: a timer is a
        # lifecycle outside the kernel (Law 11), which DEC-47 already rejected
        # for background ingestion. The mode does not announce its own expiry —
        # Mut'his speaks only after F9, so it is discovered here, silently.
        if is_idle_expired(self._session_mode):
            self._authority.request(TransitionRequest(kind=EXPIRE))
        # DEC-104 ruling 2 — THE LIVENESS STAMP, AND ITS POSITION IS THE WHOLE
        # POINT. It sits AFTER the expiry check above and never before it:
        # expiry asks whether the user was away BEFORE this turn, so a stamp
        # taken first would renew the deadline on the very turn meant to test it
        # and NO mode could ever expire. This turn renews the clock for the NEXT
        # one. Every user turn is activity — a side question, a refused move, a
        # turn that moves no step at all; PROGRESS is the other clock and is
        # stamped only by a committed step change, through the authority. This
        # is a liveness stamp and not a transition (see `record_activity`), so
        # it has no conditions, no bounds and no refusal to route past.
        self._session_mode.record_activity()
        # EXIT 1 — the DETERMINISTIC exit word, on the RAW transcript, with the
        # model uninvolved. A confused or injected model must never be able to
        # trap the user in a mode, so this path consults nothing it says.
        if detect_mode_exit(user_text):
            self._authority.request(TransitionRequest(kind=EXIT_WORD))
        # Verbosity (option A): detect a voice command in the RAW transcript,
        # then attach the internal directive ONCE per utterance — never on the
        # agentic loop's continuations or the refresh follow-up.
        user_text = self._verbosity.begin_turn(user_text)
        if interrupted:  # barge-in context (v7 Phase 3)
            user_text = f"{INTERRUPTED_NOTE_AR}\n{user_text}"
        # DEC-66: the kernel's FRAME as ONE internal-directive line, prepended
        # last so it reads first. It carries DIRECTIVE_MARKER_AR — the BINDING
        # CONSTRAINT of 2026-07-31 — so DEC-31's strip removes it before DEC-16's
        # approval detector, whose whole-utterance isolation would otherwise stop
        # matching a genuine «أوافق» for as long as a mode is running.
        frame = self._session_mode.frame
        if frame is not None:
            step = frame.plan.current_step if frame.plan is not None else None
            line = mode_directive_line(
                frame.name, self._session_mode.current_step,
                self._session_mode.total_steps, step.text if step else None)
            user_text = f"{line}\n{user_text}"
        return user_text

    def end_turn(self) -> None:
        """Decay whatever is one-shot, at the end of the WHOLE utterance."""
        # Verbosity decay (B4): EXACT is one-shot per WHOLE utterance — decaying
        # any earlier would strip it before the tool_choice="none" explain pass.
        self._verbosity.end_turn()


__all__ = ["TurnPrelude"]
