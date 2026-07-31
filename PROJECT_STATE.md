# PROJECT_STATE.md — Mut'his condensed technical state

> Token-saving snapshot (updated 2026-07-31, V2 Phase 2 M3 `doc_rag`
> COMPLETE). **`AGENTS.md` remains the full source of truth**; this is the
> compressed map. Branch `feature/v2-phase2-doc-rag` (cut from `main` at
> `b7654f7`, which already carries the M1 and M2 merges); app suite **1216 green**
> (V1 474-oracle preserved) + 27 sdk tests — run on `.venv`, NOT `.venv-v5` (that
> one lacks trafilatura and produces false failures).
> Architectural decisions & any logged ambiguities live in `DECISIONS.md` (repo root).

## CURRENT STATUS — V2 PHASE 2, M3 `doc_rag` COMPLETE (live-signed 2026-07-31)
**Phase 2, Milestone 3 — `doc_rag`** is COMPLETE on `feature/v2-phase2-doc-rag`
(cut from `main` at `b7654f7`; **main untouched — not merged, not pushed, not
tagged; the merge is Sultan's**). Mut'his opens the user's own document
(`docs__open`) and answers questions from it (`docs__query`) — catalog **v4**,
nine tools, byte-pinned — in Arabic, aloud, citing the page. Sultan ran the Live
SOP on his hardware on the FIFTH attempt, 2026-07-31, and signed off personally:
`query: candidates=` reached the live phase for the first time, the absence law
fired correctly on a genuine miss (all three DEC-57(a) clauses), and the spoken
page citation was CORRECT against ground truth.
**What the milestone cost, and why it is worth recording:** four earlier live runs
all failed with the SAME visible symptom — the model retrying — and THREE different
causes (a note that reported no state achieved; a slot rule that deferred the
payload-bearing call; a `doc_id` that could not survive a natural-language
round-trip). **A retry loop is a symptom, not a diagnosis.** The milestone also
produced the project's first automated guard for the ≤300-line LAW, after a real
breach passed in silence because neither half of the enforcement existed.
Closure record: `docs/reports/phase2_m3_doc_rag.md`; rulings DEC-44..DEC-63.
**Next (Sultan's):** merge to `main` (consider a tag); then the APPROVED
`diag_doc_rag.py` reduction, which executes AFTER close and must PROMOTE K7, K0
and G7 to pytest before deleting anything.

## V2 PHASE 2 — M3 `doc_rag` (COMPLETE, live-signed 2026-07-31)
Open a document, then ask it. Gates P0→T6, each STOP-gated.
- **The tools:** `docs__open` + `docs__query` — catalog **v4**, nine tools,
  byte-pinned (`tests/snapshots/look_tools_v4.json`); the project's FOURTH
  model-visible change, additive over v3.
- **DENSE-ONLY (DEC-50).** `pypdf` extraction → structural chunking sized in
  TOKENS (DEC-45) → `multilingual-e5-small` int8 on ONNX → cosine over unit
  vectors. No BM25, no fusion, no second normalized pipeline: the lexical half's
  unique contribution over dense measured **ZERO** at the P0 gate.
- **Three size zones decided in the BROKER (DEC-47)**, never by a plugin:
  inject the whole text, index it, or refuse honestly — the refusal estimated UP
  FRONT, with `assert_zone_invariant()` failing startup on an incoherent config.
- **Security inherited WHOLE from M2, with nothing added:** a passage is wrapped
  at the ONE router site with a fresh nonce, raises the session taint in the SAME
  branch, and the route holds NO capability. DEC-51 mounts `taint=True` TOGETHER
  WITH the kernel-side read hint, so reading a local document never demands
  spoken approval while a later web fetch still does.
- **THE LOAD-BEARING GUARANTEE is a persona law, not a gate.** At **82% effective
  recall** a retrieval miss is the EXPECTED case and DEC-49 retired the entry
  floor, so DEC-57(a)'s «ما لقيت هذا في المستند» is the only layer between a miss
  and a confident fabrication until Phase 3's visual citation. Proven live.
- **Privacy is structural:** the index is RAM-only and dies with the process, and
  the document PATH is never logged — extension, outcome and size only (DEC-61).
- `orchestrator.py` **untouched at 299**; `tool_router.py` absorbed the whole
  mount at **ZERO lines**, exactly as the P0b ceiling measurement predicted.
- **Known limits:** ~20 s of silence on first ingestion (ACCEPTED; the spoken
  announcement lands in Phase 3 with the other voice-surface items); 82% recall;
  no per-claim attribution; the model remains the messenger.

Phase 0 CLOSED + merged. **Phase 1** (broker + privileges + MCP bridge) CLOSED +
MERGED (`dbfec3a`, tag `v2-phase1-complete`). **Phase 2 M1 `sandbox_exec`** CLOSED
+ MERGED to `main` (merge `dcfa25f`, tag `v2-phase2-m1-complete`). **Phase 2,
Milestone 2 — `web_research`** CLOSED + **MERGED to `main`** (merge `1c59d60`,
tag `v2-phase2-m2-complete`; verified an ancestor of `main`): the model searches
the web via `web__search` and reads a page via
`web__fetch`, and everything it reads is treated as HOSTILE by construction.
Sultan ran the full T7 Live SOP on his hardware 2026-07-29 and signed off
personally. **The two questions the milestone could not answer for itself were
both answered live:** (1) THE COST CHAIN closed with DASHBOARD evidence — Tavily's
console moved 2 → 3 credits across CHECK A's single query while `budget.json`
recorded 0.008 USD into BOTH the plugin bucket and the sovereign daily total, so
DEC-26's doc-derived constant is VERIFIED against real billing and DEC-34's bridge
is proven end to end; (2) THE DEC-15 × DEC-16 FRICTION QUESTION answered ZERO
refusals — the model used `web__search` alone because Tavily returns extracted
content, which is precisely the property DEC-18 chose it for; both rulings stand
unchanged, and the answer is PROVIDER-CONDITIONAL (Brave/SearXNG return links, so
switching makes fetch normal again and can reintroduce the friction). The three
persona laws were confirmed live: query spoken before sending, three sources cited
in natural prose with no URLs, verbosity cap held. Closure record:
`docs/reports/phase2_m2_web_research.md`; rulings DEC-14..DEC-42 in `DECISIONS.md`.
Both follow-ups are DONE: the branch was merged (`1c59d60`) and the consolidated
docs pass (DEC-7 Trust-Modes sweep + DEC-1 batches 4-8) landed with it.

## V2 PHASE 2 — M2 `web_research` (CLOSED, live-signed 2026-07-29)
Search + fetch behind `net.fetch`. Gates P0→T7, each STOP-gated.
- **The tools:** `web__search` + `web__fetch` — catalog **v3**, seven tools,
  byte-pinned (`tests/snapshots/look_tools_v3.json`); the project's THIRD
  model-visible change (DEC-40). The plugin
  (`src/muthis_plugins/web_research/`) holds NO key, NO client, NO endpoint and
  NO socket: the provider is INJECTED already-built (DEC-27) and a page is read
  through `ctx.net.fetch_readable` (DEC-24). A search performs ZERO fetches BY
  SHAPE, and `fetch_gate.py` caps fetches at 3 per turn.
- **The untrusted-content boundary — this milestone's lasting contribution:**
  ONE wrap site (`kernel/untrusted_content.py` + `ToolRouter._outcome_for`, fresh
  nonce per wrap, DEC-14) · ONE taint-raise site, in the SAME branch, because
  wrapped-without-raised leaves the session looking clean (`kernel/
  session_taint.py`, DEC-15) · ONE confirmation site (`trust/confirm_gate.py` —
  two turns, deterministic detector, bound to sha256(tool+args), single-use,
  DEC-16). The model never participates in its own authorization.
- **The fetch** (`src/muthis/broker/net/`): IP-pinned and zero-credential, resolve
  once → validate as an IP object → PIN → re-validate EVERY hop (DEC-17), under
  ONE total wall-clock budget (DEC-22 — the per-request timeout it replaced was a
  turn-budget DoS under tainted redirects), with ONE httpx client per HOSTNAME so
  a TLS connection can never be reused across hosts (DEC-42).
- **The search seam** (`src/muthis/broker/search/`): Tavily default, Brave and
  SearXNG behind the same protocol; the destination is CONFIGURATION-ONLY (no
  url/base_url/host parameter anywhere, signature-scanned), so a tainted model can
  never aim the key-bearing client (DEC-18).
- **Attribution, three layers** (DEC-20): the persona citation law (DEC-41), the
  internal directive on the wrapped result, and the kernel-drawn domain badge
  whose facts come from the FETCHER, never from a plugin (DEC-36/37/38).
- **Privacy:** third-party HTTP logging SILENCED at the composition root
  (`logging_policy.py`, DEC-28) — httpx logs full URLs at INFO, which would have
  written fetched URLs and the user's search QUERY into the app log. Fixed before
  the first real key ran.
- **Ceiling discipline:** `orchestrator.py` BYTE-IDENTICAL throughout (DEC-19's
  zero-touch plan, proven); five mechanical extractions bought the room
  (`persona_rules.py`, `composition.py`, `kernel/tool_result_pairing.py`,
  `kernel/router_registry.py`, `kernel/router_surfaces.py`, plus
  `kernel/core_router.py`). **`tool_router.py` now sits at 300/300 and is
  IRREDUCIBLE** — any future addition needs a funnel-split RULING, so budget one
  at Milestone-3 planning (DEC-38).
- **Mutation testing's actual record:** ZERO code defects, SEVEN holes in the
  GUARDS. The three real defects (DEC-22, DEC-28, DEC-42) came from design review
  and live probing. Mutation testing tests the tests — see the closure report §5.
- **Known limits (accepted, recorded):** an empty badge on snippet-only turns · no
  per-claim attribution · the model is the MESSENGER for confirmation ·
  `_execute_route`'s docstring is protected from compression.

## V2 PHASE 2 — M1 `sandbox_exec` (CLOSED, live-signed 2026-07-22)
Isolated code execution behind `sandbox.execute`. Gates P0→T6, each STOP-gated.
- **The tool:** `sandbox__run_code` — a declaration plugin mounted namespaced →
  JOINS the model catalog (byte-pinned `look_tools_v2.json`, the FIRST
  model-visible change since Phase 1). DEC-11 fixed the namespace separator to
  `__` (a dot fails the Anthropic tool-name pattern), living in ONE place
  (`tool_router.namespaced_name`) + a guard test over EVERY catalog name.
- **The engine** (`src/muthis_plugins/sandbox_exec/`, muthis_sdk + stdlib only):
  `runner.py` (one container lifecycle over injected asyncio-subprocess + gate
  seams; ALL DEC-3 flags incl. `--read-only`; bounded ANSI tails; wall timeout →
  `docker kill` → `rm -f` always; NEVER raises), `bootstrap.py` (DEC-9 stdin
  staging into the tmpfs `/work` — NO `docker cp`), `sandbox_gate.py` (≤3
  runs/turn, DEC-3-B, decoupled from HighlightGate), `service.py` (turn-aware
  gate + runner + F9 kill).
- **Kernel touch = ONE:** the generic `on_interrupt` hook (`kernel/
  interrupt_hooks.py`, DEC-3-C) the sandbox registers `docker kill` into; the
  sealed kernel never names "docker". `turn_pass` services `run_code` after the
  sync point (like read — NEVER the draw gate); `turn.py` pairs it by name.
- **The staging guard** (`file_reader.stage_file_gate`): secret NAMES refused,
  path structure refused OUTRIGHT (DEC-13 — `/` `\` `..` → no `/work` escape, by
  construction), binary refused, content never logged. Proven DETERMINISTICALLY
  in the live SOP (DEC-12), never via model judgment.
- **Confirmation / session-taint were DEFERRED to `web_research`** (DEC-10 — no
  trigger here: the launch schema has no network param, taint is unpopulated).
  **DELIVERED there** (DEC-15/DEC-16); the DEC-15 refinement keeps a network-LESS
  sandbox run friction-free under active taint — the isolation IS the containment.
- **Untouched:** the draw path / Option-A sync / HighlightGate (git-verified).
  604 app + 27 sdk green at M1 close; ADMISSIBLE. **MERGED to `main` 2026-07-22
  (merge `dcfa25f`, tag `v2-phase2-m1-complete`)**; `main` then took the DEC-1
  docs merge and sits at `65170b2`. Full detail:
  `docs/reports/phase2_m1_sandbox.md`.

## V2 PHASE 1 — broker, privileges, MCP (M1-0→M1-7, zero V1 behavior change)
- **Q-4 settled (M1-1):** the 8 compat shims are GONE; every consumer imports
  `muthis.kernel.*`; a revived old path FAILS a guard test.
- **M1-2:** `kernel/frame_capture.py` extracted (hide→settle→capture, order
  load-bearing) → orchestrator 284/300 with the ONE router seam injected;
  `main.py` composes `build_core_router` at the root (deviation D-1 settled).
- **M1-3:** per-plugin budget column (`plugins` ledger key): every serviced
  call counted per provenance; REAL plugin costs feed the plugin bucket AND
  the sovereign daily total; `can_afford`/`record_turn` contracts untouched.
- **M1-4:** `broker/` — GrantsStore (consent sha256-pinned to manifest BYTES;
  any change invalidates = update-diff by construction), Broker (grant →
  capability-gated PluginContext; denial = absent seam; FileReader gates
  kernel-side), trust flow `python -m muthis.broker.trust <path>`; the
  conformance kit's permission-violation suite went LIVE (starved-context
  denial + undeclared-use spy detection) — 0 SKIPs on the core four.
- **M1-5:** the MCP layer, stdlib (Q-1.1): sdk `mcp/` framing+messages
  (protocol PINNED 2025-06-18, 4MiB frame wall) + broker `mcp/` client
  (20s call timeout; EOF fails in-flight INSTANTLY; sampling refused),
  policy (readOnlyHint-only exposure; text-only, 16k cap, §3.2 source-
  wrapping), host (plugins.d, lazy catalog-then-close, three-strikes +
  Arabic announce seam, list_changed quarantine), proxy (namespaced,
  taint=True). `ServiceOutcome.taint`/`TurnResult.taint` live (recorded;
  enforcement with Phase-2 high-impact tools). UTF-8 wire armor (Windows
  cp1256 pipes) at runtime/client/fixtures — live-critical on this machine.
- **M1-6:** `muthis_sdk.mcp_runtime` (SYNC stdio, owns its encoding): any
  ToolPlugin becomes an MCP server; muthis-profile/1 negotiation backs
  ctx.files/ctx.screen with `muthis/read_file`/`muthis/capture` bridge
  requests serviced through `broker.context_for` (refusal =
  CAPABILITY_NOT_GRANTED_AR as ordinary text); annotate deferred (Q-1.2).
  `examples/hello_world` = the reference community plugin.
- **M1-7:** root composition in `main.py` (router+broker+host; bridge capture
  rides the SAME chokepoint via a broker-owned FrameCapture; mount at boot;
  children terminated at shutdown). `examples/demo_server` = the Q-1.4
  self-contained Python foreign server with a destructive DECOY the filter
  hides. **Phase-1 scope law:** mounted MCP tools live in the ROUTER only —
  the model-visible catalog stays the byte-pinned V1 four until Phase 2.
- Announce seam logs for now (spoken delivery joins the voice line with
  Phase 2's first high-impact plugin — the audio path stayed untouched).

## DEFERRED / DEVIATIONS (gate-audited ledger)

> Every intentional deferral or deviation lives here so NO deferral is lost.
> Each future phase gate MUST audit this list and close any item whose closing
> condition its phase satisfies. Per item: the item / its reason / the phase
> where it lands / its closing condition.

### (a) Spoken three-strikes eviction announcement
- **Item:** when an MCP server is disabled after three consecutive failures,
  `McpHost` emits an Arabic announcement through an injected `announce` seam;
  in Phase 1 `main.py` wires that seam to the LOGGER, not the spoken voice
  line. The seam exists and is unit-tested — only the audible delivery is
  deferred.
- **Reason:** wiring it to `VoiceOut`/the turn voice touches the sacred audio
  path, and Phase 1 ships no high-impact plugin whose eviction a user would
  need to hear; adding audio plumbing for a non-existent consumer is
  unjustified risk (the audio path stayed byte-untouched this phase).
- **Lands in:** Phase 2 (with the first high-impact plugin, `sandbox_exec`).
- **Closing condition:** `McpHost.announce` routed through the turn voice so
  an evicted server is spoken in Arabic (queued behind any playing audio,
  never overlapping), proven by a live diag showing an eviction announced
  aloud.
- **Gate audits:** M1 (2026-07-22) — NOT closed; `sandbox_exec` wired no MCP
  eviction voice, so the predicted landing did not happen. M2 (2026-07-29) —
  NOT closed either; `web_research` mounts a native plugin, not an MCP server,
  so it still has no eviction a user would need to hear. **REMAINS DEFERRED**,
  and the "Phase 2" landing is now two gates stale — the next milestone that
  actually ships an MCP-backed capability should either close it or re-assign it.

### (b) The `muthis/annotate` profile bridge (Q-1.2)
- **Item:** `muthis-profile/1` ships `muthis/read_file` + `muthis/capture`
  only; the roadmap §8.4 `muthis/annotate` (a granted external plugin drawing
  via the ONE HighlightGate) is NOT implemented.
- **Reason:** decision Q-1.2 — keep the draw path isolated and sacred one more
  phase; no Phase-1 external plugin needs server-side drawing, and the draw
  circuit stayed untouched (ruling C-1).
- **Lands in:** INTENTIONALLY UNASSIGNED — this item stays deferred until
  `V2_ROADMAP.md` formally assigns it a landing phase through roadmap
  governance. No phase is committed here; the earlier informal "Phase 2+" hint
  is withdrawn, because assigning a landing phase is a roadmap decision, never
  an implementation guess.
- **Closing condition:** two gated steps — (1) `V2_ROADMAP.md` formally assigns
  `muthis/annotate` a landing phase through roadmap governance; THEN (2) it is
  added to the profile and routed through the ONE HighlightGate behind an
  `annotate.overlay` grant, with the V1 draw circuit byte-unchanged, proven by
  a live diag of an external plugin drawing via the gate. Until step (1), the
  item remains deferred and unscheduled.

### (c) Conformance-kit real-child boot check
- **Item:** the kit's `entry-class` check SKIPs `kind=mcp` plugins — it
  validates the manifest/schema but does NOT spawn the child and exercise the
  real stdio handshake + `tools/call`. (Out-of-process serving is instead
  cross-validated by `sdk/tests/test_mcp_runtime.py` against real children.)
- **Reason:** kit-driven child spawning adds process-lifecycle machinery the
  kit did not need in Phase 1; the runtime tests already prove real children,
  so the SKIP is honest, not a coverage gap.
- **Lands in:** Phase 2 (the kit's SKIP message already reads "kit-driven
  child spawning arrives in Phase 2").
- **Closing condition:** the kit spawns the `kind=mcp` child, runs
  `initialize` + `tools/list` + a golden `tools/call` over the real transport
  and asserts the profile-degradation path, replacing the SKIP with a live
  check.

## V2 PHASE 0 — kernel split + muthis-sdk (CLOSED 2026-07-17, live-verified)

### Phase 0 detail (historical)
- **kernel/**: orchestrator, turn_pass, turn, highlight_gate, draw_dispatch,
  history_hygiene, verbosity, budget moved to `src/muthis/kernel/` (git mv);
  old paths = explicit named re-export SHIMS until Phase 1 (Q-4), so the V1
  474-test oracle + diag scripts run UNMODIFIED. Shim↔kernel identity,
  SDK/plugin layering purity: test-enforced (`test_kernel_layering.py`).
- **ToolRouter** (`kernel/tool_router.py`): turn_pass's bespoke read servicing
  generalized (roadmap part 2 §1). Services ONLY `read_local_file`; the draw
  path + refresh frame lifecycle NEVER cross it (ruling C-1). Never raises —
  Arabic-note failure wall; cap 24; namespacing with core-name exemption
  (C-3). `read_file=` kwarg contract unchanged; orchestrator untouched (AT
  300 — the router injection seat moves to the Phase-1 broker composition).
- **muthis-sdk 2.0.0a1** (`sdk/`, `pip install -e sdk`): ToolPlugin /
  ToolDescriptor / ToolResult / ServiceOutcome (inert Phase-1 taint+cost
  fields) / PluginContext / manifest loader. Zero deps; CLOSED capability
  enum — no input.* exists (golden rule §1.1 by construction).
- **Core plugins** (`src/muthis_plugins/`, Q-2): look_pointer + look_shapes +
  screen_refresh (declaration-only, kernel_serviced) + file_read (routed via
  ctx.files; FileReader gates stay kernel-side). Schemas moved VERBATIM;
  `cloud/tool_schemas.py` = assembly re-export; model-visible catalog pinned
  byte-for-byte to `tests/snapshots/look_tools_v1.json` (v1.0.0 bytes).
- **Conformance kit** (`muthis plugin test <dir>`, roadmap §8.7): manifest /
  Arabic lint / schema structure / fake-kernel golden run (+ warn-only
  latency); permission-violation suite honestly SKIPPED until the Phase-1
  broker. All four core plugins: ADMISSIBLE. Broken fixtures: REJECTED.

## UAT ROUND 1 — two bugs found by Sultan, FIXED (v1.0-RC2, committed `2883321`)
**Bug 1 (F9 overlap — the old audio never died).** Three real holes, all closed:
(a) `run_turn`'s finally cleared `_active_turn_voice` BEFORE `finish()`'s
drain — but the drain IS when the tail is audible and users interrupt; the
window now stays open through it (nested finally). (b) `TurnVoice.interrupt`
early-returned on `_closed`, which finish() had already set mid-drain → now
guarded by its own `_interrupted` flag; the idempotent `session.abort()` fires
INTO the concurrent drain and unblocks it; finish() past an interrupt runs no
fallback and leaves the "listening" light alone. (c) The buffered paths were
uncancellable: `stream_pcm`'s `finally: finish()` DRAINED the queued tail on
cancellation (EL delivers ~10× realtime — the queue can hold the whole clip),
and the Gemini winsound sync clip was UNSTOPPABLE → cancel now ABORTS the EL
player, and Gemini plays via abortable `tts_ws_player.play_clip` (winsound is
out of the speech path entirely).
**Bug 2 (dialogue echo — «أبشر شوف» twice).** Two layers: (a) MECHANICAL — the
tts.py cascade replayed the WHOLE text via Gemini when ElevenLabs failed AFTER
audio had played (30 s total timeout / error frame); the ECHO GUARD
(`_last_player.got_audio`) now suppresses that fallback (truncated tail >
repeat). (b) MODEL-SIDE — pass 2 sometimes re-opens with pass 1's exact ack
(the known v7.1 regression family; prompts alone can't enforce): deterministic
`speech_stream.strip_leading_repeat` + `EchoGuard` (one-shot, ≤40 chars,
boundary-strict) strips it at the TurnVoice choke point.
**LIVE-verified (2026-07-16):** diag_interrupt — silence + clear + note
carried; the cancel-abort tightened after a measured 860 ms (the ws close
handshake ran before the player abort — now aborts INSIDE the recv loop).
diag_full_turn — the model-side echo REPRODUCED («أبشر، شوف» again as the
whole pass 2) and the suppressor caught it ("pass echo suppressed (9 chars)").
Residuals to WATCH in UAT round 2: pass-2 bare-ack (the echoed ack was pass
2's ONLY content — both ACK directives now forbid repeating the ack verbatim
and state the cost); one EL session died mid-turn (clean 1000 close between
passes) — degradation is now safe (no overlap/echo) but session stability is
an open observation.
Tests 474 green (+12 in `tests/test_uat_fixes.py`). Ceilings: orchestrator +
turn_voice now AT 300 — extract before ANY addition.

## V1 HISTORY: v1.0-RC1 — UAT / STAGING (2026-07-16, now CLOSED — see top)
RC1 = Phases 1-4 + the [DIAG] cleanup + the persona FORMATTING-SYNTAX BAN
(speech is pure spoken prose — no ** / # / ` / list dashes; the output
surface is TTS + the captions bar, never a markdown renderer — the Phase 4
live run showed raw asterisks in captions). UAT round 2 passed; V1 signed
off and released as `v1.0.0` on `main`.

## What Mut'his is
Arabic-first, LOOK-only voice teacher for Windows 11. Hold **F9**, speak Arabic,
release → Mut'his answers with Arabic speech (ElevenLabs WS primary, Gemini
fallback) while pointing/drawing on-screen. Reasoning+vision: Claude Sonnet
(`claude-sonnet-4-6`) via the `anthropic` SDK, SSE streaming. **LOOK-only** is a
hard boundary: speak, point (`highlight_target`), draw shapes (`draw_shapes`),
request a fresh screenshot, READ a local text file (`read_local_file`, v7
Phase 4 — read-only perception) — NEVER click/type/press/clipboard. RTX 4060,
~0 VRAM; everything heavy is cloud.

## Non-negotiable rules
- **≤300 lines/module**, single responsibility, importable in isolation. If a
  module nears the limit, SPLIT (don't compress). At/near ceiling now (measured
  2026-07-29): **`tool_router.py` 300 — AT the ceiling AND irreducible, any
  addition needs a funnel-split RULING (DEC-38)**, `turn_voice.py` 300,
  `orchestrator.py` 299 (byte-identical through M2), `tts.py` 296,
  `sidekick_window.py` 280, `fetcher.py` 273, `confirm_gate.py` 269,
  `turn_pass.py` 269.
- **Language split**: user-facing strings Arabic; logs/comments/identifiers/commits English.
- **Threading**: Tk lives on its own daemon thread; asyncio↔Tk only via
  `queue.Queue` commands. Keyboard→loop only via `loop.call_soon_threadsafe`.
  The ONE sanctioned cross-thread audio call is `Pa_AbortStream` (player.abort).
- **Tk teardown**: after mainloop the Tk thread drops all widget refs +
  `gc.collect()` so Tcl dies on its own thread (the `Tcl_AsyncDelete` fix).
- **cloud/ wrappers own no lifecycle** (Law 11): `run()` = one provider turn; the
  orchestrator owns history + the agentic loop + budget gating.
- **Privacy**: no transcripts/audio/screenshots logged (gate `MUTHIS_DEBUG`).
  Captions/TTS carry ONLY assistant-authored Arabic (VoiceOut is the choke point).
- **SOP**: every audio/UI phase ends with a LIVE test (`scripts/diag_*.py`),
  human approval, then commit. Live testing caught the Tcl abort AND the caption
  flashing that unit tests missed.

## Pipeline (one turn)
PTT hold → mic stream → STT (Scribe, `ar`) → agentic loop (≤4 passes,
budget-gated): ClaudeAgent.run() → TextDelta/ToolCall/TurnComplete → draw at
speak-time (Option A sync point) → point/whiteboard → speak via ONE continuous
turn voice → on `tool_use` re-call run() (point THEN explain). Draw circuit
breaker: ONE draw/turn, ONE `HighlightGate` over both draw tools; after a draw
the next pass is forced `tool_choice="none"` (API-enforced loop terminator).

## Phase 1 — Flawless Audio-Visual Sync (v7 / v7.1 / v7.2, LOCKED)
Killed the 3.48 s "stop-and-go" gap. Now draw→first-audio ≈0.26 s.
- **`turn_voice.py` `TurnVoice`**: ONE ElevenLabs generation per TURN (replaces
  per-pass streamer). Pass-1 ack is FED (instant, non-blocking) so the pass-2
  round-trip hides behind ack playback; pass-2 sentences join the SAME
  generation. `begin_open()` opens the WS EAGERLY at turn start (Fix G,
  overlaps the vision pass). `finish()` in run_turn's `finally` (drain +
  decision-15 fallbacks). `interrupt()` = Phase 3.
- **`tts_session.py`**: `try_trigger_generation` on FIRST feed only; BOS
  `chunk_length_schedule=[90,160,250,290]`; `feed(flush=True)` for a COMPLETE
  utterance (the ack); a flush ENDS the segment so the next feed re-triggers
  (v7.2 post-ack starvation fix). WS `inactivity_timeout=60`.
- **`speech_stream.py` `SentenceSplitter`**: min-length merge, ellipsis-run
  ender, soft valve (cut at space/`،`, never mid-word), EAGER FIRST emission
  (first sentence cuts at a comma ≥30 chars, digit-guarded — starvation bridge).
- **Persona (Fix E)**: pass-1 spoken ack MANDATORY (warm 2-word "أبشر، شوف"),
  a silent pass-1 banned, scoped to the pointing pass (pass-2 stays info-first).
- **Auto-hide (Fix F)**: armed ONCE at SPEECH END (run_turn's finally), keyed on
  RECEIVED draw calls (not gate.drawn); never at draw-time.

## Phase 2 — The Whiteboard + caption sync (LOCKED, commit d28a8c1)
- **`draw_shapes` gains `dim_screen` bool** → `PendingDraw.dim` (draw_dispatch,
  darkens BEFORE drawing) → overlay `dim_screen()`/`undim_screen()` →
  `FocusDimmer.show_full()` (full cover, ~250 ms alpha fade via self-rescheduling
  `after()` frames; generation counter orphans superseded fades; `hide()` stays
  INSTANT for ghosting) / `fade_out()`. Un-dim fires at SPEECH END; shapes keep
  the 7 s auto-hide grace. `spotlight_on=focus_dim_enabled()` keeps the
  whiteboard's dimmer from resurrecting the default-OFF v6 spotlight.
- **Persona**: وضع السبورة (concept/diagram → dim; user's own content → undimmed).
- **Caption↔audio sync** (the live-caught bug: captions flashed at generation
  speed): `PcmStreamPlayer.played_seconds()` (heard-audio clock, starvation-aware)
  + `ARABIC_TTS_CHARS_PER_SEC=11.5` (measured) → each caption defers to its
  estimated audio start via `CaptionBar.show_text_later` (root.after; clear()
  cancels all pending via a generation counter). `VoiceOut.show_caption(text,
  delay_s)` routes to the paced seam.
- **`win32_glue.py` (NEW)**: DPI + click-through extracted from sidekick_window
  (it sat AT 299).

## Phase 3 — Smart Interruption / F9 barge-in (LOCKED, commit e4b7bf1)
An F9 press WHILE speaking interrupts the teacher. Live: signal→silence
~92-136 ms (Pa_AbortStream); UI clears ~10 ms (hide BEFORE the audio abort).
- **`activation.py` (NEW)**: `ActivationController` extracted from main.py.
  Barge-in machine: press-during-turn opens a FRESH recording on the keyboard
  thread, then `schedule_on_loop` → `_do_interrupt`: await `interrupt_turn`
  (silence+clear+note) THEN cancel the old task (silence FIRST, cancel SECOND).
  The interrupted reset PRESERVES the barge-in mic + hold; a fast key-up is
  deferred; a stale interrupt (turn ended naturally) bails via pre-await task
  capture; double press ignored.
- **`player.abort()`** (Pa_AbortStream, discards queue, no drain), **`session.
  abort()`** (no EOS, reader cancelled, socket dropped), **`turn_voice.
  interrupt()`** (closed-FIRST → finish() no-ops, no fallback re-speak),
  **`orchestrator.interrupt_turn()`** (UI-first hide, then voice abort, sets
  the next-turn note).
- **`INTERRUPTED_NOTE_AR`** (highlight_gate): internal directive prepended to
  the NEXT turn exactly once ("the user cut you off mid-speech").

## Phase 4 — The Pedagogical Analyzer (built + live-verified 2026-07-16)
Mut'his READS a local file and teaches it: READ → ISOLATE → TEACH.
- **`file_reader.py` (NEW)**: `read_local_file` executor. Safety gates (the
  model picks the path): secret NAMES refused on raw+resolved path (.env /
  .env.* / id_rsa* / *.pem/.key / credentials* — symlink armor), binary (NUL
  sniff) refused, size double-bounded (2 MB refusal; 16k-char truncation at a
  line boundary + Arabic request-a-range hint). Returns 1-based numbered lines
  under an Arabic header; every failure = a short Arabic tool_result note
  (never raises). Content never logged.
- **Wiring**: schema in tool_schemas.py (path required, start/end_line
  optional); TurnPass detects + services the FIRST read per pass (after the
  sync point's audio is moving) → `consume()` returns a 3-tuple; turn.py's
  `build_tool_result_message` answers read ids BY NAME (serviced → content;
  duplicate → `FILE_ALREADY_READ_AR`) so a read NEVER flips the draw gate —
  the pass after a read stays `tool_choice="auto"`. Orchestrator seam
  `read_file` (default `stub_read_file`; main wires `FileReader().read`).
  Bug-3 strip extracted to `history_hygiene.py` (turn.py sat at 298).
- **Persona (التحليل التربوي)**: explain code/file/data → (1) read the REAL
  content (never guess from pixels), (2) content on screen → draw pass = ONE
  `draw_shapes` + `dim_screen=true` + rectangles around the analyzed LINES
  (the mandatory pedagogy whiteboard — the explicit carve-out to Phase 2's
  "user content stays undimmed"), (3) explain pass teaches line-by-line by
  number; file not on screen → voice-only.
- **Live SOP (`scripts/diag_pedagogy.py` +
  `assets/samples/esp32_logic/esp32_logic.ino` — the Arduino-IDE sketch
  folder)**:
  PASSED 2026-07-16 — read fired (24 lines), draw_shapes dim_screen=true with
  3 rectangles, explanation cited real line ranges + identifiers (LIMIT_C,
  readCelsius, TMP36 math), 3 passes, $0.0825, exit 0.

## Active .env flags (rollback switches)
| Flag | Default | Effect |
|---|---|---|
| `MUTHIS_STREAM_TTS` | OFF | v7 continuous turn voice (Phase 1). OFF = buffer-then-speak. |
| `MUTHIS_WHITEBOARD` | ON | Phase 2 dim-behind-drawing. Falsey = flat drawings. |
| `MUTHIS_BARGE_IN` | ON | Phase 3 F9 interrupt. Falsey = press-refused during a turn. |
| `MUTHIS_CAPTIONS` | ON | Live-captions bar. |
| `MUTHIS_FOCUS_DIM` | OFF | v6 spotlight (dim around a highlight). |
| `MUTHIS_FOCUS_ALPHA` | 0.30 | Dim opacity (spotlight + whiteboard), clamped. |
Others: `MUTHIS_HOTKEY` (f9), `MUTHIS_DAILY_BUDGET_USD` (0.75), `MUTHIS_EARCONS`,
`ELEVENLABS_VOICE_ID` (REQUIRED for the Arabic accent), `MUTHIS_GEMINI_VOICE` (Kore).

## Key module map (src/muthis/)
- **Core**: `orchestrator.py` (heart: loop/history/interrupt_turn), `turn_pass.py`
  (one pass + sync point), `turn_voice.py`, `voice_out.py` (speak+caption+privacy),
  `turn.py` (TurnResult/Overlay proto/tool_result builder), `verbosity.py`,
  `file_reader.py` (read_local_file, Phase 4), `history_hygiene.py` (Bug-3 strip).
- **Draw**: `draw_dispatch.py` (PendingDraw+next_draw), `highlight_gate.py`
  (circuit breaker + INTERRUPTED_NOTE_AR), `shapes.py`.
- **Voice**: `tts.py` (cascade), `tts_session.py`, `tts_elevenlabs.py`,
  `tts_ws_player.py`, `tts_gemini.py`, `tts_diacritics.py`, `speech_stream.py`.
- **I/O**: `mic.py`, `stt.py`, `hotkey.py`, `earcons.py`, `budget.py`,
  `activation.py`, `main.py` (composition root), `persona.py`.
- **Vision**: `vision/screen_capture.py`, `vision/downscale.py`.
- **Docs / RAG** (`broker/docs/`, V2 Phase-2 M3): `service.py` 281 (the two verbs
  `open`/`query`; owns the encoder LIFETIME, ranks nothing), `zones.py` 294 (the
  three size zones + `assert_zone_invariant`), `ingest.py` 274, `extract.py` 239
  (pypdf), `chunking.py` 222 (token-sized, structural), `encoder.py` 187
  (e5-small int8 / ONNX), `model_pin.py` 169 (artifact pinned BY FINGERPRINT),
  `blocks.py` 164, `notes.py` 133 (DEC-35's type-accurate refusals), `index.py`
  132 (RAM-only, dies with the process), `__init__.py` 87, `records.py` 70
  (`Passage`/`OpenedDocument` — the cross-boundary contract), `token_estimate.py`
  68. Plugin half: `muthis_plugins/doc_rag/plugin.py` 182, `delivery.py` 136
  (dedupe by parent, relevance order, cap), `schema.py` 104.
- **Caching** (`cloud/`, M3): `pricing.py` 105, `cache_control.py` 70 — the
  ledger cannot lie about a cached turn (DEC-60).
- **Overlay** (`overlay/`): `sidekick_window.py`, `window_commands.py`,
  `win32_glue.py`, `focus_dimmer.py`, `caption_bar.py`, `rectangle_widget.py`,
  `pointer_widget.py`, `pointer_animator.py`, `shapes_widget.py`,
  `status_indicator.py`, `style.py`, `style_env.py`.

## DIAG note
The temporary `[DIAG]` probes (logger `muthis.diag`) were REMOVED from ALL
modules on 2026-07-16 with Sultan's explicit authorization — the codebase is
production-clean (the load-bearing starvation re-anchor in tts_ws_player
survived, minus its log line). `scripts/diag_*.py` REMAIN as the live-test SOP
scripts (NEVER in CI); their docstrings note the probe removal.
