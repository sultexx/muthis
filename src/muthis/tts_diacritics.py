# src/muthis/tts_diacritics.py
"""
tts_diacritics — speech-only Arabic diacritization for مطحس's TTS layer.

WHY THIS EXISTS (bug 3): ElevenLabs (and Arabic TTS in general) mispronounces a
handful of unvowelized Saudi-persona words — أبشر، سم، طال عمرك — because the
Arabic script omits short vowels. Adding the right harakat (tashkeel) on a COPY
of the text right before it reaches the engine fixes the SPOKEN pronunciation.

HARD ARCHITECTURE RULE — speech-only, NEVER in history:
  These diacritics are applied ONLY here, in the TTS path (tts.py's speak()
  choke point), to a COPY. They are NEVER added in persona.py and NEVER stored
  in conversation history. Claude must keep WRITING — and the orchestrator must
  keep STORING — clean unvowelized Arabic, because feeding vowelized text back
  into history would corrupt the model's reasoning: it would start imitating the
  tashkeel or be distracted by it on later turns. Diacritics are a disposable
  pronunciation hint for the "tongue", not part of what مطحس actually said.

SUBSTRING-SAFETY (the سم trap):
  A naive str.replace("سم", ...) would corrupt اسم / قسم / جسم / موسم. So every
  key is matched ONLY as a whole Arabic word/phrase: the match must not be glued
  to another Arabic letter on either side (negative look-around on the Arabic
  letter class). Keys are tried longest-first so a multi-word phrase wins over
  any single word nested inside it.

EXTENDING THE MAP: add a clean-form → vowelized-form pair to _DIACRITICS_MAP.
That is the only change needed; the matcher rebuilds itself from the data.

This module imports only stdlib (logging, re), so it stays importable in
isolation and its test needs no audio/network stack.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("tts.diacritics")

# Clean (unvowelized) Saudi-persona word/phrase  →  vowelized form for SPEECH.
# Data, not scattered code: extend by adding a pair here. Keep KEYS clean so they
# match the unvowelized text Claude actually writes; put the harakat in VALUES.
_DIACRITICS_MAP: dict[str, str] = {
    "أبشر": "أَبْشِر",
    "سم": "سِمّ",
    "طال عمرك": "طال عُمرك",
}

# Arabic base-letter class used for whole-word boundaries. A key fires only when
# it is NOT preceded or followed by another Arabic letter, so short keys like
# "سم" never trigger inside اسم / قسم / جسم / موسم.
_ARABIC_LETTER = r"ء-ي"


def _build_pattern(keys: list[str]) -> re.Pattern[str] | None:
    """Compile ONE whole-word alternation of the map keys, longest-first so a
    multi-word phrase wins over any single word nested inside it. Returns None
    for an empty key set (empty map → apply_diacritics is a no-op pass-through)."""
    if not keys:
        return None
    ordered = sorted(keys, key=len, reverse=True)
    alternation = "|".join(re.escape(k) for k in ordered)
    return re.compile(
        rf"(?<![{_ARABIC_LETTER}])(?:{alternation})(?![{_ARABIC_LETTER}])"
    )


_PATTERN = _build_pattern(list(_DIACRITICS_MAP))


def apply_diacritics(text: str) -> str:
    """Return a COPY of `text` with key Saudi-persona words diacritized for
    speech. Pure and side-effect-free; the input string is never mutated.

    SPEECH-ONLY — never feed the result back into persona.py or conversation
    history (see module docstring). Whole-word matching guarantees short keys
    like "سم" never corrupt larger words (اسم / قسم / جسم / موسم)."""
    if not text or _PATTERN is None:
        return text
    return _PATTERN.sub(lambda m: _DIACRITICS_MAP[m.group(0)], text)


__all__ = ["apply_diacritics"]
