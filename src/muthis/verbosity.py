# src/muthis/verbosity.py
"""
Verbosity — voice-controlled reply-length state for مطحس (v5 Phase B).

WHY a user-message directive and NOT the system prompt (option A, decided
2026-07-13): the persona system prompt is resolved ONCE at the composition
root and frozen into ClaudeAgent's constructor — the orchestrator has no path
to it, by documented design (persona.py). So the verbosity signal rides the
one surface the orchestrator fully owns: the user message. Each turn that has
an active mode gets ONE Arabic internal directive prepended to the transcript
(the same internal-directive philosophy as highlight_gate's tool_result ACKs);
persona.py carries the matching obedience rule (execute it, never read it
aloud). claude_agent.py / protocol.py stay untouched.

States and lifetime (decided 2026-07-13):
  * NORMAL   — no directive at all (the persona's own soft cap governs).
  * SHORT    — sticky: persists across turns until another command or the
               reset phrase returns it to NORMAL.
  * DETAILED — sticky, exactly like SHORT.
  * EXACT    — one-shot, carries N: applies to the WHOLE utterance it was
               spoken in (ALL agentic passes — point → explain), then decays
               to NORMAL at `end_turn()`. Decaying any earlier would strip the
               directive before the tool_choice="none" explain pass.

State is in-memory only: every app launch starts at NORMAL. The model does not
count words reliably — an EXACT directive is an approximation nudge, and the
acceptance bar is "the right directive reaches the prompt", never a word count
of a real reply (plan_v5 B3 honesty note).

Pure stdlib, importable in isolation. The orchestrator holds ONE controller
across turns (injected with a real default, like its other seams).
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("muthis.verbosity")

# The four levels. EXACT additionally carries `exact_n`.
NORMAL = "normal"
SHORT = "short"
DETAILED = "detailed"
EXACT = "exact"
VALID_LEVELS = (NORMAL, SHORT, DETAILED, EXACT)

# The internal-directive opener — persona.py orders the model to OBEY any
# user-message line that starts with this and never read it aloud. Keep the
# wording in ONE place so persona/tests reference the same marker.
DIRECTIVE_OPEN_AR = "(توجيه داخلي — لا يراه المستخدم:"

_SHORT_DIRECTIVE_AR = (
    f"{DIRECTIVE_OPEN_AR} وضع الإيجاز مفعّل بطلب المستخدم — جاوب بأقصر صيغة "
    "مفيدة، جملة أو جملتين كحد أقصى، بلا استطراد وبلا عرض للتوسّع.)"
)

_DETAILED_DIRECTIVE_AR = (
    f"{DIRECTIVE_OPEN_AR} المستخدم طلب التفصيل — تجاوز حدّ الإيجاز المعتاد في "
    "هذا الدور وفصّل الشرح بما يخدم الموضوع، مع ترتيب واضح للنقاط.)"
)

_EXACT_DIRECTIVE_AR_TEMPLATE = (
    f"{DIRECTIVE_OPEN_AR} المستخدم طلب الرد بنحو {{n}} كلمات فقط — التزم بهذا "
    "الطول تقريبًا قدر الإمكان.)"
)


class VerbosityController:
    """Cross-turn verbosity state + the per-turn Arabic directive.

    Held by the Orchestrator for the whole session (NOT rebuilt per turn —
    unlike HighlightGate — because sticky modes must survive turns)."""

    def __init__(self) -> None:
        self._level = NORMAL
        self._exact_n: Optional[int] = None

    # ─────────────────────────────── State ───────────────────────────────

    @property
    def level(self) -> str:
        return self._level

    @property
    def exact_n(self) -> Optional[int]:
        return self._exact_n

    def set_level(self, level: str, exact_n: Optional[int] = None) -> None:
        """Explicit state change (the B2 detector routes through here). An
        unknown level, or EXACT without a usable N, is a logged no-op — bad
        input must never corrupt the running state."""
        if level not in VALID_LEVELS:
            logger.warning("[verbosity] unknown level %r — ignored", level)
            return
        if level == EXACT and (exact_n is None or exact_n < 1):
            logger.warning("[verbosity] EXACT without a valid N (%r) — ignored", exact_n)
            return
        self._level = level
        self._exact_n = exact_n if level == EXACT else None

    def end_turn(self) -> None:
        """Decay at the end of ONE WHOLE utterance (all agentic passes):
        EXACT is one-shot → back to NORMAL; sticky SHORT/DETAILED persist."""
        if self._level == EXACT:
            self._level = NORMAL
            self._exact_n = None

    # ───────────────────────────── Directive ─────────────────────────────

    def directive(self) -> str:
        """The Arabic internal directive for the CURRENT state — "" on NORMAL
        (no directive means the persona's own verbosity policy governs)."""
        if self._level == SHORT:
            return _SHORT_DIRECTIVE_AR
        if self._level == DETAILED:
            return _DETAILED_DIRECTIVE_AR
        if self._level == EXACT:
            return _EXACT_DIRECTIVE_AR_TEMPLATE.format(n=self._exact_n)
        return ""

    def attach(self, user_text: str) -> str:
        """Prepend the current directive to the transcript (unchanged text on
        NORMAL). Called ONCE per utterance by the orchestrator — never on the
        agentic loop's empty continuations or the refresh follow-up."""
        directive = self.directive()
        return f"{directive}\n{user_text}" if directive else user_text


__all__ = [
    "VerbosityController",
    "NORMAL", "SHORT", "DETAILED", "EXACT", "VALID_LEVELS",
    "DIRECTIVE_OPEN_AR",
]
