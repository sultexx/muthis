# V3 Phase 3 -- the Navigator: closure report

**Branch** `feature/v3-navigator` | **HEAD** `25d9941` | **guard** 1513 + 27 green on `.venv`
**Status: COMPLETE, NOT MERGED, NOT TAGGED.** The merge is Sultan's.

Mut'his can now walk a user through a task step by step -- holding the plan in the kernel,
drawing its own progress on screen, pointing at each step, and leaving the mode by three
independent exits. It can also point at the EVIDENCE for what it says, on screen and inside a
displayed document, and refuse honestly when the evidence is indexed but not visible.

Rulings: **DEC-65 .. DEC-86**. Design session DEC-65..68 (also labelled DEC-A..D); P0 closed by
DEC-74; build tasks T1..T6 by DEC-75..80; T7 by DEC-81..84; the close by DEC-85..86.

---

## 1. The arc, with commits

| gate | what landed | commit |
|---|---|---|
| design | DEC-65..68 signed: `SessionMode`, Plan/Step primitives, evidence pointing, the P0 gate | `510c728` |
| constraint | the mode directive MUST carry `DIRECTIVE_MARKER_AR` | `67f7e1c` |
| P0 | the measurement gate: D-1 blocked, D-2 hits its STOP condition, D-3 finds a lifecycle that does not inherit | `c5f4f8c` |
| P0 | DEC-73: design C ruled, design D rejected; **two splits executed** | `7f4f699`, `15020a7`, `d22532c` |
| P0 | D-1 executed: 23 HIT / 2 NEAR / **0 MISS** over 25 targets | `2fc0415` |
| P0 | **DEC-74 -- P0 CLOSED.** Four rulings, one known limit, one fixture defect | `06187d1` |
| T1 | `SessionMode` + `Plan`/`Step` primitives, wired in design C | `781fae3` |
| T2 | the single transition authority and the three exits | `d7e0531` |
| T3 | the kernel-drawn mode indicator | `34d4545` |
| T4 | Navigator v1, catalog **v6**, servicing before mounting | `010c005` |
| T5 | `turn_pass.py` pinned at 293 before any T5 code | `f12cc99` |
| T5 | evidence pointing, all three paths | `ce985ab` |
| T6 | the live SOP script, BUILD ONLY | `09504ba` |
| T7 | run 1: the observation leak isolated; DEC-80's open question closed | `8c0dd16` |
| T7 | `--observations-only`; the caption halt DIAGNOSED, not fixed | `9cc7c20` |
| T7 | the multi-pass ack DIAGNOSED; O-1 ruled; the prompt that killed run 3 | `ffa4947` |
| T7 | the ack scope reaches the navigator and mode directives | `c03d871` |
| T7 | the persona contradiction resolved at its source | `25d9941` |

The branch also carries the tail of Phase 2 M3 (`DEC-69..72`, the voice-surface pass, the
`doc_rag` fixes) because `main` has not been merged since M3. **34 commits ahead of `main`
in total; the Phase-3 arc begins at `510c728`.**

---

## 2. What each P0 measurement DECIDED

The gate's whole point (DEC-68) was that a number would decide something in advance, rather than
being resolved by whoever hit it first at implementation time. All three did.

### D-1 -- pointing accuracy by element size: **it bought us out of crop-and-zoom entirely**

23 HIT / 2 NEAR / **ZERO MISS** across 25 hand-marked targets, reported by size and never as one
aggregate. Zero MISS in EVERY bucket, including a **9x9-pixel** contribution square and an
**8x7-pixel** unsaved-file dot **in the sent image**, after the 1.5x downscale.

DEC-68's table offered three branches; the first was satisfied, so:

* **NO crop-and-zoom, NO second pass, NO refinement by size.** A whole mechanism, designed and
  budgeted, was not built -- because the measurement said it was unnecessary.
* **Downscaling stays unchanged.** 1920x1080 -> 1280x720, scale 1.5 exactly, 0.922 MP, under both
  provider thresholds, so the sent space IS the space the model reasons in.
* **DEC-67's deferred document path came INTO scope.** The deferral rested on the premise that
  matching a passage to a screen position is "precisely where vision models are weakest". That
  premise is refuted for our path, and T5 shipped paths (1) and (2) together as a result.

It also **overturned an expectation that was Sultan's own**: ambiguity was expected to be a
failure axis, and 14 deliberately ambiguous targets scored 13 HIT / 1 NEAR -- indistinguishable
from the crisp ones, with BOTH NEARs coming from CRISP targets. Reporting ambiguous-versus-crisp
WITHIN each size bucket is what made that visible; aggregated, the two would have confounded and
the result could have decided nothing.

### D-2 -- the state carrier: **it reframed the orchestrator ceiling as three milestones of architecture**

Written in full against scratchpad copies, with the real cost counted on every candidate carrier.
The finding was not "which file is smallest": **the minimum cost of ANY new injected seam in
`orchestrator.py` is three lines -- one import, one constructor parameter, one pass-through --
against ONE line of headroom.** So the file could not absorb the next arrival whatever it was;
`SessionMode` was merely next in the queue.

That converted a line count into an architectural fact: the ceiling had been shaping this
project's structure for three milestones (M2's zero-touch design, M3's extractions, and now a
split). DEC-73 ruled design C and executed two splits -- `kernel/pass_servicing.py` +
`PassServiced`, and `kernel/turn_prelude.py` -- and **`tool_router.py` measured ZERO lines, so
DEC-38's reserved dispatch-funnel split was NOT needed and remains unspent.**

### D-3 -- overlay capacity: **the UX half was refused, the architectural half answered**

Room exists for a second persistent element. But the interesting result was a correction:
**requirement 3 does NOT hold as written.** The caption lifecycle is two halves, and a
CROSS-TURN element needs only one of them -- so the mode indicator inherits the ghosting hide
(and is restored after the grab) while `clear_caption` deliberately does NOT touch it.

And **exact placement was ruled a UX decision, not an architectural one** -- to be settled by
Sultan's eye after a prototype, and explicitly NOT frozen at design time. T3 honoured that: the
indicator is top-anchored (every other persistent element is bottom-anchored, so it cannot
collide however the caption wraps), the two margins are a prototype, and **no test pins a pixel.**

---

## 3. What T7 settled

Three live runs on Sultan's hardware. **Verdict: no blocking issue in the product.** Every stop
was outside Mut'his -- an `EOFError` from the harness's own prompt, and an exhausted API balance.

### O-2 -- ANSWERED: the Navigator works, and it is guidance

The advances each acknowledge what the user accomplished, then give the next step and point at it:

> «قائمة Start مفتوحة، افتح الآن Settings» -> «زين، Settings مفتوحة. الحين انقر على النظام»
> -> «ممتاز، أنت الحين في صفحة النظام» -> «زين، وصلت لصفحة التخزين»

That is guidance, not a list read aloud -- the question DEC-68 posed for T7, answered by ear as
designed. **The pointing landed on the correct element**; Sultan simply could not click it before
the balance ran out.

### O-1 -- RULED: no persona law, and the VARIANCE is the answer

Three runs gave three results: `navigator__plan` called, then not called, then `draw_shapes`.
Run 2's reply explains it -- «هذي ما لها علاقة بالشاشة اللي قدامنا»: the screen state differed
between runs and the model judged the question general rather than guided. **A reasonable
judgement, not a failure.**

The T4 rule is written on a **stable OBSERVED gap**. What exists here is behavioural variance on a
question that legitimately admits a prose answer, while the genuinely guided path (O-2) reaches
the verbs reliably. **RULING: no persona law.** Revisit only if daily use shows the verbs missed
on genuinely step-shaped requests.

This superseded an earlier reading that rested on run 1 alone. **One run is not a behavioural
measurement** -- the same lesson as D-1's fixture defect, arriving from the opposite direction:
there the instrument was wrong, here the sample was one.

### The one real product defect T7 found, and it is fixed

The multi-pass spoken ack: «أبشر... أبشر», «الحين... الحين», and in the log
«سم، شوف أول خطوة!أبشر، شوف شريط البحث!» -- two acks concatenated without a space, the signature
of two feeds joining one audio generation. **An ack per PASS inside one answer.**

All three hypotheses were tested rather than argued, two with positive controls:

* the echo guard -- **REFUTED.** Driven on the real strings through the real functions, it leaves
  a DIFFERENT ack unchanged while a true verbatim echo IS stripped. It compares the right line and
  works; it cannot match different words, which its own code comment already stated.
* the clause not reaching the model -- **REFUTED.** The composed prompt is 10,575 chars, is not
  the bare fallback, and contains both clauses.
* the scope -- **the mechanism, and sharper than the hypothesis.** The directive that actually
  forbids a repeated ack **rides the DRAW pairing**, and the Navigator **inserts an ack-eligible
  pass BEFORE any draw**. Measured: all four draw directives carried the clause; all five
  navigator/mode directives were silent. T4's own passing test supplied the other half --
  `calls[1][1] == "auto"`.

**The code did not break. The Navigator EXPOSED a directive-coverage gap that was previously
closed by COINCIDENCE** -- DEC-13's posture one layer up, a property held by circumstance rather
than by construction. Fixed at both the symptom (`c03d871`) and the cause (`25d9941`), with the
scope written **per ANSWER, never per tool family**, so a future capability inherits it instead of
re-earning it.

---

## 4. Known limits, carried forward and stated

| limit | status |
|---|---|
| **The caption halt (DEC-82)** | **OPEN.** Two mechanisms both fit and neither blocks the close. (a) the BUFFERED path -- streaming off / no key / open failed -- gives the ack then ONE truncated block then nothing: **designed behaviour**, and the question is whether that is acceptable for teaching, which is a DESIGN ruling. (b) a mid-stream feed failure sets `_dead` and calls `clear_caption()`, whose generation bump ORPHANS every pending caption: **a real defect, but it PRE-DATES Phase 3** -- the caption path is git-identical across T1..T6. **The discriminator is free and visual: was caption 2 a clean SENTENCE (b) or a long BLOCK ending in an ellipsis (a)?** Settled on the next voice run, never by inference. |
| **Prose pointing (DEC-75's condition on path 2)** | **CONDITIONAL, unmeasured.** D-1's text targets were UI elements with VISUAL BOUNDARIES -- a menu row, a nav tab, a gutter number -- and BOTH NEARs came from text targets. Continuous prose inside a rendered page has no boundary and is the one shape D-1 did not drive. If T7 shows weak pointing there, **the degradation is already designed** (path 3's honest refusal) and needs no new design session. **No prose-specific mechanism was built on speculation.** |
| **Loose boxes (DEC-74)** | **RECORDED, no work.** A correct box may run somewhat past its element (a ~29 px box over a ~19 px digit). Harmless for pointing -- a human reads a rectangle around the element correctly -- but potentially visible where a Navigator step points at something fine. Measured at T7, not fixed on speculation. |
| **Navigator v2 visual verification** | **DEFERRED by Sultan's ruling at T4.** v1 does NOT verify that the user actually performed a step. |
| **Zone-1 documents and evidence pointing** | Outside the directive's reach, stated rather than silently widened: a claim from a fully-injected document is equally unpointable, but there is no per-claim location to redirect to. |
| **`orchestrator.py` has ONE line left** | Unspent. T5 measured before writing and never approached it. The standing STOP holds for whatever touches it next. |
| **The `_dead` caption clear** | Even if branch (b) is confirmed, the clear is what makes a TRANSIENT fault PERMANENT. That is the shape of the fix to rule on, not a patch to make quietly. |

---

## 5. The family, and two new faces

This project keeps meeting one defect: **a check that examines something other than its subject.**
Phase 3 met it repeatedly, and two of the sightings are shapes not seen before.

Previously recorded: DEC-40's tests that built their own graph; the zone-1 fixture that measured
the wrong zone; the `_bind` helper that set state instead of opening anything; the «باختصار»
guard that could not distinguish an order.

**NEW FACE 1 -- the defect was in the MEASUREMENT itself.** D-1's first run reported 2 MISSes.
Both were the measuring instrument: a ground-truth box aimed by hand at the WRONG INSTANCE of a
repeating structure -- one row above the application named, five rows above the tree row named.
The model had boxed the requested element exactly in both cases. **Had those been recorded, the
gate would have ruled the other way** -- 2 MISSes concentrated in the small buckets is branch two,
and we would have built crop-and-zoom to fix a defect in the ruler. It surfaced only by rendering
the model's box and the ground truth together and LOOKING. **A measurement is the one artefact
with no second guard behind it.**

**NEW FACE 2 -- a guard that pinned the OPPOSITE of its own purpose.**
`test_the_law_scopes_the_earlier_mandatory_ack_rule_rather_than_contradicting_it` asserted that
BOTH ack rules must be present, on the reasoning that the later one scopes the earlier. Its own
docstring had already named the failure mode -- *"two rules that read as a conflict are resolved
by the model unpredictably"* -- while believing the later clause removed it. **It did not. The
guard was pinning the contradiction in place.** This is not a check examining less than it claims;
it is a check **guarding the opposite of its own purpose**, and it survived three milestones
because everything it asserted was literally true.

**And the self-built graph had to be refused four times, not learned once.** Closed preventively
at T1, reappeared at T3 in the fixtures, caught pre-run at T4 while writing the mutation list, and
refused again at T5. Sultan's framing, recorded verbatim: **the self-built graph is not a lesson
learned once -- it is a DEFAULT that must be refused every time.**

Two flaws were also caught in guards *before* they landed: a copy-detection probe that searched
for a rendered sentence which is never contiguous in source (so it examined nothing and passed),
and a `persona_rules.py` match that was DEC-20 layer one stating the same law in its own words --
a stated exclusion, not a copy. And the baseline-hash guard proved itself in use when a mutation
runner rewrote a snapshot's line endings: it went RED, and rebuilding the file from the INVERSE
delta matched the pinned hash exactly, which is a second independent proof that the delta is exact.

---

## 6. What was built

**Kernel:** `session_mode.py` 211, `plan.py` 223, `mode_transition.py` 263, `mode_surfaces.py` 247,
`turn_prelude.py` 152, `pass_servicing.py` 117, `navigator_service.py` 165, `deferral_notes.py` 201,
`evidence_pointing.py` 129, `ack_scope.py` 62.
**Overlay:** `mode_indicator.py` 131.
**Plugin:** `muthis_plugins/navigator/` -- `schema.py` 71, `plugin.py` 40, `__init__.py` 6, manifest.
**Diagnostic:** `scripts/diag_navigator.py` 731.

**Model-facing surface: catalog v6** -- `navigator__plan` + `navigator__step`, eleven tools against
a cap of 24, byte-pinned, and v6 is v5 with two tools APPENDED. **Evidence pointing added ZERO
model-facing surface**: pointing is `highlight_target` as it already exists.

**Two properties worth carrying forward:**

* **`evidence_pointing.py` and `ack_scope.py` import NOTHING.** Absence proven by lack of means
  rather than by discipline -- the module that must never compute a position has no means to
  reach one, and the module that holds a law has no means to become logic.
* **`ModeAuthority`'s public surface is exactly `request`.** The servicer holds no mutator, so it
  cannot bypass the single evaluation point even by accident. That came out of MEASURING T4 rather
  than out of designing T2, and it is stronger than what T2 set out to build.

---

## 7. Guard and ceilings at the close

**1513 + 27 green on `.venv`** (1216 + 27 at the M3 close; the Phase-3 arc added the rest).

| file | lines | note |
|---|---|---|
| `kernel/tool_router.py` | 300 | IRREDUCIBLE; byte-identical through the entire milestone |
| `kernel/orchestrator.py` | 299 | ONE line left, UNSPENT; +1 at T4 with its reason declared |
| `kernel/turn_pass.py` | 293 | newly PINNED at T5's first commit, before any T5 code |
| `turn_voice.py` | 300 | untouched |
| `composition.py` | 298 | ceiling debt carried from T3 |
| `overlay/sidekick_window.py` | 296 | newly pinned at T3 |
| `persona.py` | 209 | byte-identical through the entire milestone |

A `+0` form was REFUSED at T4: packing two keyword arguments onto one line to dodge a declared
ceiling move is compression, and **a pin that reads 298 because a line was stuffed is a lie in the
pin.** The same commit did the opposite elsewhere -- an existing one-line import took a third name
and stayed one line -- and the distinction is the test Sultan set: **adding a name to a list is
that statement's natural form; merging two independent arguments and their comments is not.**

---

## 8. The rulings, in order

DEC-65 `SessionMode` | DEC-66 Plan/Step primitives | DEC-67 evidence pointing | DEC-68 the P0 gate |
DEC-69..72 (M3 tail, carried on this branch) | DEC-73 design C + two splits | DEC-74 P0 CLOSED |
DEC-75 T1 | DEC-76 T2 | DEC-77 T3 | DEC-78 T4 | DEC-79 T5 | DEC-80 T6 | DEC-81 T7 run 1 |
DEC-82 the caption halt (**OPEN**) | DEC-83 T7 runs 1-3, O-1 ruled, the ack diagnosed |
DEC-84 the ack fixed at symptom and cause | DEC-85 the append-only persona invariant RETIRES |
DEC-86 Phase 3 CLOSED, and what crosses the boundary.
