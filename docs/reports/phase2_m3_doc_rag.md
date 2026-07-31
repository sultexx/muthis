# Phase 2 -- Milestone 3 Closure Report (`doc_rag` -- open a document, then ask it)

- **Project:** Mut'his V2
- **Milestone:** Phase 2, Milestone 3 -- `doc_rag` (`docs__open`, `docs__query`)
- **Branch:** `feature/v2-phase2-doc-rag` (cut from `main` at `b7654f7`; **main untouched**)
- **Status:** **CLOSED -- signed off by Sultan's personal T6 Live SOP run, 2026-07-31 (the FIFTH live run).** The merge to `main` is his to run; it was not performed here, and no tag was created.
- **Written:** 2026-07-31 (English, UTF-8, no BOM, ASCII punctuation throughout so a cp1256 console can render it)
- **Authority:** `DECISIONS.md` (DEC-44..DEC-63) plus the 36 milestone commits below. This report certifies closure; it is not itself a decision.

> Mut'his can now be handed a real document -- a PDF, a Markdown file, a text
> file -- and answer questions from it, in Arabic, out loud, citing the page.
> Every passage it reads is treated as HOSTILE by construction: wrapped at the
> one router boundary with a fresh nonce, raising the session taint in the same
> branch, and never granted a capability. The document index lives in RAM and
> dies with the process. The path is never logged. And when the document does
> not contain the answer, the model says so and offers a way forward instead of
> inventing one -- which, at 82% effective recall, is the load-bearing guarantee
> of the whole milestone and was proven live against the exact case it exists for.

---

## 1. Verdict

`doc_rag` is COMPLETE. `docs__open` ingests one document through three size zones
decided in the broker; `docs__query` returns ranked passages the plugin dedupes,
orders and caps. The pipeline is DENSE-ONLY: `pypdf` extraction, structural
chunking sized in tokens, `multilingual-e5-small` int8 on ONNX Runtime, cosine
over unit vectors. There is no BM25, no fusion and no second normalized pipeline,
because the P0 gate measured the lexical half's unique contribution over dense at
exactly ZERO.

The draw path was never touched. `orchestrator.py` is unchanged at 299 lines.
`tool_router.py` absorbed the entire mount at **ZERO lines** -- the P0b ceiling
measurement predicted it and the git record confirms it.

**Acceptance is Sultan's live run and his personal sign-off, by eye and ear.**
Nothing in the diagnostic script closes a milestone, and this report does not
either.

---

## 2. The arc: P0 to T6

P0 (the measurement gate) closed on `main` before this branch was cut. The branch
carries 36 commits.

| Stage | Commits | What landed |
|---|---|---|
| Pre-work | `9b2fab7`, `6a1e0a9`, `4e6e2cd`, `76487f0` | DEC-51 recorded, the P0b ceiling measurement, `ROUTER_SERVICED_TOOLS` named instead of an or-chain, and `composition.py`'s extraction seam NAMED at planning time (DEC-52) |
| T1 ingestion | `3f877d7`, `46c445e` | `pypdf` extraction plus structural chunking; DEC-53 found here -- an Arabic sentence can exceed the chunk window, so the SPLITTER was fixed and not the guard |
| T2 encoder | `821e18a` | `e5-small` int8 on ONNX behind a seam, artifact PINNED BY FINGERPRINT |
| T3 zones | `0c8007c`, `61fac63`, `2f80804` | The three size zones (DEC-47); DEC-54's two boundaries want OPPOSITE biases; DEC-52's named extraction executed, byte-identical |
| T4 mount | `da219d0`, `f879d13` | `docs__open` + `docs__query` join the catalog (v4, byte-pinned); DEC-51's two flags together |
| T5 persona | `3478409` | The two `doc_rag` laws: say when the document does NOT answer, and say WHERE it does |
| T6 script | `b559353`, `66e5e1c` | The live SOP script, with the absence law SPLIT into a driven setup and an observed reply |
| T6 blocking | `bfb0162`, `1e25c88`, `1867acd`, `1584f66` | The first live run's blocking defect and its fix; both mutation survivors closed; the two M15 rules promoted to AGENTS.md |
| Caching | `3e2ceb2`, `ef9c511`, `40474fe`, `783d04c`, `cb36894`, `3595f62` | Prompt caching WITH cache-aware pricing, so the ledger cannot lie about a cached turn |
| Live rounds 2-4 | `8e39e28`, `57c3edc`, `2909945`, `ab505b8`, `2042528`, `df6c898` | The privacy leak, the slot rule, the id round-trip, and their decisions |
| Closing | `efc29a6`, `96eeb47`, `b3dfe4b`, `cd97f35` | Two dead names, the mechanical `records.py` extraction, the <=300 guard, and K5 by whole-utterance matching |

---

## 3. Governance -- DEC-44 to DEC-63

| DEC | Ruling |
|---|---|
| DEC-44 | Arabic normalization plus the encoder path |
| DEC-45 | Chunking: structural boundaries, small-to-big, sized in TOKENS |
| DEC-46 | Fusion and reranking: RRF, an entry floor, no reranker at launch |
| DEC-47 | Ingestion: three size zones, no partial ingestion, refusal estimated UP FRONT |
| DEC-48 | The P0 measurement gate results -- OBSERVATION, not a ruling |
| DEC-49 | The P0 gate: five rulings, including retiring the dense entry floor |
| DEC-50 | The lexical half is RETIRED: `doc_rag` is DENSE-ONLY |
| DEC-51 | `doc_rag` mounts `taint=True` TOGETHER WITH the kernel-side read hint |
| DEC-52 | `composition.py`'s extraction seam, NAMED at planning time |
| DEC-53 | An Arabic sentence can exceed the chunk window: fix the SPLITTER, never the GUARD |
| DEC-54 | The zone estimate is biased, and the two boundaries want OPPOSITE biases |
| DEC-55 | Three T3 items ruled |
| DEC-56 | A named seam plus an ESTIMATE is not a plan: RE-MEASURE at execution time |
| DEC-57 | The `doc_rag` persona laws: the ABSENCE clause and the SPOKEN LOCATION |
| DEC-58 | The T6 blocking defect: fix the NOTE, keep the SLOT, make re-open IDEMPOTENT |
| DEC-59 | Prompt caching: ADDITIVE at the protocol, CONTRACTUAL at the ledger |
| DEC-60 | Prompt caching SHIPPED, and the pricing that keeps Rule 10 honest shipped WITH it |
| DEC-61 | The PATH is never logged, and LOGS versus SPEECH is the general rule |
| DEC-62 | A PRECONDITION call does not consume the pass slot |
| DEC-63 | The `doc_id` must survive a natural-language round-trip; and a DIAGNOSTIC INSTRUCTION is checked against the privacy law BEFORE it is executed |

Three standing rules were promoted to `AGENTS.md` during this milestone: the two
mutation-survivor rules M15 earned, and the note law (state the state achieved,
whether the condition is terminal or transient, and the valid next step) --
promoted on its THIRD sighting in three unrelated subsystems.

---

## 4. The five live runs

Every one of the first four ended in the same visible symptom -- the model
retrying -- and each had a DIFFERENT cause. That is the single most useful fact
this milestone produced: **a retry loop is a symptom, not a diagnosis.**

### Run 1 -- the note loop (-> DEC-58)

`docs__query` was never serviced when the model batched it with `docs__open` in
one assistant message. **55 green checks over a capability that did not work.**
The deferral note said "ask again next step" while saying NOTHING about whether
the open had succeeded, so the model re-opened to "fix" it and paid a full
re-ingestion (18 s measured) every retry, while `_register`'s collision suffix
handed back a DIFFERENT id each time (`book.md`, `book.md-2`, `book.md-3`).

Fixed by making the note report the STATE ACHIEVED, and making re-open IDEMPOTENT.

### Run 2 -- the privacy leak (-> DEC-60 verified, DEC-61)

Caching was VERIFIED in production (one write, reads on every pass and across
turns). But check I6 failed: a real corpus FILE NAME reached the logs while its
CONTENT never did. The module's own recorded discipline said "path and outcome in
English, NEVER content" -- and the measurement proved that clause **wrong about
which half is sensitive.** Seven sites, not six: the seventh was
`read failed (%s: %s)`, because `OSError.__str__` embeds the offending path
verbatim.

Ruled: the path is NEVER logged. Log the EXTENSION, the OUTCOME and the SIZE.

### Run 3 -- the slot rule (-> DEC-62)

The loop persisted after the note fix. K1-K7 were green -- the note demonstrably
said the document was opened, that re-opening was unnecessary, and what the next
step was -- and the live model re-opened anyway. **A deterministic check proves
the note's TEXT; it cannot prove the note CHANGES BEHAVIOUR.** The note was a
mitigation; the root cause was the one-serviced-call-per-pass rule.

Measured correction: a count-based bound guarded the wrong quantity by ~100x.
`read_local_file` and `docs__query` deliver up to 16,000 characters; `docs__open`
delivers 110-320 (a confirmation). Ruled: classify by ROLE -- a precondition
returns a confirmation, never content, so it cannot break the invariant and is
serviced for free.

### Run 4 -- the id round-trip (-> DEC-63)

`docs__query` still never reached its ranking. `registry.get(doc_id)` returned
None, so `query` returned `DOC_NOT_OPEN_AR` **before its own log line** -- which
is why zero `query: candidates=` lines coexisted with `reopen: already open`. The
model paraphrased that note back as «أداة فتح المستندات ما تشتغل صح», a phrase
that occurs in that note and nowhere else in the codebase.

Root cause: `INDEXED_AR` presents the id INSIDE guillemets, so the live model must
extract and re-emit it. Fixed shape-independently -- normalize, then recover when
exactly one document is open, then refuse when two or more are, because there the
ambiguity is real and guessing would answer about the wrong document with no
observable difference.

### Run 5 -- SUCCESS, 2026-07-31

`query: candidates=` appears in the LIVE phase for the first time.

- **OBS-1, the absence law, WORKED and better than specified.** Given eight
  passages that invited a topically-adjacent answer, the model said plainly it
  found nothing, stated what the document DOES cover, and offered a path
  («جرّب تحدد مستند ثاني»). All three clauses of DEC-57(a), live. At 82%
  effective recall this is the only layer there is until Phase 3's visual
  citation, and it has now proven itself against the exact failure it exists to
  prevent.
- **OBS-2, the spoken location, WORKED and the page is CORRECT.** Ground truth
  «صفحة 8»; the model cited «صفحة 6 وصفحة 8» in natural prose, no citation
  syntax, inside the verbosity cap. It did not invent a position.
- **OBS-4 returned to 20.03 s from 25.79 s after a cold boot**, confirming the
  thermal-derating candidate and ruling out an accumulating structure.
- Caching held: one write, reads on every pass and across turns.

One attempted run in between never reached the live phase: the script died at a
`NameError` from a stale name left by the K2-K5 re-aim. It is not counted as a
live run because nothing was measured.

---

## 5. The check-and-subject-never-connected family

The family's canonical statement is in `AGENTS.md`: **the check and the thing
checked were never actually connected, and nothing in the green result says so.**
This milestone produced five of its eight recorded sightings.

| # | Sighting | Shape |
|---|---|---|
| 1 | DEC-40 (M2) | A test that builds its own graph proves nothing about production -- five of six mutations survived because every test built its own router |
| 2 | M2 | State a teardown also produces must be sampled BEFORE teardown |
| 3 | DEC-50, the P0 gate | A check with a cutoff can exclude its own SUBJECT: an Arabic-correctness metric whose probe set was too narrow PASSED a PDF the human eye failed on sight, and a 150-character block floor printed NOTHING for a glossary whose blocks average 52 |
| 4 | T6 survivor | Dropping DEC-51's `read_only_hint` stayed GREEN -- the counterfactual was being tested one turn too early, because the confirm gate has nothing to fire on while the session is still clean |
| 5 | T6 survivor | Answering a scanned PDF with `unsupported(".pdf")` stayed GREEN against an inequality check: the two notes really are different, while DEC-35's ruling was gone. **The inequality is necessary and not sufficient** |
| 6 | The T6 blocking defect | 55 green checks over a capability that does not work. Every earlier sighting was a GUARD that was not really guarded; **this one is the FEATURE ITSELF** |
| 7 | M15 | A survivor whose property is enforced UPSTREAM -- redundant on that path, and "unobservable" is a fact about the TEST, not a licence to delete the code |
| 8 | K5's vacuity | A purely negative assertion that any passages payload satisfied, so it never noticed its own subject had vanished |

Two further T6 survivors belong to the same family without carrying an ordinal in
the record: a delivery-cap mutation that scored GREEN in a configuration where its
checks were SKIPPED (an expected check that reports SKIP never ran, so the verdict
is SUSPECT, not green), and M20 -- nothing asserted that the startup log reports
both figures.

**Ordinals 3, 6 and 8 are stated explicitly in `DECISIONS.md`; 1 and 2 are named
in the sixth-face passage. Positions 4, 5 and 7 are reconstructed from the record
chronologically and are not numbered at source.**

### Guard holes versus code defects

| | Count | Items |
|---|---|---|
| **Code defects** | **6** | DEC-53 (an Arabic sentence exceeds the chunk window); DEC-58 (`docs__query` unserviced when batched); DEC-61 (the path reached the logs); DEC-62 (a precondition consumed the pass slot); DEC-63 (the `doc_id` did not survive the round-trip); the `service.py` <=300 breach |
| **Mutation survivors (guard holes)** | **7** | Four at the T6 build, two in the DEC-58 round (M15, M20), one in the DEC-63 round (M1) |
| **Guard holes found by audit, no mutation involved** | **4** | The <=300 LAW had no guard anywhere in the project; K5's vacuity; the hardcoded `doc_id` (fixed in passes 1 and 1b, MISSED in pass 2); K0/K7/G7 deterministic and guarded nowhere outside the diagnostic script |

The contrast with M2 is the interesting number. M2 closed with **ZERO code defects
and SEVEN guard holes**. M3 closed with **SIX code defects and ELEVEN guard
holes** -- a harder milestone by both measures, and the first in which the
instrument itself became the dominant source of defects: three of the four
defects in the final rounds lived in the diagnostic script's DETERMINISTIC half,
the half the pytest suite already owns.

---

## 6. Known limits

Recorded as limits, not as defects to be fixed before merge.

1. **~20 s of silence during first ingestion (OBS-4).** Measured 20.03 s on a
   cold boot and 25.79 s on a warm one; the difference is thermal derating, not
   an accumulating structure. **ACCEPTED as a known limit for this milestone.**
   The spoken announcement -- the DEC-3-D pattern -- lands in Phase 3 with the
   other voice-surface items owed. The `model_pin.FIRST_DOWNLOAD_AR` seam exists
   and is wired to the LOGGER, not to the voice line. A multi-second silence is a
   real defect; it is not a security defect, and it belongs with the voice work.
2. **82% effective recall.** A retrieval miss is the EXPECTED case, not an
   anomaly, and DEC-49 retired the dense entry floor. This is exactly why the
   absence law is load-bearing rather than decorative, and why its live proof in
   run 5 matters more than any deterministic check in the script.
3. **The model is the MESSENGER.** Inherited from DEC-16 and unchanged here: the
   model relays what it read, and could word a request misleadingly. Bounded by
   the directive naming tool and arguments aloud and by approval binding to the
   real call's hash; full removal needs kernel-authored confirmation, which is
   post-launch research.
4. **No per-claim attribution.** The spoken location is the model's own citation
   of a page it was given. It was CORRECT in run 5 and it is not mechanically
   verified. Phase 3's visual citation is the layer that closes this.
5. **`tool_router.py` is at 300/300 and IRREDUCIBLE.** It absorbed this milestone
   at zero cost, but the next addition requires splitting the dispatch funnel,
   which is a DESIGN decision needing a ruling, not a move.

---

## 7. Deferred

- **The `diag_doc_rag.py` reduction (APPROVED, executes AFTER milestone close).**
  The script is 2,290 lines against 308 for M1's and 1,156 for M2's. Three of the
  four late defects lived in its deterministic half, so it is not too big in
  general -- it is too big where it duplicates the suite. Estimated ~1,450 lines
  after reduction. **Two binding conditions:** K7 (re-open idempotence), K0 (the
  id is extractable from the note) and G7 (both figures differ) are PROMOTED to
  pytest BEFORE anything is deleted, because all three are deterministic and
  guarded nowhere else -- no test in the suite calls `DocumentService.open`
  twice, and K0's presentation contract cost four live runs; and D1-D7 plus
  E1-E5 STAY in the script despite the duplication, because end-to-end
  confirmation of the security guards on the real path is worth the ~106 lines.
- **Phase 3 voice surfaces:** the first-download announcement (above), the
  multi-pass ack, and the Docker-unavailable terminality note.
- **`WEB_ONE_PER_PASS_AR` fails the note law.** Recorded during T6, deliberately
  not fixed: it is a `web_research` surface and belongs to the post-milestone note
  pass with the other owed ones.
- **The M3 documentation pass** beyond the rows added at close.

---

## 8. What shipped

**Broker (`src/muthis/broker/docs/`)** -- `service.py` 281, `zones.py` 294,
`ingest.py` 274, `extract.py` 239, `chunking.py` 222, `encoder.py` 187,
`model_pin.py` 169, `blocks.py` 164, `notes.py` 133, `index.py` 132,
`__init__.py` 87, `records.py` 70, `token_estimate.py` 68.

**Plugin (`src/muthis_plugins/doc_rag/`)** -- `plugin.py` 182, `delivery.py` 136,
`schema.py` 104, `__init__.py` 37, `muthis-plugin.toml` 36.

**Cloud (prompt caching)** -- `pricing.py` 105, `cache_control.py` 70.

**Composition** -- `composition_mounts.py` 120 (DEC-52's named extraction).

**Tests added** -- `test_doc_ingest.py` 471, `test_doc_delivery.py` 404,
`test_prompt_caching.py` 337, `test_doc_zones.py` 336, `test_doc_servicing.py`
330, `test_doc_encoder.py` 320, `test_persona_doc_laws.py` 297,
`test_doc_mount.py` 278, `test_doc_extract.py` 250, `test_doc_chunking.py` 220,
`test_module_line_ceiling.py` 98, `test_doc_id_roundtrip.py` 89.

**New runtime dependencies:** `pypdf`, `onnxruntime`, `tokenizers`,
`huggingface_hub`.

**Guard: 1216 + 27 green on `.venv`.**

---

## 9. Acceptance

- The Live SOP was run by Sultan on his own hardware, on the fifth attempt, and
  signed off PERSONALLY by eye, ear and the printed summary.
- The deterministic phase reports "all checks green".
- `src/` has ZERO modules over the 300-line law, and the law now has an automated
  guard for the first time in the project's history.
- `orchestrator.py` 299, `tool_router.py` 300, `persona.py` 209 -- unchanged.
- The draw path is git-untouched.

**Not performed here, deliberately: the merge to `main` and the tag. Both are
Sultan's.**
