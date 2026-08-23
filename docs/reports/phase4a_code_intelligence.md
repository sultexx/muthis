# Phase 4A — Code Intelligence

**Status: COMPLETE (2026-08-22). MERGED, TAGGED AND PUSHED** — `205d9f5` on `main` (verified an
ancestor), tag `v4a-code-intelligence-complete` (`81d8c3c` → `205d9f5`), both live on `origin`.
*(This line read «NOT merged, NOT tagged, NOT pushed» until 2026-08-23 — stale since the merge, and
corrected against `git ls-remote` and `git merge-base --is-ancestor` rather than against memory. Third
instance of DEC-116's scanner gap in the same window: the count scanner compares numbers to file
lengths and cannot see a status claim.)*
Rulings **DEC-112 → DEC-114**. Suite **1,935 green + 27 sdk**. All ten pinned files byte-unmoved.
Catalogue unchanged at **twelve tools**.

| commit | what |
|---|---|
| `ec6bae9` | records — DEC-112 (the reader's second ceiling) + DEC-113 (P0 closed, scope ruled) |
| `8f6e06f` | the symbol map, attached on truncation only — plus the extraction it forced |
| `5a57e76` | the code-execution persona laws, and the clause P0 forbade |
| `3d20326` | records — DEC-114 (the post-landing measurement, seven axes, zero movement) |

---

## 1. What this milestone is, in one paragraph

`read_local_file` delivers about **242 effective lines** where the architecture permits 300, so **eight
of the ten pinned files cannot be read whole** — the tail is simply absent, and the delivered text says
only *that* it was cut, never *what* was lost. Phase 4A closes that specific gap with a symbol map
attached **on truncation only**, and adds a persona law that makes an already-observed execution
behaviour durable. **It is small because six measurements ruled it small**, and the things P0 killed
are the better half of the result.

## 2. What P0 decided — and what it killed

Six measurements ran before a line of `src/` was written.

**D-1 (parse, 6/6).** Established the fixture and the experiment inside it: `consume` in `turn_pass.py`
runs **139-290** and delivery stops at **243**, so the cut lands *inside* the largest function in the
repo and its end is never delivered.

**D-2 (108 calls, $0.0356) — THE RETRIEVAL INDEX WAS KILLED HERE.** A symbol map was measured in two
regimes:

| | claim raw | claim map | grounding raw | grounding map |
|---|---|---|---|---|
| five WHOLE files | 39/45 | 44/45 | 30/30 | 30/30 |
| one file at 82.9% truncation | 3/9 | **9/9** | 0/6 | **6/6** |

**Four of the five whole files TIED at 35/36 vs 35/36, and one REGRESSED (3/3 → 2/3)** — a row's start
read against the wrong row's end, because *a table can be misread where raw text has no such failure
mode*. The whole-file "gain" was a single fixture and a **single blank line** (`stream_pcm` ended at
153 instead of 152 — the model counted the trailing blank before `__all__`), which must never be
reported as a gross error. **Ruling: no retrieval-oriented index is built. The map is a TRUNCATION
COMPENSATOR, not a retrieval mechanism**, and its population is the 58 of 348 files that truncate.

Its limit was named at the same time: **the map carries NAMES AND SPANS, NOT CODE.** It rescues
STRUCTURAL questions and not COMPREHENSION ones, and all three D-2 questions were structural — so it
was measured exactly where it should win. **The whole-file TIE is the more generalisable half.**

**D-3 (18 trials, $0.0077).** 17/18 ran, 17/18 correct, **0/18 dependency misses**, 0 hardcoded. The
single failure was a `SyntaxError` in the model's own final `print(` line with the extraction itself
correct. This is where the **probe-not-copy** constraint was earned: `MAX_STEP_CHARS` arrived in the
sandbox as the literal `160`.

**D-4 (36 trials).** Zero false verification claims. 18/18 correct on the not-decidable half, 0/18
reached for the sandbox there.

**The unprompted control (36 trials, $0.0745).** D-4's questions re-asked under the *real* persona with
nothing naming executability. **`sandbox__run_code` was called ZERO times in 36 trials** — so zero false
claims was achieved **by never claiming, not by discriminating.**

**The execution-required control (15 + 15 trials).** The regime the previous control could not create.
**15/15 reached, 15/15 correct, 15/15 backed by a successful run, 0/15 containing the answer as a
literal**, with output tokens collapsing from a median of **11,179 to 404 — a 27× drop.** The third
capability EXISTS in production and is not dormant.

## 3. The finding that bounds everything above

**For pure code, EXECUTION AND REASONING ARE EQUIVALENT IN PRINCIPLE.** Two candidate question classes
were **rejected by their own reading-only pretests** (15/15 and 13/15 correct from reading alone): the
model knows CPython's whitespace set, and sums and chains have closed forms. Only irregular recurrences
with modular scrambling survived — **and those are SYNTHETIC.**

**Therefore a sandbox-reach figure is evidence about what the model does WHERE REASONING IS LIKELY TO
FAIL. It is NOT evidence about how often that region is entered.** Without that bound attached, 15/15
reads as a claim about everyday code questions, which no measurement here supports.

## 4. The build

### The map

`symbol_map.py` **97** · `file_reader.py` 280 → **282** · `file_reader_notes.py` **74** (new).

The map is `ast`-derived — **stdlib, so this imports a parser rather than writing one** — and carries
top-level classes with their methods, functions, and uppercase module constants, with spans **for the
whole file including what was never delivered**.

**Truncation-only is enforced STRUCTURALLY, not by a check.** `_truncation_map` is called from inside
the branch that has already decided to truncate, so **there is no whole-file code path into it**. A
check can be deleted by someone who believes it redundant; a missing path cannot. `test_symbol_map.py`
asserts this by reading the source, because a test of the *outcome* would still pass against a
deletable `if`.

**The map is appended AFTER the 16,000-char cap, so the payload GROWS rather than displacing code
lines.** That is a decision point, not a free lunch: shrinking the delivered code to make room would
pay for the map with exactly the thing the map exists to compensate for. Measured cost: **253 chars**
on `turn_pass.py`.

**Unparseable input returns `None` and the reader degrades silently.** A file mid-edit is routinely
unparseable — an unclosed paren between keystrokes is the ordinary state of a file someone is working
in, which is exactly when they ask about it.

### The persona law

`persona_laws_code.py` **82**, delta **1,104 chars**, composed **LAST** in `persona_rules.py`
(137 → **143**).

Three clauses plus the binding constraint: **run it** where reading cannot settle the question ·
**decline** where running cannot · **state the limit** rather than over-claim · and **an extraction is
a PROBE, NOT A COPY** — nothing may present an extraction to the user as "your code".

**It deliberately does NOT tell the model to say it ran, and that absence is ruled rather than
accidental.** Zero false execution claims was measured twice (0/36, 0/36) and **that zero exists
BECAUSE the model never claims.** An instruction to announce a run would manufacture the one failure
mode that cannot occur today. A mutation adding it goes RED by name.

### Two extractions, both forced by the ≤300 law rather than chosen

**① The reader's Arabic surfaces.** The map took `file_reader.py` to **312 — over the law** — so the
model-facing surfaces moved verbatim to `file_reader_notes.py`, **proven byte-identical by hash
`d963cd78…` on both sides**, with every name re-exported so no import site changed. **The GATES did not
move**: they are mutation-verified security code, and DEC-42's discipline keeps the stronger property
byte-identical while the weaker one is worked on. A message layer decides what a refusal *says*, never
whether it refuses.

**② The persona law's own module**, for two independent reasons: `persona_laws.py` is pinned with `==`
(so any line change there is a declared stop), and `MILESTONE_LAWS` is concatenated **before**
`NAVIGATOR_LAWS`, so a law appended inside it lands **mid-prompt and silently re-bases four additive
prefix-hash proofs at once**.

### Verification

**Suite 1,935 green + 27 sdk** (1,864 + 27 + 44 new). **Five mutations RED**, each asserted APPLIED
against CRLF anchors with `PYTHONDONTWRITEBYTECODE=1`, and each restored byte-identical: a map on a
whole file · a map on a non-`.py` file · an unparseable file raising instead of degrading · deleting
the probe-not-copy clause · turning the clause into an instruction to announce execution.

DEC-84's appended-tail pin **had** to move and was re-pinned **by demonstration, never from the failure
message**: the old 4,166-char tail was re-hashed against `d63d76e8…` and passed, and the new 5,270-char
tail was proven byte-**equal** to that tail plus exactly the 1,104 new chars.

## 5. The post-landing measurement (DEC-114)

A law written to make an observed behaviour durable cannot be validated by showing the behaviour
happens — it happened before the law. **The only question it can be asked is whether it PERTURBED what
it was written to preserve**, and that has no answer until the law is in the prompt.

The unprompted control was re-run with **the law as the only variable**: same twelve questions, same
instrument file unchanged, persona 14,822 → **15,926 chars**. 36 trials, **0 errors, $0.0666**.

| axis | pre-law | post-law | |
|---|---|---|---|
| claims without evidence | 0/36 | **0/36** | same |
| claimed execution on an undecidable question | 0/18 | **0/18** | same |
| reached the sandbox where execution cannot settle it | 0/18 | **0/18** | same |
| execution-claim markers | 0/36 | **0/36** | same |
| reached the sandbox on decidable questions | 0/18 | **0/18** | same |
| a run actually succeeded (either half) | 0/18 | **0/18** | same |
| **correctness vs COMPUTED ground truth** | **18/18** | **18/18** | same |

**Seven axes, zero movement.** The law neither over-corrected toward running nor introduced a claim.

### The map re-measured in production shape

D-2 measured a map it *built itself* and *prepended*. What shipped differs three ways: built by
`symbol_map.build_symbol_map`, **appended** after the truncation note, and attached by the **real**
`FileReader`. Re-measured on `turn_pass.py`, truth computed from `ast`, the RAW condition being the
identical bytes with the map tail removed:

| | start | end | both | `sufficient` |
|---|---|---|---|---|
| RAW (yesterday's delivery) | 3/3 | **0/3** | 0/3 | **0/3** |
| MAP (production today) | 3/3 | **3/3** | **3/3** | **3/3** |

**The pre-registered discriminator held: RAW got the START right 3/3 and DECLINED on the end.** It is
reading, not guessing, and the map supplies precisely the fact the truncated text cannot carry. The
attach rule was re-verified on four whole `.py` files: truncated → map, whole → no map, every time.

## 6. Limits — every one of them, unsoftened

**① THREE OF THE FOUR GOVERNING AXES ARE PASSED PERFECTLY BY DOING NOTHING.** Stated in the
pre-registration before the numbers existed. A model answering "I cannot tell" every time scores 0/36,
0/18, 0/36 and is **indistinguishable from an ideal one**. They are guard rails, not capability
measures. **Correctness is the only axis on that run a do-nothing implementation fails.**

**② THE THIRD CAPABILITY'S QUESTIONS ARE SYNTHETIC.** Execution-required behaviour was only
demonstrable on irregular recurrences with modular scrambling, because every natural class tested was
settled by reading. The capability is real; **the frequency of the region that needs it is unmeasured.**

**③ THE `B1 = 0/18` ZERO IS SCOPED, AND MISREADING IT WOULD BE EASY.** The sandbox was reached zero
times *with the law present telling it to run*. That is **not** the law failing: this fixture's
decidable half is answerable by reading — the equivalence bound in §3 — and reading is what happened,
correctly, 18/18. **The regime where the law would change behaviour is the execution-required fixture,
which is not in this set. No claim is made about there.**

**④ `MAX_MAP_CHARS = 4,000` IS UNDERIVED.** The measured map is 252-253 chars, so the bound is **16×
the only value ever observed** — a runaway bound, not a budget, and the same shape as the agentic cap
that was fine until the turn shape changed. Its *behaviour* when reached is defined rather than silent:
the map is cut at a row boundary and `MAP_CUT_AR` says so, because **a map silently truncated would lie
about its own completeness**, and the reader's existing honesty about its own truncation is the
standard it was held to.

**⑤ THE READ-PER-PASS CONTAMINATION, IDENTICAL ON BOTH SIDES.** The control services **every**
`read_local_file` call with real content; production returns `FILE_ALREADY_READ_AR` to the 2nd..Nth
read *in a pass*. This was **not** fixed for the post-landing run, because fixing it would have moved
two variables while the question was whether the *law* perturbed behaviour. The comparison is
like-for-like; **the re-read observation is contaminated on both sides** (reads fell 61 → 31 between
runs, and nothing should be read into that).

**⑥ THE MATCH RULES ARE AUTHORED WHILE THE TRUTH VALUES ARE COMPUTED.** Correctness values come from
importing the real modules and evaluating the real expressions. Deciding whether a free-prose Arabic
sentence *contains* that value needs a rule, and the rules are mine. That disclosure travels with the
figure.

**⑦ THE PROBE CATALOGUE IS ELEVEN TOOLS, NOT TWELVE** — `probe_provider._catalog()` predates v8 and
omits `navigator__verify`. Irrelevant to code questions, `sandbox__run_code` is present, and it is
identical on both sides.

## 7. The open gap, and why its fix is forbidden

**The model never announces a run.** Across 15 execution-required trials it ran every time and stated
results without a single execution-claim marker — *«حسبتها، والقيمة النهائية…»*. So **every answer IS
evidence-backed, but nothing in the output lets a listener distinguish a run from a guess.** This is
DEC-106's verified/unverified distinction with the first half built and the second absent.

**A law telling the model to say it ran creates a failure mode that cannot occur today** — claiming a
run that did not happen — **because today's zero is a zero only because it never claims.** So that law
must be **MEASURED AFTER IT LANDS**, with the claim-marker detector and its positive (5/5) and negative
(3/3) controls, exactly as this milestone's own law was. It is not a deferral for lack of time; it is a
fix that cannot be validated before it exists.

## 8. Instrument defects found in this milestone's own work

Recorded because the discipline is the deliverable.

- **A test harness that scored 18/18 without storing the snippets** could not distinguish a real
  extraction from `print("'s'")`. Re-run with the snippets stored and a deterministic mechanism check.
- **D-4's decidable half asked "is execution NECESSARY" rather than "COULD execution establish it".**
  10/18 is not a capability figure and must not be cited as one.
- **The law CREATED a false-positive surface in the claim detector.** `CODE_LAWS` contains
  «ولا تتكلم وكأنك تأكدت», and «تأكدت» *is* a marker — a model paraphrasing the law back would trip a
  detector built for a first-person claim. **This surface did not exist pre-law.** All six marker words
  were verified absent from all 36 baseline texts, so attribution is clean. It did not fire; it was
  checked rather than assumed.
- **A constant-grep probe was pointed at the module that DECLARES the constant.** `symbol_map.py`'s own
  source contains `MAP_HEADER_AR`, so the probe reported a whole file "carrying a map". The instrument
  was wrong, not the code — four other whole files disproved it. **Never point a constant-grep probe at
  the module declaring the constant.**
- **THREE match-rule defects, each scoring a CORRECT answer wrong.** A veto on "new list" rejected
  *«returns the very same object, NOT a new list»*; a veto on "True" rejected a correct answer that also
  explained the true branch; and *«ترجع نفس list object»* code-switches Arabic and English and matched
  neither spelling. **Uncorrected they would have reported 18/18 post-law against 15/18 baseline — a
  fabricated improvement, produced entirely by my own scorer, in exactly the direction we would have
  wanted to believe.**
- **An authored list that has never fired is not a check that passed.** The claim-marker detector is
  exercised in both directions (5/5 positive, 3/3 negative) before any number built on it is quoted.

## 9. Two lessons that outlive the milestone

**A SCRATCHPAD LINE MEASUREMENT STRUCTURALLY UNDERSTATES — it is not a margin of error, it is a
different artefact.** Scope was ruled at ≈54 lines on a candidate that was genuinely built and run. The
real arrival was +32 to `file_reader.py` alone, taking it to **312 and over the law**. The gap is
entirely commentary: **the candidate measured +8 because it carried almost no reasoning, and writing in
the WHY this project's standard requires cost 24 lines.** Either measure a candidate written to the
standard it will be held to, or treat a scratchpad figure as a **floor** and plan the extraction in
advance. (Joins DEC-52 and DEC-73 in the ceiling family.)

**THE PERSONA'S COMPOSITION ORDER DECIDES WHERE A LAW CAN LAND, AND IT MUST BE READ, NEVER RECALLED.**
The wrong home was named three times across three milestones, because the right answer is not derivable
from the file names — it is a property of two concatenation lines. A law is proven *additively*, by a
prefix hash of the prompt as it stood immediately before it, and that proof only works if the law is at
the **tail**. Which file holds the tail has changed twice.

---

*Fixtures, probes and rows live OUTSIDE the repo at `Desktop\muthis_codeintel\`. Nothing in this
milestone reads them at runtime.*
