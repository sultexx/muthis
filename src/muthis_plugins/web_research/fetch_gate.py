# src/muthis_plugins/web_research/fetch_gate.py
"""FetchGate — the per-user-turn fetch limiter for web__fetch (DEC-22).

WHY THIS EXISTS, precisely. DEC-22 gave the fetcher ONE total wall-clock budget
so a tainted slow redirect chain cannot starve the 90 s turn. But it recorded an
HONEST LIMIT that the budget cannot close: `getaddrinfo` cannot be truly
cancelled, so when the budget cuts a fetch the resolver thread keeps running in
the background until the OS resolver gives up. The turn is freed; the thread is
not. Under sustained attack those detached threads could accumulate, and DEC-22
named the STRUCTURAL bound explicitly — a per-turn fetch cap in this plugin,
NOT in the fetcher. Bounding fetches per turn bounds the threads per turn.

THE GATE LIVES IN THE PLUGIN DOMAIN, never the sealed kernel — the SandboxGate
pattern (DEC-3-B) followed to the letter: a SEPARATE object that shares no
instance and no module with HighlightGate or SandboxGate, owning no loop and no
lifecycle (Law 11). It only counts.

LIVE since T6b's wiring commit (DEC-37): the composition root registers
`WebResearchPlugin.new_turn` — which resets this gate — as one of the router's
opaque `turn_hooks`, and `TurnPass.new_turn_voice` fires them at the SAME
turn boundary the sandbox gate already used (DEC-19 forbids inventing a second).
The cap is therefore per USER TURN, as DEC-22 requires. The gate was deliberately
made live BEFORE the tool it bounds became model-visible, never the other way
round. State also resets BY CONSTRUCTION — a fresh gate is a clean budget.

Pure stdlib; importable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Three, chosen from the turn's own arithmetic rather than by feel: each fetch is
# bounded by DEC-22's 10 s TOTAL budget, so three worst-case fetches spend ~30 s
# of a 90 s turn and still leave room for the passes that must speak afterwards.
# It also matches the shape of a real teaching turn — search, read the best one
# or two sources, explain — with one spare for a dead link. Revisable BY
# MEASUREMENT at T7 (the DEC-17/DEC-22 posture: a limit value is Sultan's, and it
# is revised from a real run, never from a guess).
MAX_FETCHES_PER_TURN = 3

# The refusal for the 4th fetch — an INTERNAL directive (the «توجيه داخلي» family
# the persona obeys and never reads aloud). It tells the model to STOP opening
# pages and teach from what it already has, because the alternative failure — a
# model that keeps fetching until the agentic cap — spends the user's budget and
# ends the turn with nothing said.
FETCH_GATE_EXHAUSTED_AR = (
    "توجيه داخلي (لا يراه المستخدم): فتحتَ ثلاث صفحات في هذه الجولة، وهذا هو "
    "الحدّ الأقصى — لا تفتح صفحة رابعة. اشرح للمستخدم من المصادر التي قرأتها "
    "فعلًا، واذكر اسم المصدر، وإن نقصك شيء فاطلب منه أن يفتح الصفحة على شاشته "
    "لتقرأها معه."
)


@dataclass
class FetchGate:
    """Per-user-turn fetch counter. `fetches` is the loop's control state — its
    own field on its own object, mirroring `SandboxGate.runs` and deliberately
    never `HighlightGate.drawn`: two concerns, two objects (DEC-3-B)."""

    fetches: int = 0

    def consume(self) -> Optional[str]:
        """Call BEFORE performing a fetch. Returns None when the fetch is
        allowed (and counts it); returns the Arabic refusal directive — WITHOUT
        counting — once the per-turn cap is spent. Counting only on the allowed
        path is what makes the refusal stable: a model that keeps asking gets
        the same note rather than driving a counter to infinity."""
        if self.fetches >= MAX_FETCHES_PER_TURN:
            return FETCH_GATE_EXHAUSTED_AR
        self.fetches += 1
        return None

    def fetches_remaining(self) -> int:
        return max(0, MAX_FETCHES_PER_TURN - self.fetches)

    def new_turn(self) -> None:
        """Start a fresh per-turn budget. Named for the hook that will call it
        (`TurnPass.new_turn_voice`, T6b) so the wiring reads as one thing."""
        self.fetches = 0


__all__ = ["FetchGate", "MAX_FETCHES_PER_TURN", "FETCH_GATE_EXHAUSTED_AR"]
