# src/muthis/broker/docs/extract.py
"""
Document extraction — text PDF, Markdown and TXT into positioned `Block`s.

WHY `pypdf` AND NOT THE ROADMAP'S PyMuPDF (DEC-49 ruling 1, from the P0 gate):
PyMuPDF FAILED the binding Arabic acceptance condition on BOTH corpus PDFs under
all six of its extraction modes, and `pdfminer.six` failed differently. The
defect is not a crash — it is CHARACTER TRANSPOSITION, where the definite
article's lam hops one position («الجامعة» arrives as «اجلامعة»), and reversal
in pdfminer's case. Both emit syntactically valid Arabic, so every "did we get a
string back" check passes green while the index is silently poisoned. Speed is
NOT the binding constraint here: extraction runs ONCE at ingestion and DEC-47's
budget already bounds it, so a ~10x slower extraction is ABSORBED by the budget
while wrong text is absorbed by nothing.

WHY THE VISITOR API RATHER THAN `extract_text()`: position. `extract_text()`
returns one page-sized string with no paragraph structure, and DEC-45 makes page
+ paragraph a HARD requirement because it is unrecoverable later. The visitor
hands back every text run with its text matrix, so runs group into lines by y,
lines into paragraphs by a y-gap, and each paragraph carries its address. This
assembly is REAL WORK, not a field read — DEC-49 recorded it as a cost the
milestone plan must carry, and this module is where it is paid.

RTL IS LOAD-BEARING IN THE ASSEMBLY: runs within one line are ordered by
DESCENDING x, because the script is Arabic and the rightmost run comes first.
Ordering them left-to-right would produce a per-line word reversal that looks
exactly like the pdfminer defect this module exists to avoid.

Blocking work runs via `asyncio.to_thread` (the threading law): a 228-page parse
measured ~2.6 s at P0, and the single event loop is never frozen.

PRIVACY: logs carry the file's SUFFIX, counts and cutoffs — never its path and
never one character of its content (DEC-20/DEC-28 discipline).
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
import re
from typing import Any, Optional

from .blocks import (
    KIND_CODE, KIND_HEADING, KIND_TABLE, KIND_TEXT, Block, ExtractReport,
)

logger = logging.getLogger("muthis.broker.docs")

# The paragraph cutoff: a vertical gap larger than this many points starts a new
# paragraph. REPORTED in every ExtractReport rather than hidden, because it is a
# filter INSIDE the extraction and a wrong value silently merges or shatters
# paragraphs while the block count still looks plausible.
PARAGRAPH_GAP_POINTS = 6.0

# Markdown structure. A fenced block and a pipe table are ATOMIC (DEC-45).
_FENCE = re.compile(r"^\s*```")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_SECTION_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s")

SUPPORTED_SUFFIXES = frozenset({".pdf", ".md", ".markdown", ".txt"})


class UnsupportedDocument(Exception):
    """The format is not in the launch scope (DEC-47: text PDF + Markdown + TXT).

    Raised INSIDE the broker, never across the plugin boundary: the caller turns
    it into a type-accurate Arabic note at T3, which is where DEC-35's lesson
    lives — a refusal that misreports its reason turns a TERMINAL condition into
    a retryable one and the model rationally retries."""


class NoTextLayer(Exception):
    """A PDF whose pages carry no text layer at all — a SCANNED document.

    Distinct from `UnsupportedDocument` on purpose: scanned is TERMINAL (OCR is
    out of launch scope) while an unsupported format may simply be converted.
    DEC-35 is the whole reason these are two exceptions and not one."""


# ---------------------------------------------------------------------------
# PDF — pypdf through the visitor API
# ---------------------------------------------------------------------------

def _blocks_from_pdf(path: pathlib.Path, gap: float) -> tuple[list[Block], dict[str, Any]]:
    """Assemble positioned paragraphs out of pypdf's text runs. BLOCKING."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    blocks: list[Block] = []
    pages_total = len(reader.pages)
    pages_with_text = 0

    for page_number, page in enumerate(reader.pages, start=1):
        runs: list[tuple[float, float, str]] = []

        def visitor(text, cm, tm, font_dict, font_size, _runs=runs):  # noqa: ANN001, ARG001
            # tm[5] is the run's y, tm[4] its x. Rounded to 0.1pt so runs that
            # share a baseline group together despite float noise.
            if text and text.strip():
                _runs.append((round(tm[5], 1), tm[4], text))

        page.extract_text(visitor_text=visitor)
        if not runs:
            continue
        pages_with_text += 1

        lines: dict[float, list[tuple[float, str]]] = {}
        for y, x, text in runs:
            lines.setdefault(y, []).append((x, text))
        # Top-down by y DESCENDING (PDF origin is bottom-left), and RIGHT-to-LEFT
        # within each line — the Arabic reading order.
        ordered = [
            (y, "".join(t for _, t in sorted(lines[y], key=lambda pair: -pair[0])))
            for y in sorted(lines, reverse=True)
        ]

        paragraph: list[str] = []
        previous_y: Optional[float] = None
        index = 0
        for y, line in ordered:
            if previous_y is not None and abs(previous_y - y) > gap and paragraph:
                blocks.append(Block(text="\n".join(paragraph),
                                    page=page_number, para=index))
                index += 1
                paragraph = []
            paragraph.append(line)
            previous_y = y
        if paragraph:
            blocks.append(Block(text="\n".join(paragraph),
                                page=page_number, para=index))

    if pages_with_text == 0:
        # TERMINAL and type-accurate (DEC-35): a text-layer-less PDF is scanned,
        # and saying "not found" here is what made the model retry four paths.
        raise NoTextLayer(f"no text layer on any of {pages_total} pages")
    return blocks, {"pages_total": pages_total, "pages_with_text": pages_with_text}


# ---------------------------------------------------------------------------
# Markdown / TXT — structure from the text itself
# ---------------------------------------------------------------------------

def _blocks_from_markdown(text: str) -> list[Block]:
    """Headings, paragraphs, and ATOMIC fenced code / pipe tables.

    An UNTERMINATED fence is closed at end-of-file rather than dropped: the P0
    corpus contains exactly that, and discarding the run would silently lose the
    tail of a document while the block count still looked reasonable."""
    blocks: list[Block] = []
    section = ""
    buffer: list[str] = []
    fence: list[str] = []
    in_fence = False

    def flush(kind: str = KIND_TEXT) -> None:
        nonlocal buffer
        body = "\n".join(buffer).strip()
        if body:
            kind_final = KIND_TABLE if body.lstrip().startswith("|") else kind
            blocks.append(Block(text=body, kind=kind_final, section=section))
        buffer = []

    for line in text.splitlines():
        if _FENCE.match(line):
            if in_fence:
                fence.append(line)
                blocks.append(Block(text="\n".join(fence), kind=KIND_CODE, section=section))
                fence, in_fence = [], False
            else:
                flush()
                fence, in_fence = [line], True
            continue
        if in_fence:
            fence.append(line)
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            number = _SECTION_NUMBER.match(heading.group(2))
            section = number.group(1) if number else section
            blocks.append(Block(text=heading.group(2).strip(),
                                kind=KIND_HEADING, section=section))
            continue
        if not line.strip():
            flush()
            continue
        buffer.append(line)

    if in_fence:                      # a real property of the P0 corpus
        blocks.append(Block(text="\n".join(fence), kind=KIND_CODE, section=section))
    flush()
    return [Block(text=b.text, page=None, para=i, kind=b.kind, section=b.section)
            for i, b in enumerate(blocks)]


# ---------------------------------------------------------------------------

def extract_blocks(path: pathlib.Path, *, gap: float = PARAGRAPH_GAP_POINTS
                   ) -> tuple[list[Block], ExtractReport]:
    """BLOCKING extraction. Callers use `extract_blocks_async`."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedDocument(suffix or "(no suffix)")

    cutoffs: dict[str, float] = {}
    if suffix == ".pdf":
        cutoffs["paragraph_gap_points"] = gap
        blocks, page_stats = _blocks_from_pdf(path, gap)
    else:
        blocks = _blocks_from_markdown(path.read_text(encoding="utf-8", errors="replace"))
        page_stats = {"pages_total": None, "pages_with_text": None}

    report = ExtractReport(
        source=suffix,
        blocks=len(blocks),
        pages_total=page_stats["pages_total"],
        pages_with_text=page_stats["pages_with_text"],
        chars=sum(len(b.text) for b in blocks),
        cutoffs=cutoffs,
    )
    logger.info("%s", report.describe())
    return blocks, report


async def extract_blocks_async(path: pathlib.Path, *,
                               gap: float = PARAGRAPH_GAP_POINTS
                               ) -> tuple[list[Block], ExtractReport]:
    """Extraction OFF the event loop (the threading law, DEC-47).

    A 228-page parse measured ~2.6 s at P0 — far past anything that may run
    inline on the single loop that also drives audio."""
    return await asyncio.to_thread(extract_blocks, path, gap=gap)


__all__ = [
    "NoTextLayer", "PARAGRAPH_GAP_POINTS", "SUPPORTED_SUFFIXES",
    "UnsupportedDocument", "extract_blocks", "extract_blocks_async",
]
