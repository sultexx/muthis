# V3 Phase 4 — NAVIGATOR v2 (visual step verification) — P0 MEASUREMENT GATE REPORT

- **Project:** Mut'his V3
- **Milestone:** Navigator v2 — visual step verification (**NOT OPENED; no implementation exists**)
- **Branch:** `main` (script only, `scripts/probe_step_verification.py`; **zero changes to `src/`**)
- **Status:** **MEASURED — Sultan ruled from these numbers.** See `DECISIONS.md` DEC-99.
- **Written:** 2026-08-14 (English, UTF-8)
- **Authority:** Navigator v2 was **DEFERRED by Sultan's ruling at T4** (`phase3_navigator.md`).
  This gate answers the one question that had to precede any design: *does the difference
  between two frames carry enough signal at all?* It chose nothing; DEC-99 chose.
- **Hardware:** Windows 11, Python 3.14.4, `.venv`, `openai 2.53.0`

> **On frame privacy.** The pairs are Sultan's real desktop, held **outside the repo** at a
> path this report does not reproduce, together with the label manifest. No frame, no
> filename and no coordinate appears here; cases are described **by shape only**. The one
> verbatim model answer in §5 is reproduced **at Sultan's explicit instruction**, because
> its wording *is* the finding.

---

## 1. What this gate produced

| # | Question the deferral left open | Measured answer |
|---|---|---|
| 1 | Can it detect a CLEAR completion? | **Yes — 80/80 = 100%**, both sweeps |
| 2 | Where does detection break — SUBTLE? | **It did not break. 20/20 = 100%**, reading `50 mm` against `0.00 mm` off a twice-resampled frame |
| 3 | False advance on the declared negatives? | **0/100 = 0.0%** (95% upper 2.95%), zero of five pairs ever advanced |
| 4 | Cost and latency per verification | **2.22 s median, $0.000194** — ≈$0.0012 across a six-step walkthrough |
| 5 | Does more reasoning help? | **No. `reasoning_tokens` is 0 on 170/200 calls** at the ruled `high`; effort is not a lever here |

Plus the finding nobody asked for, **which is the one that became law**:

- **A control the brief did not specify produced the only false advance in 260 calls** — and
  its failure mode is nameable, realistic, and structurally guardable. See §5.

**The headline is not the table.** Detection and the declared-negative rate both pass Sultan's
gate, but three of the five declared negatives are *"a different application is on screen"* —
the easy half of the negative space. **The result says the signal EXISTS. It does not say the
coverage is sufficient**, and §5 is why.

---

## 2. The pairs — ten of twelve, and a manifest that was wrong

Twelve pairs across five kinds were specified. The supplied frames construct **ten**.

| Kind | Pairs | Shape |
|---|---|---|
| CLEAR | 4 | a dialog closed → open; an empty workspace → a sketch; an empty grid → a solid body; a sketch workspace → a Form body |
| SUBTLE | 1 | one numeric field `0.00 mm` → `50 mm`, an OK button disabled → enabled, a preview growing |
| NO_CHANGE | 1 | the same modelling state twice; the **only** difference is a hover tooltip present in one frame |
| WRONG_CHANGE | 1 | a failed Cut (`No target body found to cut or intersect!`, OK greyed) → the operation reverted to `New Body`, error gone, OK live |
| DISTRACTION | 3 | one pending modelling step observed across CAD → video site → code-hosting site → CAD |

**The manifest shipped with the fixture was wrong, and checking beat trusting it.** It recorded
three screenshots as MISSING and — correctly — forbade fabricating them. They were not missing:
they were on disk under Arabic filenames the earlier pass could not see. Recovering them
**restored the DISTRACTION kind entirely**, which is three of the five negatives. The two pairs
that genuinely could not be constructed were **left unbuilt rather than invented**, so the count
is honest at ten.

**The DISTRACTION trio deliberately shares ONE pending step**, and it is a *modelling* step, not
a *"get back to the app"* step. That choice is load-bearing: the return frame shows the CAD app
back on screen with a different document open and full of solid geometry, so a step phrased
around reaching the application would have been **satisfied** by it and the hardest negative in
the supplied set would have been mislabelled as a true positive.

**Consequence for the statistics, recorded because it does not go away with more runs:** three
of five negatives are correlated (one step, one episode). The negative set is **five pairs**, and
no number of repetitions changes that.

---

## 3. Detection — the two positive kinds, kept apart

Averaging them would hide the number that decides the design.

| Kind | Sweep A | Sweep B | Combined |
|---|---|---|---|
| CLEAR (4 pairs × 10 runs) | 40/40 | 40/40 | **80/80 = 100%** |
| SUBTLE (1 pair × 10 runs) | 10/10 | 10/10 | **20/20 = 100%** |
| Pooled | 50/50 | 50/50 | **100/100 = 100%** |

Zero misses, zero `unclear`, in either direction, in either sweep.

**The SUBTLE result is the strong one and it is a FLOOR, not a ceiling** (§8). The model cited
the field by value both ways — *"the Extrude dialog's Distance field visibly reads `50 mm`
… whereas the BEFORE frame shows `0.00 mm`"* — 20 times out of 20, off a lossy 1536-wide
re-encode that had then been downscaled again to 1280.

---

## 4. False advance — the declared negatives, and the governing metric as specified

| Kind | Sweep A | Sweep B | Combined | 95% upper |
|---|---|---|---|---|
| NO_CHANGE | 0/10 | 0/10 | **0/20** | 13.9% |
| WRONG_CHANGE | 0/10 | 0/10 | **0/20** | 13.9% |
| DISTRACTION | 0/30 | 0/30 | **0/60** | 4.9% |
| **Pooled** | **0/50** | **0/50** | **0/100 = 0.0%** | **2.95%** |
| Pairs that ever advanced | 0/5 | 0/5 | **0/5** | **45.1%** |

`unclear` was answered 3 times per sweep, **all on DISTRACTION pairs, and never on a positive** —
the conservative direction. It is scored as neither a detection nor an advance: it did not
detect, and it would not advance. Folding it into `no` would have flattered this table.

**Right answers for the right reasons**, verified by reading the raw evidence rather than the
verdicts:

- On WRONG_CHANGE it read *"the Operation field shows `New Body`, not `Cut`"* and noted the
  dialog was still open and unconfirmed — **refusing the lure of the error clearing and the OK
  button going live**, which is the surface signature of success.
- On the return trap it read the title bar, named the *wrong document*, and stated that no
  extrusion or 50 mm result was visible — **refusing to accept "the CAD app is back with a 3D
  model" as completion.**

### The caveat that must travel with the 0.0%

**100 negative calls are CLUSTERED on 5 pairs.** Repeated runs buy *stability* — they prove the
model is not flaky on these pairs — and buy **nothing at all** about whether five pairs
represent the negative space. The 2.95% call-level bound therefore prices stochastic wobble.
**Treated as five independent pairs, a perfectly clean sweep still admits a true pair-level
failure rate of up to 45.1%.**

---

## 5. The control the brief did not ask for — and the only false advance in 260 calls

### Why it was built

Three of the five declared negatives are *"a different application is on screen"*. That is the
easy half of the negative space, and a verifier can pass all of it while being **a
difference-detector rather than a frame-reader**. Only one supplied pair is a plausible-but-wrong
change *inside* the application, and that is the shape a real walkthrough fails in.

So: **CLEAR pairs played BACKWARDS.** The completed frame is presented as BEFORE and the
uncompleted frame as AFTER, under the original step. The step's result is therefore **absent
from the AFTER frame**, while the two frames still differ by **exactly the amount the step
describes**.

**What it separates, and nothing else in the set does:** a verifier that READS THE AFTER FRAME
answers `no`. A verifier that merely DETECTS A STEP-SHAPED DIFFERENCE answers `yes` — and would
have scored **100% on every forward case in this report** while advancing the user every time a
step was undone, a dialog dismissed, or an operation cancelled.

Reversal is not fabrication: no frame was invented, altered or duplicated to fill a gap. It is
Sultan's own pair read in the other direction, scored on its own line and **never folded into
the governing metric of §4**.

| Control | Result | 95% upper | Note |
|---|---|---|---|
| IDENTICAL — same frame twice, result absent | 0/20 | 13.9% | the instrument does not advance on zero difference |
| **REVERSED — completed frame as BEFORE** | **1/40 = 2.5%** | **11.3%** | pair-level **1 of 4** (95% upper 75.1%) |

### The single false advance, verbatim

One pair, one run in ten. Nine runs answered `no`, citing the empty canvas and the absent
Bodies folder. The tenth answered `yes`:

> *"In the AFTER frame, the rectangular shaded profile from BEFORE is no longer visible, and the
> Browser no longer shows the Sketches folder or a sketch entry. **This is consistent with the
> sketch having been used to create a solid body, though the resulting body is not visibly
> apparent in the current view.**"*

### The signature — and it is the reason v2 has a law

**It advanced on an INFERENCE FROM A DISAPPEARANCE.** The precondition (the sketch) was gone, and
the absence was read as evidence that the outcome had occurred — while the answer *explicitly
admits the outcome is not visible*. That is:

> **absence of the precondition treated as evidence of the outcome.**

This is precisely the class produced by a step that is **undone, cancelled, or Ctrl+Z'd**, and in
a parametric CAD workflow that is not an exotic case — it is Tuesday.

**A confidence threshold was available and was declined.** That call carried self-reported
confidence **72**, against a median of **97–99** for every correct answer on the same pair. It is
a single observation, and gating on it would be exactly the *"the model believes the step is
done"* that Sultan's binding condition rules out. It is recorded as an observation and **must
buy its own measurement before any gate is built on it.** The advance rule in DEC-99 is derived
from the failure instead, because a rule about *what counts as evidence* is structurally
guardable and a threshold on a self-report is not.

---

## 6. Cost and latency per verification

Measured over the 200 scored case calls. A window that fires after every step multiplies both.

| | Value |
|---|---|
| Latency, median | **2.22 s** |
| Latency, p90 / min / max | 3.20 s / 1.33 s / 6.14 s |
| Cost per verification | **$0.000194** |
| Cost across a 6-step walkthrough | **≈$0.0012** |
| Input tokens (both frames + instruction) | **2,444** |
| Cached / output tokens | 2,222 / 88 |
| Reasoning tokens (mean) | **12.1 — and exactly 0 on 170/200 calls** |
| Whole gate, 260 calls | **≈$0.05** |

**Two economic facts worth carrying forward.** Both frames cost only ~2,444 input tokens
together — confirmed on the **8 cold calls with zero cache**, so it is not a caching artifact.
And **deliberation is not a lever here**: the API echoed `high` back on all 260 calls, so the
ruled setting was genuinely applied, yet the model does not reason on this task shape at any
setting. That is the opposite of pointing (DEC-89/DEC-98), and it means v2 cannot buy accuracy
by spending effort.

---

## 7. What the apparatus proved before any number was trusted

Not in the brief, and the reason the tables above are usable:

1. **The ruled effort was READ BACK, never assumed.** `reasoning_tokens` returned 0, which has
   two very different causes — *`high` ran and declined to think*, or *`high` never arrived*.
   The probe records the effort the API reports back: **`high` on 260/260**. Without it this
   report would have described a provider default as though it were the ruled setting.
2. **The wire format is asserted, not assumed.** The production downscale returns the *original
   bytes untouched* for a frame already within the width cap, so a JPEG fixture could have
   ridden out under a `data:image/png` label. The probe aborts unless the payload is PNG —
   DEC-11's failure class, a wire-format lie that every offline check passes.
3. **The frames were confirmed to actually land**, by reading the model's evidence text rather
   than trusting the token count: it enumerated dialog entries and read title bars that exist
   only in the images.
4. **The identical-frame control** (0/20) establishes the floor: the instrument does not advance
   on zero difference.
5. **TWO INDEPENDENT SWEEPS, and they replicate exactly** — 50/50 detection and 0/50 false
   advance in each, with the `unclear` count identical at 3. The declared-case numbers are not
   one lucky run.

---

## 8. Limits — every one, including the one that shapes the next milestone

**Deliberately not measured**, because if the numbers had failed nothing would have been built
and no privacy surface would have been touched:

- **Live capture.** No capture mechanism exists, was written, or was tested.
- **The real cost of a verification window.** This is one isolated call. A real window carries
  the plan context, fires on top of an already-running turn, and may retry — §6 is a **lower
  bound on both cost and latency**.
- **How it feels.** Untested and untestable from static pairs.

**Limits of this measurement**, disclosed:

- **SINGLE PROVIDER.** `gpt-5.6-luna` only. The Anthropic account is out of credit (verified live
  at the start of this gate), so *"the signal exists"* is established **for one reasoner**. A
  second provider buys its own measurement — DEC-93's rule.
- **ENGLISH step text and a neutral ENGLISH prompt, where production speaks Arabic.** This
  isolates the vision question from a language variable, and it means **the Arabic phrasing a
  real `navigator__plan` would emit is unmeasured**.
- **NO PERSONA, and no tuned prompt.** The instruction is deliberately neutral and symmetric
  across the three answers. A conservative prompt — which a shipping window would very likely
  use, since false advance is the expensive error — is **an untested lever** that could trade
  detection for false advance in either direction.
- **A TWICE-RESAMPLED LOSSY FIXTURE.** Fifteen of the eighteen frames are 1536-wide lossy
  re-encodes that the production path then downscales again to 1280. Production would send one
  clean capture through one downscale. **The SUBTLE number is therefore a FLOOR, not a ceiling.**
- **THE PAIR-LEVEL BOUND.** Five negative pairs, three of them correlated. Clean at the call
  level, **up to 45.1% at the pair level** (§4).
- **THE REVERSED CONTROL IS A CONSTRUCTION, NOT SUPPLIED DATA** — Sultan's frames read backwards,
  reported apart, at n=40 with a 11.3% upper bound. Its rate is an existence proof of the failure
  class, **not a calibrated estimate of it**.

### The limit that shapes the next milestone

**Static pairs assume the AFTER frame is captured at the right moment.** Every number in this
report was produced by handing the model a before/after pair that a human had already chosen
correctly. A real verification window must decide **WHEN TO LOOK** — and that question is
untouched here.

**It is not a prompt problem.** No wording of the instruction, no persona, and no confidence
threshold affects it. Look too early and the step is genuinely incomplete, and the correct answer
`no` is indistinguishable from a user who has not started. Look too late and an intermediate
state has already been replaced. **The 100% detection figure in §3 is conditional on a capture
moment that this gate did not have to find**, and finding it is the first question the v2 design
session must answer.

---

## 9. Where this left the project

- **Navigator v2 PROCEEDS.** Detection 100% on both kinds, false advance 0.0% on the declared
  negatives → the specified gate's first row.
- **The governing metric CHANGED**, and this report is the argument for it: the reversed-control
  rate replaces the easy negatives. *A design that scores 0% on "a different app is open" and
  fails on a reverted step has measured the wrong thing.*
- **THE ADVANCE RULE** — advance only on **positive evidence of the step's RESULT**; absence of
  the precondition is never evidence — is derived from §5's single measured failure.
- **The probe is committed as the regression harness** for v2 and for any future provider,
  exactly as `probe_effort.py` became for pointing. The frames and labels stay outside the repo.

Rulings, the advance rule, the metric change and the deferred items: **`DECISIONS.md` DEC-99.**
