# src/muthis/kernel/verbosity.py
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
import re
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


# ───────────────────── STT-tolerant command detection (B2) ─────────────────────
# Scribe's spellings vary (hamza forms, stray tashkeel, tatweel, Arabic-Indic
# digits), so every match runs on a normalized copy — the ORIGINAL transcript
# is never altered by detection.

_TASHKEEL_RE = re.compile(r"[ً-ْ]")          # fatha…sukun + shadda
_TATWEEL = "ـ"                                     # ـ (kashida stretching)
_PUNCT_RE = re.compile(r"[؟،؛!?.,:;\"'()\[\]{}«»]")
# Arabic-Indic (٠-٩) and Eastern Arabic-Indic (۰-۹) digits → ASCII.
_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# Explicit phrases match ANYWHERE in the utterance (substring on the normalized
# text, so a clitic like "وباختصار" still hits). Reset phrases come FIRST so
# "رجّع طولك الطبيعي" can never be shadowed. Order inside the tuple = priority.
_ANYWHERE_PHRASES: tuple[tuple[str, str], ...] = (
    ("طولك الطبيعي", NORMAL),        # "رجّع طولك الطبيعي" and friends
    ("رجع للوضع الطبيعي", NORMAL),
    ("بالتفصيل", DETAILED),
    ("اشرح اكثر", DETAILED),
    ("وضح اكثر", DETAILED),
    ("باختصار", SHORT),
    ("بايجاز", SHORT),               # normalized from "بإيجاز"
)

# Ambiguous single words trigger ONLY as a (near-)standalone utterance — the
# approved false-positive guard: "أي ضلع أطول؟" must never flip the state.
_STANDALONE_WORDS: dict[str, str] = {
    "اختصر": SHORT,                  # "اختصر لي هذا النص" is a TASK, not a mode
    "اطول": DETAILED,                # normalized from "أطول"
    "طول": DETAILED,                 # normalized from "طوّل"
}

# EXACT_N: "بخمس كلمات" / "ب5 كلمات" / "ب٥ كلمات" (digits normalized) — the ب
# prefix + a count + كلمات/كلمه. Duals/singulars get their own fixed patterns.
_NUMBER_WORDS: dict[str, int] = {
    "ثلاث": 3, "ثلاثه": 3, "اربع": 4, "اربعه": 4, "خمس": 5, "خمسه": 5,
    "ست": 6, "سته": 6, "سبع": 7, "سبعه": 7, "ثمان": 8, "ثماني": 8,
    "ثمانيه": 8, "تسع": 9, "تسعه": 9, "عشر": 10, "عشره": 10,
}
_EXACT_RE = re.compile(
    r"\bب(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")\s+كلم(?:ه|ات)\b")
_EXACT_TWO_RE = re.compile(r"\bبكلمتين\b")
_EXACT_ONE_RE = re.compile(r"\bبكلمه (?:وحده|واحده)\b")
_EXACT_N_CAP = 20                    # beyond this the request is noise, not a mode


def normalize_ar(text: str) -> str:
    """A matching-only copy: strip tashkeel + tatweel, unify hamza-alif forms
    (أ/إ/آ → ا) and ة → ه, map Arabic-Indic digits to ASCII, drop punctuation,
    collapse whitespace. NEVER applied to the transcript that reaches Claude."""
    text = _TASHKEEL_RE.sub("", text).replace(_TATWEEL, "")
    text = text.translate(_DIGIT_MAP)
    for hamza_alif in "أإآ":
        text = text.replace(hamza_alif, "ا")
    text = text.replace("ة", "ه")
    text = _PUNCT_RE.sub(" ", text)
    return " ".join(text.split())


def detect_command(text: str) -> Optional[tuple[str, Optional[int]]]:
    """The verbosity command in `text`, as (level, exact_n) — None when the
    utterance carries none. Priority: EXACT_N (most specific) → the anywhere
    phrases (reset first) → the standalone-only ambiguous words."""
    norm = normalize_ar(text)
    if not norm:
        return None

    match = _EXACT_RE.search(norm)
    if match:
        token = match.group(1)
        count = int(token) if token.isdigit() else _NUMBER_WORDS[token]
        if 1 <= count <= _EXACT_N_CAP:
            return (EXACT, count)
    if _EXACT_TWO_RE.search(norm):
        return (EXACT, 2)
    if _EXACT_ONE_RE.search(norm):
        return (EXACT, 1)

    for phrase, level in _ANYWHERE_PHRASES:
        if phrase in norm:
            return (level, None)

    standalone = _STANDALONE_WORDS.get(norm)  # the WHOLE utterance is the word
    if standalone is not None:
        return (standalone, None)
    return None


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

    def begin_turn(self, user_text: str) -> str:
        """The orchestrator's single per-utterance entry: detect a verbosity
        command in the RAW transcript (STT-tolerant), update the state, then
        return the transcript with the CURRENT directive attached. A pure
        command ("اختصر" alone) still flows to Claude with its directive —
        the approved v1 behavior (no local short-circuit)."""
        detected = detect_command(user_text)
        if detected is not None:
            level, exact_n = detected
            logger.info("[verbosity] voice command → %s%s", level,
                        f"({exact_n})" if exact_n else "")
            self.set_level(level, exact_n)
        return self.attach(user_text)


__all__ = [
    "VerbosityController", "detect_command", "normalize_ar",
    "NORMAL", "SHORT", "DETAILED", "EXACT", "VALID_LEVELS",
    "DIRECTIVE_OPEN_AR",
]
