# src/muthis/kernel/plan.py
"""
`Plan` and `Step` — what the KERNEL stores when Mut'his is guiding a task
(DEC-66, T1). ARCHITECTURAL PRIMITIVES, not a list of strings.

WHY NOT A LIST OF STRINGS — the design proposal asked for one and Sultan's
ruling corrected it: a list of strings CANNOT be extended later without
redesigning every producer and every consumer at once. The kernel owns THE
PLAN; it does not own the step texts.

THE STABLE ID IS THE LOAD-BEARING PART. A plan is EDITED mid-session — steps
deleted, inserted, reordered — so a POSITIONAL reference breaks SILENTLY and
"step 3" quietly becomes a different step. That is structurally the DEC-63
id-mismatch defect in a new place: a machine identifier that cannot survive the
round trip it is actually put through, failing with no observable difference.
Every reference here is BY ID.

THE ID IS A STRING, AND THAT IS THE POINT. `"s4"` cannot be used as an index:
`plan.steps[step.id]` raises a TypeError rather than returning a plausible
wrong answer, so the positional shortcut this primitive exists to prevent is
unavailable BY CONSTRUCTION rather than by review.

IT IS A PLAN-LOCAL MONOTONIC COUNTER, NOT `secrets` — the deliberate contrast
with DEC-14's nonce. The nonce needs `secrets` precisely because it FACES
untrusted content, where a predictable value is a forgeable one. A step id
never crosses a trust boundary: it is never spoken, never drawn, never
model-visible. There is nothing to forge, and determinism makes the
insert/delete/reorder guard EXACT rather than probabilistic. The counter never
rewinds, so a deleted step's id is never re-issued to a different step.

THE FIELDS ARE NOT BUILT NOW; THE SHAPE THAT CAN RECEIVE THEM IS. Step state
and DEC-67's citation reference are NOT built here (stub-first, the AGENTS.md
LAW). `Step` is a frozen record with keyword fields, so a later field is
ADDITIVE at every existing call site — DEC-73's `PassServiced` argument applied
one layer down. DEC-45 is the precedent for paying up front: position data was
bought early because it is unrecoverable later without a full re-index, and a
plan is WORSE — it lives in RAM and dies with the session, so there is no
re-index to fall back on at all.

THIS MODULE STORES, NUMBERS AND BOUNDS-CHECKS. IT NEVER INTERPRETS TEXT.
Retention is not comprehension, and this project already runs on that
distinction: `turn_hooks` holds opaque callables the router never inspects
(DEC-37) and the router carries wrapped content it never parses (DEC-14).
Ownership here is STRUCTURAL, not linguistic — `Step.text` is written at
construction and returned whole, and is READ nowhere in this file. A guard
asserts that as an ABSENCE of any `.text` access, not as a promise.

NO LOGGER, DELIBERATELY. A step's text is MODEL-AUTHORED and may echo whatever
was on the user's screen. This module imports no logging at all, so it has no
means to leak it — the `FetchedDomains` argument (DEC-36), stronger here than
it was there. Absence proven by lack of means, never by discipline.

EVERY EDIT RETURNS A NEW PLAN, AND A REFUSED EDIT RETURNS `None` RATHER THAN
RAISING: a bound is not an exception on the turn path (Law 11). Turning that
`None` into the model-facing note that states what WAS achieved, whether the
condition is TERMINAL or TRANSIENT, and the valid NEXT STEP is the TRANSITION
AUTHORITY's job — T2's, not this module's.

Pure stdlib, no sibling imports; importable in isolation.
"""

from __future__ import annotations

import dataclasses
from typing import Optional, Sequence

# The prefix is what makes an id UNUSABLE as an index (see the docstring):
# "s4" is not 4, so the positional shortcut fails loudly instead of quietly.
STEP_ID_PREFIX = "s"


@dataclasses.dataclass(frozen=True)
class Step:
    """ONE step: a stable IDENTITY, and the text that belongs to it.

    FROZEN and keyword-constructible so a later field — step state, DEC-67's
    citation reference — is additive at every existing call site. `text` is
    OPAQUE here: stored, returned whole, never read."""

    id: str
    text: str


@dataclasses.dataclass(frozen=True)
class Plan:
    """An ordered list of identified steps, and which one is current.

    `current_step_id` is an ID and never an index. `next_step_id_number` rides
    ON the plan so a plan rebuilt by any edit below carries its counter forward
    and can never re-issue a retired id."""

    title: str
    steps: tuple[Step, ...] = ()
    current_step_id: Optional[str] = None
    next_step_id_number: int = 1

    # ─── What the kernel NUMBERS ─────────────────────────────────────────────

    @property
    def total(self) -> int:
        """The 5 in "step 3 of 5"."""
        return len(self.steps)

    @property
    def current_step(self) -> Optional[Step]:
        """The current step, or None — including after an edit DELETED it."""
        return self.step_by_id(self.current_step_id)

    @property
    def current_number(self) -> int:
        """The 3 in "step 3 of 5" — 1-based, 0 when there is no current step.

        DERIVED on every read, never stored. A second copy of one fact is how
        two views drift apart, which is why `external` was kept off
        `RouteImpact` (DEC-15); the same reasoning applies to a step number the
        kernel puts on screen and speaks in the same turn."""
        position = self.position_of(self.current_step_id)
        return 0 if position is None else position + 1

    def step_by_id(self, step_id: Optional[str]) -> Optional[Step]:
        """The step with that id, or None. The ONE lookup every reference uses."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def position_of(self, step_id: Optional[str]) -> Optional[int]:
        """The 0-based position of an id, or None.

        Positions are DERIVED from ids here and are never stored as one — the
        direction matters, because the reverse is exactly the silent break the
        stable id exists to prevent."""
        for position, step in enumerate(self.steps):
            if step.id == step_id:
                return position
        return None

    # ─── What the kernel STORES — every edit returns a NEW plan ──────────────

    @classmethod
    def build(cls, title: str, step_texts: Sequence[str] = ()) -> "Plan":
        """A fresh plan with ids assigned in order, the FIRST step current.

        An empty plan has no current step, which is the honest state rather
        than a pointer at nothing."""
        plan = cls(title=title)
        for text in step_texts:
            plan = plan.with_step_inserted(text)
        first_id = plan.steps[0].id if plan.steps else None
        return dataclasses.replace(plan, current_step_id=first_id)

    def with_step_inserted(self, text: str, *, at: Optional[int] = None) -> "Plan":
        """A NEW plan carrying one more step; appended when `at` is None.

        `at` is a 0-based POSITION and is the ONE place a position is legal,
        because an insertion POINT is not a reference to a step. It clamps
        rather than refusing — there is no wrong step to land on. Every
        existing id keeps its meaning, and the current step is untouched: the
        step that was current before this call is still current after it, even
        though its POSITION may have moved."""
        step = Step(id=f"{STEP_ID_PREFIX}{self.next_step_id_number}", text=text)
        position = len(self.steps) if at is None else max(0, min(at, len(self.steps)))
        steps = self.steps[:position] + (step,) + self.steps[position:]
        return dataclasses.replace(
            self, steps=steps, next_step_id_number=self.next_step_id_number + 1)

    def without_step(self, step_id: str) -> Optional["Plan"]:
        """A NEW plan with that step gone, or None when the id is unknown —
        the BOUNDS CHECK, reported rather than swallowed.

        Deleting the CURRENT step leaves NO current step. The kernel does not
        slide the pointer onto a neighbour: it never invents a position the
        model did not give it, and absence is more honest than a computed
        guess (DEC-67). Recovering from that is the authority's decision, made
        where a refusal can be spoken."""
        if self.step_by_id(step_id) is None:
            return None
        steps = tuple(step for step in self.steps if step.id != step_id)
        current = None if step_id == self.current_step_id else self.current_step_id
        return dataclasses.replace(self, steps=steps, current_step_id=current)

    def with_steps_reordered(self, step_ids: Sequence[str]) -> Optional["Plan"]:
        """A NEW plan in the given order, or None unless `step_ids` is exactly
        a PERMUTATION of the ids this plan holds — a reorder that dropped or
        invented a step would be a different edit wearing this one's name.

        THE WHOLE PRIMITIVE IS VISIBLE HERE: the steps move, every id survives,
        and the step that was current is still the SAME step afterwards — at a
        different number, which is what "step 3 of 5" now correctly reads."""
        if len(step_ids) != len(self.steps):
            return None
        if set(step_ids) != {step.id for step in self.steps}:
            return None
        by_id = {step.id: step for step in self.steps}
        return dataclasses.replace(
            self, steps=tuple(by_id[step_id] for step_id in step_ids))

    def with_current(self, step_id: str) -> Optional["Plan"]:
        """A NEW plan pointing at that step, or None when the id is unknown —
        the BOUNDS CHECK. A jump, an advance and a step back all land here."""
        if self.step_by_id(step_id) is None:
            return None
        return dataclasses.replace(self, current_step_id=step_id)

    def advanced(self) -> Optional["Plan"]:
        """One step forward, or None at the END — a bound, not an error."""
        return self._moved_by(1)

    def moved_back(self) -> Optional["Plan"]:
        """One step back, or None at the START."""
        return self._moved_by(-1)

    def _moved_by(self, offset: int) -> Optional["Plan"]:
        position = self.position_of(self.current_step_id)
        if position is None:
            return None
        target = position + offset
        if target < 0 or target >= len(self.steps):
            return None
        return dataclasses.replace(self, current_step_id=self.steps[target].id)


__all__ = ["Plan", "Step", "STEP_ID_PREFIX"]
