# Phase 2 — Milestone 2 Closure Report (`web_research` — search and fetch)

- **Project:** Mut'his V2
- **Milestone:** Phase 2, Milestone 2 — `web_research` (`web__search`, `web__fetch`)
- **Branch:** `feature/v2-phase2-web-research` (cut from `main` at `65170b2`; **main untouched**)
- **Status:** **CLOSED — signed off by Sultan's personal T7 Live SOP run, 2026-07-29.** The merge to `main` is his to run (not performed here).
- **Written:** 2026-07-29 (English, UTF-8, no BOM — committed to git)
- **Authority:** `DECISIONS.md` (DEC-14..DEC-42) + the milestone commits below. This report certifies closure; it is not itself a decision.

> This report certifies that Phase 2, Milestone 2 closed correctly: Mut'his can
> search the web and read a page, and everything it reads is treated as HOSTILE
> by construction — wrapped at one router boundary, tainted for the session,
> fetched only through an IP-pinned guard that refuses private space, and paid
> for out of the sovereign ledger with a figure now checked against the vendor's
> own dashboard. The draw path was never touched, `orchestrator.py` is
> byte-identical, and Sultan signed off in person by eye, ear and the printed
> summary — the only acceptance an audio/UI-touching milestone can have.

---

## 1. Verdict

`web_research` is COMPLETE. The model can call `web__search` (a configured
provider, key-bearing, destination fixed in `.env`) and `web__fetch` (the
broker's hardened fetcher, IP-pinned, robots-respecting, budget-bounded), and
speak an answer that cites its sources — the SECOND execution-adjacent
capability, delivered with LOOK-only intact and with the untrusted-content
boundary that the whole rest of V2 will inherit.

The two acceptance questions this milestone was not allowed to answer for itself
were both answered on real hardware:

- **The cost chain is CLOSED with dashboard evidence** (DEC-26 + DEC-34, §4.1).
- **The DEC-15 × DEC-16 friction question is ANSWERED with its cause** (§4.2).

## 2. Implementation — risk-ordered gates P0 → T7

Each gate ended with a STOP for Sultan's approval before the next; no gate
auto-continued. Detail lives in `DECISIONS.md` and the commit bodies.

| Gate | Commit(s) | Summary |
|---|---|---|
| P0 feasibility + governance | `1e49abd`, `79bb130`, `9c661ce` | Five probes measured; DEC-14..DEC-21 recorded BEFORE any code. The gate ruled the milestone buildable with **zero `orchestrator.py` touches**, conditional on three mechanical extractions first. |
| T1 ceiling extractions | `c901208`, `e3f82b8`, `76dd8d8` | `persona.py` 299→209 (`persona_rules.py`), `main.py` 294→170 (`composition.py`), `turn.py` 283→182 (`kernel/tool_result_pairing.py`). Each proven byte-identical to its original; `orchestrator.py` untouched. Confirmed live (full boot 22/22 + the barge-in / sandbox / shutdown paths). |
| T2 the fetcher | `cffe666`, `424f3c0`, `a77fb36` | `broker/net/` — `address_guard` (SSRF: resolve once, validate as an IP object, PIN, re-validate every hop), `fetcher`, `robots`, `session_policy`, `transport`. Follow-ups: the wire layer split out (DEC-23) and the per-request timeout replaced by ONE total wall-clock budget (DEC-22 — the per-hop timeout was a ~120 s turn-budget DoS under tainted redirects). |
| T3a extraction | `c0f14b9`, `f6c09e7`, `21e34cf` | `extract.py` — trafilatura off the event loop, output capped. Plus the DEC-21-E **allow-list** AST guard: trafilatura may be imported in exactly one module through exactly one symbol, so a future bypass entry point is caught with zero maintenance. |
| T3b the search seam | `5a63033`, `f6c8b16`, `9b23cf3`, `b29c65f` | `broker/search/` — `SearchProvider` protocol + Tavily (default), Brave, SearXNG. THE property, enforced BY SHAPE: the destination is CONFIGURATION-ONLY (no url/base_url/host parameter anywhere, signature-scanned), so a tainted model can never aim the key-bearing client. Then DEC-28: httpx logs full request URLs at INFO, so the fetcher was logging fetched URLs and a GET provider would have logged the user's QUERY — silenced at the composition root before the first real key. |
| T4 wrapping + taint | `9b5d5a0`, `8176bdf`, `7cfca97`, `c6b2ee3`, `cfd8eb7`, `88f097a` | DEC-14: every untrusted result is wrapped ONCE, centrally, at `ToolRouter.service()` with a fresh nonce per wrap. DEC-15: taint is raised in the SAME branch as the wrap — split, they open the milestone's worst hole (wrapped but not raising leaves the session looking clean). Kernel-side impact classification from the MOUNT, never from a plugin's own claim. Three ceiling extractions interleaved. |
| T5 confirmation | `872bcdf` | DEC-16: a high-impact call under taint is refused with an internal directive; the approval word spoken in the NEXT turn releases THAT EXACT call (bound to `sha256(tool + canonical args)`), single-use, consumed on match, expiring at the first turn carrying no approval. The detector is deterministic — the model never participates in the approval decision (DEC-12). |
| T6 wiring + the plugin | `f0f9f3b`, `a956a21`, `f565f2d`, `a9b654a` | `ctx.net` made a binary present/absent contract (DEC-24, closing the granted-but-unwired state). The plugin lands over an INJECTED provider (DEC-27 — a provider is not a capability) and `ctx.net`, with a per-turn fetch cap of 3. DEC-34: the router obtains a plugin's per-call cost and charges the ledger — the bridge that did not exist when T5 projected it. |
| T6b badge + boundary | `8abd526`, `ca90c1b`, `db57ffd`, `3e19bae`, `473bbdf` | DEC-36: the domain badge is drawn from FETCHER-side provenance, never a plugin-supplied field. DEC-37: the turn boundary is a GENERIC opaque carrier on the router; the composition root registers each owner's reset. DEC-38: the kernel draws the badge — and `tool_router.py` reached exactly 300/300 doing it. Two more ceiling extractions (`router_registry.py`, `router_surfaces.py`). |
| T6b model-facing | `11ee45e`, `72278b4`, `4db785a` | DEC-39: a servicing branch is a REQUIREMENT of mounting a routed tool, not a follow-up. DEC-40: catalog v3 — `web__search` + `web__fetch` become MODEL-VISIBLE (the project's THIRD model-visible change; 7 tools, byte-pinned). DEC-41: the three `web_research` persona laws, APPENDED to `persona_rules.py` so the composed prompt's delta is provably additive. |
| T7 live SOP | `0718e1d`, `7b16bfe`, `338b40c` | The acceptance script (DEC-12-driven: the security half contains NO model at all), the DEC-42 fix it forced, and the observation refresh at close. |

## 3. Governance — DEC-14 through DEC-42

Twenty-nine rulings. The ones that changed the shape of the code:

| Ruling | What it settled |
|---|---|
| **DEC-14** | Untrusted results are wrapped ONCE at the router boundary — not per plugin, not by the plugin itself. A plugin may never frame its own output. |
| **DEC-15** | Session taint is sticky, raised kernel-side in the wrap's OWN branch, from what the kernel MOUNTED as tainted. Impact classification is the kernel's, from the mount. |
| **DEC-16** | Two-turn spoken confirmation with a DETERMINISTIC detector, bound to a hash of tool + arguments, single-use. |
| **DEC-17** | Fetch defenses: a broker-owned, ZERO-CREDENTIAL, IP-pinned fetcher. Resolve once, validate as an IP object, pin, re-validate every hop. |
| **DEC-18** | The `SearchProvider` seam. Tavily default because it returns extracted CONTENT (fewer fetches = narrower SSRF surface); Brave + SearXNG behind the same seam. |
| **DEC-19 / DEC-21** | Zero `orchestrator.py` touches, three mandatory mechanical extractions first, and the feasibility census that made both provable rather than hoped. |
| **DEC-20 / DEC-36 / DEC-38** | Three-layer attribution: the persona law, the internal directive on the wrapped result, and the kernel-drawn domain badge from fetcher-side provenance. |
| **DEC-22** | ONE total wall-clock budget over the whole operation (DNS + robots + hops + stream), fail-closed. The per-request timeout was a turn-budget DoS under tainted redirects. |
| **DEC-25** | The T7 SOP MUST run the REAL-handshake SNI negative — the one property a unit test structurally cannot prove. It is what surfaced DEC-42. |
| **DEC-26** | The provider cost + wire contracts are DOC-DERIVED; verification against real billing is a T7 ACCEPTANCE GATE, because the cost fails SILENTLY into the sovereign ledger. |
| **DEC-27** | The provider reaches the plugin by INJECTION, not by a capability. Adding `web.search` to the closed enum was a category error. |
| **DEC-28** | Third-party HTTP logging is SILENCED at the composition root (not filtered — a filter puts security parsing inside the logging path). |
| **DEC-34** | The ROUTER obtains a plugin's cost and charges the ledger. A PLUGIN may never declare a number that reaches the sovereign daily total. |
| **DEC-37** | The turn boundary is a generic opaque carrier; the composition root registers each owner's reset. The kernel names no consumer. |
| **DEC-39** | Mounting a routed tool REQUIRES its servicing branch in the same breath — found before the mount, not after. |
| **DEC-40 / DEC-41** | Catalog v3 and the three persona laws — the model-facing half, landed last on purpose. |
| **DEC-42** | A TLS connection may never be reused across hosts: ONE httpx client per HOSTNAME. Closes a certificate-verification gap in DEC-17, found while building DEC-25's negative. |

Recorded-and-deferred: DEC-29 (Phase-1 wrap relocation), DEC-30 (the ceiling
breach that moved an extraction earlier), DEC-31 (the approval detector's input),
DEC-32 (impact reads `taint` as the externality signal — a deliberate coupling),
DEC-33 (`ctx.net` has no muthis-profile bridge — a deferred question for community
plugins), DEC-35 (a type-inaccurate refusal makes the model retry — an observation
for `doc_rag`).

## 4. The live SOP — Sultan's run, 2026-07-29

The T7 script (`scripts/diag_web_research.py`) drove the real graph on real
hardware. Its security half runs with NO model in the loop (DEC-12): a scripted
reasoner over a mocked wire, through the real Orchestrator → TurnPass →
ToolRouter → ConfirmGate → WebResearchPlugin → HardenedFetcher. **Sultan ran the
full SOP and signed off personally. The milestone is ACCEPTED.**

### 4.1 The cost chain — CLOSED with dashboard evidence

This was the milestone's single most important check, because a wrong cost
corrupts the ceiling Rule 10 exists to defend, and it does so SILENTLY.

- **Tavily's console moved 2 → 3 credits** across CHECK A's single query.
- **`budget.json` recorded 0.008 USD** for that query.
- **Both halves of the ledger moved by that same amount** — the `web_research`
  plugin bucket AND the sovereign daily total.

**DEC-26 is CLOSED: the doc-derived constant is now VERIFIED against real
billing.** **DEC-34 is CLOSED: the bridge is proven end to end.** The evidence
is the dashboard delta — the half no in-process check could ever supply, which
is precisely why DEC-26 made it an acceptance gate instead of a unit test.

### 4.2 The DEC-15 × DEC-16 acceptance question — ANSWERED

**The question:** the first fetch raises taint, so the second high-impact web
call in a session is refused pending spoken approval. On a genuine multi-source
research turn, how many calls get refused, and where?

**The answer: ZERO. No friction. Both rulings stand unchanged.**

**The cause matters more than the number.** The model used `web__search` ALONE.
Tavily returns extracted content, so no `web__fetch` was needed — and with no
second high-impact call, there was nothing to gate. That is not luck; **it is
precisely the property DEC-18 chose Tavily for.** Fewer fetches means a narrower
SSRF surface AND less confirmation friction, from one decision.

**The consequence, recorded so it is not rediscovered the hard way:** this answer
is PROVIDER-CONDITIONAL. Brave and SearXNG return LINKS, not content. Switching
`MUTHIS_SEARCH_PROVIDER` to either one makes `web__fetch` the normal path
again — and can reintroduce exactly the friction this question was about. A
provider change is therefore a TRUST-SURFACE change, not a configuration
preference, and re-running this observation is part of making one.

### 4.3 The three persona laws — confirmed working live

- The model **spoke its query before sending it** (the "say what you are about to
  do" law).
- It **cited three sources in natural Arabic prose** — no URLs, no machine
  formatting, no delimiter wording leaking into speech.
- It **stayed inside the verbosity cap**.

DEC-20's three attribution layers are therefore all present AND all observed:
the law (spoken), the directive (on the wrapped result), the badge (drawn by the
kernel).

## 5. What mutation testing actually found

Every ruling in this milestone was mutation-verified under
`PYTHONDONTWRITEBYTECODE=1`. The record is worth stating plainly, because it is
not the record the practice is usually sold on:

**Mutation testing found ZERO defects in the code. It found SEVEN holes in the
guards.** Every mutation either turned its test RED — the guard held — or
exposed a test that was proving something other than what it claimed. The three
REAL code defects this milestone found (DEC-22's turn-budget DoS, DEC-28's URL
logging, DEC-42's cross-host TLS reuse) were each found by design review or by
live probing, never by a mutation. **Mutation testing tests the tests.** That is
its actual job, and on this evidence it is worth its cost for exactly that.

| # | Where | The hole | The lesson |
|---|---|---|---|
| 1 | `5a63033` (T3b / DEC-18) | The key-leak check was case-SENSITIVE while `selection` lower-cases what it reads from the environment — a key echoed through that path would have slipped past. | A guard must match the normalization the code under test actually applies. |
| 2 | `b29c65f` (DEC-28) | The policy guard iterated the module's OWN tuple, so deleting an entry deleted its own expectation. | A self-referential guard checks nothing. Name the requirement independently of the code that satisfies it. |
| 3 | `ca90c1b` (DEC-37) | The composition scan asserted the `fetched_domains` KEYWORD was present, so `fetched_domains=None` passed green while production would have accumulated the badge forever. | A guard that checks a parameter's NAME checks nothing about what production WIRES. |
| 4 | `72278b4` (DEC-40) | FIVE of six mutations survived the first run — every catalog and servicing test built its OWN router, so `taint=False`, an empty `RouteImpact()`, a context without `net`, a schema drift, and DELETING THE MOUNT CALL FROM `main.py` all passed green. | A test that builds its own graph proves the CODE works and says nothing about what PRODUCTION wires. |
| 5 | `4db785a` (DEC-41) | The citation test asserted its two key words SEPARATELY; both occur elsewhere in the prompt, so deleting the entire citation law stayed green. | Asserting a law's WORDS is not asserting the LAW. |
| 6 | `0718e1d` (the T7 script) | Two in one run: single-use was passing on the EXPIRY rule (a later turn is refused whatever the gate does), and the DEC-25 SNI negative reported a false FAIL off a pooled connection. | A check must live where its property is OBSERVABLE — and a negative that skips the handshake proves nothing. |
| 7 | `7b16bfe` (DEC-42) | The eviction-closes-the-client assertion read `is_closed` AFTER the `finally` that calls `aclose()`, where it is True whatever eviction did. | Sample a state BEFORE the teardown that also produces it. |

The commit bodies keep a running tally — DEC-37's is recorded as "the fourth",
DEC-40's "the fifth", DEC-41's "the sixth", and DEC-42's as "the same shape as
the milestone's earlier six". Row 6's two were found in the acceptance script's
own checks rather than in the guard suite; the running tally does not include
them.

Two further disciplines came out of this, and both are now standing rules (§6).

## 6. Standing constraints (operative for Milestone 3)

1. **`tool_router.py` is AT 300/300 and the ceiling is IRREDUCIBLE.** No
   mechanical extraction remains — what is left is the dispatch funnel itself
   (`service` + `_outcome_for` + `_execute_route`, two delegators, three seam
   surfaces, the docstring). **Any future addition requires SPLITTING THE
   DISPATCH FUNNEL, which is a DESIGN DECISION needing a ruling, not a move.**
   It runs against DEC-30's reason for extracting `core_router` (so the funnel
   could be read whole) and the twice-upheld refusal to move `_outcome_for`.
   Budget a ruling round for it at PLANNING time. `doc_rag` mounts tools; it
   will hit this on day one.
2. **`orchestrator.py` stays at 299/300 — extract before adding, never
   compress.** It is BYTE-IDENTICAL across this entire milestone, which is the
   proof that DEC-19's "zero orchestrator touch" plan was real.
3. **Sample before teardown.** A state that teardown also produces must be
   sampled BEFORE teardown, or the assertion passes on the teardown rather than
   on the behaviour (guard hole 7). Pair every separation test with a REUSE
   control, or a component that separates everything passes vacuously.
4. **Remove the expressible weaker construction.** When a design closes a gap by
   making the bad state unrepresentable, the OLD shape must be deleted
   everywhere — including from the tests. DEC-42's seam is a client FACTORY, not
   a client: a caller cannot express "one shared client for every host" without
   deliberately writing a factory that returns the same object, and no
   composition anywhere may verify a weaker property than production wires. A
   configuration flag that happens to be set correctly is not a guarantee.

## 7. Known limits (recorded, not hidden — accepted for launch)

1. **An empty badge on snippet-only turns.** A turn answered from search
   SNIPPETS alone fetches nothing, so the badge is EMPTY. That is the honest
   signal — nothing was read in depth — but an empty badge is not
   distinguishable at a glance from a turn with no web use at all. The live
   research turn (§4.2) was exactly this case: search-only, badge empty,
   citation carried entirely by the persona law in prose. No friction was
   reported. The limit stands as recorded, now with one live data point.
2. **No per-claim attribution.** The badge says "these domains were fetched this
   turn", not "this sentence came from this domain". Precise per-claim binding
   is POST-LAUNCH research (DEC-20).
3. **The model is the MESSENGER for confirmation.** It SPEAKS the confirmation
   request, so an injected model could word it misleadingly. Mitigated by the
   directive requiring the tool and its arguments be named aloud, and by the
   detector being deterministic — the model never participates in the approval
   DECISION. Full removal requires the KERNEL to author the spoken confirmation
   (touching `TurnVoice`), recorded as POST-LAUNCH research (DEC-16).
4. **`_execute_route`'s docstring is PROTECTED from compression.** It is 18 of
   the DEC-34 bridge's 33 lines, sitting inside a file at 300/300 — the first
   thing a future contributor under ceiling pressure will reach for. Those 18
   lines carry the WHY: that the ROUTER obtains the cost so the figure never
   leaves kernel scope, that the rejected alternative would have let a PLUGIN
   declare a number reaching the sovereign daily total, the three prior refusals
   of that same shape (DEC-29 `is_error`, T5 `read_only`, DEC-14
   self-wrapping), and the known limit with its revisit trigger. **Under ceiling
   pressure, reach for an EXTRACTION, never for the rationale.** Upheld three
   times (DEC-30, the T5 ceiling finding, and this entry).

## 8. Final state

- **Tests:** **988 app + 27 sdk green** on `.venv` (note: `.venv-v5` lacks
  trafilatura and produces false failures — use `.venv`).
- **Catalog:** `tests/snapshots/look_tools_v3.json` byte-pins the 7-tool v3
  catalog (`web__search`, `web__fetch` added to v2's five). The V1 four stay bare
  and byte-pinned to `look_tools_v1.json`.
- **Line law:** every module ≤300. `tool_router.py` 300 (AT the ceiling),
  `orchestrator.py` 299 (byte-identical), `fetcher.py` 273, `confirm_gate.py`
  269, `composition.py` 247.
- **Untouched and git-verified:** the draw path (`highlight_gate.py`,
  `draw_dispatch.py`, the Option-A sync point), `turn_voice.py`, `voice_out.py`,
  `file_reader.py`, and `address_guard.py` (byte-identical across DEC-42 — the
  SSRF property did not move by one line, which is why the backend redesign was
  rejected).
- **main:** untouched at `65170b2` — this branch has never been merged, pushed
  or tagged; that is Sultan's decision.

## 9. What remains (Sultan's decisions / follow-ups — NOT actioned here)

1. **Merge `feature/v2-phase2-web-research` → `main`** (Sultan runs it; consider
   tagging the milestone as M1 was).
2. **The consolidated docs pass** — DEC-7 (the Trust-Modes documentary sweep)
   plus DEC-1 batches 4-8, which were bundled to run AFTER `web_research`. Both
   are now un-blocked.
3. **The `tool_router.py` funnel-split ruling** (§6.1) — budget it at Milestone 3
   PLANNING time, before `doc_rag` needs a line.
4. **Deferred observations still OPEN:** the caption-pacing re-measurement; the
   `MAX_EXTRACT_CHARS` spurious-truncation interaction on duplicated page bodies;
   DEC-35 (a type-inaccurate refusal makes the model retry) for `doc_rag`;
   DEC-33 (`ctx.net` has no muthis-profile bridge) for the community-plugins
   phase.
5. **Deferred deviations from earlier milestones remain OPEN** (`PROJECT_STATE.md`):
   (a) the spoken three-strikes eviction announcement, (b) `muthis/annotate`,
   (c) the conformance-kit real-child boot check.

## 10. Commit ledger (this branch, `65170b2..HEAD`)

```
338b40c 2026-07-29 docs(diag): make the B8 observation measure the CLOSED property
7b16bfe 2026-07-29 fix(net): keep one httpx client per hostname (DEC-42)
0718e1d 2026-07-29 test(diag): add the T7 web_research acceptance script (DEC-12)
4db785a 2026-07-29 feat(persona): add the three web_research laws (DEC-41)
72278b4 2026-07-29 feat(catalog): make web__search and web__fetch model-visible (v3, DEC-40)
11ee45e 2026-07-28 feat(kernel): service the web tools through the router (DEC-39)
473bbdf 2026-07-28 feat(kernel): draw the domain badge from the broker's record (DEC-20/38)
ca90c1b 2026-07-28 feat(kernel): fire the turn boundary for both web guards (DEC-37)
3e19bae 2026-07-28 refactor(kernel): extract the pre-dispatch refusals to router_surfaces.py
db57ffd 2026-07-28 refactor(kernel): extract merged_descriptors to router_registry.py
8abd526 2026-07-28 feat(overlay): draw the domain badge from fetcher-side provenance (DEC-36)
a9b654a 2026-07-25 feat(kernel): let the router obtain a plugin's cost and charge the ledger (DEC-34)
f565f2d 2026-07-25 refactor(kernel): move mount() to router_registry.py
a956a21 2026-07-25 feat(plugins): add web_research over the injected provider and ctx.net (DEC-18/27)
f0f9f3b 2026-07-25 feat(broker): wire the ctx.net seam and make net.fetch binary (DEC-24)
872bcdf 2026-07-25 feat(trust): gate high-impact calls behind a two-turn spoken confirmation (DEC-16)
88f097a 2026-07-25 refactor(kernel): extract MountedRoute to router_registry.py
c6b2ee3 2026-07-25 refactor(kernel): extract the router's model-facing surfaces
cfd8eb7 2026-07-25 feat(trust): classify high-impact calls kernel-side, from the mount (DEC-15)
7cfca97 2026-07-25 feat(kernel): raise session-sticky taint at the router (DEC-15)
9b5d5a0 2026-07-25 refactor(kernel): extract build_core_router to core_router.py
8176bdf 2026-07-25 feat(kernel): wrap untrusted tool results centrally at the router (DEC-14)
b29c65f 2026-07-25 fix(privacy): silence third-party HTTP logging at the composition root (DEC-28)
f6c8b16 2026-07-25 feat(broker): add Brave and SearXNG behind the same search seam (DEC-18)
9b23cf3 2026-07-25 docs(decisions): record DEC-26 + DEC-27 and the two-venv environment finding
5a63033 2026-07-25 feat(broker): add the SearchProvider seam + Tavily, the default (DEC-18)
21e34cf 2026-07-25 docs(test): record the two known limits of the bypass AST scan
f6c09e7 2026-07-25 test(broker): forbid trafilatura/urllib3 fetcher bypass by construction (DEC-21-E)
c0f14b9 2026-07-25 feat(broker): extract readable text from fetched HTML (DEC-18)
a77fb36 2026-07-24 fix(broker): bound the whole fetch under one total wall-clock budget (DEC-22)
424f3c0 2026-07-24 refactor(broker): extract the wire layer to transport.py (DEC-23)
752f2e8 2026-07-24 docs(decisions): record web_research T2 follow-ups (DEC-22..25)
cffe666 2026-07-24 feat(broker): add the IP-pinned hardened fetcher (DEC-17)
163e1f9 2026-07-24 docs(decisions): record ElevenLabs voice_id env finding
d6defbd 2026-07-24 docs(decisions): record deferred caption-pacing re-measurement observation
76dd8d8 2026-07-23 refactor(turn): extract tool_result pairing to kernel/tool_result_pairing.py
e3f82b8 2026-07-23 refactor(main): extract build helpers to composition.py
c901208 2026-07-23 refactor(persona): extract tool+safety rules to persona_rules.py
9c661ce 2026-07-23 docs(decisions): record DEC-21 -- web_research P0 feasibility gate
79bb130 2026-07-23 docs(decisions): add DEC-15/16/19 back-pointers + defer roadmap taint wording
1e49abd 2026-07-23 docs(decisions): record DEC-14..20 -- web_research governance
<this commit>  2026-07-29 docs(reports): Phase 2 M2 web_research closure report
```
