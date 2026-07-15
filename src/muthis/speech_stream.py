# src/muthis/speech_stream.py
"""
SentenceSplitter — Arabic sentence boundaries over streamed text (v5 Phase C1).

Feeds on the raw `TextDelta` fragments of ONE provider pass and emits COMPLETE
sentences, in order, the instant their boundary arrives — the unit Phase C2
hands to the persistent TTS session. Boundaries are the Arabic sentence enders
(`.` `؟` `!` `؛`) plus the newline; a safety valve flushes an unpunctuated run
at ~200 chars so a long Arabic sentence with no punctuation is never held
forever.

DECIMAL GUARD (approved fix): a dot BETWEEN digits ("3.14") is not a boundary.
Because the text streams, a dot that lands at the very END of the buffer right
after a digit is HELD — the next fragment may open with another digit — and is
resolved the moment the following character arrives (or at flush()).

Pure stdlib, importable in isolation. This module only SEGMENTS text: it knows
nothing of TTS, sync, or the orchestrator (the C2 branch owns the feeding).
"""

from __future__ import annotations

from typing import List, Optional

# The Arabic sentence enders (plan C1) + newline. The ender stays attached to
# its sentence — better TTS prosody than stripping it.
SENTENCE_ENDERS = frozenset({".", "؟", "!", "؛", "\n"})

# Safety valve: an unpunctuated run this long is emitted as-is rather than
# held until end-of-stream (spoken Arabic often under-punctuates).
MAX_BUFFER_CHARS = 200


class SentenceSplitter:
    """Stateful splitter for ONE pass: push() fragments in, sentences out."""

    def __init__(self, max_buffer_chars: int = MAX_BUFFER_CHARS) -> None:
        self._buffer = ""
        self._max = max_buffer_chars

    def push(self, fragment: str) -> List[str]:
        """Feed one streamed fragment; return the sentences it COMPLETED (often
        none), in order. Never cuts inside a sentence or a decimal number."""
        self._buffer += fragment
        return self._drain()

    def flush(self) -> List[str]:
        """End of stream: whatever remains (a held decimal dot included) is the
        final sentence. Resets the splitter for reuse."""
        tail = self._buffer.strip()
        self._buffer = ""
        return [tail] if tail and _speakable(tail) else []

    # ─────────────────────────────── Internals ───────────────────────────────

    def _drain(self) -> List[str]:
        sentences: List[str] = []
        while True:
            cut = self._boundary_index()
            if cut is None:
                if len(self._buffer) >= self._max:
                    # The valve: emit the whole unpunctuated run as one sentence.
                    run = self._buffer.strip()
                    self._buffer = ""
                    if run and _speakable(run):
                        sentences.append(run)
                break
            sentence = self._buffer[:cut + 1].strip()
            self._buffer = self._buffer[cut + 1:]
            if sentence and _speakable(sentence):
                sentences.append(sentence)
        return sentences

    def _boundary_index(self) -> Optional[int]:
        """Index of the first REAL sentence ender in the buffer, or None. A dot
        between digits is skipped; a dot at buffer END after a digit is HELD
        (the next fragment may continue the number)."""
        for index, char in enumerate(self._buffer):
            if char not in SENTENCE_ENDERS:
                continue
            if char == "." and index > 0 and self._buffer[index - 1].isdigit():
                if index + 1 >= len(self._buffer):
                    return None                      # held: "…3." awaiting context
                if self._buffer[index + 1].isdigit():
                    continue                         # inside a number: "3.14"
            return index
        return None


def _speakable(sentence: str) -> bool:
    """False for punctuation-only scraps (a lone "!" must never reach TTS)."""
    return any(char not in SENTENCE_ENDERS and not char.isspace()
               for char in sentence)


__all__ = ["SentenceSplitter", "SENTENCE_ENDERS", "MAX_BUFFER_CHARS"]
