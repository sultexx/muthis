# src/muthis_plugins/sandbox_exec/sandbox_gate.py
"""SandboxGate — the per-user-turn run limiter for sandbox.run_code (DEC-3-B).

Built on the HighlightGate PATTERN (a per-turn control object + an Arabic
internal-directive refusal surface), but a SEPARATE object in a SEPARATE
domain: it never imports or shares HighlightGate, and it lives here in the
plugin package, NEVER in the sealed kernel. Two gates, two objects — DEC-3-B is
explicit.

The gate ONLY bounds runs (≤3 per turn); it owns NO loop and NO lifecycle
(Law 11). The self-correction loop IS the existing agentic loop (`can_afford`
before each pass, unchanged); this gate merely refuses the 4th run so a broken
snippet cannot spin to the budget cap. State is per-turn and resets BY
CONSTRUCTION — a fresh gate each turn (or `reset()`) starts a clean 3-run
budget, exactly like HighlightGate. Pure stdlib; importable in isolation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

MAX_SANDBOX_RUNS = 3

# The refusal for the 4th run — an INTERNAL directive (the «توجيه داخلي» family
# the persona obeys and never reads aloud), carrying Sultan's §2.5 framing: stop
# retrying and hand the user the last error with the best suggested fix.
SANDBOX_GATE_EXHAUSTED_AR = (
    "توجيه داخلي (لا يراه المستخدم): شغّلتَ الكود ثلاث مرّات في هذه الجولة، وهذا "
    "هو الحدّ الأقصى — لا تُشغّله مرّة رابعة. توقّف عن المحاولة وقدّم للمستخدم آخر "
    "خطأ ظهر مع أفضل اقتراح لديك لإصلاحه، بروح «جرّبتُ ثلاث مرات — هذا آخر خطأ "
    "وهذا ما أقترحه»."
)


@dataclass
class SandboxGate:
    """Per-user-turn sandbox run counter. `runs` is the loop's control state
    (distinct from a run's RESULT), mirroring HighlightGate.drawn — its own
    field on its own object, never HighlightGate's."""

    runs: int = 0

    def consume(self) -> Optional[str]:
        """Call BEFORE servicing a run_code call. Returns None when the run is
        allowed (and counts it); returns the Arabic refusal directive — WITHOUT
        counting — once the ≤3 per-turn cap is spent."""
        if self.runs >= MAX_SANDBOX_RUNS:
            return SANDBOX_GATE_EXHAUSTED_AR
        self.runs += 1
        return None

    def runs_remaining(self) -> int:
        return max(0, MAX_SANDBOX_RUNS - self.runs)

    def reset(self) -> None:
        """Start a fresh per-turn budget (the caller may also just build a new
        gate — the by-construction reset, like HighlightGate)."""
        self.runs = 0


__all__ = ["SandboxGate", "MAX_SANDBOX_RUNS", "SANDBOX_GATE_EXHAUSTED_AR"]
