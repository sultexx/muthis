# src/muthis/broker/docs/blocks.py
"""
The position-carrying records of the ingestion path: `Block` (what a parser
yielded) and `Chunk` (what the chunker made of them), plus the reports each
stage returns.

WHY POSITION IS CAPTURED HERE AND NOW, while nothing reads it (DEC-45): the
parser yields page and paragraph FREE at ingestion, and it is UNRECOVERABLE
afterwards without a full re-index. It stays INERT until the Phase-3 visual
citation — the roadmap's stated differentiator — so the asymmetry decides it:
carrying it costs a field, and not carrying it costs the entire ingestion budget
again, on the one feature that needs it most.

WHY THE REPORTS CARRY A CUTOFF AND AN ADMITTED COUNT (standing rule, AGENTS.md,
from the doc_rag P0 gate): every stage here filters — a y-gap groups lines into
paragraphs, a window bounds a chunk, a length floor drops noise. A filter INSIDE
a check can silently exclude the check's own subject, and the stage then reports
success having examined nothing. It happened twice in one gate. So each stage
states which cutoff it used and how many cases it admitted, and **zero admitted
is a FAILURE, never a pass**.

Pure stdlib, importable in isolation.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

# Block kinds. `code` and `table` are ATOMIC by DEC-45: splitting one destroys
# BOTH retrievers at once — half a table loses the header row that gives every
# cell meaning, half a code block loses the identifiers that were the exact-match
# signal. No other kind has that property, which is why only these two are named.
KIND_TEXT = "text"
KIND_HEADING = "heading"
KIND_CODE = "code"
KIND_TABLE = "table"
ATOMIC_KINDS = frozenset({KIND_CODE, KIND_TABLE})


@dataclasses.dataclass(frozen=True)
class Block:
    """ONE structural unit exactly as the parser yielded it, with its LOCATION.

    `page` is 1-based and None for formats that have no pages (Markdown, TXT) —
    None is the honest answer there, not a zero that would read as "page zero".
    `para` is the paragraph's index WITHIN its page (paginated) or within the
    document (not paginated), so the pair is always a real address.

    `section` carries the heading number for structured text ("1.1") and is ""
    elsewhere; it is what makes a Markdown chunk addressable at all, since it has
    no page to name.
    """

    text: str
    page: Optional[int] = None
    para: int = 0
    kind: str = KIND_TEXT
    section: str = ""

    @property
    def is_atomic(self) -> bool:
        return self.kind in ATOMIC_KINDS


@dataclasses.dataclass(frozen=True)
class Chunk:
    """One indexable unit: the text, its token size, and where it came from.

    `blocks` is kept rather than discarded because small-to-big (DEC-45) returns
    the PARENT, and the parent is derived from the blocks a chunk was built from
    — so throwing them away here would cost a second pass later.

    `truncated` marks the ONE case DEC-45 handles explicitly instead of silently:
    an atomic block bigger than the window. It is never split; it is carried with
    this flag so the caller can attach a truncation note the user can see.
    """

    text: str
    n_tokens: int
    blocks: tuple[Block, ...]
    truncated: bool = False

    @property
    def page(self) -> Optional[int]:
        return self.blocks[0].page if self.blocks else None

    @property
    def para(self) -> int:
        return self.blocks[0].para if self.blocks else 0

    @property
    def section(self) -> str:
        return self.blocks[0].section if self.blocks else ""

    @property
    def parent(self) -> str:
        """The small-to-big PARENT key: the page for a paginated document, the
        heading section otherwise. Stable and derived, never stored twice."""
        page = self.page
        return f"p{page}" if page is not None else f"s{self.section}"


@dataclasses.dataclass(frozen=True)
class ExtractReport:
    """What an extraction did, INCLUDING the cutoffs it applied.

    `admitted` is the load-bearing field: a parser that returned nothing must not
    look like a parser that ran cleanly. `ok` is False when it admitted zero.
    """

    source: str                     # the file's suffix — never its path (privacy)
    blocks: int
    pages_total: Optional[int]
    pages_with_text: Optional[int]
    chars: int
    cutoffs: dict[str, float] = dataclasses.field(default_factory=dict)

    @property
    def admitted(self) -> int:
        return self.blocks

    @property
    def ok(self) -> bool:
        """Zero admitted is a FAILURE, not a pass (the standing cutoff rule)."""
        return self.blocks > 0

    def describe(self) -> str:
        """One English log line. Carries counts and cutoffs, NEVER content."""
        cut = ", ".join(f"{k}={v:g}" for k, v in sorted(self.cutoffs.items()))
        pages = ("-" if self.pages_total is None
                 else f"{self.pages_with_text}/{self.pages_total}")
        return (f"[doc_rag] extract {self.source}: blocks={self.blocks} "
                f"pages_with_text={pages} chars={self.chars} cutoffs({cut})")


@dataclasses.dataclass(frozen=True)
class ChunkReport:
    """What the chunker did, including the window it enforced."""

    chunks: int
    window_tokens: int
    overlap_tokens: int
    truncated_atomic: int
    fallback_windowed: int          # blocks that took the fixed-window FALLBACK

    @property
    def admitted(self) -> int:
        return self.chunks

    @property
    def ok(self) -> bool:
        return self.chunks > 0

    def describe(self) -> str:
        return (f"[doc_rag] chunk: chunks={self.chunks} window={self.window_tokens}tok "
                f"overlap={self.overlap_tokens}tok truncated_atomic={self.truncated_atomic} "
                f"windowed_fallback={self.fallback_windowed}")


__all__ = [
    "ATOMIC_KINDS", "Block", "Chunk", "ChunkReport", "ExtractReport",
    "KIND_CODE", "KIND_HEADING", "KIND_TABLE", "KIND_TEXT",
]
