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

---

## src/muthis/turn_voice.py

Current shape (see AGENTS.md for the authoritative row): ONE continuous speech
generation for the WHOLE turn, built fresh per turn, opened eagerly, fed by every
pass, and settled in run_turn's finally -- with interrupt() as the barge-in path.

Evolution:

- **v7 (born):** the STOP-AND-GO FIX. Before it, each pass spoke its own buffered text
  through a separate TTS call, so a multi-pass turn came out as several disconnected
  utterances with a round-trip of silence between them. TurnVoice makes the TURN, not
  the pass, the unit of speech: one generation, fed from wherever the text comes from.
- **v7.1 Fix G (eager open):** `begin_open()` fires the turn's ONE open attempt as a
  background task at turn start, overlapping the vision pass, instead of paying the WS
  handshake at first speech; `ensure_open()` joins that same attempt rather than
  starting a second, and finish()/abandon() settle it even when the turn dies before
  speaking, so no orphan task or socket survives. Lazy open on first speech remains for
  callers that never call begin_open.
- **v7.1 (the ack-held-under-the-schedule-floor fix):** buffered pass text is fed with
  `flush=True` so ElevenLabs synthesizes the complete utterance NOW. A 4-character ack
  sat under the 90-char chunk-length floor and played ~2.6 s late, which defeated the
  whole point of the ack -- it exists to mask the inter-pass round trip.
- **v7 Phase 2 (caption pacing):** measured live bug -- sentences fed in ~4 s while
  their audio played over ~26 s flashed the caption bar at GENERATION speed. Each
  caption now defers to its sentence's estimated audio start (cumulative fed chars /
  ARABIC_TTS_CHARS_PER_SEC ~= 11.5, measured over three runs, minus the player's
  starvation-aware `played_seconds()`), and the bar clears once at finish().
- **v7 Phase 3 (barge-in):** interrupt() closes FIRST so a later finish() no-ops and no
  decision-15 fallback can re-speak text the user just silenced; it settles an in-flight
  eager open, aborts the session (duck-typed, so pre-Phase-3 fakes get a quiet close),
  clears the caption/paced queue, and leaves the status light to the barge-in press's
  own "listening".
- **v1.0-RC2 (UAT):** interrupt() got its OWN `_interrupted` flag rather than reusing
  `_closed`, because a barge-in landing WHILE finish() drains the audio tail must still
  abort the session -- the idempotent abort is what unblocks that drain. finish() past
  an interrupt runs NO fallback and never stomps the "listening" light. The same round
  added the PASS-ECHO guard: speak_or_feed arms speech_stream.EchoGuard with the turn's
  last SHORT utterance (the ack) and both feed paths strip a verbatim leading repeat of
  it from the immediately next utterance, once.
- **Concurrency posture (unchanged since v7):** feeds are inline awaits -- deliberately
  NOT the Batch-3 wedge. The only concurrency is the existing player worker, the bounded
  session reader, and the ONE begin_open task, settled on every path.

## src/muthis/speech_stream.py

Current shape: the Arabic SentenceSplitter plus the pass-echo suppressor; it segments
text only and knows nothing of TTS or the sync point.

Evolution:

- **v5 Phase C1 (born):** emit COMPLETE sentences in order the instant their ender
  arrives, with the DECIMAL GUARD from the start (a dot between digits never splits).
- **v7 (measured fixes):** MIN-LENGTH MERGE killed the standalone "1." numeral scrap by
  merging a too-short completion into the NEXT sentence; ELLIPSIS RUN treats consecutive
  dots as ONE ender cut after the last dot; the SOFT VALVE made the ~200-char overflow
  cut at the last space or Arabic comma instead of mid-word.
- **v7.2 (post-ack starvation fix):** EAGER FIRST EMISSION -- the first emission of a
  pass may cut at a comma past ~30 chars (digit-guarded so "1,250" never splits), so
  first audio starts at the first natural pause rather than after a whole opening
  sentence. Later emissions keep full-sentence boundaries; flush() re-arms the window.
- **v1.0-RC2 (UAT bug 2):** the PASS-ECHO suppressor arrived here --
  strip_leading_repeat + EchoGuard -- normalization-tolerant but BOUNDARY-strict, so a
  two-letter key never bites a longer word that contains it.

## src/muthis/voice_out.py

Current shape: the orchestrator's mouth and the app's speech + caption privacy choke
points; never reorders the sync point.

Evolution:

- **v5 Phase B prep:** extracted WHOLE from orchestrator.py under the <=300-line law
  (that file had sat at 299), carrying speak() and refuse_for_budget().
- **v6 C:** became the CAPTION choke point as well, so the privacy boundary that covered
  the ears covered the eyes too. MUTHIS_CAPTIONS defaults ON (Sultan's release decision,
  2026-07-15) with a falsey value as the one-env rollback; the overlay is duck-typed so
  StubOverlay and old fakes no-op and the turn.Overlay protocol never changed.
- **v7 Phase 2:** `delay_s > 0` routes to the overlay's show_caption_later paced seam
  (falling back to immediate when absent) -- the caption/audio sync fix.

## src/muthis/tts.py and the TTS engine files

Current shape: tts.py is the cascade (ElevenLabs WS primary, Gemini REST fallback) and
the single home for env reading; tts_session.py holds the persistent generation;
tts_elevenlabs.py and tts_gemini.py are the two providers; tts_ws_player.py is the
abortable player; tts_diacritics.py is the speech-only vowelizer.

Evolution:

- **SAPI/pyttsx3 removed** early: the cascade is ElevenLabs -> Gemini -> provider="none",
  and speak() never raises so the orchestrator's seam cannot break.
- **v5 Phase C:** open_speech_session() added as the streaming factory, returning None
  when ElevenLabs is disabled or unkeyed so the caller simply stays buffered;
  SpeechSession born with the key in the BOS message rather than the URI.
- **v7 Fix A (tts_session):** try_trigger_generation on the FIRST sentence only. Forcing
  it per feed was the MEASURED cause of baked-in mid-sentence pauses -- audio bursts
  aligned 1:1 with feeds -- because later chunking belongs to ElevenLabs' lookahead.
- **v7.1 / v7.2 (tts_session):** flush=True for a complete utterance; then the discovery
  that a flush ENDS the generation segment, so the next feed must re-trigger -- without
  the re-arm the explanation's first sentence sat on ElevenLabs' buffer while the player
  starved post-ack (measured ~5 s).
- **v7 Phase 2 (tts_ws_player):** played_seconds() added as the caption pacer's clock,
  excluding starvation gaps.
- **v7 Phase 3 (tts_ws_player, tts_session):** abort() on both -- Pa_AbortStream as the
  one sanctioned cross-thread stream call, and an EOS-less session teardown.
- **v1.0-RC2 (UAT bug 1, tts_elevenlabs):** a cancelled stream_pcm ABORTS its player
  instead of draining. ElevenLabs delivers ~10x realtime, so the old drain-on-cancel
  played the whole remaining clip out over the NEXT turn.
- **v1.0-RC2 (UAT, tts.py):** the cascade ECHO GUARD -- an ElevenLabs failure arriving
  AFTER audio played returns provider="elevenlabs" without falling back, because
  replaying the same text was the measured dialogue echo. The Gemini clip moved onto the
  abortable player at the same time; winsound left the speech path because its
  synchronous clip could not be stopped after a barge-in.
- **bug 3 (tts_diacritics):** born speech-only. Vowelizing history would corrupt the
  model's reasoning, so the map is applied to a COPY at the speak() choke point, with
  whole-word Arabic-boundary matching so a short key never corrupts a longer word.

---

## src/muthis/overlay/ (the overlay package)

Current shape: `sidekick_window.py` owns the Tk lifecycle and the command queue;
`window_commands.py` is the pure dispatcher; the widgets (rectangle, pointer, shapes,
caption bar, status dot, domain badge) are pure VIEWs on one shared canvas;
`focus_dimmer.py` is the second Toplevel; `style.py` + `style_env.py` are the styling
config; `win32_glue.py` holds the ctypes.

Evolution:

- **Batch 1 (the neon look):** OverlayStyle born frozen, with the dataclass defaults AS
  the neon defaults, plus glow_strokes() emulating a glow Tk cannot do natively (outer
  dim halo + inner bright core).
- **Batch 2-A / 2-B (the status light):** StatusIndicator added as a VISUAL-ONLY corner
  dot with per-state colors and a cosine pulse; 2-A shipped it no-op-safe through the
  same command queue so 2-B only had to add the real turn-phase call sites and the
  capture-chokepoint light-clear. The same round REMOVED an earlier pointer HALO that
  hugged the gliding tip -- it cluttered content over code -- along with its only
  support, `pointer.last_pos`.
- **v5 Phase A (Law 17.4 split):** style.py had reached the 300-line ceiling, so the
  env parsing and the transparent-key guard were extracted WHOLE to style_env.py, with
  TRANSPARENT_KEY re-exported so importers did not change.
- **Geometric drawing Phase A:** ShapesWidget added, drawing ALREADY-PHYSICAL shapes on
  the shared canvas under SHAPES_TAG, exercised only by a smoke script until Phase B
  wired the tool.
- **v6 B (step badges):** numbered how-to badges -- an unfilled glow ring plus one crisp
  Arabic-Indic numeral at its centre, numbered by list ORDER counting step shapes only,
  restarting every draw().
- **v6 C (live captions):** CaptionBar born as the bottom-centre chip; the same round
  made VoiceOut the caption choke point, so the privacy boundary covered the eyes too.
- **v6 C0 (Law 17.4 split):** sidekick_window.py sat at 299, so dispatch_command and
  _bbox_center were extracted WHOLE to window_commands.py, both re-exported.
- **v6 D (Cinematic Spotlight):** FocusDimmer born, cutting a transparent hole around
  the highlight bbox; default OFF from the start.
- **v7 Phase 2 (the whiteboard + caption sync):** FocusDimmer gained show_full() /
  fade_out() so the dim could become a BOARD rather than a spotlight (flag default ON),
  with the fade built from self-rescheduling after() frames on the status-pulse pattern;
  CaptionBar gained show_text_later() and the generation counter, because streamed
  sentences had been flashing at text-generation speed while their audio played much
  longer; and the Win32 DPI / click-through glue was extracted to win32_glue.py under
  the same 299-line pressure.
- **v7.2 (teardown thread-affinity):** after mainloop the Tk thread now deletes every
  widget/root reference and forces a gc.collect(), so Tcl objects are freed on the
  thread that created them. Without it the process aborted with Tcl_AsyncDelete.
- **A KNOWN, ACCEPTED interplay:** a NEW highlight_target wipes drawn shapes, because
  RectangleWidget clears with delete("all"). highlight_target is the V1 path and stays
  untouched; the shapes widget is tag-scoped precisely so the reverse can never happen.

---

## src/muthis_plugins/ (the plugin layer) and sdk/ (muthis-sdk)

Current shape: four native V1 plugins, plus sandbox_exec and web_research; the SDK is
the independently semver'd public contract.

Evolution:

- **V2 Phase 0, Q-2 (dogfood):** the four V1 tools were re-founded as core plugins over
  muthis-sdk with their schemas moved VERBATIM, precisely so the plugin contract would
  be proven by the app's own tools before any third party used it. Three are DECLARATION
  plugins (kernel_serviced=True -- execution stays on the V1 circuits letter for letter);
  file_read is the fully ROUTED executor, with FileReader's secret/binary/size gates kept
  KERNEL-side and never delegated.
- **Phase 0 M4:** cloud/tool_schemas.py became an assembly re-export in the exact V1
  order, so the catalog's byte-identity survived the move.
- **Phase 1 (SDK extended):** ScreenCapability added at 2.0.0a2; the conformance kit's
  permission-violation suite went live (starved-context denial + undeclared-capability
  spy detection) at ZERO skips on the core four.
- **Phase 2 M1 (sandbox_exec):** built gate by gate -- the contract skeleton first, then
  the runner, then the per-turn gate, then the servicing wiring. DEC-8's `docker cp`
  staging was superseded live by DEC-9's stdin bootstrap when cp proved incompatible with
  --read-only. The T6 live SOP then produced two rulings that outlived the milestone:
  DEC-11 (the `__` separator, after a real Anthropic 400 on the dotted name -- the actual
  defect was a MISSING guard, now a test over every catalog name) and DEC-12 (a security
  guard is verified by driving the guard directly, never through model judgment), which
  in turn surfaced DEC-13 (path structure in staged names refused outright).
- **Phase 2 M2 (web_research):** the first plugin that holds NO key, NO client, NO
  endpoint and NO socket -- the provider is injected already-built (DEC-27) and pages are
  read through ctx.net (DEC-24). It became model-visible under DEC-40 (catalog v3), and
  its cost reaches the ledger through the router's own carrier (DEC-34) rather than any
  field the plugin controls.
- **SDK 2.0.0a3:** NetCapability added -- ONE verb, `fetch_readable(url)`, with no
  socket, client, base URL, header or method surface, so a plugin cannot CONSTRUCT a
  request. Adding a capability class is an additive contract change, hence the a3 bump.

## src/muthis/broker/ and broker/mcp/ (Phase 1)

Current shape: grants + the capability-gated context door; the MCP client/host/policy/
proxy; the kernel stays blind to MCP entirely.

Evolution:

- **M1-4:** the golden rule made inspectable -- consent pinned to the manifest sha256 so
  ANY manifest byte change silently invalidates the grant (an update-diff by
  construction); denial expressed as an ABSENT seam rather than a different API.
- **M1-5:** the MCP layer landed stdlib-only (Q-1.1), with the protocol version PINNED
  and a 4 MiB frame wall. UTF-8 wire armor for python children was live-critical on this
  machine: Windows cp1256 pipes broke the wire in practice.
- **M1-6/7:** mcp_runtime turned any ToolPlugin into an MCP stdio server (deliberately
  SYNC stdio -- the Windows asyncio-stdin swamp avoided); the composition root mounts
  trusted plugins.d servers READ-ONLY at boot. The Phase-1 scope law kept them out of the
  model catalog, which stayed the byte-pinned V1 four until Phase 2 chose to change it.
- **Phase 2 M2 (T4/DEC-14):** the untrusted-content WRAPPING left broker/mcp/policy.py
  for the ONE router boundary. Keeping both would have double-wrapped the MCP path and
  nested a STATIC, forgeable delimiter inside the nonce-bearing one. policy.py keeps
  result HYGIENE only; do not re-add a wrap there.
- **Phase 2 M2 (T6a/DEC-24):** the broker gained the net_fetch seam and `net.fetch` LEFT
  the granted-but-unwired set -- while it sat there, a granted and a denied plugin saw
  the same absent seam and the same silence, which is the undefined THIRD state M1-4
  forbids.
