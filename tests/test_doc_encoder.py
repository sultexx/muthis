# tests/test_doc_encoder.py
"""
The dense encoder seam (V2 Phase 2 M3, T2) — format, pin, absence, isolation.

THE PREFIX TESTS ARE THE POINT OF THIS FILE. Indexing without `passage: ` does
not raise, does not warn, and does not look wrong: vectors come back the right
shape and dtype, every downstream stage reports success, and retrieval quality
degrades across EVERY result at once. There is no runtime signal at all, so the
only place the contract can be defended is here.

No model is downloaded and no ONNX session is built by these tests. The
tokenizer and session are faked, because what is under test is OUR contract —
which prefix, which pooling, which absence — not a vendor's arithmetic, which the
P0 gate already measured against the real corpus.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import numpy as np
import pytest

from muthis.broker.docs.encoder import (
    DEFAULT_BATCH, E5Encoder, EncoderUnavailable, PASSAGE_PREFIX, POOLING,
    QUERY_PREFIX, _mean_pool_l2,
)
from muthis.broker.docs.model_pin import (
    E5_SMALL_INT8, ModelFingerprintMismatch, ensure_model, verify,
)

SRC = pathlib.Path("src")


# ---------------------------------------------------------------------------
# The BINDING input format
# ---------------------------------------------------------------------------

class _CapturingEncoder(E5Encoder):
    """Records the exact strings that reach tokenization."""

    def __init__(self):
        super().__init__(pathlib.Path("."))
        self.seen: list[str] = []
        self._session = object()          # pretend loaded; _encode_batch is stubbed

    def _encode_batch(self, prefixed):
        self.seen.extend(prefixed)
        return np.zeros((len(prefixed), E5_SMALL_INT8.dim), dtype=np.float32)


def test_passages_are_prefixed_and_queries_are_prefixed_DIFFERENTLY():
    """The card's asymmetric-retrieval contract, driven at the boundary.

    Both halves in ONE test as an inequality: two separate tests could each be
    satisfied by a mutation that hard-codes the same prefix on both sides, which
    is precisely the mistake that would look fine and retrieve badly."""
    enc = _CapturingEncoder()
    enc.encode_passages(["نص المستند"])
    enc.encode_queries(["سؤال المستخدم"])

    assert enc.seen == ["passage: نص المستند", "query: سؤال المستخدم"]
    assert QUERY_PREFIX != PASSAGE_PREFIX


def test_the_prefix_constants_are_exactly_the_model_card_strings():
    """Pinned by VALUE including the trailing space — `query:` without it is a
    different token sequence, and nothing downstream would notice."""
    assert QUERY_PREFIX == "query: "
    assert PASSAGE_PREFIX == "passage: "
    assert POOLING == "mean"


def test_every_text_in_a_batch_is_prefixed_not_just_the_first():
    """A loop that prefixes only the head is a real and easy mistake, and the
    resulting index is poisoned for every chunk after the first."""
    enc = _CapturingEncoder()
    enc.encode_passages([f"قطعة {i}" for i in range(5)], batch=2)

    assert len(enc.seen) == 5
    assert all(t.startswith(PASSAGE_PREFIX) for t in enc.seen)


def test_pooling_is_MEAN_over_the_mask_and_the_result_is_unit_length():
    """CLS pooling would return a vector of the right shape from the right model
    and simply encode the wrong thing (bge-m3 uses CLS — applying one card's
    contract to the other is the confusion P0 read the cards to avoid).

    Built so CLS and MEAN differ: token 0 is deliberately not the mean."""
    hidden = np.array([[[10.0, 0.0], [0.0, 2.0], [999.0, 999.0]]])   # 3rd is masked
    mask = np.array([[1, 1, 0]])

    pooled = _mean_pool_l2(hidden, mask, np)

    expected = np.array([5.0, 1.0])
    expected = expected / np.linalg.norm(expected)
    assert np.allclose(pooled[0], expected)
    assert np.isclose(np.linalg.norm(pooled[0]), 1.0)      # L2, so dot == cosine
    assert not np.allclose(pooled[0], hidden[0][0] / np.linalg.norm(hidden[0][0]))


def test_masked_positions_do_not_contribute():
    """Padding must be invisible: including it makes every short chunk's vector
    drift toward whatever the pad embedding happens to be."""
    hidden = np.array([[[1.0, 0.0], [50.0, 50.0]]])
    unmasked = _mean_pool_l2(hidden, np.array([[1, 0]]), np)
    assert np.allclose(unmasked[0], np.array([1.0, 0.0]))


# ---------------------------------------------------------------------------
# Absence is LOUD (DEC-44)
# ---------------------------------------------------------------------------

def test_a_missing_model_raises_EncoderUnavailable_and_logs_in_ENGLISH(tmp_path, caplog):
    """DEC-50 note: DEC-44's original degradation was 'fall back to lexical-only',
    and the lexical half is retired — so there is no weaker retrieval to fall back
    TO. What survives is the requirement that mattered: the failure is LOUD."""
    caplog.set_level("ERROR")
    with pytest.raises(EncoderUnavailable):
        E5Encoder(tmp_path / "absent").load()

    records = [r for r in caplog.records if "ENCODER UNAVAILABLE" in r.message]
    assert records, "a missing encoder degraded SILENTLY"
    text = records[0].getMessage()
    assert "dense retrieval is OFF" in text
    # English only — the Arabic the user hears is the caller's job.
    assert not any("؀" <= ch <= "ۿ" for ch in text)


def test_count_tokens_before_load_is_an_error_not_a_guess(tmp_path):
    """Sizing chunks with anything but the model's own tokenizer is how a chunk
    overflows the window and loses its tail (DEC-45), so there is no fallback."""
    with pytest.raises(EncoderUnavailable):
        E5Encoder(tmp_path).count_tokens("نص")


# ---------------------------------------------------------------------------
# The fingerprint pin (DEC-3-D)
# ---------------------------------------------------------------------------

def test_a_tampered_file_FAILS_CLOSED(tmp_path):
    """Missing and WRONG are deliberately different outcomes: missing is an
    ordinary first run, wrong is a supply-chain event. Collapsing them into one
    're-download' path would let a tampered file be silently replaced."""
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    (tmp_path / "model_qint8_avx512_vnni.onnx").write_bytes(b"not the model")

    with pytest.raises(ModelFingerprintMismatch):
        verify(tmp_path)


def test_missing_files_are_reported_not_raised(tmp_path):
    missing = verify(tmp_path)
    assert set(missing) == set(E5_SMALL_INT8.files)
    assert len(missing) == 3 > 0        # admitted count, per the standing rule


def test_offline_posture_never_reaches_the_network(tmp_path):
    """A caller that must not touch the network can PROVE it."""
    with pytest.raises(FileNotFoundError):
        ensure_model(tmp_path, allow_download=False)


def test_the_pin_names_a_publisher_int8_artifact():
    """DEC-49 ruling 2: bge-m3 was disqualified partly because no publisher int8
    exists, so any pin of it would fingerprint OUR build, not the publisher's."""
    assert "qint8" in "".join(E5_SMALL_INT8.files)
    assert E5_SMALL_INT8.repo == "intfloat/multilingual-e5-small"
    assert E5_SMALL_INT8.dim == 384 and E5_SMALL_INT8.max_sequence == 512
    assert all(len(h) == 64 for h in E5_SMALL_INT8.files.values())


# ---------------------------------------------------------------------------
# THE AST ALLOW-LIST — no torch, no transformers, anywhere in src/
# ---------------------------------------------------------------------------

# Every third-party top-level module `src/` is permitted to import. An ALLOW-LIST
# and not a deny-list, following the DEC-21-E trafilatura precedent: a deny-list
# naming `torch` passes the day someone adds `sentence_transformers`, which pulls
# torch transitively — and mutation proved that exact hole real. Adding a
# dependency must be a deliberate edit HERE.
ALLOWED_THIRD_PARTY = frozenset({
    "PIL", "anthropic", "dotenv", "httpx", "mss", "numpy", "onnxruntime",
    "pynput", "pypdf", "sounddevice", "tokenizers", "trafilatura", "websockets",
    "huggingface_hub",
})

# Named for the message only — the allow-list is what enforces.
HEAVY_ML_STACK = frozenset({
    "torch", "transformers", "sentence_transformers", "optimum",
    "tensorflow", "jax", "onnx",
})


def _third_party_imports() -> dict[str, set[str]]:
    stdlib = set(sys.stdlib_module_names)
    local = {"muthis", "muthis_sdk", "muthis_plugins"}
    found: dict[str, set[str]] = {}
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules = [node.module.split(".")[0]]
            for module in modules:
                if module and module not in stdlib and module not in local:
                    found.setdefault(module, set()).add(path.as_posix())
    return found


def test_src_imports_nothing_outside_the_allow_list():
    """The guard, stated as an ALLOW-LIST so an unforeseen dependency fails too."""
    found = _third_party_imports()
    assert found, "scanned src/ and found ZERO third-party imports — the scan is broken"
    unexpected = {m: sorted(f) for m, f in found.items() if m not in ALLOWED_THIRD_PARTY}
    assert not unexpected, f"third-party imports outside the allow-list: {unexpected}"
    # Report the admitted count, per the standing cutoff rule.
    assert len(found) >= 10, f"only {len(found)} modules admitted to the scan"


def test_the_heavy_ml_stack_is_absent_from_src():
    """The DEC-44 dependency-weight rejection, stated positively as well.

    Redundant with the allow-list ON PURPOSE: this one names the modules, so the
    failure message says WHY rather than only that a set differed."""
    found = _third_party_imports()
    present = sorted(HEAVY_ML_STACK & set(found))
    assert not present, (
        f"DEC-44 rejects these on dependency weight: {present} "
        f"(in {[sorted(found[m]) for m in present]})")
    assert not (HEAVY_ML_STACK & ALLOWED_THIRD_PARTY), \
        "the allow-list itself admits a rejected dependency"


def test_the_allow_list_is_not_vacuously_wide():
    """A guard that admits everything is not a guard: the list must stay a list."""
    assert len(ALLOWED_THIRD_PARTY) < 25
    assert "torch" not in ALLOWED_THIRD_PARTY


# ---------------------------------------------------------------------------
# The index has NO WAY to persist (structural, the FetchedDomains precedent)
# ---------------------------------------------------------------------------

FORBIDDEN_IN_INDEX = frozenset({
    "open", "pathlib", "os", "json", "pickle", "shelve", "sqlite3", "shutil",
    "tempfile", "io", "save", "savez", "tofile", "dump", "dumps", "write_text",
    "write_bytes",
})


def test_the_index_module_cannot_write_to_disk():
    """Privacy proven by ABSENCE, not by policy — the `FetchedDomains` shape.

    `index.py` imports numpy and nothing else, so a user's document has no route
    to disk from here. Adding an import is what fails, never a review."""
    source = (SRC / "muthis/broker/docs/index.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0] if node.level == 0 else "<relative>")
    assert imported <= {"logging", "typing", "__future__", "<relative>"}, imported

    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    leaked = FORBIDDEN_IN_INDEX & (names | attrs)
    assert not leaked, f"the session index can reach disk via {sorted(leaked)}"


def test_the_index_ranks_and_clears(caplog):
    from muthis.broker.docs.blocks import Block, Chunk
    from muthis.broker.docs.index import IndexRegistry, SessionIndex

    chunks = [Chunk(text=f"c{i}", n_tokens=1, blocks=(Block(text=f"c{i}", page=i),))
              for i in range(3)]
    vectors = np.array([[1.0, 0.0], [0.0, 1.0], [0.7071, 0.7071]], dtype=np.float32)
    index = SessionIndex(chunks, vectors)

    hits = index.search(np.array([1.0, 0.0], dtype=np.float32), top=2)
    assert [i for i, _ in hits] == [0, 2]            # relevance order
    assert hits[0][1] > hits[1][1]

    registry = IndexRegistry()
    registry.put("doc1", index)
    assert "doc1" in registry and len(registry) == 1
    registry.clear()
    assert len(registry) == 0 and len(index) == 0


def test_the_index_refuses_a_mismatched_build():
    from muthis.broker.docs.blocks import Block, Chunk
    from muthis.broker.docs.index import SessionIndex

    chunks = [Chunk(text="a", n_tokens=1, blocks=(Block(text="a"),))]
    with pytest.raises(ValueError):
        SessionIndex(chunks, np.zeros((3, 2), dtype=np.float32))


def test_there_is_no_entry_floor(caplog):
    """DEC-49 ruling 3 RETIRED it: the distributions OVERLAP, so any floor trades
    a true hit for a false one and would HIDE content from the model."""
    from muthis.broker.docs.blocks import Block, Chunk
    from muthis.broker.docs.index import SessionIndex

    chunks = [Chunk(text="x", n_tokens=1, blocks=(Block(text="x"),))]
    index = SessionIndex(chunks, np.array([[1.0, 0.0]], dtype=np.float32))

    # A near-orthogonal query still returns its nearest chunk — nothing is hidden.
    hits = index.search(np.array([0.0, 1.0], dtype=np.float32), top=5)
    assert len(hits) == 1
    assert hits[0][1] == pytest.approx(0.0, abs=1e-6)
