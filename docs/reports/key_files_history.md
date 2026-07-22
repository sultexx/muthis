# Key Files -- migrated per-file evolution history

**Provenance:** DEC-1 (see `DECISIONS.md`). The AGENTS.md "Key Files" table had
accreted detailed per-file version history (V1 / v5 / v6 / v7 and the V2-phase
narratives) mixed into each row's description -- the documented root cause of the
repeated documentation drift (D1-D12). Under DEC-1 that detailed history is migrated
HERE, so the AGENTS.md table stays a concise description of each file's CURRENT purpose
and live constraints instead of a changelog.

**How to read this file:** the authoritative CURRENT description + line count live in
`AGENTS.md`; this file is the "how we got here" for each file. Migrated milestone by
milestone under DEC-1 (never one pass); this is an append-only log. Em-dashes and
arrows are rendered ASCII (`--`, `->`) for byte stability; Arabic appears only as
identifier names (e.g. `INTERRUPTED_NOTE_AR`).

---

## src/muthis/kernel/orchestrator.py

Current shape (see AGENTS.md for the authoritative row): the heart of the turn
machinery -- owns the single asyncio event loop, conversation history, the 90 s session
bound, and the agentic loop; owns the Option-A draw->speak sync point and the per-turn
HighlightGate / TurnVoice lifecycle; fires the barge-in silencer and the generic
InterruptHooks on F9 while staying blind to Docker; delegates frame capture, voice
output, pass draining, and tool routing to injected seams.

Evolution:

- **v5 (extractions under the <=300-line law):** the spoken surfaces were extracted to
  `voice_out.py` (this file had sat at 299 -- the orchestrator builds ONE
  `VoiceOut(tts, overlay)` and delegates); pass-draining was extracted to `turn_pass.py`
  (the agentic loop calls `TurnPass.consume()` once per pass; history, pairing, budget
  gating and the loop stay in the orchestrator); verbosity became the `VerbosityController`
  seam, held ACROSS turns (unlike the per-turn HighlightGate).
- **Agentic loop (`_run_turn_pipeline`):** after a `tool_use` turn the orchestrator
  appends the Option-B pairing and re-calls `run()` to fetch the continuation, looping
  WHILE `stop_reason == "tool_use"` (so Muthis explains AFTER pointing instead of
  hanging), capped at `MAX_AGENTIC_ITERATIONS` (4) with `can_afford()` before EVERY
  iteration; it ends cleanly on `end_turn`, a None stop_reason, or the cap (spoken
  `AGENTIC_CAP_NOTE_AR`). A per-turn `HighlightGate` (rebuilt at the top of
  `_run_turn_pipeline`) is the loop circuit breaker, unified over both draw tools; the
  HARD terminator is `tool_choice` -> "none" once drawn.
- **v7 continuous voice:** `run_turn` builds ONE `TurnVoice` per turn
  (`self._pass.new_turn_voice()`, like the per-turn HighlightGate), calls `begin_open()`
  immediately (v7.1 Fix G -- the WS handshake overlaps the vision pass instead of sitting
  in the draw->first-audio gap), threads it through every `consume()`, speaks the budget
  refusal + agentic-cap note THROUGH it, abandons it on a no-TurnComplete pass, and in a
  `finally` OUTSIDE the 90 s timeout scope calls `turn_voice.finish()` then lifts the
  whiteboard dim (v7 Phase 2, `overlay.undim_screen()`) then arms the auto-hide when the
  turn drew -- the ONLY arm site (v7.1 Fix F; a draw-time arm was measured hiding the
  rectangle mid-explanation, draw+7 s < speech end), keyed on the RECEIVED draw calls.
- **v7 Phase 3 (barge-in):** `interrupt_turn()` -- the silencer: instant `overlay.hide()`
  + auto-hide cancel FIRST (the user SEES the response ~10 ms in), then
  `turn_voice.interrupt()` (closed-first: the finally's `finish()` no-ops, no fallback
  re-speak), then flags `_interrupted_last_turn` so the NEXT `run_turn` prepends
  `INTERRUPTED_NOTE_AR` (once); the caller cancels the turn task AFTER it returns.
  `_active_turn_voice` tracks the live voice (set in run_turn, cleared in its finally).
  The unused PriorityQueue placeholder was removed here (dead code).
- **v7 Phase 4:** the `read_file` seam (default `stub_read_file`, production
  `FileReader().read`) rides into TurnPass; the pipeline unpacks consume()'s
  `(turn_complete, refresh_call, read_result)` and hands `read_result` to
  `build_tool_result_message` -- a read NEVER touches the draw gate, so the pass after a
  read stays `tool_choice="auto"`.
- **v1.0-RC2 (UAT bug 1):** `run_turn`'s finally holds `_active_turn_voice` OPEN through
  `turn_voice.finish()` (the audio tail is still audibly playing during that drain --
  clearing it first made a late F9 silence nothing) and clears it in a nested finally.
- **V2 Phase 1 (M1-2):** the hide/settle/capture chokepoint was extracted WHOLE to
  `frame_capture.py` (the orchestrator delegates through `self._frames.capture`) to free
  room for the ONE injected `router` seam (`ToolRouter`, roadmap part 2 section 1) that
  `main.py` composes at the root; `OVERLAY_SETTLE_S` moved with it.
- **V2 Phase 2 (T4, DEC-3-C):** `interrupt_turn()` also `fire()`s a generic
  `InterruptHooks` list (composed in `__init__`, registered via the public
  `add_interrupt_hook`) on F9 -- gated on an active turn, alongside the silence; the
  kernel stays BLIND to what the hooks do (a plugin registers a `docker kill`; the kernel
  never names Docker/the sandbox -- source-asserted). `turn_pass` services
  `sandbox.run_code` after the sync point and resets the SandboxGate per turn inside
  `new_turn_voice()`.
- **Ceiling debt (DECISIONS.md CONSTRAINT, 2026-07-22):** at **299/300** lines after T5
  (the sandbox seam threading). ANY future touch -- notably web_research (Phase-2
  Milestone 2) -- MUST extract before adding, NEVER compress; identify the extraction
  candidate at planning time (a likely candidate: the `run_turn` `finally` teardown --
  the whiteboard-undim + auto-hide arm -- could move to a small `turn_teardown.py`).

## src/muthis/kernel/turn_pass.py

Current shape: `TurnPass` drains ONE provider pass -- streams the reasoner's events,
buffers text, gates the draws (first draw wins across BOTH draw tools via `next_draw`),
then owns the Option-A sync point (apply the ONE buffered draw -> speak); services the
routed tools (`read_local_file`, `sandbox.run_code`) after the sync point; stateless, no
lifecycle/locks/loop (Law 11); built once by the Orchestrator.

Evolution:

- **Original extraction:** extracted whole from `orchestrator._consume_stream` under the
  <=300-line law: streams the reasoner's events, buffers the text, gates the draws (first
  draw wins across BOTH tools via `next_draw`), then the Option-A SYNC POINT -- apply the
  ONE buffered draw, THEN speak -- which this module OWNS (same "muthis.orchestrator"
  logger). `REFRESH_TOOL` lives here (orchestrator re-exports).
- **V2 Phase 0:** the read servicing is generalized through `kernel/tool_router.py` --
  the `read_file=` kwarg contract is UNCHANGED (the default router is built from that
  seam; an explicit `router=` wins -- the Phase-1 broker's seat); the None-seam Arabic
  unavailable note is now ruled inside the router, byte-identical.
- **v7 Phase 4:** takes the injected `read_file` seam, detects `read_local_file`
  ToolCalls (perception like refresh -- never gates the draw; first read of the pass
  wins), services the read AFTER the sync point's audio is moving, and `consume()` now
  returns `(turn_complete, refresh_call, read_result)` where read_result is
  `(call, content)`.
- **v7 continuous voice:** the per-pass `_PassStreamer` was REPLACED by the turn-level
  `turn_voice.TurnVoice`; TurnPass keeps the `MUTHIS_STREAM_TTS` flag + lazy
  `TTS().open_speech_session` factory seams and exposes `new_turn_voice()` (run_turn
  builds ONE per turn, like the HighlightGate) -- `consume()` takes that TurnVoice: a
  `tool_choice=="none"` pass streams sentences mid-pass into it (decision 13 unchanged --
  "auto" passes stay buffered since a draw could arrive), and at the sync point the
  buffered text goes through `turn_voice.speak_or_feed()` -- an INSTANT feed when the turn
  session is live, so the pass-1 ack no longer blocks the agentic loop (the measured
  3.48 s stop-and-go). v7.1 Fix F: the auto-hide is NOT armed here anymore (run_turn's
  finally is the only arm site, at speech end), so TurnPass no longer takes the auto_hide
  seam.
- **V2 Phase 1 (M1-5):** `consume()` propagates a routed read's `ServiceOutcome.taint`
  onto `TurnResult.taint` (coarse turn-level record; no tainted tool reaches this path
  yet in Phase 1).
- **V2 Phase 2 (T5):** adds the `sandbox.run_code` service branch (route through
  `router.service`, like the read) after the sync point, and resets the per-turn
  SandboxGate inside `new_turn_voice()`.

## src/muthis/kernel/turn.py

Current shape: `TurnResult` (sent-image dims + physical<->sent scale factors + the
session `taint` flag) + the injected-dependency type aliases + the `Overlay` protocol +
`scale_bbox_to_physical` + `build_tool_result_message` (the Option-B pairing) + the
user-facing Arabic constants. The draw circuit-breaker lives in `highlight_gate.py` and
the Bug-3 stale-frame strip in `history_hygiene.py`; both are re-exported here for old
importers. Split under the <=300-line law; the orchestrator re-exports.

Evolution:

- **Contents:** `TurnResult` (incl. sent-image dims + physical<->sent scale_x/scale_y +
  the V2 Phase-1 `taint` flag, recorded per turn when an external/MCP result crossed) +
  injected-dependency type aliases (MicFn/SttFn/TtsFn/ScreenCaptureFn/DownscaleFn) + the
  `Overlay` protocol (`show(bbox, label_ar)`/`hide()`, `PhysicalBBox`) that replaced the
  old OverlayFn callable + `scale_bbox_to_physical` (pure sent->physical map) +
  `next_highlight` (the circuit-breaker draw decision, kept exported for existing
  importers; consumers now go through `draw_dispatch.next_draw`) + the `DownscaledImage`
  payload contract + user-facing Arabic constants (incl. `AGENTIC_CAP_NOTE_AR`) +
  `build_tool_result_message`.
- **`build_tool_result_message` (Option B):** pairs EVERY assistant `tool_use` with a
  `tool_result` so the next turn never replays an orphan `tool_use` (the 400). A DRAW-tool
  id (`highlight_target` OR `draw_shapes`) -> the gate-aware directive via
  `draw_result_text(gate, tool_name)`; `request_screen_refresh` id -> a fresh screenshot.
- **v7 Phase 4:** `build_tool_result_message` gains `read_result` and answers
  `read_local_file` ids BY NAME so a read can NEVER hit the draw branch or flip the gate:
  the serviced call gets the file content, another read id in the same pass gets
  `FILE_ALREADY_READ_AR`, an unserviced one (legacy caller) gets the error note. The
  Bug-3 stale-frame strip itself was EXTRACTED to `history_hygiene.py` (this file had sat
  at 298); re-exported here with `STALE_SCREENSHOT_NOTE_AR` so old imports keep working.
- **Circuit-breaker split:** the circuit-breaker constants/state/selector live in
  `highlight_gate.py` (re-exported here). Split under the <=300-line law; orchestrator
  re-exports.
- **V2 Phase 2 (T5):** `build_tool_result_message` pairs `sandbox.run_code` BY NAME
  (Option B), routing its serviced result like the read.

---

## src/muthis/kernel/budget.py

Current shape: the sovereign daily spend gate (Rule 10) -- see AGENTS.md.

- **V2 Phase 1 (M1-3):** added the reserved `plugins` ledger key --
  `record_plugin_call(provenance, cost)` counts every serviced call and adds real plugin
  costs to BOTH the plugin bucket and the sovereign daily total; the
  `can_afford`/`record_turn` contracts were untouched; legacy dates-only ledgers still
  load unchanged.

## src/muthis/kernel/verbosity.py

Current shape: the voice-controlled reply-length state (`VerbosityController`) -- see
AGENTS.md.

- **v5 Phase B:** born as the reply-length controller, held by the Orchestrator ACROSS
  turns (unlike the per-turn HighlightGate).
- **STT-tolerant detection internals:** `normalize_ar` strips tashkeel/tatweel, unifies
  hamza-alif and taa-marbuta -> haa, maps Arabic-Indic digits -> ASCII, and drops
  punctuation -- on a MATCHING copy only; the transcript is never altered. `detect_command`
  priority: EXACT_N (number words 1-10, digits, the "two-words" dual) -> reset phrases ->
  explicit anywhere-phrases (substring) -> the ISOLATION rule for ambiguous single words
  (a bare "shorten"/"longer" fires only as a standalone utterance -- an in-sentence use
  like "which side is longer?" never flips the state).

## src/muthis/kernel/interrupt_hooks.py

Current shape: the kernel's Docker-BLIND F9 eradication seam -- see AGENTS.md.

- **V2 Phase 2 M1 (T4, DEC-3-C):** born as the ONE kernel touch of the sandbox_exec
  milestone -- a generic `on_interrupt` hook list; the sandbox (at T5) registers its
  `docker kill` there. The kernel owns the mechanism; the plugin owns the content; the
  kernel never names Docker (source-asserted in test_barge_in).

## src/muthis/kernel/frame_capture.py

Current shape: the hide->settle->capture chokepoint (order load-bearing) -- see AGENTS.md.

- **V2 Phase 1 (M1-2):** extracted WHOLE from the orchestrator (extract-BEFORE-inject
  under the <=300-line law) to free room for the injected `router` seam. The order was
  unchanged and stays load-bearing: cancel stale auto-hide -> clear dot -> hide -> settle
  -> grab -> downscale -> relight -> record dims+scales. `OVERLAY_SETTLE_S` moved here
  with it. Used by every turn frame AND the broker's bridge capture.

## src/muthis/kernel/history_hygiene.py

Current shape: the Bug-3 stale-frame strip -- see AGENTS.md.

- **v7 Phase 4:** extracted WHOLE from turn.py (which had sat at 298; Law 17.4);
  `STALE_SCREENSHOT_NOTE_AR` + `strip_images_from_history` moved here, and turn.py
  re-exports both.

## src/muthis/kernel/highlight_gate.py  (draw circuit -- universal invariants)

Current shape: the draw circuit breaker, unified over both draw tools -- see AGENTS.md.
The row keeps ALL invariants (first-draw-wins, the internal-directive tool_result
surfaces, the `tool_choice`->"none" hard terminator, the hosted `INTERRUPTED_NOTE_AR`);
only the phase tags migrated here.

- **Its own module:** split out so orchestrator.py/turn.py stay <=300.
- **The completion-framing rationale (kept live in the row):** `HIGHLIGHT_ACK_TEXT_AR`
  carries NO completion lead and no success ("bi-najah") framing because those framings
  caused the pass-2 bare-ack regression -- the surface COMMANDS the explanation to start
  with the info instead.
- **v7 Phase 3:** also began hosting `INTERRUPTED_NOTE_AR`, the barge-in next-turn
  internal directive.

## src/muthis/kernel/draw_dispatch.py  (draw circuit -- universal invariants)

Current shape: unified draw dispatch (`DRAW_TOOLS` / `PendingDraw` / `next_draw`) -- see
AGENTS.md. The row keeps ALL invariants (first-draw-wins across both tools, the physical
buffering, the dim-before-draw whiteboard order, the malformed-draw-still-gated rule);
only the split history migrated here.

- **B-1:** split into its own module because orchestrator.py had no room (it was 284
  after the M1-2 extraction -- now 299/300) and highlight_gate.py can't host it (turn.py
  imports highlight_gate; importing turn back would cycle). Hence: its own module to avoid
  the turn<->highlight_gate import cycle.
- **v7 Phase 2:** `PendingDraw` gained the `dim` command -> the whiteboard (`apply()`
  calls the duck-typed `overlay.dim_screen()` BEFORE the draw so the board forms under the
  chalk).

## src/muthis/shapes.py  (draw circuit -- universal invariants)

Current shape: the geometric-drawing data model + scaling + tool-args parsing -- see
AGENTS.md. The row keeps ALL invariants (the frozen `Shape` contract, the enclosing-bbox
rule, `parse_shapes_args`'s defensive drop, `scale_shapes_to_physical` as the ONLY
multiply site + the per-axis mirror of `turn.scale_bbox_to_physical`, the separate
`ShapesOverlay` protocol, the honest region-level accuracy limit); only the phase tags
migrated.

- **v6 B:** added the `step` kind -- a numbered how-to badge whose 4-tuple is the badge
  circle's enclosing bbox (like circle) and which carries NO number field (badges number
  by their ORDER among the list's step shapes).
- **B-1:** added `parse_shapes_args` (the defensive draw_shapes args parser) and the
  scaling functions; the `ShapesOverlay` protocol was kept OUT of `turn.Overlay` so
  existing overlay fakes keep passing isinstance (Phase B types against it).

## src/muthis/kernel/tool_router.py

Current shape: the dispatch registry (`ToolRouter` / namespacing / `service()`) -- see
AGENTS.md.

- **V2 Phase 0:** born as "the one surgical change" (roadmap part 2 section 1). Only
  `file_read` is router-serviced; the DRAW path never crosses the router and the refresh
  frame lifecycle stays kernel state (ruling C-1). `service()` never raises.
- **DEC-11 (Phase 2 M1, live-caught):** the non-core namespace separator became `__`
  (double underscore) not `.` -- a dot fails the Anthropic tool-name pattern
  `^[a-zA-Z0-9_-]{1,128}$`; the separator lives once in `namespaced_name`/`NAMESPACE_SEP`
  and every catalog name derives from it. The core four keep bare V1 names (C-3's
  exemption, unchanged).
- **V2 Phase 1:** `build_core_router(plugin_ledger=...)` attributes serviced calls to the
  per-plugin budget column (M1-3); `mount(taint=...)` tags external (MCP) routes so their
  `ServiceOutcome.taint` is set (M1-5).

## src/muthis/kernel/__init__.py

Current shape: the sealed kernel package root -- see AGENTS.md.

- **V2 Phase 1 (M1-1, decision Q-4):** the 8 flat compat shims
  (`muthis.orchestrator`/`.turn_pass`/`.turn`/`.highlight_gate`/`.draw_dispatch`/
  `.history_hygiene`/`.verbosity`/`.budget`) that briefly re-exported the moved kernel
  modules were REMOVED; every consumer now imports `muthis.kernel.*`, and
  `test_the_shims_are_gone` fails any revived old path (the live guard, kept in the row).
