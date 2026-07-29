# src/muthis/broker/docs/chunking.py
"""
Structural chunking, sized in TOKENS (DEC-45).

THE ORDER IS THE DESIGN: heading → paragraph → fill to the cap, with a fixed
window only as a FALLBACK for a block that has no structure to follow. A
document's own boundaries are free, already correct, and produced by the author;
a window is a guess. Using the guess only where structure is ABSENT means the
guess never overrides a known answer.

SIZED IN TOKENS, NEVER IN CHARACTERS, and the reason survives P0's correction.
DEC-45 justified this by "Arabic emits far more tokens per character"; measured,
that factor is only ×1.11 (0.269–0.326 vs 0.295 for English), and the MIXED
technical document tokenizes worse than the pure-Arabic one — so the stated
reason was overstated and DEC-49 ruling 5 corrected it. **The RULE is unchanged
and must not be relaxed**: overflowing the encoder window is forbidden
regardless of ratio, and a 2 000-character chunk overflows a 512-token model in
EITHER language. The ratio was never what made the rule necessary.

THE GUARD FAILS THE OPERATION, IT DOES NOT WARN. A chunk over the window is
truncated by the encoder at its max sequence length: the tail is never indexed,
nothing complains, and the document LOOKS fully ingested. A warning on a path
that produces a silently incomplete index is a warning nobody reads before
trusting the answer. It raises INSIDE the broker; the plugin boundary turns it
into an Arabic note and never lets it reach the kernel (Law 11).

ATOMIC BLOCKS ARE NEVER SPLIT (DEC-45). Splitting a code block or a table
destroys BOTH retrievers at once, which no other content type does. One larger
than the window is carried WHOLE and flagged `truncated`, so the caller can
attach a note the user can see — explicitly handled, never silently cut.

THE TOKENIZER IS INJECTED, not imported. T1 builds the chunker against a
`count_tokens` callable; T2 supplies e5's own tokenizer (stub-first, and the law
that says a module must be importable in isolation — this file pulls in no model
and no ONNX runtime).
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Iterable

from .blocks import KIND_HEADING, Block, Chunk, ChunkReport

logger = logging.getLogger("muthis.broker.docs")

TokenCounter = Callable[[str], int]

# The roadmap states 400–700 tokens per chunk. P0 measured `multilingual-e5-small`
# at a 512-token MAXIMUM SEQUENCE LENGTH, so the top of that range CANNOT be
# encoded — a 700-token chunk is truncated at 512 and loses its tail silently.
# 400 sits inside both, which is why it is the default rather than the midpoint.
DEFAULT_WINDOW_TOKENS = 400
DEFAULT_OVERLAP_RATIO = 0.15          # the roadmap's figure, applied to tokens

# Overlap lands on SENTENCE boundaries: a cut mid-sentence reproduces, at small
# scale, the amputation small-to-big exists to prevent.
_SENTENCE_END = re.compile(r"(?<=[.!?؟۔])\s+|\n+")


class ChunkWindowExceeded(Exception):
    """A chunk exceeded the window AFTER tokenization — the operation FAILS.

    Deliberately not a warning: see the module docstring. Carries the offending
    size and the window so the caller's note can be specific rather than vague."""

    def __init__(self, n_tokens: int, window: int) -> None:
        super().__init__(f"chunk of {n_tokens} tokens exceeds the {window}-token window")
        self.n_tokens = n_tokens
        self.window = window


def _sentences(text: str) -> list[str]:
    return [s for s in (part.strip() for part in _SENTENCE_END.split(text)) if s]


class Chunker:
    """Structural chunking with a fixed-window fallback and a STRICT guard."""

    def __init__(self, count_tokens: TokenCounter, *,
                 window: int = DEFAULT_WINDOW_TOKENS,
                 overlap_ratio: float = DEFAULT_OVERLAP_RATIO) -> None:
        self._count = count_tokens
        self.window = window
        self.overlap = max(1, int(window * overlap_ratio))

    # -- the fixed-window FALLBACK -----------------------------------------
    def _word_split(self, text: str) -> list[str]:
        """Cut on WORD boundaries, never mid-word — the `speech_stream.py` soft
        valve's rule, reused because it solves the same problem.

        Reached when ONE SENTENCE alone exceeds the window. That is not a corner
        case in this corpus: Arabic prose runs long between full stops, and PDF
        extraction routinely yields a paragraph with no sentence ender at all, so
        a sentence-only splitter would hand the guard an over-window chunk and
        REFUSE a perfectly ordinary document.

        Terminates by construction: a word that alone exceeds the window is
        emitted alone rather than looped on, and the guard catches it — which is
        the correct division of labour, because no boundary can split a single
        token without cutting inside it."""
        out: list[str] = []
        current: list[str] = []
        for word in text.split():
            if current and self._count(" ".join(current + [word])) > self.window:
                out.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            out.append(" ".join(current))
        return out

    def _window_split(self, block: Block) -> list[Chunk]:
        """Cut an over-long unstructured block on SENTENCE boundaries.

        Reached only when a single block already exceeds the window, i.e. the
        document offered no smaller structure to follow."""
        out: list[Chunk] = []
        current: list[str] = []
        for sentence in _sentences(block.text):
            if self._count(sentence) > self.window:
                # One sentence bigger than the whole window: flush what is held,
                # then fall to the WORD boundary — one level down, still never
                # mid-word.
                if current:
                    out.append(self._make(" ".join(current), (block,)))
                    current = []
                out.extend(self._make(piece, (block,))
                           for piece in self._word_split(sentence))
                continue
            trial = " ".join(current + [sentence])
            if current and self._count(trial) > self.window:
                out.append(self._make(" ".join(current), (block,)))
                # Overlap: carry the last sentence forward when it fits the
                # budget, so a fact spanning the cut is present on both sides.
                tail = current[-1:] if self._count(current[-1]) <= self.overlap else []
                current = tail + [sentence]
            else:
                current.append(sentence)
        if current:
            out.append(self._make(" ".join(current), (block,)))
        return out

    def _make(self, text: str, blocks: tuple[Block, ...], *,
              truncated: bool = False) -> Chunk:
        return Chunk(text=text, n_tokens=self._count(text),
                     blocks=blocks, truncated=truncated)

    # -- the structural pass ------------------------------------------------
    def chunk(self, blocks: Iterable[Block]) -> tuple[list[Chunk], ChunkReport]:
        out: list[Chunk] = []
        pending: list[Block] = []
        truncated_atomic = 0
        windowed = 0

        def flush() -> None:
            nonlocal pending
            if not pending:
                return
            out.append(self._make("\n".join(b.text for b in pending), tuple(pending)))
            pending = []

        for block in blocks:
            size = self._count(block.text)

            if block.is_atomic:
                # NEVER split. Over the window it is carried WHOLE and flagged.
                flush()
                if size > self.window:
                    truncated_atomic += 1
                    logger.info(
                        "[doc_rag] atomic %s block at %s = %d tokens > window %d "
                        "— carried whole with a truncation note (DEC-45)",
                        block.kind, block.section or block.page, size, self.window)
                    out.append(self._make(block.text, (block,), truncated=True))
                else:
                    out.append(self._make(block.text, (block,)))
                continue

            if block.kind == KIND_HEADING:
                # A heading OPENS a chunk: it is the structural boundary the
                # whole design prefers, and it belongs WITH the text it titles.
                flush()
                pending = [block]
                continue

            if size > self.window:
                flush()
                pieces = self._window_split(block)
                windowed += len(pieces)
                out.extend(pieces)
                continue

            if pending and self._count(
                    "\n".join(b.text for b in pending + [block])) > self.window:
                flush()
            pending.append(block)

        flush()
        out = [c for c in out if c.text.strip()]

        # THE STRICT GUARD (DEC-45). An atomic chunk carrying its truncation flag
        # is the ONE documented exception — it was handled explicitly above.
        for chunk in out:
            if chunk.n_tokens > self.window and not chunk.truncated:
                raise ChunkWindowExceeded(chunk.n_tokens, self.window)

        report = ChunkReport(
            chunks=len(out), window_tokens=self.window,
            overlap_tokens=self.overlap, truncated_atomic=truncated_atomic,
            fallback_windowed=windowed,
        )
        logger.info("%s", report.describe())
        return out, report


__all__ = [
    "Chunker", "ChunkWindowExceeded", "DEFAULT_OVERLAP_RATIO",
    "DEFAULT_WINDOW_TOKENS", "TokenCounter",
]
