# src/muthis_plugins/doc_rag/__init__.py
"""
`doc_rag` — read a real document and teach from what it ACTUALLY says (V2 Phase 2,
Milestone 3; Roadmap §4, DEC-44..DEC-55).

Two tools, namespaced by the router to `docs__open` / `docs__query` (DEC-11).

THE SHAPE OF THIS PACKAGE IS THE SECURITY ARGUMENT: it holds no file handle, no
parser, no encoder and no index. All of those live in `muthis.broker.docs`, because
this code opens the user's private files and a plugin never holds an OS handle
(DEC-17) — and because a plugin may import `muthis_sdk` and stdlib ONLY, so it
could not reach them even if it tried. What arrives is an injected, duck-typed
service; what goes back is text.

  · `schema.py`   — the two model-facing contracts. No zone, no size limit, no
    top_k, no threshold: each absence is a decision recorded there.
  · `delivery.py` — DEC-46's TWO SURVIVING clauses (DEC-50 retired the rest):
    dedupe BY PARENT before filling the cap, deliver in RELEVANCE order, under one
    total character cap. The location labels are CITATION METADATA, never security
    boundaries.
  · `plugin.py`   — the servicing surface. Aggregates and orders; wraps nothing.

NOT HERE, deliberately: no BM25, no RRF, no fusion and no document normalizer.
DEC-50 retired the lexical half after its unique contribution over dense measured
ZERO, so all four would be components with no caller.
"""

from __future__ import annotations

from .delivery import MAX_PASSAGE_CHARS, render, select
from .plugin import DocRagPlugin, OPEN_TOOL, QUERY_TOOL
from .schema import OPEN_SCHEMA, QUERY_SCHEMA

__all__ = [
    "DocRagPlugin", "MAX_PASSAGE_CHARS", "OPEN_SCHEMA", "OPEN_TOOL",
    "QUERY_SCHEMA", "QUERY_TOOL", "render", "select",
]
