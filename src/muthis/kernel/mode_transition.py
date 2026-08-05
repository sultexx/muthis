# src/muthis/kernel/mode_transition.py
"""
`ModeAuthority` — THE SINGLE TRANSITION AUTHORITY (DEC-65, T2).

**The model REQUESTS; the KERNEL decides. There is never a direct state change
from model output.** `SessionMode.enter` / `.leave` / `.record_progress` shipped
INERT at T1; this module is what governs them, exactly as `raise_taint` shipped
inert at M2's T4 and its gate arrived at T5.

ONE EVALUATION POINT, AND IT IS ENFORCED BY SHAPE. `request()` is the ONLY public
method on this class, so there is no `advance()`, no `jump()` and no `exit_now()`
side door to reach for — enter, leave, advance, back, jump, plan-edit, the
deterministic exit word and the idle expiry ALL cross the same line. A guard
additionally asserts that no module in `src/` outside this one calls the mode's
mutators at all. **Today the conditions are trivial; tomorrow they are not — a
pending confirmation (DEC-16), a running sandbox — and one evaluation point is
what keeps that from becoming scattered special cases.**

THE CONDITIONS ARE NAMED NOW AND BUILT LATER, IN THE `RouteImpact` SHAPE:
a frozen record of the KERNEL's own facts with a predicate over them, and nothing
else. `TransitionConditions` carries the two DEC-65 names and **nothing sets them
yet** — the seam is a callable so the composition root can wire the real facts at
T4/T5 without this file changing. Stub-first, the AGENTS.md LAW and the DEC-34
deferral precedent. **RECORDED READING:** DEC-65 names *"the `RouteImpact` shape
(`src/muthis/trust/high_impact.py`)"* as the home, which reads two ways. The SHAPE
is taken and the FILE is not, because `trust/high_impact.py` classifies TOOL CALLS
for spoken approval — conversational-transition preconditions are a different
concern, and putting them there would be the placement-by-convenience DEC-73
rejected for design D. It would also break that module's own pinned guards
(`test_high_impact.py` fixes its imports and its public surface), and a ruling
does not break its own guards.

CONTROL REQUESTS ARE NEVER REFUSED, AND THIS ASYMMETRY IS LOAD-BEARING. The
conditions gate MODEL-initiated transitions only. The deterministic exit word and
the idle expiry pass through the same point but skip the condition check, because
**if a pending condition could block the user's exit, a model could trap the user
in a mode by keeping one pending** — which is precisely what DEC-65's
model-INDEPENDENT exit 1 exists to make impossible. Being trapped is a CONTROL
problem, not a content one.

NO NESTING, THROUGH THE AUTHORITY. A mode-to-mode change is ONE evaluated decision
— exit and enter TOGETHER — never two sequential operations, because two create an
intermediate state nobody owns (the undefined THIRD state DEC-24 closed at
`broker.py:92`). `_enter` therefore calls the mode's single replacing assignment
and NEVER `leave` first; no function here calls both, and a test asserts that
structurally as well as by observing that the mode is never seen inactive between
two modes.

PROGRESS IS A REQUEST THE KERNEL APPROVES — NOT A DETERMINISTIC DETECTOR, and that
is DEC-62's classification by ROLE. DEC-16 needs a deterministic detector because
approval is an AUTHORIZATION decision where a false positive is a BYPASS. Step
progress is not authorization: its worst case is being on the WRONG STEP, which is
visible in the kernel-drawn indicator (T3) and corrected with a word. **EXIT is
different in KIND and keeps its detector.**

EXPIRY IS EVALUATED LAZILY AND THERE IS NO TIMER. `is_idle_expired` is a PURE
PREDICATE the caller runs at the start of a turn; the mutation it may lead to
still goes through `request()`. A background timer is a lifecycle outside the
kernel, which Law 11 forbids and which DEC-47 already rejected for background
ingestion. ACCEPTED CONSEQUENCE, recorded rather than discovered: **the mode does
not announce its own expiry** — Mut'his speaks only after F9, so an expired mode
is discovered at the next turn, with the indicator already gone.

A MODE STILL GRANTS NO PRIVILEGE. This module reads two booleans about kernel
state; it holds no capability, raises no taint and touches no grant, and a guard
asserts the absence rather than trusting it. **F9 keeps its ONE meaning —
barge-in. It never means "exit", in any mode** (DEC-16 rejected state-dependent
gestures outright, and nothing here is wired to it).

Sibling imports plus stdlib; importable in isolation. Never raises: a refused
transition is a value, because a bound is not an exception on the turn path
(Law 11).
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Callable, Optional

from .mode_surfaces import (
    AT_END, AT_START, BLOCKED, NO_MODE, NO_PLAN, UNKNOWN_STEP, UNNAMED_MODE,
    refusal_note,
)
from .plan import Plan
from .session_mode import SessionMode

logger = logging.getLogger("muthis.kernel.mode_transition")

# The request kinds. Every mode change in the product is one of these — there is
# no eighth kind reachable by another path, which is what "no special paths"
# means in code rather than in prose.
ENTER = "enter"
LEAVE = "leave"
ADVANCE = "advance"
BACK = "back"
JUMP = "jump"
EDIT_PLAN = "edit_plan"
EXIT_WORD = "exit_word"
EXPIRE = "expire"

# The two that are NEVER refused (see the module docstring). Membership is the
# ONE copy of that fact: deriving it anywhere else is how two lists drift.
CONTROL_KINDS = frozenset({EXIT_WORD, EXPIRE})
# Every kind that ends the mode, control or not — one list, read once below.
_LEAVING_KINDS = frozenset({LEAVE}) | CONTROL_KINDS

# Which refusal a bounds failure is, per kind. A table rather than a chain so a
# new kind cannot silently inherit another's wording (the DEC-35 lesson: a
# refusal that misreports its reason turns a terminal condition into a retryable
# one).
_BOUND_REASONS = {
    ADVANCE: AT_END,
    BACK: AT_START,
    JUMP: UNKNOWN_STEP,
    EDIT_PLAN: NO_PLAN,
}

# DEC-65's inactivity exit. It lives HERE and deliberately NOT in
# `session_mode.py`, whose guard fails on any bare numeric constant: the frame
# holds the idle CLOCK, the authority holds the idle DECISION.
MODE_IDLE_TIMEOUT_S = 900.0


@dataclasses.dataclass(frozen=True)
class TransitionRequest:
    """ONE requested mode change, as a value.

    Frozen and keyword-defaulted so a later kind's payload is additive at every
    call site — DEC-66's argument about a list of strings, applied to the
    request type itself."""

    kind: str
    mode_name: Optional[str] = None      # ENTER
    plan: Optional[Plan] = None          # ENTER / EDIT_PLAN
    step_id: Optional[str] = None        # JUMP


@dataclasses.dataclass(frozen=True)
class TransitionConditions:
    """The kernel's OWN facts about whether a mode change may proceed NOW.

    THE `RouteImpact` SHAPE: kernel-owned facts, a predicate over them, and no
    behaviour. **Both fields are STUBS — nothing sets them yet** (T4/T5 wire the
    real ones through the callable seam). They are named now because naming an
    unknown in advance is the decision; leaving it unnamed hands it to whoever
    hits it first, at implementation time, alone."""

    confirmation_pending: bool = False   # DEC-16: an approval awaiting the user
    sandbox_running: bool = False        # DEC-3: a container still executing

    def blocking(self) -> bool:
        """May a MODEL-initiated transition proceed? (Control never asks.)"""
        return self.confirmation_pending or self.sandbox_running


@dataclasses.dataclass(frozen=True)
class TransitionOutcome:
    """What the authority decided. `note_ar` is populated only on a refusal, and
    is never empty when it is: a refusal that is not reported produces a retry
    loop, and the agentic loop exists to retry."""

    applied: bool
    reason: Optional[str] = None
    note_ar: Optional[str] = None


def is_idle_expired(mode: SessionMode,
                    *, timeout_s: float = MODE_IDLE_TIMEOUT_S) -> bool:
    """Has the mode been idle past its bound? A PURE PREDICATE — it decides
    nothing and mutates nothing, so the one mutation path stays `request()`.

    On IDLE TIME, never turn count (DEC-65): a user may spend ten minutes on one
    step without producing a turn, so counting turns measures the wrong thing."""
    return mode.active and mode.idle_seconds() >= timeout_s


class ModeAuthority:
    """The ONE evaluation point. `request` is its ONLY public method."""

    def __init__(self, *, mode: SessionMode,
                 conditions: Optional[Callable[[], TransitionConditions]] = None) -> None:
        self._mode = mode
        # A real default, never None — the `SessionTaint` / `PassServiced` shape:
        # a consumer must never branch on absence. The stub answers "nothing
        # blocks", which is the honest state until T4/T5 wire the real facts.
        self._conditions = conditions or TransitionConditions

    def request(self, request: TransitionRequest) -> TransitionOutcome:
        """Evaluate ONE requested mode change and apply it, or refuse it with a
        note that states what was achieved, whether the condition is terminal or
        transient, and the valid next step.

        Control requests (the deterministic exit word, the idle expiry) skip the
        condition check and only that check — they take the same path, the same
        bounds and the same notes. A separate control path is how the single
        evaluation point would quietly become two."""
        if request.kind not in CONTROL_KINDS and self._conditions().blocking():
            return self._refuse(BLOCKED)
        if request.kind == ENTER:
            return self._enter(request)
        if request.kind in _LEAVING_KINDS:
            return self._leave()
        return self._move(request)

    # ─── The three mutations, each in its own body ───────────────────────────

    def _enter(self, request: TransitionRequest) -> TransitionOutcome:
        """ENTER, including mode-to-mode: ONE call, which the frame applies as a
        single replacing assignment. This body must never call `leave` first —
        that is the two-operation shape DEC-65 forbids, and it is asserted
        structurally, not merely avoided here."""
        if not request.mode_name:
            return self._refuse(UNNAMED_MODE)
        self._mode.enter(request.mode_name, plan=request.plan)
        # THE ONE MODE-ENTRY LOG LINE (DEC-93), placed where entry is DECIDED
        # rather than scattered: this is the only `SessionMode.enter` call site
        # in `src/`, so one line here cannot miss an entry and cannot double-count
        # one. It exists because DEC-92 found that a mode entry left NO TRACE
        # ANYWHERE — not in a log, not in the plugin ledger (a `kernel_serviced`
        # verb never reaches `ToolRouter._record`) — so "did the model reach the
        # Navigator at all" was unanswerable after the fact. The one tool family
        # designed to PERSIST ACROSS TURNS was the one whose invocation could not
        # be confirmed.
        #
        # THE MODE NAME IS DELIBERATELY NOT LOGGED, and the omission is the
        # careful part. `navigator_service` passes the MODEL-AUTHORED plan TITLE
        # as `mode_name`, and a title may echo whatever was on the user's screen.
        # That is exactly the content `session_mode.py` refuses a logger in order
        # to protect ("no means to leak it"), and this line must not become the
        # leak that module's absence-of-means was built to prevent. The STEP
        # COUNT is an integer and the FACT of entry is the kernel's own, so both
        # are safe under the DEC-20 / DEC-28 rule that a log carries the kernel's
        # facts and never content. Discriminating between modes in the log needs
        # a kernel-ASSIGNED kind distinct from the display title — a design note
        # for whoever adds the second mode, not something to improvise here.
        logger.info("[mode] ENTERED — walkthrough of %d step(s); persists ACROSS "
                    "TURNS until an exit (exit word / completion / idle)",
                    request.plan.total if request.plan else 0)
        return TransitionOutcome(applied=True)

    def _leave(self) -> TransitionOutcome:
        """LEAVE / the exit word / expiry. Leaving when nothing is running is a
        refusal rather than a silent success, because reporting "nothing was
        running" is the accurate state and inventing a success is not."""
        if not self._mode.active:
            return self._refuse(NO_MODE)
        self._mode.leave()
        return TransitionOutcome(applied=True)

    def _move(self, request: TransitionRequest) -> TransitionOutcome:
        """ADVANCE / BACK / JUMP / PLAN-EDIT — all four, no special paths.

        The kernel BOUNDS-CHECKS by asking the plan, which answers None at its
        own edges (DEC-66); this body only decides which refusal that None is."""
        if not self._mode.active:
            return self._refuse(NO_MODE)
        plan = self._mode.plan
        if plan is None:
            return self._refuse(NO_PLAN)
        if request.kind == EDIT_PLAN:
            moved = request.plan
        elif request.kind == ADVANCE:
            moved = plan.advanced()
        elif request.kind == BACK:
            moved = plan.moved_back()
        elif request.kind == JUMP:
            moved = plan.with_current(request.step_id) if request.step_id else None
        else:  # an unrecognised kind is REFUSED, never quietly treated as a jump
            return self._refuse(BLOCKED)
        if moved is None:
            return self._refuse(_BOUND_REASONS.get(request.kind, BLOCKED))
        self._mode.record_progress(plan=moved)
        return TransitionOutcome(applied=True)

    def _refuse(self, reason: str) -> TransitionOutcome:
        """The ONE refusal builder, so every refused transition is reported and
        none can be swallowed by a branch that forgot its note."""
        return TransitionOutcome(
            applied=False, reason=reason,
            note_ar=refusal_note(reason, current=self._mode.current_step,
                                 total=self._mode.total_steps))


__all__ = [
    "ADVANCE", "BACK", "CONTROL_KINDS", "EDIT_PLAN", "ENTER", "EXIT_WORD",
    "EXPIRE", "JUMP", "LEAVE", "MODE_IDLE_TIMEOUT_S", "ModeAuthority",
    "TransitionConditions", "TransitionOutcome", "TransitionRequest",
    "is_idle_expired",
]
