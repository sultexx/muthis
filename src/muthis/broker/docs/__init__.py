# src/muthis/broker/docs/__init__.py
"""
The broker-owned document ingestion path (V2 Phase 2, M3 — `doc_rag`).

PLACED IN THE BROKER for the reason `broker/net/` and `broker/search/` are:
external plugin code never holds an OS handle (DEC-17). Parsing a document is
file I/O plus heavy CPU, so it lives HERE and hands back positioned text — the
plugin receives CONTENT, never a path or a file object. DEC-18's placement was
confirmed on the argument that a key-bearing call makes that principle STRONGER
rather than weaker; a call that opens the user's private files makes it stronger
again.

T1 SCOPE (this commit): extraction and chunking only.
  · `extract.py`  — text PDF via `pypdf`'s visitor API (DEC-49 ruling 1),
    Markdown and TXT, every block carrying page + paragraph (DEC-45), off the
    event loop via `asyncio.to_thread`.
  · `chunking.py` — structural boundaries with a fixed-window FALLBACK, ATOMIC
    code and tables, sized in TOKENS against an INJECTED counter, and the STRICT
    guard that FAILS rather than warns.
  · `blocks.py`   — the position-carrying records and the stage reports, which
    state the cutoff used and the count admitted (the standing rule).

NOT HERE, deliberately: no BM25, no fusion, and no document normalizer — DEC-50
retired the lexical half, so all three have no consumer and building them would
be a component with no caller (stub-first). The encoder arrives at T2 behind its
own seam; nothing in this package imports a model or an ONNX runtime, so it all
stays importable in isolation.
"""

from __future__ import annotations

from .blocks import Block, Chunk, ChunkReport, ExtractReport
from .chunking import (
    Chunker, ChunkWindowExceeded, DEFAULT_WINDOW_TOKENS, TokenCounter,
)
from .extract import (
    NoTextLayer, SUPPORTED_SUFFIXES, UnsupportedDocument, extract_blocks,
    extract_blocks_async,
)

__all__ = [
    "Block", "Chunk", "ChunkReport", "Chunker", "ChunkWindowExceeded",
    "DEFAULT_WINDOW_TOKENS", "ExtractReport", "NoTextLayer",
    "SUPPORTED_SUFFIXES", "TokenCounter", "UnsupportedDocument",
    "extract_blocks", "extract_blocks_async",
]
