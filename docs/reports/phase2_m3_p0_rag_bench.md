# Phase 2 — Milestone 3 (`doc_rag`) — P0 MEASUREMENT GATE REPORT

- **Project:** Mut'his V2
- **Milestone:** Phase 2, Milestone 3 — `doc_rag` (NOT OPENED; no implementation exists)
- **Branch:** `main` (script only, `scripts/diag_rag_bench.py`; **zero changes to `src/`**)
- **Status:** **MEASURED — awaiting Sultan's rulings.** This report chooses nothing.
- **Written:** 2026-07-29 (English, UTF-8)
- **Authority:** `DECISIONS.md` DEC-44, DEC-45, DEC-46, DEC-47 fix the conditions. This
  report supplies the numbers those decisions deferred to P0. It is not itself a decision.
- **Hardware:** Windows 11, Intel i7-13620H, 15.7 GB RAM, Python 3.14.4, `.venv`

> **On corpus privacy.** The corpus is Sultan's real private files, read from a path
> outside the repo. No corpus text, and no corpus filename, appears in this report —
> documents are described by shape only. The one Arabic extraction sample the human
> acceptance check requires is printed by the script at runtime and is deliberately
> NOT reproduced here, because this file is committed and that sample is not.

---

## 1. What this gate produced

Four numbers DEC-44/45/47 deferred, one property DEC-46 asked to be derived, and
**one acceptance failure that overturns the roadmap's named candidate**.

| # | Question the design deferred | Measured answer |
|---|---|---|
| 1 | Which PDF library? | **PyMuPDF — the roadmap's candidate — FAILS the binding Arabic condition on BOTH PDFs.** `pypdf` is the only candidate passing both conditions on both files. |
| 2 | Which encoder? | Both roadmap candidates measured. **e5-small int8: 118 MB, 30.6 ms/chunk, 76 % @5. bge-m3: 2,268 MB, 558 ms/chunk, 82 % @5, and NO publisher int8 artifact exists.** |
| 3 | Arabic token-per-character ratio | **0.269–0.326 tok/char**, vs **0.295** for English → **×1.11 at the high end, far weaker than DEC-45's rationale assumes.** Identical under both tokenizers. |
| 4 | Per-chunk encode time → ingestion max | **30.6 ms** (e5) → ≈745,000 tokens; **558.4 ms** (bge-m3) → ≈40,830 tokens, at a 60 s budget. |
| 5 | Dense entry floor (DEC-46) | **NOT DERIVABLE under either model.** Positive and negative cosine distributions overlap by 0.11 (e5) and 0.20 (bge-m3). |

Plus three findings nobody asked for, which is usually where the value is:

- **The refusal path is reachable under one encoder and unreachable under the other** —
  and under bge-m3 at a 60 s budget **zone 2 is empty**, because the derived maximum
  (40,830 tokens) falls *below* `MUTHIS_DOC_INJECT_LIMIT` (50,000). See §7.
- **RRF never beats dense alone**, under either encoder, at any k — and the gap widens
  as the dense half gets better. See §8.
- **The automated Arabic-correctness check was too weak, and the human sample caught it
  on the first run.** See §4.

**The headline is #1.** DEC-47 wrote its acceptance condition — *"it must work on a real
Arabic PDF"* — precisely because a library that works in English can fail in Arabic. That
is exactly what happened, to the library the roadmap names.

---

## 2. Corpus and ground truth

| Document | Shape | Pages | Extracted chars |
|---|---|---|---|
| A | Arabic/English technical glossary, PDF | 228 (223 with a text layer) | 384,288 |
| B | Arabic institutional booklet, PDF | 66 (60 with a text layer) | 31,350 |
| C | Mixed Arabic/English technical Markdown | — | 2,788 |

Ground truth: **17 positive** questions (`doc`, `q`, `at`) and **3 negative** questions
(`doc: null`, `at: null`). `at` is `صفحة N` (1-based page) or a `§X.Y` heading.

**Ground truth was verified before it was trusted:** all 12 positive PDF labels were
confirmed to actually carry their answer on the cited page. A benchmark scored against
unverified labels measures the labels, not the system.

**One discrepancy, reported not silently fixed:** the ground truth names document B by a
slugified filename that does not match the file on disk (`.` and spaces replaced by `_`).
The mapping is unique and the bench resolves it by slug with a uniqueness assertion.

**A second discrepancy:** the P0 brief describes "the 232-page PDF". The document
measures **228 pages**. Everything below uses the measured value.

---

## 3. Dependencies installed (recorded, NOT added to `AGENTS.md`)

Per the constraint, these are recorded here only; the install line changes when a
candidate is chosen.

| Package | Version | On disk | Import | Transitive |
|---|---|---|---|---|
| `pymupdf` | 1.28.0 | 55.3 MB | 0 ms | — |
| `onnxruntime` | 1.28.0 | 45.1 MB | 264 ms | flatbuffers, numpy, packaging, protobuf |
| `tokenizers` | 0.23.1 | 8.0 MB | 121 ms | huggingface-hub, httpx, pyyaml, tqdm, … |
| `huggingface_hub` | 1.25.1 | 7.0 MB | 0 ms | httpx, filelock, fsspec, pyyaml, tqdm |
| `numpy` | 2.4.6 | 43.2 MB | (present) | — |
| `protobuf` | 7.35.1 | 2.7 MB | — | — |
| `flatbuffers` | 25.12.19 | 0.2 MB | 6 ms | — |
| **Total** | | **161.5 MB** | | |

Added later for the extraction comparison: `pypdf` 6.14.2, `pdfminer.six` 20260107
(pulls `cryptography` 49.0.0).

**`transformers` was deliberately NOT installed.** `tokenizers` alone loads each model's
own `tokenizer.json`, which is all the bench needs, and it avoids the heavier package.

### The torch condition — DEC-44

**`TORCH / CUDA PRESENT: NONE`.** No candidate above pulls `torch`, `nvidia-*` or
`triton`, directly or transitively. **DEC-44's dependency-weight rejection is not
triggered by anything measured here.** This was achieved by using **publisher-provided
ONNX artifacts** rather than exporting with `optimum`, which would have required torch
as a build dependency. That is a real constraint on candidate selection, not a detail:
**a model with no pre-exported ONNX cannot be adopted without either torch at build time
or a locally-produced artifact that the publisher never fingerprinted.**

---

## 4. PDF extraction — ACCEPTANCE CONDITION (DEC-47 binding, DEC-45 position)

Two binding conditions, neither a benchmark:
**(a)** Arabic comes out correct — reading order, joined letters, no transposition.
**(b)** page + paragraph position is available (DEC-45: unrecoverable later).

### Document A (228 pages)

| Library | Time | Blocks | Correct | Transposed | Reversed | Position | Verdict |
|---|---|---|---|---|---|---|---|
| `pymupdf` 1.28.0 | 0.19 s | 6,145 | 11 | **109** | 0 | yes | **FAIL — transposed** |
| `pypdf` 6.14.2 | 2.60 s | 7,243 | 121 | 0 | 0 | yes | **PASS** |
| `pdfminer.six` | 4.87 s | 10,477 | 0 | 2 | **718** | yes | **FAIL — reversed** |

### Document B (66 pages)

| Library | Time | Blocks | Correct | Transposed | Reversed | Position | Verdict |
|---|---|---|---|---|---|---|---|
| `pymupdf` 1.28.0 | 0.09 s | 587 | 21 | **107** | 0 | yes | **FAIL — transposed** |
| `pypdf` 6.14.2 | 1.03 s | 565 | 127 | 0 | 0 | yes | **PASS** |
| `pdfminer.six` | 1.83 s | 546 | 0 | 0 | **59** | yes | **FAIL — reversed** |

### The two failure modes are DIFFERENT, and naming them correctly matters

- **TRANSPOSITION (PyMuPDF).** The definite article's *lam* hops one position:
  `الجامعة` arrives as `اجلامعة`, `الاصطناعي` as `االصطناعي`. Caused by fonts whose
  ToUnicode CMap maps lam-ligature glyphs in visual order.
- **REVERSAL (pdfminer.six).** Whole words emitted in visual order: `جامعة` → `ةعماج`.

Both produce **syntactically valid Arabic text**. Every "did we get a string back" check
passes, and the index is poisoned silently — which is exactly why DEC-47 made this an
acceptance condition rather than a benchmark. Reporting them as one failure would repeat
**DEC-35's** defect: a wrong reason is worse than a vague one.

### No PyMuPDF configuration rescues it

All six extraction modes were measured on document B — `text` default,
`TEXT_PRESERVE_LIGATURES`, ligatures off, `TEXT_PRESERVE_WHITESPACE`, `words`, `rawdict`.
**All six fail identically** (≈5 correct / ≈49 transposed). The failure is the library's
glyph mapping for these fonts, not a flag.

### The machine check was NOT sufficient — and this is the finding about method

The first version of the acceptance metric (whole-string reversal + presentation-form
count) **PASSED document A under PyMuPDF**. The human-judged sample failed it instantly:
`االصطناعي` was visible in the first printed line. The probe set was then widened, and the
corrected metric fails PyMuPDF on **both** documents.

**DEC-47's instruction to make this half human-judged earned its place on the first run.**
An automated Arabic-correctness check is a proxy, and this one was measurably too weak
before a human looked at the output.

### Position availability

`pypdf`'s `extract_text()` alone yields a page-sized string with no paragraph structure.
Position comes from its **visitor API**, which returns every text run with its text
matrix — runs group into lines by *y*, lines into paragraphs by a *y*-gap, and each
paragraph carries page + paragraph index. Measured: **565 blocks over 60 pages** (B) and
**7,243 blocks over 223 pages** (A), page and paragraph present on every block, and the
visitor-assembled text keeps the correctness that `extract_text()` has (0 transposed).
Bounding boxes are derivable from the same matrices, which Phase 3's visual citation
needs. **This is assembly work `pypdf` does not do for you** — a real cost to weigh.

---

## 5. Arabic token-per-character ratio (DEC-45)

Measured with the candidate's **own** tokenizer.

| Text | Arabic share | Chars | Tokens | tok/char |
|---|---|---|---|---|
| Corpus doc C (md) | 69 % | 2,788 | 909 | **0.326** |
| Corpus doc B (pdf) | 97 % | 31,350 | 9,945 | **0.317** |
| Corpus doc A (pdf) | 44 % | 384,288 | 103,187 | **0.269** |
| `V2_ROADMAP.md` (mixed ar/en) | 76 % | 34,237 | 12,262 | **0.358** |
| `CONTRIBUTING.md` (English control) | 0 % | 3,452 | 1,017 | **0.295** |

### DEC-45's RULE is right; its stated REASON is much weaker than written

DEC-45 says *"multilingual tokenizers emit MORE tokens per Arabic character"*, and treats
that as the reason to measure in tokens. **Measured, the factor is ×1.11 at the high end**
— and the most Arabic-dense document in the corpus (97 % Arabic) has a **lower**
tok/char ratio (0.317) than the **mixed** technical document (0.358). The highest ratio
in the whole set belongs to the mixed Arabic/English roadmap, not to Arabic prose.

**The rule survives intact and should not be relaxed** — sizing in tokens is still the
only correct unit, and the overflow it prevents is real:

> a 1,500-character chunk = **442 tokens in English** but **489 in Arabic** (limit 512)
> a 2,000-character chunk = **589 tokens in English** but **652 in Arabic** — both overflow

But the *driver* is token density generally (markup, identifiers, punctuation), not
Arabic specifically. **This is a correction to a rationale recorded in a signed decision,
and it is reported rather than quietly absorbed.**

**The ratios came out identical under both candidates** — every token count in the table
above is the same digit-for-digit for `multilingual-e5-small` and `bge-m3` (909 / 9,945 /
103,187 / 12,262 / 1,017). Both repositories ship a 5.1 MB `sentencepiece.bpe.model` and a
17.1 MB `tokenizer.json`, so the two are evidently the same SentencePiece vocabulary and
the ratio is a property of that vocabulary rather than of either model. DEC-45's rule —
measure with "the model's own tokenizer" — remains correct; on these two candidates it
happens to give the same answer, which is a fact about this pair and not a general one.

### A hard conflict with the roadmap — measured

`multilingual-e5-small` has a **512-token maximum sequence length**. The roadmap
(part 2 §4.2) specifies chunks of **400–700 tokens**. **The top of that range cannot be
encoded by this model** — a 700-token chunk is truncated at 512 and its tail never enters
the index, silently. This is precisely the failure DEC-45's strict guard exists to catch.
The bench runs at a **400-token window**, which is inside both.

---

## 6. Encoder measurements

### Candidate 1 — `intfloat/multilingual-e5-small`, int8

| Property | Value |
|---|---|
| Artifact | `onnx/model_qint8_avx512_vnni.onnx` — **publisher-provided int8** |
| Size on disk | **118.3 MB** |
| Session load | **226–241 ms** |
| Dimension / max sequence | 384 / **512** |
| **Per-chunk encode (median)** | **30.6 ms** (p90 32.6 ms, mean 27.9 ms), n = 60 real Arabic chunks |
| Batched (8) | 38.5 ms/chunk — **batching is SLOWER per chunk here** |

**Input format — read from the model card, not from memory.** The card states:
*"Each input text should start with `query: ` or `passage: `, even for non-English texts"*,
and *"use `query: ` and `passage: ` correspondingly for asymmetric tasks such as passage
retrieval in open QA"* — which is exactly this use. Pooling is **mean**
(`1_Pooling/config.json`: `pooling_mode_mean_tokens: true`), followed by L2 normalisation
(`modules.json` includes `Normalize`). Benching without the prefixes would have produced
bad numbers and could have wrongly disqualified the model.

### Candidate 2 — `BAAI/bge-m3`

**A measured supply-chain finding, before any speed number:** the official repository ships
**no int8 artifact**. It provides `onnx/model.onnx` (0.7 MB graph) plus
`onnx/model.onnx_data` (**2,266.8 MB** external data) — fp32 only. DEC-44 specifies an
**int8-quantized** model, so bge-m3 cannot satisfy that clause from the publisher's own
artifacts. The options are (a) measure it at fp32, (b) quantize locally, or (c) use a
community re-upload. Option (c) collides with DEC-44's *"pinned by fingerprint"*: a hub
search returns a dozen community ONNX/int8 forks with 0–582 downloads and no provenance,
and pinning one of those fingerprints a stranger's build, not the publisher's.

**Measured at fp32**, since that is the artifact that actually exists:

| Property | Value |
|---|---|
| Artifact | `onnx/model.onnx` + `model.onnx_data` — **fp32, no publisher int8** |
| Size on disk | **2,267.5 MB** (≈ 19× e5-small int8) |
| Dimension / max sequence | 1,024 / 8,192 |

| Property | Value |
|---|---|
| Session load | **1,475 ms** (6× e5-small) |
| **Per-chunk encode (median)** | **558.4 ms** — **18× slower than e5-small int8** |
| p90 / mean | 1,804.8 ms / 777.9 ms — **very high variance** |
| Batched (8) | 786.5 ms/chunk — batching is slower here too |

**Input format — read from the model card, not from memory.** The bge-m3 card documents
**no prefix** (its only match for "prefix" is a bibtex `archivePrefix`), and
`1_Pooling/config.json` specifies **CLS** pooling (`pooling_mode_cls_token: true`), with
`Normalize` in `modules.json`. The two candidates therefore need **different** input
handling — prefix + mean pooling versus no prefix + CLS pooling. Applying e5's contract to
bge-m3, or the reverse, would have produced quietly wrong vectors and a bad comparison.

### The two candidates, side by side

| | e5-small int8 | bge-m3 fp32 |
|---|---|---|
| Disk | **118 MB** | 2,268 MB (**19×**) |
| Load | **226 ms** | 1,475 ms |
| Per chunk | **30.6 ms** | 558.4 ms (**18×**) |
| Dim / max seq | 384 / 512 | 1,024 / **8,192** |
| int8 available | **yes, publisher** | **no** |
| Dense hit @5 | 76 % | **82 %** |
| Dense hit @1 | 47 % | **71 %** |
| Arabic-only @5 | 62 % | **75 %** |

**bge-m3 is clearly the better retriever and clearly the more expensive one.** That is the
trade DEC-44 anticipated when the roadmap offered it as the "higher quality, longer index
time" option — now with numbers on both sides.

---

## 7. Zone placement (DEC-47)

`MUTHIS_DOC_INJECT_LIMIT = 50,000` **tokens** (DEC-4's value, unit corrected in DEC-47).

| Document | Tokens | Zone |
|---|---|---|
| C (md) | 909 | **1 — full injection + prompt-cache**, no indexing at all |
| B (66 pp) | 9,945 | **1 — full injection + prompt-cache**, no indexing at all |
| A (228 pp) | 103,187 | **2 — index and retrieve** |

**Two of the three corpus documents never touch the index.** This is direct support for
DEC-47's build order: zone 1 is the common path, and it is both the cheapest and the most
accurate.

### The derived maximum, and the refusal path — exercised, not assumed

`max_tokens = ingestion_budget ÷ per-chunk encode time × tokens-per-chunk`, at a mean
chunk of 380 tokens. **The maximum is a function of the encoder, so it differs by 18×
between the two candidates:**

| Budget | e5-small int8 (30.6 ms) | bge-m3 fp32 (558.4 ms) |
|---|---|---|
| 60 s | 1,961 chunks → **≈ 745,000 tokens** | 107 chunks → **≈ 40,830 tokens** |
| 120 s | 3,923 → ≈ 1,491,000 | 214 → ≈ 81,660 |
| 180 s | 5,884 → ≈ 2,236,000 | 322 → ≈ 122,490 |

**The refusal path is exercised under one candidate and unreachable under the other** —
the same 228-page document, the same corpus:

- **e5-small int8:** 103,187 tokens vs ≈745,000 → **7× UNDER, not refused.** Encodes in
  **≈ 8.2 s** (267 chunks) plus ≈2.6 s to parse. The refusal threshold sits near a
  ~1,600-page document, so DEC-47's third zone is real but far away.
- **bge-m3 fp32:** the same document needs **≈ 149.1 s** to encode → **EXCEEDS the 60 s
  budget maximum → CLEAN REFUSAL (DEC-47).**

### A structural finding: with a slow encoder, ZONE 2 CAN BE EMPTY

`MUTHIS_DOC_INJECT_LIMIT` is 50,000 tokens, and zone 2 is the band between that limit and
the derived maximum. **For bge-m3 at a 60 s budget the derived maximum is ≈ 40,830 tokens
— BELOW the injection limit.** The band is negative: every document large enough to need
an index is already too large to build one, so **the three-zone design collapses to two,
with no retrieval path at all.**

| Encoder / budget | Zone 2 band (tokens) | Width |
|---|---|---|
| e5-small, 60 s | 50,000 → 745,000 | wide |
| bge-m3, 60 s | 50,000 → 40,830 | **EMPTY (inverted)** |
| bge-m3, 120 s | 50,000 → 81,660 | narrow |
| bge-m3, 180 s | 50,000 → 122,490 | moderate |

This is not a defect in DEC-47 — the decision derives the maximum from measured encode
time exactly so this is visible rather than discovered in production. But it means
**`MUTHIS_DOC_INJECT_LIMIT` and the ingestion budget are not independent knobs**: the pair
must satisfy `budget ÷ per-chunk-time × tokens-per-chunk > MUTHIS_DOC_INJECT_LIMIT`, or
the middle zone does not exist. That relation is not currently written down anywhere.

The roadmap's own estimate — a 400-page book at 1–3 minutes — is **≈10× pessimistic for
e5-small** (228 pages in ~11 s end to end) and **roughly right for bge-m3** (~149 s).

---

## 8. Retrieval quality (DEC-46) — the reason this gate exists

17 positive questions, per-document indexes (matching DEC-47's `docs.open`/`docs.query`
shape), 400-token window, structural chunking (DEC-45), no stemming (DEC-44), two
pipelines (normalised text for BM25, near-raw for the encoder).

**Strict token guard: PASS** — no chunk exceeded the window after tokenization.

### Hit rate — both candidates

**`multilingual-e5-small` int8**

| Config | @1 | @3 | @5 | @10 |
|---|---|---|---|---|
| BM25 only | 29 % | 47 % | 65 % | 76 % |
| **Dense only** | **47 %** | **71 %** | **76 %** | **82 %** |
| RRF hybrid | 41 % | 65 % | 76 % | 76 % |

**`bge-m3` fp32**

| Config | @1 | @3 | @5 | @10 |
|---|---|---|---|---|
| BM25 only | 29 % | 47 % | 65 % | 76 % |
| **Dense only** | **71 %** | **71 %** | **82 %** | **82 %** |
| RRF hybrid | 47 % | 71 % | 76 % | 76 % |

(BM25 is identical across the two, as it must be — it does not use the encoder. It is a
useful control that the harness is behaving.)

### THE FINDING: the hybrid never beats dense alone — under EITHER encoder

- **e5-small:** RRF ties dense at @5, and is **worse** at @1, @3 and @10.
- **bge-m3:** RRF is **worse than dense at every single k** — 47 % vs 71 % at @1, and
  76 % vs 82 % at @5.

**The stronger the dense half, the more the hybrid costs.** With bge-m3 the gap at @1 is
24 points, because RRF's rank-only fusion gives the weak half **equal weight by
construction**. That is precisely the property DEC-46 chose RRF *for* — immunity to
incomparable score scales — and the same property is what destroys precision when the two
halves are not comparably strong. The decision's reasoning is sound; its premise (two
comparably useful retrievers) does not hold on this corpus.

**A confound was ruled out, not assumed away.** Because the parent for a PDF chunk is the
page, a dense glossary page collapses to one slot under DEC-46's parent dedupe. The same
rankings were therefore scored **without** dedupe as a control: **the numbers are identical
at every k**. The misses are genuine retrieval failures, not a dedupe artifact.

### Per document — and this CONFIRMS DEC-44's no-stemming reasoning

| Document | BM25 @5 | Dense @5 (e5) | Dense @5 (bge-m3) | n |
|---|---|---|---|---|
| A — Arabic/English glossary | 50 % | 67 % | 67 % | 6 |
| B — Arabic booklet | 50 % | 67 % | **83 %** | 6 |
| **C — technical Markdown** | **100 %** | 100 % | 100 % | 5 |

DEC-44 refused stemming on the argument that BM25's unique strength is **exact technical
identifiers**, and that morphology belongs to the dense half. **The measurement matches
the argument exactly**: BM25 scores **100 %** on the document full of `L298N`, `BTS7960`,
`RPWM`, `safe_mode` — and **50 %** on both Arabic prose documents, where inflection
defeats unstemmed lexical matching. The decision's reasoning is confirmed on both sides.

### Per language

| Language | BM25 @5 | Dense @5 (e5) | Dense @5 (bge-m3) | n |
|---|---|---|---|---|
| `ar` | 50 % | 62 % | **75 %** | 8 |
| `ar+en` | 78 % | 89 % | 89 % | 9 |

**Pure-Arabic questions are markedly harder than mixed ones** under every configuration —
the mixed questions carry an English technical anchor (`RAG`, `QS`, `Overfitting`,
`Vector Database`) that both retrievers latch onto. **The entire quality difference between
the two encoders is in the Arabic-only column** (62 % → 75 %); they are identical on mixed
questions. This is the sharp Arabic variation DEC-44 predicted, and it is the reason the
decision refused to name a model from memory: the two candidates are indistinguishable on
mixed technical text and 13 points apart on pure Arabic.

### The four questions every configuration missed

Four positives miss at @5 under **both** encoders and all three fusion configurations:
two definition lookups in the glossary (pages 221 and 140) and two count/quantity lookups
in the booklet (pages 20 and 41). bge-m3 recovers one further booklet question (page 41)
at dense-only. The residual failures are concentrated in **numeric/tabular answers**, not
in prose — consistent with DEC-45's warning that tables are structurally hostile to both
retrievers, and worth noting since this corpus contains exactly that shape.

---

## 9. The dense entry floor (DEC-46) — NOT DERIVABLE on this corpus

DEC-46 requires an explicit entry floor because cosine always returns something, and asks
for it to be derived from the observed distribution for unrelated queries.

**`multilingual-e5-small` int8**

| Distribution | n | min | median | max |
|---|---|---|---|---|
| Negative queries (max cosine per query × document) | 9 | 0.7612 | 0.8092 | **0.8813** |
| Positive ground-truth hits | 16 | **0.7716** | 0.8362 | 0.8863 |

**`bge-m3` fp32**

| Distribution | n | min | median | max |
|---|---|---|---|---|
| Negative queries | 9 | 0.3441 | 0.4248 | **0.5772** |
| Positive ground-truth hits | 16 | **0.3774** | 0.5812 | 0.6801 |

**Separation (lowest true hit − highest false hit): −0.1097 for e5-small, −0.1998 for
bge-m3. Both OVERLAP.** Under neither model does an absolute cosine threshold admit every
true hit while rejecting every negative; any floor trades one for the other.

**The mechanism, from the per-negative numbers:** the worst offender under both models is
the question about PID tuning scored against the motor-control document — 0.8813 (e5) and
0.5772 (bge-m3), in each case **higher than most true positives**. The document is
genuinely about motor control; the answer is genuinely absent. **A topically-adjacent
absence is semantically indistinguishable from a correct answer under raw cosine.** That is
structural, not a sampling artifact — and it is what DEC-46's floor was meant to catch.

**One measurable difference worth recording:** e5-small compresses every score, true or
false, into **0.76–0.89** (a 0.13-wide band), while bge-m3 spreads them over
**0.34–0.68** (0.34 wide). bge-m3 has far more dynamic range to work with, and its median
separation is better (0.5812 vs 0.4248 — a 0.16 gap between medians, against e5's 0.03).
**A floor set at a percentile rather than an absolute value would be far more workable on
bge-m3**, but that is a different mechanism from the one DEC-46 specifies, and proposing
it is not this gate's job.

**Reported, not resolved.** DEC-46 states the floor is *"a property of the model, not a
choice"*. Measured on this corpus: **neither candidate has that property in the form the
decision assumes.**

---

## 10. Privacy assertion

- The corpus was read from a path outside the repository, passed on the command line.
- After the model fetch, every measurement phase ran under an **armed socket guard** that
  raises on any outbound connection, with `HF_HUB_OFFLINE=1`. The guard also records
  attempts, so silence is evidence rather than hope.
- **Verdict on every run reported here: `ZERO network calls`.**
- No corpus content, and no corpus filename, was written to the repository, to any log, or
  to this report. The one extraction sample required for the human check is printed at
  runtime only.

---

## 11. Guard state

- **988 + 27 green** on `.venv`, before and after.
- **Zero changes to `src/`, `sdk/` or `tests/`** — `git diff` over those trees is empty.
- `orchestrator.py` **299**, `tool_router.py` **300**, `persona.py` **209** — untouched.
- The only added file is `scripts/diag_rag_bench.py`.

---

## 12. What is now Sultan's to rule

This report ends here deliberately. Each item below is a decision the measurements inform
but do not make.

1. **The PDF library.** The roadmap's candidate FAILS its own binding acceptance
   condition on both Arabic PDFs, under all six of its extraction modes. `pypdf` passes
   both conditions on both files but is ~10× slower and needs visitor-API assembly to
   produce position. No candidate is both fast and correct.
2. **The encoder — a genuine trade, now priced.** e5-small int8: 118 MB,
   publisher-fingerprinted (so DEC-44's "pinned by fingerprint" works as written),
   30.6 ms/chunk, 76 % @5, 62 % on Arabic-only. bge-m3: 19× the disk, 18× the time, **no
   publisher int8 artifact**, but 82 % @5 and 75 % on Arabic-only. The quality gap is
   entirely in the Arabic-only column.
3. **How to get an int8 bge-m3 at all, if it is chosen** — local quantization (torch-free
   via `onnxruntime.quantization`, but then the fingerprint pins *our* build, not the
   publisher's) or a community re-upload (provenance unknown). Both weaken DEC-44's
   pinning clause in different ways. Not attempted here; it needs a ruling first.
4. **The chunk window.** 400 tokens was measured. The roadmap's 400–700 range is
   incompatible with e5-small's 512 limit at the top, and fine for bge-m3's 8,192.
5. **The `MUTHIS_DOC_INJECT_LIMIT` / ingestion-budget relation**, which is currently
   unwritten and which can make zone 2 empty. See §7.
6. **DEC-46's fusion, given that RRF never beats dense alone under either encoder.** Keep
   RRF on principle, strengthen BM25, or revisit the fusion — the measurement is that the
   hybrid buys nothing on this corpus and costs up to 24 points at @1.
7. **DEC-46's entry floor, which is not derivable as specified under either model.**
8. **DEC-45's rationale**, whose stated Arabic-token premise measured ×1.11 rather than the
   large factor implied. The rule is unaffected; the reason is weaker than written.
9. **Whether the corpus is representative enough** to carry rulings 1–8. Three documents
   and 17 questions is a small sample, the residual misses cluster on numeric/tabular
   answers, and every number above is a property of *this* corpus on *this* hardware.
