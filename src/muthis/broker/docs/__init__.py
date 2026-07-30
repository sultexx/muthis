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

SCOPE SO FAR (T1 ingestion, T2 encoder, T3 zones):
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
  · `zones.py`     — WHICH of the three paths a document takes (DEC-47), plus the
    STARTUP INVARIANT that fails loudly when a configuration would empty zone 2
    (DEC-49 ruling 4). The decision lives here, in the broker, and never in a
    plugin: a plugin that could pick its own zone could pick full injection for a
    hostile 200-page document.
  · `token_estimate.py` — characters to tokens, at the HIGHEST ratio P0 measured.
    An upper bound on purpose; the direction of error is argued at the constant.
  · `notes.py`     — the Arabic refusals, each TYPE-ACCURATE and each offering a
    path. This is DEC-35's closure: a scanned PDF and an unsupported format are
    DIFFERENT conditions and get different notes, because a refusal that
    misreports its reason turns a TERMINAL condition into a retryable one.
  · `ingest.py`    — the router: suffix, extract, estimate, zone. Zone 1 and zone
    3 never CONSTRUCT an encoder (one factory reference, AST-asserted), and both
    refusal gates fire before the first vector.

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
from .ingest import DocumentIngestor, EncoderFactory, IngestOutcome
from .model_pin import (
    E5_SMALL_INT8, ModelFingerprintMismatch, ModelPin, ensure_model,
)
from .token_estimate import TOKENS_PER_CHAR_CEILING, estimate_tokens
from .zones import (
    DocZone, ZoneConfigurationError, ZoneDecision, ZonePolicy,
    assert_zone_invariant,
)

__all__ = [
    "Block", "Chunk", "ChunkReport", "Chunker", "ChunkWindowExceeded",
    "DEFAULT_WINDOW_TOKENS", "DocZone", "DocumentIngestor", "E5_SMALL_INT8",
    "E5Encoder", "EncoderFactory", "EncoderUnavailable", "ExtractReport",
    "IndexRegistry", "IngestOutcome", "ModelFingerprintMismatch", "ModelPin",
    "NoTextLayer", "PASSAGE_PREFIX", "QUERY_PREFIX", "SUPPORTED_SUFFIXES",
    "SessionIndex", "TOKENS_PER_CHAR_CEILING", "TokenCounter",
    "UnsupportedDocument", "ZoneConfigurationError", "ZoneDecision",
    "ZonePolicy", "assert_zone_invariant", "ensure_model", "estimate_tokens",
    "extract_blocks", "extract_blocks_async",
]
