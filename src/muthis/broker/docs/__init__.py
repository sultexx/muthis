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

SCOPE SO FAR (T1 ingestion, T2 encoder):
  · `extract.py`   — text PDF via `pypdf`'s visitor API (DEC-49 ruling 1),
    Markdown and TXT, every block carrying page + paragraph (DEC-45), off the
    event loop via `asyncio.to_thread`.
  · `chunking.py`  — structural boundaries with a fixed-window FALLBACK, ATOMIC
    code and tables, sized in TOKENS against an INJECTED counter, and the STRICT
    guard that FAILS rather than warns.
  · `blocks.py`    — the position-carrying records and the stage reports, which
    state the cutoff used and the count admitted (the standing rule).
  · `model_pin.py` — the artifact pinned by sha256 with a spoken first-download
    (the DEC-3-D pattern); a present-but-wrong hash FAILS CLOSED.
  · `encoder.py`   — `multilingual-e5-small` int8 on ONNX Runtime, with the
    BINDING `query: ` / `passage: ` prefixes and MEAN pooling read from the model
    card at P0 (DEC-49 ruling 2).
  · `index.py`     — the session-scoped dense index. RAM only, and provably so:
    it imports `numpy` and nothing else, so it has NO WAY to write to disk.

NOT HERE, deliberately: no BM25, no fusion, and no document normalizer — DEC-50
retired the lexical half, so all three have no consumer and building them would
be a component with no caller (stub-first).

NOTHING IN THIS PACKAGE IMPORTS A MODEL EAGERLY: `onnxruntime` and `tokenizers`
are lazy inside `E5Encoder.load`, so importing `muthis.broker.docs` costs a
process that never opens a document nothing at all.
"""

from __future__ import annotations

from .blocks import Block, Chunk, ChunkReport, ExtractReport
from .chunking import (
    Chunker, ChunkWindowExceeded, DEFAULT_WINDOW_TOKENS, TokenCounter,
)
from .encoder import (
    E5Encoder, EncoderUnavailable, PASSAGE_PREFIX, QUERY_PREFIX,
)
from .extract import (
    NoTextLayer, SUPPORTED_SUFFIXES, UnsupportedDocument, extract_blocks,
    extract_blocks_async,
)
from .index import IndexRegistry, SessionIndex
from .model_pin import (
    E5_SMALL_INT8, ModelFingerprintMismatch, ModelPin, ensure_model,
)

__all__ = [
    "Block", "Chunk", "ChunkReport", "Chunker", "ChunkWindowExceeded",
    "DEFAULT_WINDOW_TOKENS", "E5_SMALL_INT8", "E5Encoder", "EncoderUnavailable",
    "ExtractReport", "IndexRegistry", "ModelFingerprintMismatch", "ModelPin",
    "NoTextLayer", "PASSAGE_PREFIX", "QUERY_PREFIX", "SUPPORTED_SUFFIXES",
    "SessionIndex", "TokenCounter", "UnsupportedDocument", "ensure_model",
    "extract_blocks", "extract_blocks_async",
]
