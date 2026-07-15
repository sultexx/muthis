# src/muthis/speech_stream.py
"""
SentenceSplitter — Arabic sentence boundaries over streamed text (v5 Phase C1,
v7 soft-boundary revision).

Feeds on the raw `TextDelta` fragments of ONE provider pass and emits COMPLETE
sentences, in order, the instant their boundary arrives — the unit the TTS
generation is fed. Boundaries are the Arabic sentence enders (`.` `؟` `!` `؛`)
plus the newline; a safety valve frees an unpunctuated run at ~200 chars.

v7.2 EAGER FIRST EMISSION (measured starvation fix): the FIRST emission of a
pass may cut at a comma (`،`/`,`) once ≥ EAGER_FIRST_MIN_CHARS, instead of
waiting out the whole first sentence — the explanation's audio starts at the
first natural pause, shrinking the post-ack dead air. Later emissions keep
full-sentence boundaries; flush() re-arms the eager window for the next pass.

v7 SOFT BOUNDARIES (measured fixes — diag 2026-07-15):
  * MIN-LENGTH MERGE: a boundary whose sentence would be shorter than
    ~MIN_SENTENCE_CHARS does not cut — the short piece merges into the NEXT
    sentence (kills the standalone "١." list-numeral scrap and micro-chunks).
  * ELLIPSIS RUN: consecutive dots are ONE ender — the cut lands after the
    LAST dot, never inside the run (a run touching the buffer end is HELD:
    the stream may still be growing it).
  * SOFT VALVE: the ~200-char overflow now cuts at the LAST whitespace or
    comma (`،`/`,`) instead of the arbitrary stream-fragment edge that was
    measured cutting MID-WORD; the remainder stays buffered.

DECIMAL GUARD (unchanged): a dot BETWEEN digits ("3.14") is not a boundary; a
dot at buffer END right after a digit is HELD until context arrives (flush()
releases it).

Punctuation-only scraps never come out (a lone "!" must not reach TTS). Pure
stdlib, importable in isolation. This module only SEGMENTS text: it knows
nothing of TTS, sync, or the orchestrator (turn_voice.py owns the feeding).
"""

from __future__ import annotations

from typing import List, Optional

# The Arabic sentence enders (plan C1) + newline. The ender stays attached to
# its sentence — better TTS prosody than stripping it.
SENTENCE_ENDERS = frozenset({".", "؟", "!", "؛", "\n"})

# Safety valve: an unpunctuated run this long is emitted rather than held
# until end-of-stream (spoken Arabic often under-punctuates).
MAX_BUFFER_CHARS = 200

# v7: a completed sentence shorter than this merges into the next one — short
# scraps ("١.", a two-word burst) make bad TTS/caption units on their own.
MIN_SENTENCE_CHARS = 20

# v7: where the safety valve is allowed to cut — natural breath points only.
SOFT_CUT_CHARS = (" ", "\t", "،", ",")

# v7.2 (measured starvation fix): the FIRST emission of a pass may cut EARLY
# at a comma once this long, instead of waiting out the whole first sentence —
# time-to-first-audio drops by the rest of that sentence, and a comma is a
# natural prosodic pause. Commas ONLY (never a bare space): a mid-clause cut
# would put an audible boundary where speech has none.
EAGER_FIRST_MIN_CHARS = 30
EAGER_CUT_CHARS = ("،", ",")


class SentenceSplitter:
    """Stateful splitter for ONE pass: push() fragments in, sentences out."""

    def __init__(
        self,
        max_buffer_chars: int = MAX_BUFFER_CHARS,
        min_sentence_chars: int = MIN_SENTENCE_CHARS,
    ) -> None:
        self._buffer = ""
        self._max = max_buffer_chars
        self._min = min_sentence_chars
        # v7.2: the NEXT emission is a pass's first → it may cut early at a
        # comma (time-to-first-audio). Re-armed by flush() for the next pass.
        self._eager_first = True

    def push(self, fragment: str) -> List[str]:
        """Feed one streamed fragment; return the sentences it COMPLETED (often
        none), in order. Never cuts inside a sentence, a decimal number, an
        ellipsis run, or (v7) a word."""
        self._buffer += fragment
        return self._drain()

    def flush(self) -> List[str]:
        """End of stream: whatever remains (a held decimal dot / a short tail
        awaiting a merge included) is the final sentence. Resets for reuse —
        including the eager-first window for the NEXT pass."""
        tail = self._buffer.strip()
        self._buffer = ""
        self._eager_first = True
        return [tail] if tail and _speakable(tail) else []

    # ─────────────────────────────── Internals ───────────────────────────────

    def _drain(self) -> List[str]:
        sentences: List[str] = []
        while True:
            cut = self._next_cut()
            if self._eager_first:
                eager = self._eager_comma_index()
                if eager is not None and (cut is None or eager < cut):
                    cut = eager                  # first audio: cut at the comma
            if cut is None:
                if len(self._buffer) >= self._max:
                    run = self._soft_valve_cut()
                    if run and _speakable(run):
                        sentences.append(run)
                        self._eager_first = False
                    continue                     # the remainder may still overflow
                break
            sentence = self._buffer[:cut + 1].strip()
            self._buffer = self._buffer[cut + 1:]
            if sentence and _speakable(sentence):
                sentences.append(sentence)
                self._eager_first = False        # only the FIRST emission is eager
        return sentences

    def _next_cut(self) -> Optional[int]:
        """Index of the first boundary that yields a LONG-ENOUGH sentence.
        A boundary whose sentence would be too short is skipped — the piece
        merges into the next sentence (punctuation-only scraps still cut, so
        they can be dropped rather than glued onto real speech)."""
        search_from = 0
        while True:
            cut = self._boundary_index(search_from)
            if cut is None:
                return None
            candidate = self._buffer[:cut + 1].strip()
            if not _speakable(candidate) or len(candidate) >= self._min:
                return cut
            search_from = cut + 1                # too short: merge forward


    def _boundary_index(self, start: int = 0) -> Optional[int]:
        """Index of the first REAL sentence ender at/after `start`, or None.
        A dot between digits is skipped; a dot at buffer END after a digit is
        HELD (the next fragment may continue the number); consecutive dots are
        ONE ender ending at the LAST dot — held while they touch the end."""
        for index in range(start, len(self._buffer)):
            char = self._buffer[index]
            if char not in SENTENCE_ENDERS:
                continue
            if char == ".":
                if index > 0 and self._buffer[index - 1].isdigit():
                    if index + 1 >= len(self._buffer):
                        return None              # held: "…3." awaiting context
                    if self._buffer[index + 1].isdigit():
                        continue                 # inside a number: "3.14"
                run_end = index
                while (run_end + 1 < len(self._buffer)
                       and self._buffer[run_end + 1] == "."):
                    run_end += 1                 # "..." is ONE ender
                if run_end > index and run_end == len(self._buffer) - 1:
                    return None                  # held: the run may still grow
                return run_end
            return index
        return None

    def _eager_comma_index(self) -> Optional[int]:
        """v7.2: the first comma at/after EAGER_FIRST_MIN_CHARS, or None. Used
        ONLY for a pass's first emission, so the explanation's audio starts at
        the first natural pause instead of after the whole first sentence.
        Digit-guarded like the decimal dot: "1,250" never splits, and a comma
        at buffer END after a digit is held until context arrives."""
        for index in range(EAGER_FIRST_MIN_CHARS - 1, len(self._buffer)):
            if self._buffer[index] not in EAGER_CUT_CHARS:
                continue
            if index > 0 and self._buffer[index - 1].isdigit():
                if index + 1 >= len(self._buffer):
                    return None                  # held: "…1," awaiting context
                if self._buffer[index + 1].isdigit():
                    continue                     # thousands separator: "1,250"
            return index
        return None

    def _soft_valve_cut(self) -> str:
        """Overflow: emit up to the LAST soft point (space/comma) inside the
        window — never mid-word — keeping the remainder buffered. An unbroken
        run with no soft point falls back to the old hard cut at the window."""
        window = self._buffer[:self._max]
        soft = max(window.rfind(mark) for mark in SOFT_CUT_CHARS)
        if soft < self._min:                     # degenerate: one unbroken token
            soft = self._max - 1
        emitted = self._buffer[:soft + 1].strip()
        self._buffer = self._buffer[soft + 1:]
        return emitted


def _speakable(sentence: str) -> bool:
    """False for punctuation-only scraps (a lone "!" must never reach TTS)."""
    return any(char not in SENTENCE_ENDERS and not char.isspace()
               for char in sentence)


__all__ = ["SentenceSplitter", "SENTENCE_ENDERS", "MAX_BUFFER_CHARS",
           "MIN_SENTENCE_CHARS", "SOFT_CUT_CHARS",
           "EAGER_FIRST_MIN_CHARS", "EAGER_CUT_CHARS"]
