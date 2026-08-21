# Navigator v2 — step verification, P0 to live

**Status: COMPLETE and LIVE-VERIFIED, 2026-08-21. NOT merged, NOT tagged — the merge is Sultan's.**
DEC-99 → DEC-111. 1,864 + 27 green. Every number below is measured; where a number is a probe's and
not this build's, it says so.

**THE CLAIM THE MILESTONE SET OUT TO PROVE:** that Mut'his can tell, from the screen alone, whether
the user finished a step — and advance without being told.

**THE LIVE RUN PROVED IT.** Sultan asked *«وش أسوي بعد؟»* — a question that announces nothing — and
the step advanced. **He never said «تم» once in the session**, and the mode chip cleared correctly at
completion.

---

## 1. What each measurement DECIDED

The design was not reasoned into existence; each part of it was decided by a measurement that could
have gone the other way.

| # | measurement | what it DECIDED |
|---|---|---|
| **DEC-99** | 260 calls, two replicating sweeps | **THE ADVANCE RULE: advance only on POSITIVE evidence of the step's RESULT. Absence of the precondition is NEVER evidence.** Earned from the ONE false advance in 260 — a reversed pair, where the model inferred completion from a DISAPPEARANCE. A confidence threshold was DECLINED at n=1. |
| **DEC-100** | 120 calls, 4 moments × 3 steps | **WHEN TO LOOK — and the answer was that the trailing edge was never the problem.** A neutral instruction failed T₁ at **43.3%** (17 false advances in 30); the conservative one took it to **100%** with T₂ and T₃ **unmoved** — the failure REMOVED, not relocated. It also **refuted a perceptual-ceiling argument on the same frame**: neutral gave *"the body visibly has rounded top edges"* 10/10, the rule gave *"only a live preview"* 10/10. **The model could always SEE the dialog; the missing piece was the rule.** |
| **DEC-105** | 120 calls, 4 shapes | **THE BOUNDARY, NAMED — and the APPLICATION framing REFUTED by its own numbers.** The automatic path covers **mid-steps whose unsettled state is ACTUALLY RENDERED** — not "apps with modal confirmation": Explorer has none and passed twice, Excel has none and failed. Excel failed **10/10 at confidence 99** with the model applying the rule CORRECTLY against a disqualifier that is never drawn. |
| **DEC-106** | 320 calls | **THE THREE-WAY CONTRACT.** *"Not proven" is EPISTEMIC; "did not happen" is a claim about the external world, and a verifier must not make the second from one frame.* Category 3 fired **37/40** with **ZERO false advances** and **0 of 4 pairs never reaching for it**. **F9 is the trigger UNDER THE CURRENT CONSTITUTION** — recorded as correct-under-the-constitution, never as a permanent rejection of event-driven observation. And **UNOBSERVABLE → no advance → fallback is a DECLARED CAPABILITY BOUNDARY, not a defect.** |
| **DEC-107** | argument, not calls | **`expected_result` — the field the advance rule had been verifying against without ever having.** Authored WITH THE PLAN, free text the kernel never reads, IMMUTABLE for the cycle. Every rate before it was measured against a step text that lived in a fixture manifest; **in production there is no manifest.** |
| **DEC-108** | a read-only lifecycle trace | **THE CALL SITE: the nav arm in `pass_servicing.py`** — and the finding that decided it, *the kernel never needs the frame*, because it validates REPRESENTATION and not truth. |
| **DEC-109** | a cache-prefix measurement | **THE OFFER-GATE RULING, REVERSED BY ITS OWN MEASUREMENT** (§5). |
| **DEC-110** | a persona scan | **THE JUDGEMENT RULE WAS NEVER SHIPPED** (§6) — the finding that stopped the live run. |
| **DEC-111** | the live SOP | **THE PASS ECONOMY** (§7) — the one defect, and it was not the cap. |

---

## 2. The gates

Four gates, each opened only after the previous one was reviewed, and **three mechanical extractions
taken BEFORE the work that needed them** rather than after a breach.

| gate | commit | what shipped |
|---|---|---|
| **1** | `c2824cf` (+ pin `108ddc4`) | `Step.expected_result`, catalog **v7** (a REVISION — blast radius pinned as a CHANGED SET), the loud boundary, the argument-aware immutability guard, the authoring law |
| **2A** | `1043110` | `kernel/step_verification.py` — the three-way outcome, **fail-closed as a SHAPE** · the `navigator_verify` plugin · catalog **v8** (an EXTENSION) · `NAV_TOOLS` |
| **2B** | `c60a210` → `af91a01` | the P4 servicing arm, then the mount — **two commits in that order, so DEC-39's law is a fact of the history rather than a claim in a comment** |
| **2C** | `a4db4e4` → `587c2d1` | the pin, three extractions, the **four-state machine**, and the two persona clauses |
| **live** | `add3ee8` → `484f268` | the judgement law, DEC-111's pass-economy clause, the HOLDING note's distinction |

**THE THREE EXTRACTIONS, each met by a pin that had been declared for exactly this:**
`deferral_notes.py` 283 → **207** · `session_mode.py` 309-measured → **287** (via `mode_frame.py`) ·
`persona_laws.py` 285 → **244** (via `persona_laws_navigator.py`, **composed prompt proven
byte-identical by hash**).

---

## 3. What the kernel actually does

**FAIL-CLOSED IS A SHAPE, NOT A CHECK.** `StepVerification` **has no `outcome` field**. There is no
slot to put an advance in — `outcome` is DERIVED from `claimed` + `evidence` — so an evidence-free
`RESULT_PROVEN` is not a bad value the module refuses but **one it cannot hold**, including for a
caller that skips the entry point and builds the record by hand. Inside every function body the name
`RESULT_PROVEN` appears **only as a comparison operand**.

**AND INVARIANT ① TRAVELS IN THE SIGNATURE.** `after_verification` takes the RECORD, never a bare
outcome string, so `ADVANCED` cannot be *asked for* without holding the evidence.

| DEC-106 invariant | how it is enforced |
|---|---|
| ① `ADVANCED` only from `VERIFYING` with represented evidence | the signature (above) + the state test |
| ② no transition reads confidence, absence of a disqualifier, or a disappearance | **an absence of INPUTS** — the functions see a state string and a two-field record |
| ③ no timer, no polling, no background observer | no clock import exists in the module; every transition fires on F9 or on a verification |
| ④ dies with its mode | the state lives on `ModeFrame`; `leave()` empties the one slot |
| ⑤ `FALLBACK` never returns to `VERIFYING` for the same step | **ONE enforcement point** — the reset rides on `record_progress`, where transitions 3 and 6 both already arrive |

**THE STAMP IS NOT A TRANSITION.** `record_verification` takes no plan and touches one field, so the
step pointer still moves only through the authority — which is why a proven LAST step is refused at
the plan's edge and receives the AUTHORITY's own note. **`mode_transition.py` cost ZERO lines.**

---

## 4. The live results

**FIRST SESSION — the claim proven, one defect three times.**

- The step advanced on a question that announced nothing; **«تم» never said**; the chip cleared.
- `RESULT_NOT_PROVEN_OBSERVABLE` fired correctly on *«ممتاز بس أنت ما وريتني المية وثمانين»* — the
  result should have been visible, was not established, so the model **asked, did not blame, and did
  not advance**.
- **The double advance did NOT occur** — no step jump, no `NAV_ONE_PER_PASS_AR` anywhere.
- **THE DEFECT:** three turns ended on `AGENTIC_CAP_NOTE_AR` («اكتفيت بهذا القدر») **after a correct
  draw**. Proven from the loop: once anything is drawn the next call is `tool_choice="none"` and the
  turn ends, **so the cap note is reachable ONLY if the draw landed on pass 4** — three passes spent
  before it, where v1 spent none.

**SECOND SESSION — after the pass-economy clause:**

| | before | after |
|---|---|---|
| agentic cap hits | **3** | **0** |
| passes per turn | 3–4 | **2 on nine of ten turns** |
| cost per turn | ≈$0.0057 | **≈$0.0033** |

**The truncation and the latency resolved together, exactly as the option predicted.** Two barge-ins
fired immediately.

**AND ONE EMERGENT BEHAVIOUR WORTH PRESERVING, WHICH NOTHING PRESCRIBES.** Faced with a result that
was achieved but not visible from the current viewpoint, the model **asked Sultan to change the
camera angle** rather than falling back — and it worked. Neither the contract nor any note describes
that move; it is strictly better than a fallback, because it turns an unobservable state into an
observable one instead of spending the boundary. **Recorded as OBSERVED BEHAVIOUR, deliberately NOT
codified: one sighting is not a rule, and codifying an emergent move on one sighting is the
generalisation this project refuses.**

---

## 5. The offer-gate ruling, reversed by its own measurement

DEC-108 ruled that the kernel would gate whether `navigator__verify` is OFFERED — *no active step, no
tool*. Gate 2B **stopped instead of building it**, and the ruling was reversed.

**THE CATALOGUE IS FIXED AT CONSTRUCTION** (`main.py:141`, both agents; `luna_agent` additionally
transforms it), so varying it per turn needs a **`CloudReasoner` PROTOCOL change** — a documented
contract with two implementors — or a private-field mutation. **And `tools` is the FIRST element of
the cached prefix**, so varying it invalidates the persona behind it: 10,785 of 10,828 input tokens
(**99.6%**) fixed, persona alone **61%**, and at 0.10× read against 1.25× write a prefix switch costs
**≈12.4k token-equivalents**.

**"Offered" became NAMED IN THE DIRECTIVE LINE** — zero cache cost, because the directive is in the
per-turn user message and not the prefix. **The economic argument is now a TEST**: the verb's name
must never appear in the composed persona.

> **THE STANDING LESSON: a ruling's MECHANISM is a claim, and a claim can be measured.** The trace was
> right about everything it looked at; the ruling reached one step past it, into a construction the
> trace never examined.

---

## 6. The judgement rule that was measured and nearly shipped without

**DEC-100's conservative instruction produced every number in this series and lived only in the
probe's `INSTRUCTION`.** Measured at Gate 2C's close: **ZERO occurrences of any of its load-bearing
ideas in 13,529 characters of composed persona.** Gate 1 shipped how to WRITE an expected result;
Gate 2C shipped WHEN to verify; **no gate owned how to JUDGE.**

> **A RULE THAT LIVES IN THE MEASURING INSTRUMENT IS NOT SHIPPED BY MEASURING WITH IT.** DEC-100
> recorded its instruction as an APPARATUS property — *"the probe was NOT edited"* — which is exactly
> the discipline that made the measurement clean, and exactly what kept the rule out of the product.

**THE ASYMMETRY IS WHY IT WAS DANGEROUS:** a missing MACHINE fails loudly — nothing advances. A
missing JUDGEMENT RULE fails as **wrong advances that look like model error**, checked against a
measurement taken with the rule present. It shipped BEFORE the live run, in four clauses, with the
preview clause and the absence clause **separately required** and mutation-verified as such.

---

## 7. The pass economy

**THE COST WAS NEVER STRUCTURAL.** `turn_pass.py` keeps `pending_draw` and `nav_call` as **separate
first-wins slots**, so a navigator verb and a draw in ONE assistant message are BOTH serviced — and
`test_advance_AND_point_in_one_pass_completes_in_TWO` has driven exactly that since T5. **The model
was spending a pass the machine never asked for.**

**RULED: the verify rides the draw's pass; THE CAP STAYS AT 4.** The clause is **guidance, not a
prohibition** — a model that separates them is not wrong, it is slower — and it NAMES the two pairs
in its own first line, because DEC-55 measured that the model reads LINEARLY.

**WHY THE CAP WAS NOT RAISED, and the argument stands on its own:** `SESSION_TIMEOUT_S = 90.0` did
not move and **the timeout path SPEAKS NOTHING** — so raising the cap can convert an audible-but-wrong
ending into a **silent** truncation. Beside it, the method reason: the measurement could not
establish WHICH passes were spent, and a number chosen without that becomes a definition by accident.
**Four was sized against a two-pass turn at `f8c188f`, 2026-07-12, and never re-derived while the
catalogue went from four tools to twelve.**

---

## 8. Every declared limit, unsoftened

**① THE EXCEL CASE IS UNTOUCHED BY EVERYTHING IN THIS MILESTONE.** The result IS positively
established — `123` is in the cell — while the STATE is unsettled and the application **never draws
the difference**. The model applies the rule CORRECTLY against a disqualifier that is never rendered,
10/10 at confidence 99, twice. **DEC-105's boundary stands exactly where it was named**, and neither
`expected_result`, nor the machine, nor the judgement law moves it by a pixel. A step whose app never
draws its unsettled state stays outside the automatic path, and the honest outcome there is *not
proven*.

**② THE PRODUCTION FALLBACK RATE WILL EXCEED DEC-106's FIGURES, AND IS NOT BOUNDED.** Those fixtures
were built to make category 3 fire on demand; **none sampled a real user's plan**, where a step like
*"save the file to your Downloads folder"* is off-frame for as long as the folder stays closed. The
rate is stated as a DIRECTION and is still not predicted.

**③ PRODUCTION SENDS ONE FRAME; EVERY NUMBER CAME FROM A LABELLED PAIR.** `orchestrator.py:231`
strips images from history, so each turn carries the current screen and no before-frame. Category 3's
cue is a one-frame judgement and should survive; **category 1's rates may not**, because a
difference-detector has nothing to difference against. **DEC-106's 92.5% and 99/100 do not transfer
by assumption — the live run was a FIRST MEASUREMENT, not a confirmation.** The image-stripping does
NOT move: changing it so a rate transfers would be fitting the system to the measurement.

**④ THE KERNEL NEVER READS THE EVIDENCE, SO ITS QUALITY IS UNMEASURED AND UNMEASURABLE FROM HERE.**
Presence and non-emptiness are checked; the text is never parsed (DEC-66). **A model that writes a
plausible sentence WITHOUT LOOKING receives an advance**, and nothing in this build distinguishes
that from a model that looked. Live it appears as advances that are correct more often than they
should be — unfalsifiable by ear. Settling it needs the probe apparatus pointed at production
payloads.

**⑤ TWO OPEN OBSERVATIONS, ruled on by nobody.** The cap's note **misattributes who ended the turn**
and is wrong at any cap value (DEC-58's class). And **the log cannot answer "which passes"** — no
per-pass tool line exists, so any future cap decision that wants to be evidence-based needs that line
or a diag run first.

---

## 9. Practice notes this milestone earned

- **A pin ruled an hour earlier caught three arrivals in the same gate**, each becoming an extraction
  rather than a breach — the clearest case this project has produced for declaring a count *before*
  it is needed.
- **Guards were RAISED where they could not follow, never lowered.** A bare frozen record cannot
  satisfy a scan's positive control, so `mode_frame.py` is held to *defines NO FUNCTION AT ALL*. A
  magic `+400` bound that loosened every time the frame grew became a differential that cannot drift.
- **Three live guards caught real collisions in drafts of these very laws** — the pinned ack «شفت»
  twice, a §3.2 delimiter word once — and every one was **fixed in the LAW, never in the guard**.
- **The CRLF note earned a third direction:** `\n` written in a mutation harness becomes a real
  newline where the source holds two characters. Four mutations reported NOT APPLIED; without the
  applied-assertion they would have read as silent passes.
- **An argument converted into a guard outlives the argument** — the cache-cost reasoning behind the
  directive-line relocation is now a test, not a memory.
