# src/muthis/trust/confirm_gate_state.py
"""
THE GATE'S STATE — what the confirm gate REMEMBERS between calls, and every
transition of it. Never what it DECIDES.

EXTRACTED FROM `confirm_gate.py` ahead of DEC-143, on `call_binding.py`'s
precedent and for its reason: POLICY versus MECHANISM. The canonicalisation left
the gate because it is the same bytes whichever gate consumes them; the state
leaves because it is the same record whatever the gate decides about it. The gate
keeps the policy — whether a call is REFUSED and whether it is RELEASED — and
owns ONE of these, built in its own constructor and never shared or injected, so
the router's default gate and the composition root's gate stay ONE gate.

THE MEASUREMENT THAT MADE IT A MOVE AND NOT A PREFERENCE (G1, 2026-09-24).
DEC-143's grant is WIRING more than logic: in place it measured 332 lines in the
gate's own comment density, and 302 even as bare code with a docstring left
false. Moving the records alone left 314 and the spoken hand-over alone 318; both
together fit at exactly 300 with no room, and a subclass fit at 298 by splitting
the one confirmation site across two classes while fifteen test files kept
building the other — DEC-40's measured failure. Neither was taken.

THE THIRD HOME. DEC-138 found no coherent home for the spoken hand-over: the only
candidates were the gate and the speech module, which is pure and stateless. The
hand-over is STATE, so it lives here, and the speech module stays pure.

IT DECIDES NOTHING, and that is guarded rather than promised: no detector, no
note, no binding, no classification and NO LOGGER — every log line stays in the
gate, on the gate's logger, so the durable log reads the same across the move.
Pure stdlib (`dataclasses`, `typing`), importable in isolation.
"""

from __future__ import annotations

import dataclasses
from typing import Optional


@dataclasses.dataclass(frozen=True)
class _Pending:
    """The ONE call awaiting the user's word. Replaced, never queued: a second
    high-impact call supersedes the first, so an unapproved call can never sit
    behind another waiting to be released by an unrelated approval."""

    fingerprint: str
    tool: str
    approved: bool = False


class GateState:
    """The confirm gate's memory: the ONE pending call, the turn's ONE look,
    whether the last utterance missed, and the ONE request waiting to be spoken."""

    def __init__(self) -> None:
        self.pending: Optional[_Pending] = None
        # Nothing to observe until a turn arms it: a stray observe() before the
        # first turn must not spend the turn's one look.
        self.observed_this_turn = True
        # Did the LAST observed utterance reach the detector and come back as
        # NEITHER answer? It selects the retry note (DEC-136 ruling 3) and does
        # nothing else — it never affects WHETHER a call is refused, which is
        # why widening the accepted set and this flag are separate rulings.
        self.missed = False
        # DEC-138: the kernel's OWN utterance for the refusal just taken, built
        # from the canonical bytes and handed over ONCE. None whenever nothing is
        # outstanding to say — which is every state but "refused, not yet
        # spoken", so a pass that refuses nothing can never speak.
        self.spoken: Optional[str] = None

    @property
    def pending_tool(self) -> Optional[str]:
        """The tool awaiting approval, for tests and logs — never the args."""
        return self.pending.tool if self.pending is not None else None

    @property
    def awaiting_approval(self) -> bool:
        """True while a REFUSED call is still waiting for the user's word.

        IT IS NOT `pending_tool is not None`, AND THE DIFFERENCE IS THE WHOLE
        POINT (DEC-131). `observe()` sets `approved` on the pending state and
        LEAVES IT IN PLACE, so the name-only accessor stays truthy ACROSS the
        approval. A brake keyed on that would gag the very pass that must
        re-issue the call the user just approved, and the approval could never
        be spent — the fix would break the success path it exists to reach.
        This one goes False the moment the word is heard."""
        return self.pending is not None and not self.pending.approved

    def arm(self) -> None:
        """Open the coming turn's ONE look — the gate's `new_turn`."""
        self.observed_this_turn = False

    def take_look(self) -> bool:
        """Spend the turn's ONE look: True the first time, False after it.

        ONE-SHOT on purpose: `consume()` runs once per agentic PASS, and a
        continuation pass carries either empty text or the refresh follow-up
        constant. Without the one-shot those passes would count as "a turn
        carrying no approval" and expire the pending state INSIDE the very turn
        that created it, so the approval could never arrive."""
        if self.observed_this_turn:
            return False
        self.observed_this_turn = True
        return True

    def approve(self) -> None:
        """The heard approval, marked on the ONE pending call and left in place."""
        self.pending = dataclasses.replace(self.pending, approved=True)

    def clear(self) -> None:
        """A refusal, or a turn that carried no approval: nothing is pending."""
        self.pending = None

    def released_by(self, fingerprint: str) -> bool:
        """Does an APPROVED pending cover exactly this call's fingerprint?"""
        pending = self.pending
        return pending is not None and pending.approved and pending.fingerprint == fingerprint

    def consume(self) -> None:
        """Spend a matched approval, and leave nothing outstanding."""
        self.pending = None      # SINGLE-USE: consumed the moment it matches
        self.missed = False      # nothing outstanding to explain any more
        self.spoken = None       # nothing outstanding to SAY either

    def place(self, fingerprint: str, tool: str) -> None:
        """(Re)place the ONE pending call — replaced, never queued."""
        self.pending = _Pending(fingerprint=fingerprint, tool=tool)

    def take_spoken(self) -> Optional[str]:
        """The kernel's approval request, handed over ONCE and cleared.

        ONE-SHOT, AND THAT IS THE WHOLE OF THE S3 CASE. A pass can carry several
        refusable calls; only the first is dispatched (`turn_pass.py`'s
        first-router-call-wins rule), but nothing stopped a future caller from
        looping. Clearing on hand-over makes "spoke twice for one pass"
        unrepresentable rather than merely unusual.

        IT IS NOT `pending_tool`-SHAPED AND MUST NOT BECOME SO: a pending state
        SURVIVES the utterance (it is what the next turn's approval matches), so
        a reader keyed on the pending would speak the same request every pass —
        DEC-131's loop, rebuilt on the other side of the mouth."""
        spoken, self.spoken = self.spoken, None
        return spoken


__all__ = ["GateState"]
