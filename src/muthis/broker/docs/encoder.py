# src/muthis/broker/docs/encoder.py
"""
The dense encoder behind a seam — `multilingual-e5-small`, int8, ONNX Runtime.

THE INPUT FORMAT IS BINDING (DEC-49 ruling 2), and it is the most dangerous
contract in this milestone because breaking it FAILS SILENTLY. The model card
states: *"Each input text should start with `query: ` or `passage: `, even for
non-English texts"*, and *"use `query: ` and `passage: ` correspondingly for
asymmetric tasks such as passage retrieval in open QA"* — which is exactly this
use. Pooling is MEAN (`1_Pooling/config.json`: `pooling_mode_mean_tokens: true`),
followed by L2 normalisation (`modules.json` ships a `Normalize` module).

**Indexing without the prefixes does not raise, does not warn, and does not look
wrong.** Vectors come back the right shape and the right dtype; every downstream
stage reports success; retrieval quality simply degrades across EVERY result at
once. That is the worst failure shape available in this milestone, which is why
the prefixes are constants asserted by test rather than string literals at the
call sites, and why a mutation that drops one must go RED.

Read from the model card at P0, never from memory — the DEC-43 discipline
applied to a vendor spec instead of a law.

NO `torch`, NO `transformers`, NO `sentence-transformers`. `tokenizers` alone
loads the model's own `tokenizer.json` (P0-proven), and `onnxruntime` runs the
publisher's int8 export. DEC-44 rejected torch on dependency weight; an AST
ALLOW-LIST in `tests/test_doc_encoder.py` enforces the absence across ALL of
`src/`, following the trafilatura bypass-guard precedent.

DEGRADATION IS EXPLICIT AND ENGLISH (DEC-44). A missing or unloadable encoder
raises `EncoderUnavailable` with a loud English log; the caller turns it into an
Arabic note. **Note the DEC-50 consequence:** DEC-44's original degradation was
"fall back to lexical-only", and DEC-50 retired the lexical half — so there is no
weaker retrieval to fall back TO. What survives is the requirement that actually
mattered: the failure is LOUD. Zone 1 (full injection) is unaffected and needs no
encoder at all, which P0 measured as the common case (2 of 3 corpus documents).

Both heavy imports are LAZY, so this module stays importable in isolation and a
process that never opens a document never pays for an ONNX runtime.
"""

from __future__ import annotations

import logging
import pathlib
import time
from typing import Any, Optional, Sequence

from .model_pin import E5_SMALL_INT8, ModelPin

logger = logging.getLogger("muthis.broker.docs")

# THE BINDING FORMAT. Constants, not literals at the call sites, so a test can
# pin them and a mutation cannot quietly delete one.
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "
POOLING = "mean"

# Batch size for passage encoding. P0 measured batching at 38.5 ms/chunk against
# 30.6 ms single — SLOWER per chunk on this int8 export — so this exists to bound
# peak memory on a long document, never as a speed optimisation.
DEFAULT_BATCH = 8


class EncoderUnavailable(Exception):
    """The encoder could not be loaded or run. LOUD, never silent (DEC-44)."""


class E5Encoder:
    """Loads the pinned int8 ONNX export and encodes text into unit vectors."""

    def __init__(self, directory: pathlib.Path, *, pin: ModelPin = E5_SMALL_INT8,
                 threads: int = 0) -> None:
        self._dir = pathlib.Path(directory)
        self._pin = pin
        self._threads = threads
        self._session: Any = None
        self._tokenizer: Any = None
        self._inputs: frozenset[str] = frozenset()
        self.load_seconds: float = 0.0

    # -- lifecycle ----------------------------------------------------------
    def load(self) -> None:
        """Build the ONNX session and the tokenizer. Raises EncoderUnavailable.

        Both imports are LAZY and live here: a process that never opens a
        document never loads an inference runtime."""
        if self._session is not None:
            return
        started = time.perf_counter()
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            onnx_name = self._pin.local_name("onnx/model_qint8_avx512_vnni.onnx")
            options = ort.SessionOptions()
            options.intra_op_num_threads = self._threads
            self._session = ort.InferenceSession(
                str(self._dir / onnx_name), options,
                providers=["CPUExecutionProvider"])
            self._tokenizer = Tokenizer.from_file(str(self._dir / "tokenizer.json"))
            self._inputs = frozenset(i.name for i in self._session.get_inputs())
        except Exception as exc:  # noqa: BLE001 — every failure is the same failure
            # ENGLISH, LOUD, and naming the cause. The Arabic the user hears is
            # the caller's job; a log that mixed the two would break the split.
            logger.error("[doc_rag] ENCODER UNAVAILABLE — dense retrieval is OFF "
                         "for this session (%s: %s)", type(exc).__name__, exc)
            raise EncoderUnavailable(str(exc)) from exc
        self.load_seconds = time.perf_counter() - started
        logger.info("[doc_rag] encoder loaded in %.0f ms (dim=%d max_seq=%d int8)",
                    self.load_seconds * 1000, self._pin.dim, self._pin.max_sequence)

    @property
    def ready(self) -> bool:
        return self._session is not None

    # -- tokenization -------------------------------------------------------
    def count_tokens(self, text: str) -> int:
        """The chunker's injected counter — the MODEL'S OWN tokenizer (DEC-45).

        Sizing with anything else is how a chunk overflows the encoder's window
        and loses its tail from the index with nothing complaining."""
        if self._tokenizer is None:
            raise EncoderUnavailable("count_tokens before load()")
        return len(self._tokenizer.encode(text).ids)

    # -- encoding -----------------------------------------------------------
    def encode_passages(self, texts: Sequence[str], *,
                        batch: int = DEFAULT_BATCH) -> Any:
        """Encode INDEXED text. Always `passage: ` prefixed (BINDING)."""
        return self._encode([PASSAGE_PREFIX + t for t in texts], batch)

    def encode_queries(self, texts: Sequence[str], *,
                       batch: int = DEFAULT_BATCH) -> Any:
        """Encode a QUESTION. Always `query: ` prefixed (BINDING)."""
        return self._encode([QUERY_PREFIX + t for t in texts], batch)

    def _encode(self, prefixed: Sequence[str], batch: int) -> Any:
        import numpy as np

        if not self.ready:
            self.load()
        if not prefixed:
            return np.zeros((0, self._pin.dim), dtype=np.float32)
        parts = [self._encode_batch(prefixed[i:i + batch])
                 for i in range(0, len(prefixed), batch)]
        return np.vstack(parts)

    def _encode_batch(self, prefixed: Sequence[str]) -> Any:
        import numpy as np

        encoded = [self._tokenizer.encode(t) for t in prefixed]
        # Truncated at the model's own maximum: past it the tail is dropped by
        # the runtime anyway, and DEC-45's chunk guard is what keeps real chunks
        # from ever reaching this line.
        limit = min(self._pin.max_sequence, max(len(e.ids) for e in encoded))
        ids = np.zeros((len(encoded), limit), dtype=np.int64)
        mask = np.zeros((len(encoded), limit), dtype=np.int64)
        for row, item in enumerate(encoded):
            take = min(len(item.ids), limit)
            ids[row, :take] = item.ids[:take]
            mask[row, :take] = 1

        feed: dict[str, Any] = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        feed = {k: v for k, v in feed.items() if k in self._inputs}

        hidden = self._session.run(None, feed)[0]
        return _mean_pool_l2(hidden, mask, np)


def _mean_pool_l2(hidden: Any, mask: Any, np: Any) -> Any:
    """MEAN pooling over the attention mask, then L2 — the card's contract.

    CLS pooling here would be silently wrong: it returns a vector of the right
    shape from the right model and simply encodes the wrong thing. (bge-m3 uses
    CLS; applying one model's contract to the other is exactly the confusion the
    P0 gate read the cards to avoid.)"""
    weights = mask[..., None].astype(hidden.dtype)
    pooled = (hidden * weights).sum(1) / np.clip(weights.sum(1), 1e-9, None)
    return pooled / np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9, None)


__all__ = [
    "DEFAULT_BATCH", "E5Encoder", "EncoderUnavailable", "PASSAGE_PREFIX",
    "POOLING", "QUERY_PREFIX",
]
