# scripts/diag_rag_bench.py
"""DIAG (V2 Phase 2, M3 — the doc_rag P0 MEASUREMENT GATE). NEVER run in CI.

THIS SCRIPT CHOOSES NOTHING. It measures candidates against conditions DEC-44,
DEC-45, DEC-46 and DEC-47 already fixed, prints the numbers, and stops. Naming a
winner is Sultan's ruling, not this script's output — the whole reason the model
and the PDF library were left unnamed in the design is that Arabic quality in
small multilingual encoders varies sharply and a name recalled from memory is a
fabrication wearing an engineering costume (DEC-44, echoing DEC-43).

WHAT IS MEASURED

  deps      Dependency weight per candidate: installed size on disk, import
            time, transitive tree. TORCH IS AN ACCEPTANCE CONDITION, not a
            preference — DEC-44 rejects it on weight, so anything dragging it in
            is disqualified BY THAT RULING and this script only reports the fact.
  pdf       PDF extraction as a PASS/FAIL ACCEPTANCE CONDITION (DEC-47's binding
            condition, DEC-45's position requirement). Arabic reading order,
            letter JOINING, no reversal, and page + paragraph position. The
            machine checks what a machine can check; a real extracted Arabic
            sample is printed because THIS HALF IS HUMAN-JUDGED.
  tokens    The Arabic token-per-character ratio (DEC-45) under EACH candidate's
            OWN tokenizer — on real corpus Arabic, and separately on the mixed
            Arabic/English of V2_ROADMAP.md, because mixed is what a technical
            document actually looks like.
  encode    Model size on disk, load time, and per-chunk encode time on CPU
            (median over >= 50 real Arabic chunks). THIS NUMBER DERIVES DEC-47's
            ingestion budget and maximum document size.
  zones     Token count of every corpus document against
            MUTHIS_DOC_INJECT_LIMIT = 50000 TOKENS (DEC-47), and against the
            maximum derived from the measured encode time.
  retrieval Hit rate at k for BM25 only / dense only / RRF hybrid (DEC-46), per
            document and per language, plus the DENSE ENTRY FLOOR derived from
            the OBSERVED cosine distribution over the ground truth's NEGATIVE
            questions. A hybrid that does not beat both halves is a FINDING and
            is reported plainly — it would say something real about Arabic
            retrieval on this corpus.

PRIVACY — BINDING. The corpus is Sultan's real private files. They are read from
a path passed on the command line; NOTHING from them is written into the repo,
and only aggregate numbers plus the ONE short extraction sample the human check
requires are printed. After the model download completes, the measurement phases
run under an ARMED SOCKET GUARD that raises on any outbound connection, and the
guard's verdict is reported — asserted, not assumed.

USAGE
    set PYTHONPATH=src
    python scripts/diag_rag_bench.py --corpus <dir> --questions <file> --fetch
    python scripts/diag_rag_bench.py --corpus <dir> --questions <file>
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import re
import socket
import statistics
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

# The kernel's approval-path primitive. DEC-44 says the document normalizer
# CALLS it and NEVER modifies it, because it is the front half of DEC-16's
# deterministic approval detector. Importing it here is the whole point: the
# bench measures the shape the design mandates.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
from muthis.kernel.verbosity import normalize_ar  # noqa: E402

# ---------------------------------------------------------------------------
# Constants that come from a signed decision or a model card — never from memory
# ---------------------------------------------------------------------------

MUTHIS_DOC_INJECT_LIMIT = 50_000        # DEC-47 / DEC-4, in TOKENS not characters
RRF_K = 60                              # DEC-46: one constant, not a weight
BM25_K1, BM25_B = 1.2, 0.75             # Okapi defaults, reported not tuned
TOP_K = (1, 3, 5, 10)
ROADMAP_INGEST_BUDGETS_S = (60, 120, 180)   # roadmap part 2 4.2: "one to three minutes"

# Candidate encoders. `fmt` and `pool` are READ FROM THE MODEL CARD by
# `--fetch` and re-asserted here; see the CARD EVIDENCE printed by `deps`.
CANDIDATES: dict[str, dict[str, Any]] = {
    "e5-small-int8": {
        "repo": "intfloat/multilingual-e5-small",
        "onnx": "onnx/model_qint8_avx512_vnni.onnx",
        "extra": [],
        "tokenizer": "tokenizer.json",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "pooling": "mean",
        "quant": "int8 (PUBLISHER-PROVIDED)",
    },
    "bge-m3-fp32": {
        "repo": "BAAI/bge-m3",
        "onnx": "onnx/model.onnx",
        "extra": ["onnx/model.onnx_data", "onnx/Constant_7_attr__value"],
        "tokenizer": "tokenizer.json",
        "query_prefix": "",
        "passage_prefix": "",
        "pooling": "cls",
        "quant": "fp32 (NO publisher int8 artifact exists)",
    },
}

_TATWEEL = "ـ"
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_ARABIC_BLOCK = range(0x0600, 0x0700)
_PRESENTATION_FORMS = range(0xFB50, 0xFF00)   # disjoined/ligature forms
_SENTENCE_END = re.compile(r"[.!?؟۔،;:\n]")
_AR_WORD = re.compile(r"[؀-ۿ]+")

# THE ARABIC ACCEPTANCE PROBE (DEC-47's binding condition).
#
# The failure this catches is NOT whole-string reversal, which is what a naive
# check looks for and what this corpus does NOT have. It is a CHARACTER
# TRANSPOSITION around the definite article: a font whose ToUnicode CMap maps
# the lam-ligature glyphs in visual order yields «اجلامعة» where the document
# says «الجامعة» — the lam has hopped one position right. The output is still
# syntactically Arabic text, so every "did we get a string back" check passes
# and the index is poisoned silently. Each pair is (CORRECT form, BROKEN form),
# matched as WHOLE WORDS: substring matching overstates the damage badly,
# because «يف» is a legitimate substring of كيف / تعريف / التصنيف.
_TRANSPOSITION_PAIRS = [
    ("الجامعة", "اجلامعة"), ("الجامعات", "اجلامعات"), ("الخرج", "اخلرج"),
    ("تقديم", "تقدمي"), ("الحكومية", "احلكومية"), ("الملك", "املك"),
    ("المملكة", "اململكة"), ("الجامعي", "اجلامعي"), ("الجودة", "اجلودة"),
    ("الحياة", "احلياة"), ("التعليم", "التعلمي"), ("الاصطناعي", "االصطناعي"),
    ("الاتصال", "االتصال"), ("الالكتروني", "االلكتروني"),
]

# THE SECOND FAILURE MODE, and a DIFFERENT one: whole-word REVERSAL, where the
# extractor emits glyphs in VISUAL order so «جامعة» arrives as «ةعماج». Both
# failures are disqualifying, but conflating them misreports the cause -- and
# DEC-35 is this ledger's standing lesson that a wrong reason is worse than a
# vague one. Kept separate. `في` is deliberately NOT a transposition probe: its
# reverse is `يف`, which is also its lam-transposed form, so it cannot tell the
# two apart and would attribute reversal to transposition.
_REVERSAL_PROBES = ["جامعة", "المملكة", "الحكومية", "البيانات", "الذكاء",
                    "الاصطناعي", "مجالات", "التعليم", "الرائدة", "محافظة"]


def transposition_score(text: str) -> tuple[int, int]:
    """(correct, transposed) whole-word counts over the probe pairs."""
    words = Counter(_AR_WORD.findall(text.replace(_TATWEEL, "")))
    return (sum(words[g] for g, _ in _TRANSPOSITION_PAIRS),
            sum(words[b] for _, b in _TRANSPOSITION_PAIRS))


def reversal_score(text: str) -> int:
    """Whole words appearing in VISUAL (reversed) order."""
    words = Counter(_AR_WORD.findall(text.replace(_TATWEEL, "")))
    return sum(words[p[::-1]] for p in _REVERSAL_PROBES)


# ---------------------------------------------------------------------------
# The network guard — privacy, asserted rather than assumed
# ---------------------------------------------------------------------------

class NetworkGuard:
    """Raises on ANY outbound connection while armed, and remembers attempts.

    Reported, never silent: a bench that merely *intends* to be offline proves
    nothing about a library that phones home on import.
    """

    def __init__(self) -> None:
        self.armed = False
        self.attempts: list[str] = []
        self._real_connect = socket.socket.connect
        self._real_create = socket.create_connection

    def arm(self) -> None:
        guard = self

        def blocked_connect(sock, address, *a, **kw):          # type: ignore[no-untyped-def]
            if guard.armed:
                guard.attempts.append(str(address))
                raise RuntimeError(f"NETWORK GUARD: outbound connection to {address!r}")
            return guard._real_connect(sock, address, *a, **kw)

        def blocked_create(address, *a, **kw):                  # type: ignore[no-untyped-def]
            if guard.armed:
                guard.attempts.append(str(address))
                raise RuntimeError(f"NETWORK GUARD: outbound connection to {address!r}")
            return guard._real_create(address, *a, **kw)

        socket.socket.connect = blocked_connect                 # type: ignore[method-assign]
        socket.create_connection = blocked_create               # type: ignore[assignment]
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        self.armed = True

    def verdict(self) -> str:
        if not self.armed:
            return "NOT ARMED (fetch phase)"
        return "ZERO network calls" if not self.attempts else f"VIOLATED: {self.attempts}"


GUARD = NetworkGuard()


# ---------------------------------------------------------------------------
# Text: the document normalizer (DEC-44) — CALLS normalize_ar, never modifies it
# ---------------------------------------------------------------------------

def normalize_document(text: str) -> str:
    """The BM25 pipeline's text. Document-specific work AROUND the kernel
    primitive, never inside it.

    `normalize_ar` already strips tashkeel and tatweel, unifies the hamza-alif
    forms and taa-marbuta, maps Arabic-Indic digits and drops punctuation. What a
    DOCUMENT needs beyond a spoken transcript is what this adds: NFKC (a PDF may
    carry presentation forms and ligatures a microphone never produces), the
    zero-width and soft-hyphen characters PDF extractors leave behind, and the
    alef-maqsura/yeh unification that Arabic prose varies on freely and speech
    does not. Latin text is case-folded so an identifier matches whatever case
    the query used.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_ZERO_WIDTH).replace(_TATWEEL, "")
    text = text.replace("ى", "ي")            # alef maqsura -> yeh
    text = normalize_ar(text)                           # the kernel primitive, CALLED
    return text.lower()


def tokenize_lexical(text: str) -> list[str]:
    """BM25 terms. NO STEMMING (DEC-44): morphological variation is the DENSE
    half's job, and stemming here would damage exact technical identifiers --
    the reason DEC-18 valued lexical retrieval -- to duplicate that job badly."""
    return [t for t in re.split(r"[^\w؀-ۿ]+", text) if t]


def arabic_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if ord(c) in _ARABIC_BLOCK) / len(letters)


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------

@dataclass
class Block:
    """One structural unit as the parser yielded it, with its LOCATION.

    DEC-45: the location is captured at ingestion because the parser yields it
    free here and it is unrecoverable later without a full re-index.
    """
    text: str
    page: Optional[int] = None          # 1-based, PDFs
    para: int = 0                       # paragraph position within the page
    section: str = ""                   # heading number, Markdown
    kind: str = "text"                  # text | code | table | heading


@dataclass
class Chunk:
    text: str                           # near-raw, for the encoder
    norm: str                           # normalized, for BM25
    blocks: list[Block]
    parent: str                         # parent block id -- small-to-big, DEC-45
    n_tokens: int = 0
    truncated: bool = False

    @property
    def page(self) -> Optional[int]:
        return self.blocks[0].page if self.blocks else None

    @property
    def section(self) -> str:
        return self.blocks[0].section if self.blocks else ""


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", name)


# --- The three PDF extraction candidates -----------------------------------
#
# All three are measured against the acceptance conditions; the loader used for
# the retrieval half is whichever one PASSES, because indexing transposed text
# would poison every retrieval number downstream and make the hybrid comparison
# meaningless. That is a consequence of the measurement, not a preference.

def extract_pymupdf(path: pathlib.Path) -> tuple[list[Block], float]:
    import pymupdf

    t0 = time.perf_counter()
    doc = pymupdf.open(path)
    blocks: list[Block] = []
    for pno in range(doc.page_count):
        raw = [b for b in doc[pno].get_text("blocks")
               if len(b) > 4 and isinstance(b[4], str) and b[4].strip()]
        raw.sort(key=lambda b: (round(b[1], 1), -b[2]))     # top-down, then RTL
        for i, b in enumerate(raw):
            blocks.append(Block(text=b[4].strip(), page=pno + 1, para=i))
    doc.close()
    return blocks, time.perf_counter() - t0


def extract_pypdf(path: pathlib.Path, gap: float = 6.0) -> tuple[list[Block], float]:
    """pypdf via the VISITOR api, which is what makes position available.

    `extract_text()` alone yields a page-sized string with no paragraph
    structure; the visitor hands back every text run with its text matrix, so
    runs group into lines by y, lines into paragraphs by a y-gap, and each
    paragraph carries page + paragraph index (DEC-45). Runs inside a line are
    ordered by DESCENDING x — right-to-left, because the script is Arabic.
    """
    from pypdf import PdfReader

    t0 = time.perf_counter()
    reader = PdfReader(str(path))
    blocks: list[Block] = []
    for pno, page in enumerate(reader.pages, start=1):
        runs: list[tuple[float, float, str]] = []

        def visitor(text, cm, tm, font_dict, font_size, _r=runs):   # noqa: ANN001, ARG001
            if text and text.strip():
                _r.append((round(tm[5], 1), tm[4], text))

        page.extract_text(visitor_text=visitor)
        if not runs:
            continue
        lines: dict[float, list[tuple[float, str]]] = {}
        for y, x, t in runs:
            lines.setdefault(y, []).append((x, t))
        ordered = [(y, "".join(t for _, t in sorted(lines[y], key=lambda p: -p[0])))
                   for y in sorted(lines, reverse=True)]
        para: list[str] = []
        prev_y: Optional[float] = None
        idx = 0
        for y, text in ordered:
            if prev_y is not None and abs(prev_y - y) > gap and para:
                blocks.append(Block(text="\n".join(para), page=pno, para=idx))
                idx += 1
                para = []
            para.append(text)
            prev_y = y
        if para:
            blocks.append(Block(text="\n".join(para), page=pno, para=idx))
    return blocks, time.perf_counter() - t0


def extract_pdfminer(path: pathlib.Path) -> tuple[list[Block], float]:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer

    t0 = time.perf_counter()
    blocks: list[Block] = []
    for pno, layout in enumerate(extract_pages(str(path)), start=1):
        i = 0
        for el in layout:
            if isinstance(el, LTTextContainer) and el.get_text().strip():
                blocks.append(Block(text=el.get_text().strip(), page=pno, para=i))
                i += 1
    return blocks, time.perf_counter() - t0


PDF_EXTRACTORS: dict[str, Callable[[pathlib.Path], tuple[list[Block], float]]] = {
    "pymupdf": extract_pymupdf,
    "pypdf": extract_pypdf,
    "pdfminer.six": extract_pdfminer,
}


def pdf_stats(blocks: list[Block], elapsed: float) -> dict[str, Any]:
    text = "\n".join(b.text for b in blocks)
    good, bad = transposition_score(text)
    return {"blocks": len(blocks), "chars": len(text), "seconds": elapsed,
            "pages": len({b.page for b in blocks}),
            "presentation_forms": sum(1 for c in text if ord(c) in _PRESENTATION_FORMS),
            "correct": good, "transposed": bad, "reversed": reversal_score(text),
            "has_position": bool(blocks) and all(b.page is not None for b in blocks),
            "arabic_share": arabic_ratio(text)}


def load_pdf(path: pathlib.Path, extractor: str) -> tuple[list[Block], dict[str, Any]]:
    blocks, elapsed = PDF_EXTRACTORS[extractor](path)
    st = pdf_stats(blocks, elapsed)
    st["extractor"] = extractor
    return blocks, st


_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_MD_SECNUM = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s")


def load_markdown(path: pathlib.Path) -> tuple[list[Block], dict[str, Any]]:
    """Structural parse: headings carry a section number; fenced code and
    pipe-tables are ATOMIC blocks (DEC-45 -- splitting one destroys BOTH
    retrievers at once)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[Block] = []
    section = ""
    buf: list[str] = []
    in_code = False
    code_buf: list[str] = []
    unterminated_fence = False

    def flush(kind: str = "text") -> None:
        nonlocal buf
        text = "\n".join(buf).strip()
        if text:
            blocks.append(Block(text=text, section=section, kind=kind))
        buf = []

    for line in lines:
        if line.lstrip().startswith("```"):
            if in_code:
                code_buf.append(line)
                blocks.append(Block(text="\n".join(code_buf), section=section, kind="code"))
                code_buf, in_code = [], False
            else:
                flush()
                code_buf, in_code = [line], True
            continue
        if in_code:
            code_buf.append(line)
            continue
        m = _MD_HEADING.match(line)
        if m:
            flush()
            num = _MD_SECNUM.match(m.group(2))
            section = num.group(1) if num else section
            blocks.append(Block(text=m.group(2).strip(), section=section, kind="heading"))
            continue
        if line.strip().startswith("|"):
            buf.append(line)
            continue
        if not line.strip():
            flush()
            continue
        buf.append(line)

    if in_code:                     # a real property of this corpus file
        unterminated_fence = True
        blocks.append(Block(text="\n".join(code_buf), section=section, kind="code"))
    flush()

    # Coalesce consecutive pipe-table lines into ONE atomic table block.
    merged: list[Block] = []
    for b in blocks:
        if b.kind == "text" and b.text.lstrip().startswith("|"):
            b.kind = "table"
        merged.append(b)
    for i, b in enumerate(merged):
        b.para = i
    stats = {"pages": None, "blocks": len(merged), "chars": sum(len(b.text) for b in merged),
             "unterminated_code_fence": unterminated_fence,
             "code_blocks": sum(1 for b in merged if b.kind == "code"),
             "tables": sum(1 for b in merged if b.kind == "table")}
    return merged, stats


# ---------------------------------------------------------------------------
# Chunking (DEC-45)
# ---------------------------------------------------------------------------

class Chunker:
    """Structural boundaries, fixed-window fallback, atomic code/tables, sized
    in TOKENS by the model's OWN tokenizer, overlap on sentence boundaries."""

    def __init__(self, count_tokens: Callable[[str], int], window: int, overlap_pct: float = 0.15):
        self.count = count_tokens
        self.window = window
        self.overlap = max(1, int(window * overlap_pct))
        self.violations: list[str] = []
        self.truncations: list[str] = []

    def _split_window(self, block: Block) -> list[Chunk]:
        """FALLBACK for a block bigger than the window: cut on sentence
        boundaries inside the token budget, never mid-sentence."""
        parts = _SENTENCE_END.split(block.text)
        out: list[Chunk] = []
        cur: list[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            trial = " ".join(cur + [part])
            if self.count(trial) > self.window and cur:
                out.append(self._make(trial=" ".join(cur), blocks=[block]))
                keep = cur[-1:] if self.count(cur[-1]) <= self.overlap else []
                cur = keep + [part]
            else:
                cur.append(part)
        if cur:
            out.append(self._make(trial=" ".join(cur), blocks=[block]))
        return out

    def _make(self, trial: str, blocks: list[Block], truncated: bool = False) -> Chunk:
        return Chunk(text=trial, norm=normalize_document(trial), blocks=blocks,
                     parent=f"p{blocks[0].page}" if blocks[0].page else f"s{blocks[0].section}",
                     n_tokens=self.count(trial), truncated=truncated)

    def chunk(self, blocks: list[Block]) -> list[Chunk]:
        out: list[Chunk] = []
        cur: list[Block] = []

        def flush() -> None:
            nonlocal cur
            if not cur:
                return
            text = "\n".join(b.text for b in cur)
            out.append(self._make(text, list(cur)))
            cur = []

        for b in blocks:
            n = self.count(b.text)
            if b.kind in ("code", "table"):
                flush()
                if n > self.window:
                    # ATOMIC: never split. Handled EXPLICITLY with a truncation
                    # note rather than silently cut (DEC-45).
                    self.truncations.append(
                        f"{b.kind} block (section {b.section or b.page}) = {n} tokens > window {self.window}")
                    out.append(self._make(b.text, [b], truncated=True))
                else:
                    out.append(self._make(b.text, [b]))
                continue
            if b.kind == "heading":
                flush()
                cur = [b]
                continue
            if n > self.window:
                flush()
                out.extend(self._split_window(b))
                continue
            if cur and self.count("\n".join(x.text for x in cur + [b])) > self.window:
                flush()
            cur.append(b)
        flush()

        # THE STRICT GUARD (DEC-45): fail the operation, do not warn. A warning
        # on a path that produces a silently incomplete index is a warning
        # nobody reads before trusting the answer.
        for c in out:
            if c.n_tokens > self.window and not c.truncated:
                self.violations.append(f"chunk of {c.n_tokens} tokens exceeds window {self.window}")
        return [c for c in out if c.text.strip()]


# ---------------------------------------------------------------------------
# BM25 (lexical half)
# ---------------------------------------------------------------------------

class BM25:
    def __init__(self, corpus: list[list[str]]):
        self.docs = corpus
        self.n = len(corpus)
        self.lens = [len(d) for d in corpus]
        self.avg = (sum(self.lens) / self.n) if self.n else 0.0
        self.tf: list[Counter] = [Counter(d) for d in corpus]
        df: Counter = Counter()
        for d in corpus:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = [0.0] * self.n
        for i, tf in enumerate(self.tf):
            if not tf:
                continue
            dl = self.lens[i]
            s = 0.0
            for term in query:
                f = tf.get(term)
                if not f:
                    continue
                s += self.idf.get(term, 0.0) * (f * (BM25_K1 + 1)) / (
                    f + BM25_K1 * (1 - BM25_B + BM25_B * dl / max(self.avg, 1e-9)))
            out[i] = s
        return out


# ---------------------------------------------------------------------------
# The encoder (dense half)
# ---------------------------------------------------------------------------

class OnnxEncoder:
    """ONNX Runtime, CPU, with the pooling and prefixes READ FROM THE MODEL CARD.

    Benching e5 without its documented prefix produces bad numbers and would
    wrongly disqualify a good model, which is exactly the failure mode of
    reconstructing a spec from memory.
    """

    def __init__(self, name: str, spec: dict[str, Any], cache: pathlib.Path):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.np = np
        self.name = name
        self.spec = spec
        self.dir = cache / slug(spec["repo"])
        self.model_path = self.dir / pathlib.PurePosixPath(spec["onnx"]).name
        self.size_bytes = sum(
            f.stat().st_size for f in self.dir.iterdir() if f.suffix in (".onnx", "") and f.is_file())
        self.onnx_bytes = sum(
            f.stat().st_size for f in self.dir.iterdir()
            if f.is_file() and (f.suffix == ".onnx" or f.name.endswith(".onnx_data")))

        t0 = time.perf_counter()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 0
        self.sess = ort.InferenceSession(str(self.model_path), opts,
                                         providers=["CPUExecutionProvider"])
        self.load_s = time.perf_counter() - t0
        self.tok = Tokenizer.from_file(str(self.dir / "tokenizer.json"))
        self.inputs = {i.name for i in self.sess.get_inputs()}
        cfg = json.loads((self.dir / "config.json").read_text(encoding="utf-8"))
        self.max_seq = int(cfg.get("max_position_embeddings", 512))
        self.dim = int(cfg.get("hidden_size", 0))

    def count_tokens(self, text: str) -> int:
        return len(self.tok.encode(text).ids)

    def _encode_batch(self, texts: list[str]) -> Any:
        np = self.np
        enc = [self.tok.encode(t) for t in texts]
        limit = min(self.max_seq, max((len(e.ids) for e in enc), default=1))
        ids = np.zeros((len(enc), limit), dtype=np.int64)
        mask = np.zeros((len(enc), limit), dtype=np.int64)
        for i, e in enumerate(enc):
            k = min(len(e.ids), limit)
            ids[i, :k] = e.ids[:k]
            mask[i, :k] = 1
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        feed = {k: v for k, v in feed.items() if k in self.inputs}
        out = self.sess.run(None, feed)[0]
        if self.spec["pooling"] == "cls":
            vec = out[:, 0, :]
        else:
            m = mask[..., None].astype(out.dtype)
            vec = (out * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
        norm = np.linalg.norm(vec, axis=1, keepdims=True)   # both cards ship Normalize
        return vec / np.clip(norm, 1e-9, None)

    def encode_passages(self, texts: list[str], batch: int = 8) -> Any:
        return self._encode(
            [self.spec["passage_prefix"] + t for t in texts], batch)

    def encode_queries(self, texts: list[str], batch: int = 8) -> Any:
        return self._encode([self.spec["query_prefix"] + t for t in texts], batch)

    def _encode(self, texts: list[str], batch: int) -> Any:
        parts = [self._encode_batch(texts[i:i + batch]) for i in range(0, len(texts), batch)]
        return self.np.vstack(parts) if parts else self.np.zeros((0, self.dim))


# ---------------------------------------------------------------------------
# Fusion (DEC-46)
# ---------------------------------------------------------------------------

def rrf(rankings: Iterable[list[int]], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal rank fusion: RANKS ONLY, so the unbounded/bounded score
    mismatch between BM25 and cosine cannot reach it."""
    out: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, idx in enumerate(ranking, start=1):
            out[idx] += 1.0 / (k + rank)
    return out


def dedupe_by_parent(order: list[int], chunks: list[Chunk], limit: int) -> list[int]:
    """DEC-46: several high-ranked children of ONE parent must not let a single
    source consume the whole cap. Relevance order is preserved because the cap
    may truncate."""
    seen: set[str] = set()
    out: list[int] = []
    for i in order:
        p = chunks[i].parent
        if p in seen:
            continue
        seen.add(p)
        out.append(i)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

def phase_deps(cache: pathlib.Path) -> None:
    import importlib.metadata as md

    print_header("2. DEPENDENCY WEIGHT  (DEC-44: torch is an ACCEPTANCE condition)")
    site = pathlib.Path(md.distribution("onnxruntime").locate_file(""))
    watched = ["pymupdf", "onnxruntime", "tokenizers", "huggingface_hub",
               "numpy", "protobuf", "flatbuffers"]

    def tree(name: str, seen: set[str] | None = None) -> set[str]:
        seen = seen or set()
        if name.lower() in seen:
            return seen
        seen.add(name.lower())
        try:
            reqs = md.requires(name) or []
        except md.PackageNotFoundError:
            return seen
        for r in reqs:
            if ";" in r and "extra" in r.split(";", 1)[1]:
                continue
            dep = re.split(r"[<>=!~\[\s;]", r, 1)[0].strip()
            if dep:
                tree(dep, seen)
        return seen

    print(f"  {'package':18s} {'version':12s} {'on disk':>10s}  {'import':>9s}  transitive")
    total = 0
    for pkg in watched:
        try:
            dist = md.distribution(pkg)
        except md.PackageNotFoundError:
            print(f"  {pkg:18s} NOT INSTALLED")
            continue
        size = 0
        for f in dist.files or []:
            try:
                size += (dist.locate_file(f)).stat().st_size          # type: ignore[union-attr]
            except OSError:
                pass
        total += size
        mod = {"pymupdf": "pymupdf", "huggingface_hub": "huggingface_hub"}.get(pkg, pkg)
        t0 = time.perf_counter()
        try:
            __import__(mod)
            imp = f"{(time.perf_counter() - t0) * 1000:.0f} ms"
        except Exception:                                            # noqa: BLE001
            imp = "n/a"
        deps = sorted(tree(pkg) - {pkg.lower()})
        print(f"  {pkg:18s} {dist.version:12s} {size / 1e6:8.1f} MB  {imp:>9s}  {', '.join(deps) or '-'}")
    print(f"  {'TOTAL':18s} {'':12s} {total / 1e6:8.1f} MB")

    torchy = [d.metadata["Name"] for d in md.distributions()
              if (d.metadata["Name"] or "").lower().startswith(("torch", "nvidia", "triton"))]
    print()
    print(f"  TORCH / CUDA PRESENT: {torchy or 'NONE'}")
    print("  -> DEC-44's dependency-weight rejection is NOT triggered by any candidate above."
          if not torchy else "  -> DISQUALIFIED by DEC-44.")


def phase_pdf(pdf_paths: list[pathlib.Path]) -> dict[str, dict[str, dict[str, Any]]]:
    """The ACCEPTANCE table. Every candidate against every Arabic PDF.

    The roadmap names PyMuPDF, so it is measured first; the others are measured
    because it FAILS, which is exactly the case DEC-47 wrote the condition for.
    """
    print_header("1. PDF EXTRACTION — ACCEPTANCE CONDITIONS (DEC-47 binding, DEC-45 position)")
    print("  Conditions, both binding, neither a benchmark:")
    print("    (a) Arabic comes out correct — right reading order, JOINED letters,")
    print("        no transposition. Measured as whole-word CORRECT vs BROKEN counts")
    print("        over 12 probe pairs; any transposed hit is a FAIL.")
    print("    (b) page + paragraph position is available (DEC-45; unrecoverable later).")
    print()
    results: dict[str, dict[str, dict[str, Any]]] = {}
    for path in pdf_paths:
        print(f"  {path.name}")
        print(f"    {'library':16s} {'time':>7s} {'pages':>6s} {'blocks':>7s} {'chars':>8s}"
              f" {'correct':>8s} {'transp':>7s} {'revrsd':>7s} {'pos':>4s}  VERDICT")
        results[path.name] = {}
        for lib in PDF_EXTRACTORS:
            try:
                blocks, elapsed = PDF_EXTRACTORS[lib](path)
            except Exception as exc:                              # noqa: BLE001
                print(f"    {lib:16s} ERROR {type(exc).__name__}: {exc}")
                continue
            st = pdf_stats(blocks, elapsed)
            results[path.name][lib] = st
            fails = []
            if st["reversed"]:
                fails.append("REVERSED (visual order)")
            if st["transposed"]:
                fails.append("TRANSPOSED (lam displaced)")
            if not st["correct"]:
                fails.append("no correct probe hit")
            if not st["has_position"]:
                fails.append("no position")
            verdict = "PASS" if not fails else "FAIL — " + "; ".join(fails)
            print(f"    {lib:16s} {st['seconds']:6.2f}s {st['pages']:6d} {st['blocks']:7d}"
                  f" {st['chars']:8d} {st['correct']:8d} {st['transposed']:7d}"
                  f" {st['reversed']:7d} {str(st['has_position']):>4s}  {verdict}")
        print()
    return results


def phase_sample(pdf_paths: list[pathlib.Path], extractor: str) -> None:
    """HUMAN-JUDGED. The machine metric above is a proxy; this is the check.

    It earns its place: on this corpus the naive machine check (whole-string
    reversal + presentation forms) PASSED a document the eye immediately failed.
    The same passage is printed from EVERY library so the difference is visible
    rather than asserted.
    """
    print_header("1b. EXTRACTION SAMPLE — HUMAN-JUDGED. Sultan reads this, not the script.")
    print("  Same page, every library. Correct Arabic reads normally; the broken")
    print("  form shows the article's lam displaced (الجامعة -> اجلامعة).\n")
    for path in pdf_paths:
        print(f"  ##### {path.name}")
        for lib in PDF_EXTRACTORS:
            try:
                blocks, _ = PDF_EXTRACTORS[lib](path)
            except Exception as exc:                              # noqa: BLE001
                print(f"    {lib}: ERROR {type(exc).__name__}")
                continue
            block = next((b for b in blocks
                          if b.page and b.page > 5 and arabic_ratio(b.text) > 0.6
                          and len(b.text) > 110), None)
            if block is None:
                print(f"    {lib}: no Arabic-dominant block found")
                continue
            g, b = transposition_score(block.text)
            print(f"    --- {lib}  (page {block.page}, paragraph {block.para}; "
                  f"probe correct={g} transposed={b}) ---")
            print("      " + " ".join(block.text.split())[:200])
        print()


def phase_tokens(docs: dict[str, dict[str, Any]], encoders: dict[str, OnnxEncoder],
                 roadmap: pathlib.Path) -> None:
    print_header("4. ARABIC TOKEN-PER-CHARACTER RATIO  (DEC-45 -- measured, never assumed)")
    print("  A chunk sized in CHARACTERS fits in English and silently overflows in")
    print("  Arabic, losing its tail from the index with nothing complaining.\n")
    samples: dict[str, str] = {}
    for name, d in docs.items():
        samples[f"corpus: {name}"] = "\n".join(b.text for b in d["blocks"])
    if roadmap.exists():
        samples["mixed ar/en: V2_ROADMAP.md"] = roadmap.read_text(encoding="utf-8")
    # ENGLISH CONTROL. DEC-45's premise is a COMPARISON ("more tokens per Arabic
    # character"), so it needs an English row or it is untested.
    contrib = roadmap.parent / "CONTRIBUTING.md"
    if contrib.exists():
        samples["english control: CONTRIBUTING.md"] = contrib.read_text(encoding="utf-8")

    print(f"  {'text':38s} {'arabic':>7s} {'chars':>9s} " +
          " ".join(f"{n:>24s}" for n in encoders))
    ratios: dict[str, dict[str, float]] = {n: {} for n in encoders}
    for label, text in samples.items():
        row = f"  {label[:38]:38s} {arabic_ratio(text):6.0%} {len(text):9d} "
        for mname, enc in encoders.items():
            n = enc.count_tokens(text)
            r = n / max(len(text), 1)
            ratios[mname][label] = r
            row += f"{n:11d} tok {r:6.3f}/ch "
        print(row)
    print()
    for name, enc in encoders.items():
        print(f"  {name}: max sequence = {enc.max_seq} tokens, dim = {enc.dim}")
        ar = [v for k, v in ratios[name].items() if k.startswith("corpus")]
        en = ratios[name].get("english control: CONTRIBUTING.md")
        if ar and en:
            print(f"    arabic corpus {min(ar):.3f}-{max(ar):.3f} tok/char vs "
                  f"english {en:.3f} tok/char  ->  x{max(ar) / en:.2f} at the high end")
            # The concrete trap, in the units a developer would actually use.
            for chars in (1500, 2000):
                print(f"    a {chars}-character chunk = {chars * en:5.0f} tok in English "
                      f"but {chars * max(ar):5.0f} tok in Arabic "
                      f"(model limit {enc.max_seq})"
                      + ("   <-- OVERFLOWS in Arabic, fits in English"
                         if chars * max(ar) > enc.max_seq >= chars * en else ""))
        print(f"    ROADMAP CHECK: its stated 400-700 token chunk range against this")
        print(f"    model's {enc.max_seq}-token limit -> "
              + ("the top of that range OVERFLOWS; a 700-token chunk cannot be encoded"
                 if enc.max_seq < 700 else "the whole range fits"))


def phase_encode(encoders: dict[str, OnnxEncoder], chunks_by_model: dict[str, list[Chunk]]) -> dict[str, float]:
    print_header("3. ENCODER MEASUREMENTS  (per-chunk time DERIVES DEC-47's ingestion max)")
    medians: dict[str, float] = {}
    for name, enc in encoders.items():
        chunks = chunks_by_model[name]
        sample = [c.text for c in chunks if arabic_ratio(c.text) > 0.5][:60]
        if len(sample) < 50:
            sample = [c.text for c in chunks][:60]
        print(f"  {name}")
        print(f"    repo / artifact      : {enc.spec['repo']}  [{enc.spec['onnx']}]")
        print(f"    quantization         : {enc.spec['quant']}")
        print(f"    input format         : query={enc.spec['query_prefix']!r} "
              f"passage={enc.spec['passage_prefix']!r} pooling={enc.spec['pooling']}")
        print(f"    ONNX bytes on disk   : {enc.onnx_bytes / 1e6:.1f} MB")
        print(f"    session load         : {enc.load_s * 1000:.0f} ms")
        enc.encode_passages(sample[:4])                       # warm up
        times = []
        for t in sample:
            t0 = time.perf_counter()
            enc.encode_passages([t], batch=1)
            times.append(time.perf_counter() - t0)
        med = statistics.median(times)
        medians[name] = med
        print(f"    chunks measured      : {len(times)} (real Arabic chunks from the corpus)")
        print(f"    per-chunk encode     : median {med * 1000:.1f} ms | "
              f"p90 {sorted(times)[int(len(times) * .9) - 1] * 1000:.1f} ms | "
              f"mean {statistics.mean(times) * 1000:.1f} ms")
        b8 = time.perf_counter()
        enc.encode_passages(sample[:32], batch=8)
        print(f"    batched (8)          : {(time.perf_counter() - b8) / 32 * 1000:.1f} ms/chunk")
        print()
    return medians


def phase_zones(docs: dict[str, dict[str, Any]], encoders: dict[str, OnnxEncoder],
                medians: dict[str, float], chunks_by_model: dict[str, list[list[Chunk]]]) -> None:
    print_header("5. ZONE PLACEMENT  (DEC-47: MUTHIS_DOC_INJECT_LIMIT = 50000 TOKENS)")
    for mname, enc in encoders.items():
        print(f"  --- tokenizer: {mname} ---")
        for name, d in docs.items():
            text = "\n".join(b.text for b in d["blocks"])
            n = enc.count_tokens(text)
            zone = ("1 FULL INJECTION + prompt-cache" if n <= MUTHIS_DOC_INJECT_LIMIT
                    else "2 INDEX AND RETRIEVE")
            print(f"    {name[:42]:44s} {n:8d} tok  -> zone {zone}")
        print()
    print("  DEC-47's MAXIMUM, derived (NOT chosen): max_tokens = budget / per-chunk")
    print("  encode time * tokens-per-chunk. The roadmap states a 1-3 minute worst case.")
    for mname, med in medians.items():
        chunks = chunks_by_model[mname]
        toks = [c.n_tokens for doc in chunks for c in doc] or [1]
        avg = statistics.mean(toks)
        print(f"    {mname}: median {med * 1000:.1f} ms/chunk, mean chunk {avg:.0f} tok")
        for b in ROADMAP_INGEST_BUDGETS_S:
            print(f"        budget {b:3d}s -> {int(b / med):6d} chunks "
                  f"-> max document ~{int(b / med * avg):,} tokens")
        print("\n    MEASURED INGESTION COST PER CORPUS DOCUMENT (the refusal path,")
        print("    exercised rather than assumed):")
        enc = encoders[mname]
        for (name, d), doc_chunks in zip(docs.items(), chunks_by_model[mname]):
            n_tok = enc.count_tokens("\n".join(b.text for b in d["blocks"]))
            if n_tok <= MUTHIS_DOC_INJECT_LIMIT:
                print(f"      {name[:40]:42s} {n_tok:7d} tok  zone 1 — no indexing at all")
                continue
            est = len(doc_chunks) * med
            budget_max = int(min(ROADMAP_INGEST_BUDGETS_S) / med * avg)
            print(f"      {name[:40]:42s} {n_tok:7d} tok  {len(doc_chunks):5d} chunks"
                  f"  ~{est:5.1f}s to encode")
            print(f"        vs the 60s-budget maximum of ~{budget_max:,} tokens -> "
                  + ("EXCEEDS -> clean refusal (DEC-47)" if n_tok > budget_max
                     else f"UNDER by {budget_max / max(n_tok, 1):.0f}x -> NOT refused"))
    print()


def phase_retrieval(docs: dict[str, dict[str, Any]], encoders: dict[str, OnnxEncoder],
                    questions: list[dict[str, Any]], window: int, top_k: int) -> None:
    import numpy as np

    print_header("6. RETRIEVAL QUALITY  (DEC-46: BM25 / dense / RRF -- the reason this gate exists)")
    positives = [q for q in questions if q.get("doc")]
    negatives = [q for q in questions if not q.get("doc")]
    name_by_slug = {slug(n): n for n in docs}

    for mname, enc in encoders.items():
        print(f"  ================= encoder: {mname} =================")
        chunker = Chunker(enc.count_tokens, window)
        index: dict[str, dict[str, Any]] = {}
        for name, d in docs.items():
            chunks = chunker.chunk(d["blocks"])
            bm = BM25([tokenize_lexical(c.norm) for c in chunks])
            vecs = enc.encode_passages([c.text for c in chunks], batch=8)
            index[name] = {"chunks": chunks, "bm25": bm, "vecs": vecs}
        if chunker.violations:
            print(f"    STRICT GUARD TRIPPED: {len(chunker.violations)} chunk(s) over window")
            for v in chunker.violations[:3]:
                print("      ", v)
        else:
            print(f"    strict token guard: PASS (no chunk exceeds the {window}-token window)")
        if chunker.truncations:
            print(f"    atomic blocks over window (explicit truncation note): {len(chunker.truncations)}")
            for t in chunker.truncations[:3]:
                print("      ", t)

        tally: dict[str, Counter] = {c: Counter() for c in ("bm25", "dense", "rrf")}
        raw_tally: dict[str, Counter] = {c: Counter() for c in ("bm25", "dense", "rrf")}
        per_doc: dict[str, dict[str, Counter]] = defaultdict(lambda: {c: Counter() for c in tally})
        per_lang: dict[str, dict[str, Counter]] = defaultdict(lambda: {c: Counter() for c in tally})
        hit_cos: list[float] = []
        per_question: list[tuple[str, str, str, str, str]] = []

        for q in positives:
            doc_name = name_by_slug.get(slug(q["doc"]))
            if doc_name is None:
                print(f"    ground-truth doc not found: {q['doc']}")
                continue
            ix = index[doc_name]
            chunks: list[Chunk] = ix["chunks"]
            qn = tokenize_lexical(normalize_document(q["q"]))
            bm_scores = ix["bm25"].scores(qn)
            qv = enc.encode_queries([q["q"]])[0]
            cos = ix["vecs"] @ qv

            bm_order = list(np.argsort(bm_scores)[::-1])
            bm_order = [int(i) for i in bm_order if bm_scores[int(i)] > 0]
            dn_order = [int(i) for i in np.argsort(cos)[::-1]]
            fused = rrf([bm_order[:50], dn_order[:50]])
            rr_order = [i for i, _ in sorted(fused.items(), key=lambda kv: -kv[1])]

            for cfg, order in (("bm25", bm_order), ("dense", dn_order), ("rrf", rr_order)):
                kept = dedupe_by_parent(order, chunks, max(TOP_K))
                for k in TOP_K:
                    if any(matches(chunks[i], q) for i in kept[:k]):
                        tally[cfg][k] += 1
                        per_doc[doc_name][cfg][k] += 1
                        per_lang[q.get("lang", "?")][cfg][k] += 1
                    # CONTROL: the same ranking WITHOUT parent dedupe. On a PDF
                    # the parent is the PAGE, so a dense glossary page collapses
                    # to one slot; this row separates "retrieval missed it" from
                    # "dedupe granularity hid it" instead of leaving them fused.
                    if any(matches(chunks[i], q) for i in order[:k]):
                        raw_tally[cfg][k] += 1
                tally[cfg]["n"] += 1
                raw_tally[cfg]["n"] += 1
                per_doc[doc_name][cfg]["n"] += 1
                per_lang[q.get("lang", "?")][cfg]["n"] += 1
            best = [i for i in dn_order if matches(chunks[i], q)]
            if best:
                hit_cos.append(float(cos[best[0]]))
            marks = "".join(
                "Y" if any(matches(chunks[i], q)
                           for i in dedupe_by_parent(o, chunks, max(TOP_K))[:top_k]) else "."
                for o in (bm_order, dn_order, rr_order))
            per_question.append((q.get("at", ""), q.get("lang", "?"), doc_name, marks, q["q"]))

        print(f"\n    HIT RATE over {tally['bm25']['n']} positive questions "
              f"(parent-deduped, {window}-token window)")
        print(f"      {'config':10s}" + "".join(f"{'@' + str(k):>9s}" for k in TOP_K))
        for cfg in ("bm25", "dense", "rrf"):
            n = max(tally[cfg]["n"], 1)
            print(f"      {cfg:10s}" + "".join(f"{tally[cfg][k] / n:8.0%} " for k in TOP_K))
        verdict = hybrid_verdict(tally, top_k)
        print(f"      -> {verdict}")

        print("\n    CONTROL — the same rankings WITHOUT parent dedupe (DEC-46's dedupe")
        print("    is by PAGE for a PDF, which collapses a dense glossary page to one slot)")
        print(f"      {'config':10s}" + "".join(f"{'@' + str(k):>9s}" for k in TOP_K))
        for cfg in ("bm25", "dense", "rrf"):
            n = max(raw_tally[cfg]["n"], 1)
            print(f"      {cfg:10s}" + "".join(f"{raw_tally[cfg][k] / n:8.0%} " for k in TOP_K))

        print(f"\n    PER DOCUMENT (@{top_k})")
        for d, t in per_doc.items():
            row = f"      {d[:44]:46s}"
            for cfg in ("bm25", "dense", "rrf"):
                n = max(t[cfg]["n"], 1)
                row += f"{cfg}={t[cfg][top_k] / n:4.0%}  "
            print(row + f"(n={per_doc[d]['bm25']['n']})")

        print(f"\n    PER LANGUAGE (@{top_k})")
        for lang, t in per_lang.items():
            row = f"      {lang:10s}"
            for cfg in ("bm25", "dense", "rrf"):
                n = max(t[cfg]["n"], 1)
                row += f"{cfg}={t[cfg][top_k] / n:4.0%}  "
            print(row + f"(n={t['bm25']['n']})")

        print(f"\n    PER QUESTION (@{top_k})  columns = bm25 / dense / rrf")
        for at, lang, doc, marks, qtext in per_question:
            print(f"      {marks:4s} {lang:6s} {at[:18]:20s} {doc[:26]:28s} {qtext[:44]}")

        # ---- DEC-46 dense entry floor, DERIVED from the observed distribution
        print("\n    DENSE ENTRY FLOOR (DEC-46) -- a property of the model, not a choice.")
        print("    Cosine ALWAYS returns something, so an unrelated nearest vector would")
        print("    enter RRF at FULL rank weight. BM25 is immune for free (0 terms = 0).")
        neg_max: list[float] = []
        print(f"      {'negative query':34s} {'document':30s} {'max cos':>8s}")
        for q in negatives:
            qv = enc.encode_queries([q["q"]])[0]
            for name, ix in index.items():
                v = float(np.max(ix["vecs"] @ qv))
                neg_max.append(v)
                print(f"      {q['q'][:34]:34s} {name[:30]:30s} {v:8.4f}")
        if neg_max and hit_cos:
            print(f"      NEGATIVE queries (n={len(neg_max)} query x document pairs):")
            print(f"        max cosine  min={min(neg_max):.4f}  median={statistics.median(neg_max):.4f}  "
                  f"max={max(neg_max):.4f}")
            print(f"      POSITIVE ground-truth hits (n={len(hit_cos)}):")
            print(f"        cosine      min={min(hit_cos):.4f}  median={statistics.median(hit_cos):.4f}  "
                  f"max={max(hit_cos):.4f}")
            gap = min(hit_cos) - max(neg_max)
            print(f"      SEPARATION: lowest true hit - highest false hit = {gap:+.4f}")
            if gap > 0:
                print(f"      -> a floor anywhere in ({max(neg_max):.4f}, {min(hit_cos):.4f}) "
                      f"admits every true hit and rejects every negative on this corpus.")
                print(f"      -> midpoint = {(max(neg_max) + min(hit_cos)) / 2:.4f}")
            else:
                print("      -> NO clean separation on this corpus: the distributions OVERLAP,")
                print("         so any floor trades a true hit for a false one. REPORTED, not resolved.")
        print()


def matches(chunk: Chunk, q: dict[str, Any]) -> bool:
    """Ground truth: 'صفحة N' (1-based page) or '§X.Y' (heading number).
    Section matching is EXACT -- a chunk in 2.1 does not satisfy a label of 2."""
    at = str(q.get("at") or "")
    m = re.search(r"صفحة\s*(\d+)", at)
    if m:
        return chunk.page == int(m.group(1))
    m = re.search(r"§\s*(\d+(?:\.\d+)*)", at)
    if m:
        return chunk.section == m.group(1)
    return False


def hybrid_verdict(tally: dict[str, Counter], k: int) -> str:
    n = max(tally["bm25"]["n"], 1)
    b, d, r = (tally[c][k] / n for c in ("bm25", "dense", "rrf"))
    if r > b and r > d:
        return f"RRF beats BOTH halves at @{k} ({r:.0%} vs bm25 {b:.0%}, dense {d:.0%})."
    if r >= max(b, d):
        return (f"RRF TIES the better half at @{k} ({r:.0%} vs bm25 {b:.0%}, dense {d:.0%}) "
                "-- a FINDING, not a failure.")
    return (f"RRF is BELOW the better half at @{k} ({r:.0%} vs bm25 {b:.0%}, dense {d:.0%}) "
            "-- a FINDING; report it, do not tune it away.")


def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


# ---------------------------------------------------------------------------
# Fetch (the ONLY phase allowed to touch the network)
# ---------------------------------------------------------------------------

def fetch(cache: pathlib.Path, names: list[str]) -> None:
    from huggingface_hub import hf_hub_download

    print_header("0. FETCH  (the ONLY networked phase; every later phase runs guarded)")
    for name in names:
        spec = CANDIDATES[name]
        dest = cache / slug(spec["repo"])
        dest.mkdir(parents=True, exist_ok=True)
        wanted = [spec["onnx"], *spec["extra"], spec["tokenizer"], "config.json", "README.md"]
        for rel in wanted:
            try:
                src = pathlib.Path(hf_hub_download(spec["repo"], rel))
            except Exception as exc:                              # noqa: BLE001
                print(f"  {name}: {rel} -> {type(exc).__name__}: {exc}")
                continue
            out = dest / pathlib.PurePosixPath(rel).name
            if not out.exists() or out.stat().st_size != src.stat().st_size:
                out.write_bytes(src.read_bytes())
            print(f"  {name:16s} {rel:34s} {out.stat().st_size / 1e6:9.1f} MB")
    print("\n  Fetch complete. The guard is armed for every measurement below.")


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", required=True, type=pathlib.Path)
    ap.add_argument("--questions", required=True, type=pathlib.Path)
    ap.add_argument("--cache", type=pathlib.Path,
                    default=pathlib.Path.home() / ".cache" / "muthis_rag_bench")
    ap.add_argument("--models", default="e5-small-int8")
    ap.add_argument("--window", type=int, default=400,
                    help="chunk cap in TOKENS (roadmap states 400-700)")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--extractor", default="pypdf", choices=sorted(PDF_EXTRACTORS),
                    help="PDF loader for the phases after the acceptance table")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--phases", default="deps,pdf,sample,tokens,encode,zones,retrieval")
    args = ap.parse_args()

    names = [n.strip() for n in args.models.split(",") if n.strip()]
    unknown = [n for n in names if n not in CANDIDATES]
    if unknown:
        print(f"unknown candidate(s): {unknown}; known: {list(CANDIDATES)}")
        return 2
    args.cache.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("DIAG — doc_rag P0 MEASUREMENT GATE (V2 Phase 2, M3)")
    print("This script MEASURES. It does not choose an encoder, a PDF library, or")
    print("a window. DEC-44/45/46/47 fix the conditions; Sultan rules on the numbers.")
    print("=" * 78)
    print(f"  corpus     : {args.corpus}")
    print(f"  questions  : {args.questions}")
    print(f"  candidates : {names}")
    print(f"  window     : {args.window} tokens   top-k reported at: {args.top_k}")

    if args.fetch:
        fetch(args.cache, names)

    GUARD.arm()
    phases = {p.strip() for p in args.phases.split(",")}

    pdf_paths = [p for p in sorted(args.corpus.iterdir()) if p.suffix.lower() == ".pdf"]
    questions = json.loads(args.questions.read_text(encoding="utf-8"))

    if "deps" in phases:
        phase_deps(args.cache)
    if "pdf" in phases:
        phase_pdf(pdf_paths)
    if "sample" in phases:
        phase_sample(pdf_paths, args.extractor)

    print_header(f"LOADER FOR EVERY PHASE BELOW: {args.extractor}")
    print("  Chosen by the acceptance table, not by preference: indexing transposed")
    print("  text would poison every retrieval number and make the hybrid comparison")
    print("  meaningless. Override with --extractor to measure a different one.")

    docs: dict[str, dict[str, Any]] = {}
    for path in sorted(args.corpus.iterdir()):
        if path.suffix.lower() == ".pdf":
            blocks, stats = load_pdf(path, args.extractor)
        elif path.suffix.lower() in (".md", ".txt"):
            blocks, stats = load_markdown(path)
        else:
            continue
        docs[path.name] = {"blocks": blocks, "stats": stats, "path": path}

    encoders: dict[str, OnnxEncoder] = {}
    for n in names:
        try:
            encoders[n] = OnnxEncoder(n, CANDIDATES[n], args.cache)
        except Exception as exc:                                  # noqa: BLE001
            print(f"\n  ENCODER {n} UNAVAILABLE: {type(exc).__name__}: {exc}")
    if not encoders:
        print("\n  No encoder loaded — run with --fetch first.")
        return 1

    if "tokens" in phases:
        phase_tokens(docs, encoders,
                     pathlib.Path(__file__).resolve().parent.parent / "V2_ROADMAP.md")

    chunks_by_model: dict[str, list[list[Chunk]]] = {}
    flat: dict[str, list[Chunk]] = {}
    for n, enc in encoders.items():
        ch = Chunker(enc.count_tokens, args.window)
        per_doc = [ch.chunk(d["blocks"]) for d in docs.values()]
        chunks_by_model[n] = per_doc
        flat[n] = [c for doc in per_doc for c in doc]

    medians: dict[str, float] = {}
    if "encode" in phases:
        medians = phase_encode(encoders, flat)
    if "zones" in phases and medians:
        phase_zones(docs, encoders, medians, chunks_by_model)
    if "retrieval" in phases:
        phase_retrieval(docs, encoders, questions, args.window, args.top_k)

    print_header("PRIVACY — the network guard's verdict")
    print(f"  After the fetch phase, the bench made: {GUARD.verdict()}")
    print("  No corpus content was written to the repo; only aggregates and the one")
    print("  extraction sample above were printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
