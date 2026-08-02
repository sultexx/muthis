# src/muthis/broker/docs/ingest.py
"""
The three-zone ingestion path (DEC-47) — one document in, one outcome out.

THE ORDER OF OPERATIONS IS THE FEATURE, not an implementation detail:

    suffix -> extract -> ESTIMATE -> zone -> (inject | chunk+encode+index | refuse)

Each step is cheaper than the next, and each can refuse. A refusal therefore costs
what it took to REACH it, never the whole budget. DEC-47 states the alternative
plainly: ingesting and THEN refusing is worse than either option on its own,
because the user waits out the entire indexing budget in silence and is refused at
the end of it, having paid the full cost for nothing.

ZONE 1 IS BUILT AND TESTED FIRST, and the build order is DEC-47's ruling rather
than convenience — the `stub_read_file` ordering, where the simplest working path
lands first and the elaborate machinery arrives behind it. Zone 1 is the MOST
COMMON path (two of the three P0 corpus documents), and it is simultaneously the
CHEAPEST and the MOST ACCURATE, because no retrieval step can beat handing the
model the whole document. Chunking, encoding and indexing are all bypassed.

THE BYPASS IS STRUCTURAL, NOT A PROMISE. `self._encoder_factory` is referenced on
exactly ONE line of this file, inside `_index`, which is reached only from the
INDEX branch and only after every refusal has returned. So a zone-1 or a zone-3
document does not merely skip encoding — it never CONSTRUCTS an encoder, and there
is no code path from those branches to one. A test asserts the single reference by
AST, so a future edit that hoists the factory for convenience FAILS rather than
quietly re-coupling the cheap path to the expensive one.

TWO REFUSAL GATES, BOTH BEFORE ANY ENCODING:
  1. the ESTIMATED gate, from the character count, before anything is chunked — so
     an absurd document is refused in the seconds extraction took;
  2. the EXACT gate, from the true chunk count, after chunking and before the
     first vector. Chunking hands over the real cost unit for free, and the second
     gate is what keeps the first gate's inexactness from ever being discovered by
     running out of time.

NOTHING HERE OWNS A LIFECYCLE (Law 11). No loop, no retry, no lock, no background
task. DEC-47 rejected a background ingestion task outright on exactly this ground:
it is a lifecycle outside the kernel, which is a law rather than a trade-off, so
the feature was redesigned around it. One call does one document and returns.

THE ZONE IS NEVER A PARAMETER. `ingest` takes a path and nothing else — see
`zones.py` for why a plugin that could choose its own zone is a plugin that could
choose full injection for a hostile 200-page document.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
from typing import Any, Callable, Optional

from . import notes
from .blocks import Block, Chunk, ChunkReport, ExtractReport
from .chunking import Chunker, ChunkWindowExceeded
from .encoder import EncoderUnavailable
from .extract import (
    NoTextLayer, SUPPORTED_SUFFIXES, UnsupportedDocument, extract_blocks_async,
)
from .paths import resolve_document_path
from .index import SessionIndex
from .zones import DocZone, ZoneDecision, ZonePolicy

logger = logging.getLogger("muthis.broker.docs")

# The encoder arrives as a FACTORY rather than an instance, and that is what makes
# the bypass real: an instance passed in would already have been built by the
# caller, so "zone 1 touches no encoder" would be a claim about the caller instead
# of a property of this file.
EncoderFactory = Callable[[], Any]


class IngestOutcome:
    """What one ingestion produced: a zone, and exactly one of text / index / note.

    Not a union type but a small record with an `ok` — the `ServiceOutcome` shape,
    for the same reason: every caller must handle the refusal, and a refusal that
    arrives as an exception across a boundary becomes a caller's choice about
    whether to catch it."""

    def __init__(self, zone: DocZone, *, decision: Optional[ZoneDecision] = None,
                 note_ar: Optional[str] = None, text: str = "",
                 index: Optional[SessionIndex] = None,
                 extract: Optional[ExtractReport] = None,
                 chunks: Optional[ChunkReport] = None) -> None:
        self.zone = zone
        self.decision = decision
        self.note_ar = note_ar
        self.text = text
        self.index = index
        self.extract = extract
        self.chunks = chunks

    @property
    def ok(self) -> bool:
        """A note present means a refusal. There is no partial success here —
        DEC-47 rejected partial ingestion, because the disclosure fires ONCE at
        ingestion while the wrong answer arrives LATER, with nothing connecting
        the two, and the model cannot know what it was not given."""
        return self.note_ar is None


def _page_marker(block: Block, previous: Optional[Block]) -> str:
    """A position marker, emitted whenever the position CHANGES — the FIRST block
    included, because `previous is None` is a change from nothing.

    The first page is the one a reader is most likely to ask about, and an earlier
    draft of this function skipped it (no previous, so nothing "changed"), leaving
    page 1 as the only unlabelled page in the document. A test caught it.

    Zone 1 hands over the whole document, and DEC-45 captures page and section
    precisely so a location can be named — a 228-page document injected as one
    unmarked blob is a document the model cannot cite. The markers cost well under
    1% of the character count (228 pages measured ~2.7k chars against ~384k), which
    sits far inside the estimator's upward margin, so they cannot push a zone-1
    document past the limit it was admitted under."""
    if block.page is not None:
        return f"\n\n[صفحة {block.page}]\n" if (
            previous is None or previous.page != block.page) else "\n\n"
    if block.section and (previous is None or previous.section != block.section):
        return f"\n\n[قسم {block.section}]\n"
    return "\n\n"


def _assemble(blocks: list[Block]) -> str:
    """The full document, every position marked, in reading order."""
    parts: list[str] = []
    previous: Optional[Block] = None
    for block in blocks:
        parts.append(_page_marker(block, previous))
        parts.append(block.text)
        previous = block
    return "".join(parts).strip()


class DocumentIngestor:
    """The broker's ingestion entry point. Built ONCE at the composition root.

    Every collaborator is INJECTED — the policy, the extractor and the encoder
    FACTORY — for the reason the fetcher and the search provider are: a test can
    then drive the real decision logic against seams that record what was touched,
    which is the only way "this path never encodes" can be asserted rather than
    reviewed."""

    def __init__(self, *, policy: Optional[ZonePolicy] = None,
                 encoder_factory: Optional[EncoderFactory] = None,
                 extract=extract_blocks_async) -> None:
        self._policy = policy or ZonePolicy.from_env()
        self._encoder_factory = encoder_factory
        self._extract = extract

    @property
    def policy(self) -> ZonePolicy:
        return self._policy

    # ── the one entry point. A PATH, and nothing else. ────────────────────────
    async def ingest(self, path: pathlib.Path) -> IngestOutcome:
        """Open one document and take it down whichever of the three paths its
        SIZE dictates. Never raises: every failure is an Arabic note, because a
        refusal that arrives as an exception ends the turn instead of continuing
        it (the `FileReader` precedent, and the Law-11 wall)."""
        # RAW wins when it exists; a percent-encoded path is retried decoded, and
        # `url_encoded` lets the refusal NAME the cause. Why decoding is a
        # FALLBACK and never a rewrite: `paths.py`.
        resolved = resolve_document_path(pathlib.Path(path))
        path = resolved.path
        suffix = path.suffix.lower()
        # Cheapest refusal first, and it opens NO file: an unsupported format is
        # knowable from the name alone.
        if suffix not in SUPPORTED_SUFFIXES:
            logger.info("[doc_rag] refused unsupported format: %s", suffix or "(none)")
            return IngestOutcome(DocZone.REFUSE, note_ar=notes.unsupported(suffix))

        blocks, report, note = await self._extract_blocks(path, resolved.url_encoded)
        if note is not None:
            return IngestOutcome(DocZone.REFUSE, note_ar=note, extract=report)

        # THE UP-FRONT DECISION (DEC-47), from characters, before any encoding.
        # The count is over extracted BLOCK TEXT, which is what will be injected
        # or chunked — not the file's size on disk, which for a PDF says more
        # about its images than about its text.
        decision = self._policy.decide(report.chars)
        logger.info("%s", decision.describe())

        if decision.zone is DocZone.REFUSE:
            # ZERO chunking and ZERO encoding: nothing below this line has run,
            # and `_encoder_factory` has not been called.
            return IngestOutcome(DocZone.REFUSE, decision=decision, extract=report,
                                 note_ar=notes.too_large(decision.tokens,
                                                         decision.max_tokens))

        if decision.zone is DocZone.INJECT:
            # ZONE 1 — the whole document. No chunker, no encoder, no index.
            # The prompt-cache marking that makes this cheap on repeat turns is
            # the MOUNT's business, not the broker's: caching is a property of how
            # a content block is sent, and this layer does not know a provider.
            return IngestOutcome(DocZone.INJECT, decision=decision, extract=report,
                                 text=_assemble(blocks))

        # OFF THE EVENT LOOP. This line RESTORES A GUARANTEE rather than adding a
        # feature, which is why it lands inside a signed, merged milestone.
        # `_index` used to be called SYNCHRONOUSLY from this async function, so
        # chunk + load + encode ran ON the loop thread and BLOCKED it for ~20 s —
        # and a blocked loop cannot run the F9 barge-in, which arrives through
        # `loop.call_soon_threadsafe`. The silence was the SYMPTOM; the defect was
        # that stop did nothing for twenty seconds, which a user reads as a HANG.
        # DEC-64 ruling 3's measurement stands; its CAUSE was misdiagnosed.
        # Full argument: DECISIONS.md, "the ~20 s was a BLOCKED LOOP".
        #
        # `extract.py` already offloads its parse this way — this is that line's
        # sibling. `_index` stays SYNC (CPU work, no lifecycle): `to_thread` is a
        # bounded offload of ONE call, never the background task DEC-47 rejected.
        # ACCEPTED: a cancelled turn no longer waits for the encode (the worker
        # finishes and its index is discarded — the user gets their interrupt), and
        # concurrency becomes expressible though it stays unreachable (see the DEC).
        return await asyncio.to_thread(self._index, blocks, decision, report)

    # ── extraction, with each failure named as itself (DEC-35) ────────────────
    async def _extract_blocks(self, path: pathlib.Path, url_encoded: bool = False):
        try:
            blocks, report = await self._extract(path)
        except NoTextLayer as exc:
            # TERMINAL, and the note says so. This is the condition whose
            # mis-report cost four provider calls in DEC-35's live evidence.
            logger.info("[doc_rag] refused scanned pdf (no text layer): %s", exc)
            return [], None, notes.PDF_SCANNED_AR
        except UnsupportedDocument as exc:
            logger.info("[doc_rag] refused unsupported document: %s", exc)
            return [], None, notes.unsupported(str(exc))
        except OSError as exc:
            # DEC-61: the exception TEXT is dropped, not shortened — OSError's
            # __str__ embeds the offending path verbatim.
            logger.warning("[doc_rag] extraction failed (%s, url_encoded=%s)",
                           type(exc).__name__, url_encoded)
            return [], None, notes.read_failed(url_encoded=url_encoded)
        if not report.ok:
            # Zero admitted is a FAILURE, never a pass (the standing cutoff rule).
            logger.info("[doc_rag] extraction admitted ZERO blocks — refusing")
            return [], report, notes.DOC_EMPTY_AR
        return blocks, report, None

    # ── ZONE 2. The ONLY place an encoder is constructed in this file. ────────
    def _index(self, blocks: list[Block], decision: ZoneDecision,
               report: ExtractReport) -> IngestOutcome:
        """Chunk with the model's OWN tokenizer, then encode, then index.

        The encoder is built HERE and nowhere else, which is what makes the zone-1
        and zone-3 bypasses structural rather than promised."""
        if self._encoder_factory is None:
            logger.error("[doc_rag] no encoder configured — zone 2 is unavailable")
            return IngestOutcome(DocZone.INDEX, decision=decision, extract=report,
                                 note_ar=notes.DOC_ENCODER_UNAVAILABLE_AR)
        try:
            encoder = self._encoder_factory()
            encoder.load()
            chunks, chunk_report = Chunker(encoder.count_tokens).chunk(blocks)
        except EncoderUnavailable:
            # Already logged LOUDLY and in English by the encoder (DEC-44).
            return IngestOutcome(DocZone.INDEX, decision=decision, extract=report,
                                 note_ar=notes.DOC_ENCODER_UNAVAILABLE_AR)
        except ChunkWindowExceeded as exc:
            # DEC-53: the SPLITTER is what gets fixed when this fires, never the
            # guard. Refusing beats indexing a document whose tails are missing.
            logger.error("[doc_rag] chunking failed: %s", exc)
            return IngestOutcome(DocZone.INDEX, decision=decision, extract=report,
                                 note_ar=notes.DOC_CHUNK_FAILED_AR)

        # THE SECOND GATE — exact, and still before the first vector. The estimate
        # above is an upper bound but not a proof; this is the real cost unit,
        # because encode time is per CHUNK rather than per token.
        if self._policy.exceeds_budget(len(chunks)):
            exact = ZoneDecision(zone=DocZone.REFUSE, chars=report.chars,
                                 tokens=sum(c.n_tokens for c in chunks),
                                 inject_limit=self._policy.inject_limit,
                                 max_tokens=self._policy.max_tokens, exact=True)
            logger.info("%s", exact.describe())
            return IngestOutcome(DocZone.REFUSE, decision=exact, extract=report,
                                 chunks=chunk_report,
                                 note_ar=notes.too_large(exact.tokens,
                                                         exact.max_tokens))
        return self._encode(encoder, chunks, decision, report, chunk_report)

    def _encode(self, encoder: Any, chunks: list[Chunk], decision: ZoneDecision,
                report: ExtractReport, chunk_report: ChunkReport) -> IngestOutcome:
        try:
            vectors = encoder.encode_passages([c.text for c in chunks])
        except EncoderUnavailable:
            return IngestOutcome(DocZone.INDEX, decision=decision, extract=report,
                                 chunks=chunk_report,
                                 note_ar=notes.DOC_ENCODER_UNAVAILABLE_AR)
        return IngestOutcome(DocZone.INDEX, decision=decision, extract=report,
                             chunks=chunk_report,
                             index=SessionIndex(chunks, vectors))


__all__ = ["DocumentIngestor", "EncoderFactory", "IngestOutcome"]
