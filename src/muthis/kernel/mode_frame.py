# src/muthis/kernel/mode_frame.py
"""
`ModeFrame` — the kernel's frame for ONE active mode, extracted from
`session_mode.py` under the ≤300-line law (DEC-108 Gate 2C). A MOVE ONLY: the
class, its docstring and its fields are the originals, unchanged.

THE SEAM IS THE VALUE / SLOT SPLIT, and it is the one `router_registry.py`
already took: `MountedRoute` (the record) left `tool_router.py` and the dispatch
stayed. Here the record of WHAT A MODE IS leaves, and the ONE SLOT that holds it
— with the two clocks it stamps and the observer it fires — stays. They change
for different reasons: this file gains a field when the kernel learns a new fact
about a running mode; `session_mode.py` gains a line when the SLOT learns a new
verb.

WHY NOW, MEASURED RATHER THAN ESTIMATED. DEC-106's verification state is a fact
about a running mode, so it belongs to this record — and writing it took
`session_mode.py` to **309/300**: a field, a read property, a reset inside
`record_progress` and a stamp beside `record_activity`. The law's second clause
forbids buying that back by compression, so the seam was taken instead, ALONE
and BEFORE the machine, exactly as `deferral_notes.py`'s extraction was taken
before Gate 2C's notes.

RE-EXPORTED from `session_mode.py`, so no importer changed — the
`router_surfaces.py` precedent, and the dependency runs slot → record, so
nothing cycles.

Sibling `plan` import plus stdlib; importable in isolation.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .plan import Plan
# ONE name, and it is a CONSTANT rather than a capability: the verification
# state a mode starts in and returns to. `step_verification` imports nothing but
# the stdlib, so this record still cannot persist, log, grant or interpret.
from .step_verification import INITIAL_STATE


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
    # DEC-106's verification state, held HERE so invariant ④ — the machine dies
    # with its mode — is STRUCTURAL rather than a rule anyone keeps: `leave()`
    # empties the one slot and this goes with it, having no home of its own.
    verification: str = INITIAL_STATE


__all__ = ["ModeFrame"]
