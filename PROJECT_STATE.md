# PROJECT_STATE.md — Mut'his v7 condensed technical state

> Token-saving snapshot (updated 2026-07-16, v1.0-RC1). **`AGENTS.md` remains
> the full source of truth**; this is the compressed map. Branch
> `v7-experimental`, 462 tests green.

## CURRENT STATUS: v1.0-RC1 — UAT / STAGING (2026-07-16)
V1 is FEATURE-COMPLETE and committed on `v7-experimental` as a RELEASE
CANDIDATE — **NOT launched, NOT merged to main**. Sultan is running
comprehensive manual real-world testing (UAT). Agent posture: STAND BY for
his feedback; fix what UAT surfaces; open NO new work unprompted (the
phase-gated SOP governs). RC1 = Phases 1-4 + the [DIAG] cleanup + the
persona FORMATTING-SYNTAX BAN (speech is pure spoken prose — no ** / # /
` / list dashes; the output surface is TTS + the captions bar, never a
markdown renderer — the Phase 4 live run showed raw asterisks in captions).

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
