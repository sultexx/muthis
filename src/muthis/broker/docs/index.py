# src/muthis/broker/docs/index.py
"""
The session-scoped dense index — RAM only, dies with the process.

PRIVACY IS STRUCTURAL HERE, NOT PROMISED. This module imports `numpy` and
nothing else: no `pathlib`, no `os`, no `json`, no `pickle`, no `open`. It
therefore has NO WAY to write a user's document to disk, which is a stronger
claim than a policy that says it will not — the `FetchedDomains` precedent, which
proved it could not leak a domain by having no logger to leak it from. A test
asserts the absence by AST, so adding an import is what fails, not a review.

DENSE ONLY (DEC-50). There is no BM25 here, no fusion and no normalized second
pipeline, because the lexical half was retired when its unique contribution over
dense measured ZERO (0/17 at @5 and at the effective k). Building any of them now
would be a component with no caller — stub-first forbids it. Cosine over unit
vectors is the whole ranking, which is why the encoder L2-normalises: a dot
product IS the cosine, so this file needs no normalisation step of its own.

DELIVERY RULES SURVIVE DEC-46's retirement, because they were never fusion rules
(DEC-50 says so explicitly): deduplicate BY PARENT before filling the cap, and
deliver in RELEVANCE order because the cap may truncate. Both live at the plugin
boundary (T4) — this file ranks and returns, it does not decide what is sent.

`search` returns INDICES, never text: the caller already holds the chunks and a
second copy is how two views of one fact drift apart (the DEC-32 lesson).
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from .blocks import Chunk

logger = logging.getLogger("muthis.broker.docs")


class SessionIndex:
    """Chunks plus their unit vectors, held for one session and no longer."""

    def __init__(self, chunks: Sequence[Chunk], vectors: Any) -> None:
        if len(chunks) != len(vectors):
            raise ValueError(
                f"index built from {len(chunks)} chunks and {len(vectors)} vectors")
        self._chunks: tuple[Chunk, ...] = tuple(chunks)
        self._vectors = vectors
        logger.info("[doc_rag] index built: chunks=%d dim=%d (RAM only, "
                    "dies with the session)",
                    len(self._chunks), vectors.shape[1] if len(vectors) else 0)

    def __len__(self) -> int:
        return len(self._chunks)

    @property
    def chunks(self) -> tuple[Chunk, ...]:
        return self._chunks

    def search(self, query_vector: Any, *, top: int = 20) -> list[tuple[int, float]]:
        """The `top` best chunk indices with their cosine scores, best first.

        Cosine is a plain dot product because both sides are already L2-normalised
        by the encoder — normalising again here would be a second place for the
        same fact to live.

        NO ENTRY FLOOR. DEC-49 ruling 3 RETIRED it after P0 measured the positive
        and negative cosine distributions OVERLAPPING under both candidate models
        (−0.11 for this one): a topically-adjacent absence scores like a true
        answer, so any floor trades a real hit for a false one and would HIDE
        content from the model — worse than having none. What replaced it is the
        persona law ordering Mut'his to say «ما لقيت هذا في المستند» rather than
        infer, which DEC-50 upgraded to LOAD-BEARING because effective recall is
        82% and roughly one question in five has no retrieved answer."""
        if not len(self._chunks):
            return []
        scores = self._vectors @ query_vector
        # argsort over the whole set: the corpus fits in RAM by construction
        # (P0 measured 2 MB for 2 500 chunks), so a heap would buy nothing.
        order = scores.argsort()[::-1][:top]
        return [(int(i), float(scores[i])) for i in order]

    def clear(self) -> None:
        """Drop everything. The session's end is the only reset (privacy).

        There is no `save`, no `load` and no path anywhere in this module — see
        the module docstring."""
        self._chunks = ()
        self._vectors = self._vectors[:0]
        logger.info("[doc_rag] index cleared")


class IndexRegistry:
    """The open documents of ONE session, keyed by doc_id.

    A dict, deliberately: no eviction policy, no persistence, no lifecycle. Law
    11 keeps lifecycles in the kernel, and the only lifecycle here is the
    process's own — which is exactly the privacy guarantee (`CONTRIBUTING.md`
    condition 6: working memory lives in RAM and dies with the session)."""

    def __init__(self) -> None:
        self._open: dict[str, SessionIndex] = {}

    def put(self, doc_id: str, index: SessionIndex) -> None:
        self._open[doc_id] = index

    def get(self, doc_id: str) -> Optional[SessionIndex]:
        return self._open.get(doc_id)

    def __contains__(self, doc_id: object) -> bool:
        return doc_id in self._open

    def sole_doc_id(self) -> Optional[str]:
        """The ONE open document's id, or None when zero or many are open.

        Used by `query`'s mismatch recovery: with exactly one document open there
        is no ambiguity to resolve, so an id the model mangled in transit can be
        recovered. With two or more the ambiguity is REAL and the caller must
        return the honest note instead of guessing."""
        if len(self._open) == 1:
            return next(iter(self._open))
        return None

    def __len__(self) -> int:
        return len(self._open)

    def clear(self) -> None:
        for index in self._open.values():
            index.clear()
        self._open.clear()
        logger.info("[doc_rag] all session indexes cleared")


__all__ = ["IndexRegistry", "SessionIndex"]
