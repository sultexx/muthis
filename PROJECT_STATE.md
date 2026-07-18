# PROJECT_STATE.md — Mut'his condensed technical state

> Token-saving snapshot (updated 2026-07-17, V2 Phase 1). **`AGENTS.md` remains
> the full source of truth**; this is the compressed map. Branch
> `feature/v2-phase1-broker-mcp`; app suite 532 green (V1 474-oracle
> preserved through the Q-4 import flip) + 27 sdk tests.

## CURRENT STATUS — PHASE 1 CODE-COMPLETE (2026-07-17); LIVE GATE PENDING
Phase 0 CLOSED by Sultan after live UAT (all four diags on real hardware);
merged to `main` (+ `pre-v2-phase1` anchor). Phase 1 (broker + privileges +
MCP bridge) executed M1-0→M1-7 per the approved plan (decisions Q-1.0→Q-1.4).
**Exit gate pending Sultan's live run:** `diag_hello_plugin.py` +
`diag_mcp_mount.py` (both zero-cost, both PASSED in engineering smoke) +
V1 regression diags (`diag_pedagogy` at minimum).

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

### (b) The `muthis/annotate` profile bridge (Q-1.2)
- **Item:** `muthis-profile/1` ships `muthis/read_file` + `muthis/capture`
  only; the roadmap §8.4 `muthis/annotate` (a granted external plugin drawing
  via the ONE HighlightGate) is NOT implemented.
- **Reason:** decision Q-1.2 — keep the draw path isolated and sacred one more
  phase; no Phase-1 external plugin needs server-side drawing, and the draw
  circuit stayed untouched (ruling C-1).
- **Lands in:** UNASSIGNED in V2_ROADMAP.md — earliest sensible is a phase
  where a granted external plugin needs to draw (Phase 2+). **Needs Sultan's
  explicit phase assignment; deliberately not guessed here.**
- **Closing condition:** `muthis/annotate` added to the profile and routed
  through the ONE HighlightGate behind an `annotate.overlay` grant, with the
  V1 draw circuit byte-unchanged, proven by a live diag of an external plugin
  drawing via the gate.

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
  module nears the limit, SPLIT (don't compress). At/near ceiling now:
  `orchestrator.py` 300, `tts.py` 300, `turn.py` 298, `sidekick_window.py` ~270.
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
