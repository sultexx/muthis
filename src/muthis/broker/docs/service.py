# src/muthis/broker/docs/service.py
"""
The document service — the ONE object the `doc_rag` plugin is handed (T4).

WHY THIS LIVES IN THE BROKER AND NOT IN THE PLUGIN PACKAGE. Two independent
reasons, and either alone would decide it:

  1. **A plugin may import `muthis_sdk` and stdlib ONLY**, and a test enforces it.
     This object needs the ingestor, the encoder and the index — all app code — so
     the plugin package is not a lawful home for it. Compare `SandboxService`,
     which DOES live in its plugin package: it drives a Docker CLI through
     injected asyncio seams and imports nothing from the app. The layering law is
     what separates the two cases, not preference.
  2. **DEC-17's principle: external plugin code never holds an OS handle.** This
     opens the user's private files. It also holds the WHOLE DOCUMENT — every
     chunk of it — which is strictly more than a handle. The plugin receives the
     RETRIEVED PASSAGES and nothing else, so the largest thing it can leak is the
     answer to the question that was asked.

SO IT IS INJECTED ALREADY-BUILT, duck-typed on the far side — the DEC-27 shape
that keeps the search provider out of `web_research`. The composition root builds
it; the plugin calls two verbs on it and cannot reach past them.

WHAT IT OWNS, AND WHAT IT DELIBERATELY DOES NOT:
  · OWNS the `DocumentIngestor` (the three zones) and the `IndexRegistry` (the
    session's open documents, RAM-only, dying with the process).
  · OWNS the encoder's LIFETIME — one per process, built lazily on the first
    zone-2 document. A per-document encoder would pay the ~1,010 ms session load
    again for every file; a per-process one pays it once, which is why the figure
    was reported as measured rather than smoothed.
  · DOES NOT rank, dedupe, order or cap. Ranking is the index's (cosine over unit
    vectors); dedupe, ORDER and the delivery cap are the PLUGIN's, because DEC-46
    assigns aggregation and ordering there — "the plugin AGGREGATES and ORDERS,
    and WRAPS NOTHING".
  · DOES NOT wrap and DOES NOT classify taint. Those are the router's two
    absolutes (DEC-14/DEC-15) and this module names neither.

NO LIFECYCLE (Law 11). No loop, no lock, no retry, no background task. `open` does
one document and returns; `query` does one lookup and returns. The only lifecycle
is the process's own, which is exactly the privacy guarantee.
"""

from __future__ import annotations

import dataclasses
import logging
import pathlib
from typing import Any, Optional

from . import notes
from .blocks import Chunk
from .encoder import E5Encoder, EncoderUnavailable
from .index import IndexRegistry, SessionIndex
from .ingest import DocumentIngestor
from .model_pin import E5_SMALL_INT8
from .zones import DocZone, ZonePolicy

logger = logging.getLogger("muthis.broker.docs")

# How many chunks the index returns before the plugin dedupes and fills its cap.
# Generous ON PURPOSE: parent dedupe COLLAPSES rows (small-to-big means several
# children of one parent rank together), so a tight candidate list would leave the
# plugin nothing to fill the cap WITH after collapsing. P0 measured the real
# delivery shape at 8-17 parents, so 40 candidates keeps the cap the binding
# constraint rather than this number.
CANDIDATES = 40

# No document is open under this id. Its own note, because "not found" would be
# the DEC-35 defect one layer up: the model would retry the QUERY when what it
# needs is to open the document first.
DOC_NOT_OPEN_AR = (
    "ما فيه مستند مفتوح بهذا الاسم. افتح المستند أول بأداة فتح المستندات، "
    "بعدها اسألني عن اللي فيه."
)
# The note law again: the document is STILL OPEN and nothing failed — only the
# question was missing — so the note says so, or the model re-opens to "fix" it.
EMPTY_QUESTION_AR = (
    "ما وصلني سؤال أبحث عنه في المستند. المستند لا يزال مفتوحاً وجاهزاً وما "
    "تغيّر شي، فأعد الاستعلام بنفس المعرّف ومعه سؤال محدد."
)


@dataclasses.dataclass(frozen=True)
class Passage:
    """One retrieved chunk, with WHERE it came from and HOW well it matched.

    `parent` and `score` are here because the plugin needs both to apply DEC-46's
    two surviving delivery rules — dedupe by parent, deliver in relevance order —
    and it is duck-typed across the boundary, so the fields ARE the contract.

    `page` / `section` are the citation metadata DEC-46 distinguishes from a
    security boundary: they exist so a claim can be attributed to a location, and
    nothing downstream may read them as a trust signal."""

    text: str
    score: float
    parent: str
    page: Optional[int] = None
    section: str = ""


@dataclasses.dataclass(frozen=True)
class OpenedDocument:
    """What `open` produced: a zone, and either text, a doc_id, or a refusal."""

    zone: str
    note_ar: Optional[str] = None
    text: str = ""
    doc_id: str = ""
    pages: Optional[int] = None
    chunks: int = 0

    @property
    def ok(self) -> bool:
        return self.note_ar is None


class DocumentService:
    """`open` a document, then `query` it. Two verbs, and no third."""

    def __init__(self, *, model_dir: pathlib.Path, policy: Optional[ZonePolicy] = None,
                 registry: Optional[IndexRegistry] = None,
                 encoder: Optional[Any] = None) -> None:
        self._model_dir = pathlib.Path(model_dir)
        self._policy = policy or ZonePolicy.from_env()
        self._registry = registry or IndexRegistry()
        # T6: path -> (doc_id, pages), so re-opening the SAME document is
        # IDEMPOTENT. See `open`. RAM-only and dies with the process, exactly
        # like the registry it mirrors; never logged (it holds a real path).
        self._opened_paths: dict[str, tuple[str, Optional[int]]] = {}
        # ONE encoder per process, built on first use. `encoder` is injectable so
        # a test drives the real service without an ONNX runtime present.
        self._encoder = encoder
        self._ingestor = DocumentIngestor(policy=self._policy,
                                          encoder_factory=self._encoder_once)

    # -- the encoder's single construction site ------------------------------
    def _encoder_once(self) -> Any:
        """Build the encoder ONCE per process, on the first zone-2 document.

        Lazy for the reason `E5Encoder.load` is: a session that only ever opens
        small documents pays nothing at all, and P0 measured that as the common
        case (2 of 3 corpus documents never touch the index)."""
        if self._encoder is None:
            self._encoder = E5Encoder(self._model_dir, pin=E5_SMALL_INT8)
        return self._encoder

    # -- open ---------------------------------------------------------------
    async def open(self, path: pathlib.Path) -> OpenedDocument:
        """Ingest one document. The ZONE is decided inside the broker (DEC-47) and
        the caller cannot name it — see `zones.py` for why that ownership matters.

        Never raises: `DocumentIngestor` already turns every failure into an
        Arabic note, and this adds no new failure surface of its own.

        RE-OPENING AN ALREADY-OPEN PATH IS IDEMPOTENT (T6): the SAME doc_id comes
        back and the existing index is reused, at essentially zero cost. This is
        correct independently of any model behaviour — the index is
        session-scoped and the document has not changed — and the check has to
        sit HERE, before `ingest`, because everything expensive is downstream of
        this line. Without it every retry paid a FULL re-ingestion (18 s measured
        live) and `_register`'s collision suffix handed back a DIFFERENT id each
        time (`book.md`, `book.md-2`, `book.md-3`), so the model also lost the id
        it had just been given."""
        path = pathlib.Path(path)
        known = self._opened_paths.get(_path_key(path))
        if known is not None:
            doc_id, pages = known
            index = self._registry.get(doc_id)
            if index is not None:
                logger.info("[doc_rag] reopen: already open, reusing the index "
                            "(chunks=%d) — no re-ingestion", len(index))
                return OpenedDocument(zone=DocZone.INDEX.value, doc_id=doc_id,
                                      pages=pages, chunks=len(index))
        outcome = await self._ingestor.ingest(path)
        if not outcome.ok:
            return OpenedDocument(zone=outcome.zone.value, note_ar=outcome.note_ar)
        if outcome.zone is DocZone.INJECT:
            # Zone 1 hands over the whole document and registers NOTHING: there is
            # no index to query, so there is deliberately no doc_id either. An id
            # here would invite a `query` against a document that was never
            # indexed, and the honest answer to that is the text itself.
            return OpenedDocument(zone=outcome.zone.value, text=outcome.text,
                                  pages=_pages(outcome))
        doc_id = self._register(path, outcome.index)
        pages = _pages(outcome)
        self._opened_paths[_path_key(path)] = (doc_id, pages)
        return OpenedDocument(zone=outcome.zone.value, doc_id=doc_id,
                              pages=pages, chunks=len(outcome.index))

    def _register(self, path: pathlib.Path, index: SessionIndex) -> str:
        """Store the index under a SPEAKABLE id — the file's own name.

        An opaque handle would be worse in a VOICE product: the model repeats this
        id back, and Mut'his may say it aloud. A collision (the same file name in
        two directories) gets a suffix rather than silently REPLACING the earlier
        document, which would answer questions about the wrong file with no
        observable difference — the DEC-47 argument against partial ingestion,
        in miniature."""
        base = path.name or "document"
        doc_id, n = base, 1
        while doc_id in self._registry:
            n += 1
            doc_id = f"{base}-{n}"
        self._registry.put(doc_id, index)
        return doc_id

    # -- query --------------------------------------------------------------
    def query(self, doc_id: str, question: str) -> tuple[list[Passage], Optional[str]]:
        """The best CANDIDATES for one question, best first, or an Arabic note.

        Returns candidates rather than a final answer set: dedupe, ordering and
        the delivery cap belong to the plugin (DEC-46), so this stops at ranking.

        DENSE ONLY (DEC-50). There is no BM25 here, no fusion and no second
        normalized pipeline, because the lexical half's unique contribution over
        dense measured ZERO — 0 of 17 at @5 and 0 at the effective k, with the
        union scoring exactly dense alone. Building any of it now would be a
        component with no caller.

        NO ENTRY FLOOR (DEC-49 ruling 3): the positive and negative cosine
        distributions OVERLAP, so any floor trades a real hit for a false one and
        would HIDE content from the model. What replaced it is the persona law
        ordering Mut'his to say «ما لقيت هذا في المستند» rather than infer — which
        is why T5 calls that law LOAD-BEARING rather than decorative."""
        if not isinstance(question, str) or not question.strip():
            return [], EMPTY_QUESTION_AR
        doc_id = _normalize_doc_id(doc_id)
        index = self._registry.get(doc_id)
        if index is None:
            sole = self._registry.sole_doc_id()
            if sole is None:
                # Zero open, or MORE THAN ONE: the ambiguity is real and the
                # model must disambiguate. Guessing here would answer questions
                # about the wrong document with no observable difference.
                return [], DOC_NOT_OPEN_AR
            # RECOVERED MISMATCH. Made VISIBLE rather than papered over — but the
            # values are NOT logged: a doc_id IS the file's own name (`_register`),
            # so printing it beside the key would re-open the I6 breach DEC-61
            # closed. The SHAPE of what the model sent is captured by the live
            # OBSERVATION line instead, which prints and never logs.
            logger.warning(
                "[doc_rag] RECOVERED MISMATCH: the doc_id received does not match "
                "the registry key (received len=%d, key len=%d, differ_only_by_"
                "wrapping=%s) — exactly ONE document is open, so it was used",
                len(doc_id), len(sole), _normalize_doc_id(sole) == doc_id)
            doc_id, index = sole, self._registry.get(sole)
        try:
            encoder = self._encoder_once()
            vector = encoder.encode_queries([question.strip()])[0]
        except EncoderUnavailable:
            # Already logged LOUDLY and in English by the encoder (DEC-44).
            return [], notes.DOC_ENCODER_UNAVAILABLE_AR
        ranked = index.search(vector, top=CANDIDATES)
        chunks = index.chunks
        logger.info("[doc_rag] query: candidates=%d of %d chunks (cutoff top=%d)",
                    len(ranked), len(chunks), CANDIDATES)
        return [_passage(chunks[i], score) for i, score in ranked], None

    # -- lifecycle (the process's own, and only that) ------------------------
    def clear(self) -> None:
        """Drop every open document. Called at shutdown by the root that built
        this — the index is session-scoped and dies with the session (privacy).

        The path map goes WITH the registry: leaving it behind would hand back a
        doc_id whose index no longer exists, which is the one state `open`'s
        reuse branch must never be able to reach."""
        self._registry.clear()
        self._opened_paths.clear()

    @property
    def open_documents(self) -> int:
        return len(self._registry)


# The wrappers a natural-language round-trip adds. `INDEXED_AR` presents the id
# INSIDE guillemets («…»), so the model must extract and re-emit it — and may echo
# a guillemet, quote the value, or pad it. DEC-16's rule governs: a machine
# identifier must never depend on the model's paraphrasing.
_DOC_ID_WRAPPERS = '«»"\'“”‘’ \t\r\n'


def _normalize_doc_id(raw: str) -> str:
    """The id as the registry keys it, whatever punctuation survived the trip."""
    return raw.strip().strip(_DOC_ID_WRAPPERS).strip()


def _path_key(path: pathlib.Path) -> str:
    """The identity of a document ON DISK, for the idempotent-reopen check.

    Resolved so that two spellings of one file — the model may echo the user's
    path back differently — are recognised as the same document. Falls back to
    the raw string when resolution fails (a path that cannot be resolved cannot
    be ingested either, so the fallback only has to be STABLE, not correct)."""
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _passage(chunk: Chunk, score: float) -> Passage:
    return Passage(text=chunk.text, score=score, parent=chunk.parent,
                   page=chunk.page, section=chunk.section)


def _pages(outcome: Any) -> Optional[int]:
    report = getattr(outcome, "extract", None)
    return getattr(report, "pages_total", None) if report is not None else None


__all__ = [
    "CANDIDATES", "DOC_NOT_OPEN_AR", "DocumentService", "EMPTY_QUESTION_AR",
    "OpenedDocument", "Passage",
]
