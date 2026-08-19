# src/muthis/kernel/session_mode.py
"""
`SessionMode` — the KERNEL's half of a long-lived conversational mode
(DEC-65, T1). A GENERAL primitive, deliberately NOT a "Teach Mode".

WHY GENERAL — Sultan's ruling: future modes (Teaching, Review, Debug) must
INHERIT this structure rather than force a redesign. Binding a primitive to the
one feature that needed it first is how rigid architectures are born. Navigator
is the first CONSUMER of `SessionMode`; it is not its definition.

THE OWNERSHIP SPLIT — THE KERNEL OWNS THE FRAME, THE MODEL OWNS THE CONTENT.
Held here: `active` · the mode NAME · the CURRENT STEP · the TOTAL · the
LAST-PROGRESS TIME. Held by the model: what each step says, what to point at,
how to explain it. **"Step 3 of 5" is a STRUCTURAL FACT, not a phrase.** If the
model owned it, it would be a CLAIM with no backing — indistinguishable from a
fabricated one, and unfalsifiable at exactly the moment it matters. That is WHO
OWNS THE FACT in a sixth place, after plugin-set `is_error` (DEC-29), a
plugin's declared `read_only` (DEC-15), a plugin wrapping its own output
(DEC-14), a plugin-set number reaching the sovereign ledger (DEC-34) and the
domain badge's provenance (DEC-36).

STORAGE ONLY — AND SAYING SO IS PART OF THE JOB. This object evaluates nothing.
It refuses nothing, returns no note, enforces no condition and reads no
transcript. DEC-65's SINGLE TRANSITION AUTHORITY — the one evaluation point,
the three independent exits, the refusal that states what was achieved — is
T2's and is NOT here. The precedent is exact: `SessionTaint.raise_taint` shipped
INERT at M2's T4 and the gate that reads it arrived at T5, because
classification and the gate are one concern. **A guard documented as active
while actually inert is the inverse error and has bitten this project, so it is
stated plainly: at T1 this is inert.**

NO NESTING — AND THE TYPE CANNOT REPRESENT TWO. There is ONE frame slot. Not a
stack, not a list: "pop back to the previous mode" is not expressible, so it
cannot be reached for. `enter()` on an active mode REPLACES the frame in a
SINGLE assignment, which is DEC-65's mode-to-mode change as ONE decision (exit
and enter together) rather than two sequential operations. Two operations would
create an intermediate state nobody owns — the undefined THIRD state DEC-24
closed at `broker.py:92`, where a granted plugin and a denied plugin saw the
same absent seam. The contract there was made BINARY; so is this one.

TWO CLOCKS, TWO QUESTIONS (DEC-104 ruling 2), both stamped from the INJECTED
clock. `last_progress_at` answers **DID THE STEP MOVE** and is stamped by
`enter` and `record_progress` — exactly the events it always was.
`last_activity_at` answers **IS THE USER STILL HERE** and is stamped by `enter`
and `record_activity`, which the turn prelude calls once per user turn. NEITHER
IS DERIVABLE FROM THE OTHER, and that gap is the whole defect DEC-102 measured:
with only the first clock, "idle" meant time since the last COMMITTED STEP
CHANGE, so a turn that moved no step — a side question, or a refused "advance"
at the last step — AGED the mode while the user was sitting right there, and the
turn that killed it was the user's own return.

IDLE TIME, NOT EXPIRY. `idle_seconds()` REPORTS elapsed time. There is no
threshold here, no timeout constant, and nothing anywhere near a timer. DEC-65
puts the timeout on IDLE
TIME rather than turn count — a user may spend ten minutes on one step without
producing a turn, so counting turns measures the wrong thing — and has it
evaluated LAZILY at the start of the next turn (T2), NEVER by a background
timer: a timer is a lifecycle outside the kernel, which Law 11 forbids and
which DEC-47 already rejected for background ingestion. MONOTONIC by default,
never wall clock, so a system clock change cannot age a mode.

A MODE GRANTS NO PRIVILEGE, EVER — HARD INVARIANT, ASSERTED STRUCTURALLY. A
mode changes conversational behaviour ONLY. It grants no capability, raises no
taint (it ingests no external content), and is NEVER PERSISTED — it dies with
the process, the `SessionIndex` / `SessionTaint` shape. Recorded because it
looks obvious today and becomes tempting after three modes: *"in Debug mode,
give the sandbox network"* is a CONSTITUTIONAL change (DEC-3 / V2 Roadmap
decision #0 is the only execution carve-out and it does not move) and must read
as one when someone proposes it. **The proof is by ABSENCE OF MEANS.** This
module imports nothing that could persist, log, grant or taint, and names no
such symbol — the `FetchedDomains` argument (DEC-36), which had no logger and
therefore could not leak a domain. **If the module cannot EXPRESS a privilege
change, it cannot REGRESS into one**, and a guard asserts that rather than
trusting it.

NO LOGGER, for a reason sharper than habit: the frame holds a `Plan`, and a
plan's step text is MODEL-AUTHORED and may echo whatever was on the user's
screen. There is no logging import here, so there is no means to leak it.

LOOK-ONLY DOES NOT MOVE — not in this milestone and not in any mode. No
`type_text`, no `real_click`, no input synthesis of any kind (DEC-6,
permanent).

Sibling `plan` import plus stdlib; importable in isolation. Holds no lifecycle,
no lock and no loop (Law 11): it is state the composition root builds once and
the kernel reads.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Callable, Optional

from .plan import Plan


def _ignore_change(mode: "SessionMode") -> None:
    """The default observer: a real callable, never None, so `SessionMode` has
    exactly one notification path rather than one plus an absence check."""


@dataclasses.dataclass(frozen=True)
class ModeFrame:
    """The kernel's frame for ONE active mode — a VALUE, replaced whole.

    It carries no reference to another frame and no collection of them, which
    is one half of why nesting is unrepresentable; the other half is that
    `SessionMode` holds exactly one of these."""

    name: str
    plan: Optional[Plan] = None
    # TWO CLOCKS, TWO QUESTIONS (DEC-104 ruling 2). Kept as separate fields
    # because neither answer can be recovered from the other one.
    last_progress_at: float = 0.0   # did the STEP move
    last_activity_at: float = 0.0   # is the USER still here


class SessionMode:
    """The ONE mode slot: built at the composition root, injected, and alive
    for the PROCESS — the `SessionTaint` shape, with the same reason. A mode
    that outlived the process would be a persisted conversational state nobody
    consented to, and a mode rebuilt per turn could not span turns at all."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 on_change: Optional[Callable[["SessionMode"], None]] = None) -> None:
        # Injected so idle time is DRIVEN in tests rather than slept for, and
        # monotonic by default so a clock change cannot age a mode.
        self._clock = clock
        # T3: an OPAQUE observer, fired after every state change. This module
        # never learns what it does — the DEC-37 `turn_hooks` shape exactly, and
        # the reason the indicator can be drawn without this file naming an
        # overlay, a canvas or a draw. The composition root is the one place
        # that knows both sides, and it is the root's callable that must never
        # raise; a real no-op default means no consumer branches on absence.
        self._on_change = on_change or _ignore_change
        # ONE SLOT — the whole no-nesting property, in one line.
        self._frame: Optional[ModeFrame] = None

    # ─── The FRAME, read-only (DEC-65) ───────────────────────────────────────

    @property
    def active(self) -> bool:
        """Whether a mode is running. The indicator (T3) draws from this."""
        return self._frame is not None

    @property
    def frame(self) -> Optional[ModeFrame]:
        """The whole frame, or None. Read-only: the only ways in are below."""
        return self._frame

    @property
    def name(self) -> Optional[str]:
        """The mode's name, or None when no mode is active."""
        return None if self._frame is None else self._frame.name

    @property
    def plan(self) -> Optional[Plan]:
        """The plan this mode is guiding, or None — a mode may run without one
        (a Review mode has no steps), which is why it is optional rather than
        assumed."""
        return None if self._frame is None else self._frame.plan

    @property
    def current_step(self) -> int:
        """The 3 in "step 3 of 5" — 1-based, 0 when there is no plan or no
        current step. DERIVED from the plan on every read and never stored
        here: one fact, one home (DEC-15). A stored copy is what would let the
        spoken number and the drawn number disagree."""
        plan = self.plan
        return 0 if plan is None else plan.current_number

    @property
    def total_steps(self) -> int:
        """The 5 in "step 3 of 5" — 0 when there is no plan."""
        plan = self.plan
        return 0 if plan is None else plan.total

    def idle_seconds(self) -> float:
        """Seconds since the USER was last here; 0.0 when inactive.

        READS `last_activity_at`, NOT `last_progress_at` (DEC-104 ruling 2). The
        NAME did not change, because the name was never the wrong part: "idle"
        always meant the user, and the defect was that it measured the step. A
        turn that moves no step is still a user who is present.

        REPORTS, and decides nothing. There is no threshold in this module —
        DEC-65's inactivity exit is evaluated lazily at the next turn's start
        by the T2 authority, never here and never by a timer."""
        if self._frame is None:
            return 0.0
        return self._clock() - self._frame.last_activity_at

    # ─── Storage — no evaluation, no refusal, no note (all T2's) ─────────────

    def enter(self, name: str, *, plan: Optional[Plan] = None) -> None:
        """STORE a mode in the one slot, stamping the idle clock at entry.

        Entering while a mode is already active REPLACES the frame in ONE
        assignment: there is no instant at which two modes are held, and none
        at which the slot is empty in between. That is DEC-65's exit-and-enter
        as a single evaluated decision, made unrepresentable-otherwise rather
        than merely discouraged."""
        # BOTH clocks start here, from ONE reading: entering is a step change AND
        # a user who is unmistakably present. Two readings could differ, and two
        # clocks that start at different instants is a subtle wrongness nobody
        # would look for; an UNSTAMPED activity clock would read 0.0 and expire
        # the mode on its very first turn.
        now = self._clock()
        self._frame = ModeFrame(name=name, plan=plan,
                                last_progress_at=now, last_activity_at=now)
        self._on_change(self)

    def leave(self) -> None:
        """Empty the slot. Idempotent — leaving twice is not an error, and a
        mode that already expired is simply not there."""
        self._frame = None
        self._on_change(self)

    def record_progress(self, *, plan: Optional[Plan] = None) -> None:
        """Re-stamp the PROGRESS clock, and store the plan the caller computed.

        STAMPED ON EXACTLY THE EVENTS IT ALWAYS WAS (DEC-104 ruling 2 leaves
        this untouched): a committed step change, and nothing else. It answers
        "did the step move", that answer is still wanted, and it is NOT
        repurposed into a liveness signal — the second clock exists so it does
        not have to be. It deliberately does NOT stamp `last_activity_at`
        either: the turn this runs inside already stamped that at its start, and
        one clock with two stamp sites is how two answers drift into one.

        A no-op when no mode is active, so a stray call can never resurrect
        one. MODE PERSISTENCE IS INDEPENDENT OF STEP PROGRESS (DEC-65): a side
        question answered mid-mode simply does not call this, and the mode
        survives it untouched — by design, not by patch."""
        if self._frame is None:
            return
        self._frame = dataclasses.replace(
            self._frame,
            plan=self._frame.plan if plan is None else plan,
            last_progress_at=self._clock())
        self._on_change(self)

    def record_activity(self) -> None:
        """Re-stamp the LIVENESS clock: the user produced a turn.

        THE SECOND CLOCK (DEC-104 ruling 2). Every user turn is activity — a
        side question, a refused move, a turn that moves no step at all — which
        is precisely the class that used to AGE the mode while the user sat
        right there. The side-question exclusion above STAYS and is now
        CONSISTENT rather than contradictory: a side question does not move the
        step, so it must not touch progress, but it IS activity, so it renews
        liveness. The exclusion was never the bug; the missing clock was.

        DELIBERATELY NOT A TRANSITION, which is why it does not go through the
        single authority, and the property is STRUCTURAL rather than promised:
        it takes no argument, so it cannot carry a mode, a plan or a step; it is
        a no-op when nothing is active, so it cannot create one; it touches ONE
        field; and it fires NO observer, because nothing the indicator draws has
        changed. There are no conditions, no bounds and no refusal note here to
        bypass — which is the whole of what that authority protects."""
        if self._frame is None:
            return
        self._frame = dataclasses.replace(
            self._frame, last_activity_at=self._clock())


__all__ = ["ModeFrame", "SessionMode"]
