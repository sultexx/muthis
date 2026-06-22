# Mut'his (مطحس) — Agent Instructions

<!-- This is the single source of truth for all AI coding agents (Claude Code, Cursor, Copilot, Gemini CLI). -->
<!-- CLAUDE.md points here. On Windows, symlinks need Developer Mode (`mklink CLAUDE.md AGENTS.md` in an elevated
     cmd); if unavailable, keep CLAUDE.md as a one-line file: "Read AGENTS.md — it is the single source of truth." -->
<!-- Full design rationale lives in ARCHITECTURE_v4_1.md. When this file and the architecture doc disagree on
     CURRENT scope, this file wins; when they disagree on LAWS, the architecture doc wins. -->

## Overview

Arabic-first voice sidekick for Windows 11. The user **holds** the **push-to-talk hotkey** (default **F9**,
configurable via `MUTHIS_HOTKEY`) while speaking Arabic and releases to send,
and Mut'his answers with Arabic speech (ElevenLabs TTS, Gemini fallback) while pointing at on-screen UI elements with a
**cyan rectangle overlay**. Reasoning + vision: **Claude Sonnet** (`claude-sonnet-4-6`) via the official
`anthropic` SDK with SSE streaming.

**CURRENT PHASE: LOOK-only.** Mut'his speaks and points. It does **not** click, type, press hotkeys, or touch
the clipboard. Trust Modes (ASSIST / AUTOPILOT) are designed in ARCHITECTURE_v4_1.md §12 but are **not in scope
yet** — do not build them, do not stub them, do not add their tools to any schema.

Hardware target: Windows 11, RTX 4060 8 GB. The app must use ~0 GB VRAM and never compete with the user's
Blender/YOLO workloads. Everything heavy is cloud.

## Architecture

```
PTT hold → mic streaming capture (record while held, flush on release) →
   STT (ElevenLabs Scribe, language pinned "ar") → ClaudeAgent.run()
   → TextDelta stream → buffer-then-speak TTS (accumulate the full reply, then
     speak it ONCE at end-of-turn; ElevenLabs WS PRIMARY with progressive audio, Gemini fallback)
   → ToolCall(highlight_target) → gliding pointer → cyan rectangle + Arabic caption (Tk overlay)
   → TurnComplete(usage, cost) → budget.py
   → if stop_reason == "tool_use": append tool_result, loop back to run() (agentic loop,
     ≤ MAX_AGENTIC_ITERATIONS=4, budget-gated per pass) so the explanation lands AFTER the pointer
```

- **One asyncio event loop, one PriorityQueue, one dispatcher** (orchestrator.py owns them — Law §3.3).
- **CloudReasoner protocol** (`cloud/protocol.py`): every provider hides behind the same three events —
  `TextDelta`, `ToolCall`, `TurnComplete`. The orchestrator never knows which vendor answered (Law §3.7).
- **Single-path v1**: Claude only. The speed-path (Gemini) and the router are deferred until the single path
  is boringly reliable in daily use. The Gemini **TTS voice fallback** (`tts_gemini.py`) is NOT that
  speed-path — it synthesizes audio only and must never gain text/vision calls.
- **Keys**: `.env` only, loaded once at process entry before any SDK import (Law §5.1-3). A Cloudflare Worker
  proxy is the planned production key home (Clicky pattern); `MUTHIS_ANTHROPIC_BASE_URL` already supports it.

### Key Architecture Decisions (and the Clicky lessons behind them)

**Shared HTTP client + TLS warmup**: `ClaudeAgent` owns ONE long-lived `httpx.AsyncClient`, passed into
`AsyncAnthropic`, and fires a HEAD warmup through that same client at startup. Warming a different client is
theater — the pool must be shared (Clicky hit "Socket is not connected" by recreating sessions per request).

**Image media-type sniffing**: PNG (`89 50 4E 47`) vs JPEG (`FF D8 FF`) detected from leading bytes before
declaring `media_type`. The API rejects mismatches.

**Partial JSON discipline**: tool inputs stream as `input_json_delta` fragments. They are buffered per content
block and parsed only at `content_block_stop`. Partial JSON never leaves `claude_agent.py`.

**Structured tools, not text tags**: Clicky parses `[POINT:x,y]` tags out of prose; Mut'his uses real tool
calls (`highlight_target`). Never regress to regex-parsing coordinates from response text.

**Stateless wrapper**: `ClaudeAgent.run()` is one provider turn. No retries, no loops, no conversation memory
inside the wrapper — history AND the agentic loop (tool_use → tool_result → re-call run(), ≤4×) are the
orchestrator's (Law 11: wrappers own no lifecycles, locks, or events).

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `src/muthis/cloud/protocol.py` | ~104 | `CloudReasoner` protocol + the three response events. `run()` takes a `tool_choice` ("auto" default) the caller forces to "none" on a pass that must NOT call a tool. Zero third-party deps; importable in isolation. |
| `src/muthis/cloud/claude_agent.py` | ~300 | Quality-path wrapper: `anthropic` SDK streaming, vision payload build, media-type sniffing, LOOK-only tool schemas, Arabic system prompt, TLS warmup, cost annotation. `run(tool_choice="auto")` maps to the SDK as `tool_choice={"type": tool_choice}`; "none" forbids ALL tool use so the model must answer in text (the orchestrator's post-highlight pass → end_turn). Folds a trailing user message (an Option B `tool_result` pairing) into the new turn's user content so roles keep alternating; an empty `user_input.text` (an agentic continuation) adds NO new block, so run() resumes straight from the trailing `tool_result`. |
| `tests/cloud/test_claude_agent.py` | ~264 | Fake-session integration test (§15 step 8): asserts event sequence, partial-JSON buffering, cost math, that no action tool is offered, that run() folds a trailing user `tool_result` into the new turn (strict alternation), and that `tool_choice` stays `auto` — never forced to any/tool (forcing would suppress the dual-action explanation prose). |
| `src/muthis/budget.py` | ~229 | Sovereign daily spend gate (Rule 10): UTC-date-keyed `budget.json` ledger, `can_afford` pre-flight + `record_turn` consuming `TurnComplete.cost_usd`, limit from `MUTHIS_DAILY_BUDGET_USD`. Boolean contract, no exceptions. |
| `tests/test_budget.py` | ~150 | Deterministic budget tests: limit gating, accumulation + persistence, date rollover via injected clock, corrupt-ledger recovery, env-driven limit. |
| `src/muthis/orchestrator.py` | ~300 | The heart: owns the loop, queue, history, 90 s session bound. Budget gate before EVERY provider call; handle_activation: mic→STT→run_turn with Arabic-spoken early aborts; each turn captures physical pixels → downscaled COPY (the ONLY thing sent) and records the physical↔sent scale_x/scale_y; buffer-then-speak: the full TextDelta reply is accumulated then spoken ONCE at end-of-turn; highlight_target→ `next_highlight` scales sent→physical then BUFFERS it (FIRST wins — highlight circuit breaker: ONE draw per turn, later highlights suppressed; LOOK-only enforced); the buffered highlight is sent to overlay.show — which GLIDES the animated pointer from the OS cursor (read-only GetCursorPos) to the bbox and draws the rectangle on ARRIVAL — + the auto-hide armed (`AutoHideController.schedule`, cancel-and-replace — see overlay_autohide.py) the instant BEFORE the buffered reply is spoken, so the motion starts WITH the audio start (Option A: the timer counts from here; the ~glide is negligible vs the 7 s timeout, keeping the asyncio↔Tk boundary clean) and the timeout counts from the draw (not ~12 s earlier on receipt); overlay.hide() runs before EVERY capture (hide→settle→capture ghosting fix, OVERLAY_SETTLE_S) and that chokepoint also cancels any stale auto-hide; request_screen_refresh answered via tool_result follow-up; EVERY assistant tool_use is paired with a tool_result (Option B, `build_tool_result_message`) so the next turn never replays an orphan tool_use (the 400). **Agentic loop** (`_run_turn_pipeline`): after a `tool_use` turn the orchestrator appends the pairing and re-calls run() to fetch the continuation, looping WHILE `stop_reason == "tool_use"` (so Muthis explains AFTER pointing instead of hanging), capped at `MAX_AGENTIC_ITERATIONS` (4) with `can_afford()` before EVERY iteration; it ends cleanly on `end_turn`, a None stop_reason, or the cap (spoken `AGENTIC_CAP_NOTE_AR`). A per-turn `HighlightGate` (rebuilt at the top of `_run_turn_pipeline`) is the loop circuit breaker: only the FIRST `highlight_target` draws; a repeat is suppressed and its `tool_result` says "already shown — explain now" (`HIGHLIGHT_ALREADY_SHOWN_AR`). The HARD loop terminator is `tool_choice`: once `gate.drawn`, the NEXT run() is called with `loop_tool_choice(gate)` → "none", so Claude CANNOT call a tool and MUST emit its explanation as text → `stop_reason` becomes end_turn → the loop ends (API-enforced; the gate is the belt-and-suspenders). A `request_screen_refresh` never sets `gate.drawn`, so a refresh follow-up stays "auto". A `request_screen_refresh` frame rides its `tool_result` for the current iteration, then is stripped from history at turn-end (`strip_images_from_history`) so a stale view never replays next turn (Bug 3). |
| `src/muthis/turn.py` | ~294 | TurnResult (incl. sent-image dims + physical↔sent scale_x/scale_y) + injected-dependency type aliases (MicFn/SttFn/TtsFn/ScreenCaptureFn/DownscaleFn) + the `Overlay` protocol (`show(bbox, label_ar)`/`hide()`, `PhysicalBBox`) that replaced the old OverlayFn callable + `scale_bbox_to_physical` (pure sent→physical map) + `next_highlight` (circuit-breaker draw decision: scales the FIRST highlight of a turn, returns the unchanged pending for later ones so the overlay draws once) + the `DownscaledImage` payload contract + user-facing Arabic constants (incl. `AGENTIC_CAP_NOTE_AR`) + `build_tool_result_message` (pairs EVERY assistant tool_use with a tool_result — a `highlight_target` id → the gate-aware directive via `highlight_result_text` (`HIGHLIGHT_ACK_TEXT_AR` "explain now" for the first, `HIGHLIGHT_ALREADY_SHOWN_AR` for repeats), `request_screen_refresh` id → fresh screenshot) + `strip_images_from_history` (drops a refresh frame from STORED history after its turn — `STALE_SCREENSHOT_NOTE_AR` placeholder, id/pairing kept — so a stale view never replays, Bug 3). The circuit-breaker constants/state/selector live in `highlight_gate.py` (re-exported here). Split under the ≤300-line law; orchestrator re-exports. |
| `src/muthis/highlight_gate.py` | ~91 | The highlight circuit breaker (its own module so orchestrator.py/turn.py stay ≤300): the `HighlightGate` per-turn state (`drawn`), the two tool_result surfaces — `HIGHLIGHT_ACK_TEXT_AR` is a COMMAND to explain NOW, opened as an INTERNAL directive ("توجيه داخلي … لا يراه المستخدم") with NO completion lead ("تم وضع المؤشّر …") and no "بنجاح" framing — those completion framings caused the pass-2 bare-ack regression; it orders the explanation to start with the info), `HIGHLIGHT_ALREADY_SHOWN_AR` similarly forces the explanation while forbidding a re-point — `highlight_result_text(gate)` which picks the text and advances the gate, and `loop_tool_choice(gate)` → "none" once drawn (the HARD loop terminator) else "auto". Pure stdlib; imported by turn.py + orchestrator.py. |
| `src/muthis/overlay_autohide.py` | ~96 | `AutoHideController`: owns the SINGLE auto-hide task for the cyan overlay with cancel-and-replace. `schedule()` arms a non-blocking `asyncio.create_task` that waits `timeout_s` (DEFAULT_OVERLAY_TIMEOUT_S = 7 s, injected into the orchestrator as `overlay_timeout_s`) then calls `overlay.hide()`, cancelling any pending prior task first (no stacking, no orphan); `cancel()` drops a pending timer WITHOUT hiding (used at the hide-before-capture chokepoint + shutdown); a cancellation mid-wait skips the hide. stdlib asyncio only; importable in isolation. The `.env` `MUTHIS_OVERLAY_TIMEOUT_S` wiring at the composition root is deferred to a later polish batch. |
| `src/muthis/persona.py` | ~212 | The GENERAL-PURPOSE Saudi-dialect persona for «مطحس» (coding in VS Code / web / files, with Fusion 360 as ONE capability among many — never assumes 3D modeling), with TWO-PASS dual-action guidance (a WHERE-question → pass 1 is ack-ONLY: ≤1-2 words then highlight_target, NEVER a screen-narration ("أشوف..."/"بأشّر على...") or any explanation, then pass 2 dives STRAIGHT into the explanation on the NEXT turn — start with the info, NO filler/ack like "أبشر"/"أشرت لك"/"تم"; EXPLAIN-only → speak, no highlight) matching the `tool_choice="none"` two-pass architecture + a verbosity SHORT cap (~40-60 words: natural short small-talk; a snappy WHAT+WHY of 3-4 short sentences when asked to point/explain/analyze, a SOFT ~40-60-word target — snappy for voice, not a hard truncation — with an explicit offer-to-elaborate "أكمّل لك أكثر؟" when the topic needs more) + an anti-laziness rule (a pointing reply never collapses to a bare ack) + `resolve_system_prompt()`. Injects the EXACT sent-image pixel dimensions (the coordinate space) as explicit args, computed ONCE at the composition root (resolution is static for the session). Injected through ClaudeAgent's EXISTING `system_prompt` seam (claude_agent.py untouched); falls back to LOOK_SYSTEM_PROMPT with a LOUD English warning ONLY if the builder is empty/raises (dims clause appended either way). stdlib-only, importable in isolation. |
| `tests/test_persona.py` | ~233 | Persona tests (no SDK): Saudi dialect markers (أبشر/سم/طال عمرك/وشلونك/عاد), the "UI names stay English" rule + Sketch/Extrude/Fusion 360, general-purpose scope (VS Code/web/files, NOT Fusion-centric), the injected sent-image dimensions, LOOK-only honesty + no action-tool name leak, the TWO-PASS dual-action rule (pass 1 is ack-ONLY — ≤1-2 words then highlight_target, NEVER a screen-narration "أشوف..."/"بأشّر على..."; pass 2 explains on the NEXT turn starting with the info — asserts the old single-response "في نفس الدور" wording is GONE) + the EXPLAIN-only path, the anti-laziness rule (forbids a filler ack like "أشرت لك" in the explanation turn), that the old 2-3 sentence / ~180-char cap is GONE, and the verbosity SHORT cap policy (short small-talk vs a snappy WHAT+WHY, a SOFT ~40-60-word target + an explicit offer-to-elaborate, the earlier ~250-word soft cap + figure replaced) — all coexisting with the Saudi/UI-English/LOOK-only pillars, and the loud empty/raise fallback (dims appended). |
| `src/muthis/tts.py` | ~284 | The tongue: ElevenLabs WebSocket PRIMARY (progressive — see tts_elevenlabs.py + tts_ws_player.py) with Gemini TTS REST FALLBACK (collect-then-play; see tts_gemini.py). Before EITHER engine, `speak()` diacritizes a COPY for SPEECH ONLY via `tts_diacritics.apply_diacritics` (the clean text + history stay unvowelized). `speak(text)→TTSResult` NEVER raises and its signature is UNCHANGED (orchestrator + DI seam untouched); any ElevenLabs failure falls back to Gemini, else provider="none". ElevenLabs is PRIMARY by default; a falsey `MUTHIS_TRY_ELEVENLABS` disables it and forces Gemini (one-env rollback). DI seams `ws_connect`/`player_factory` (real defaults) make the WS + playback fakeable. SAPI/pyttsx3 removed. Gemini voice configurable: `MUTHIS_GEMINI_VOICE` > `DEFAULT_GEMINI_VOICE` "Kore" (male). ElevenLabs voice config is read HERE (os.getenv lives in tts.py, so tts_elevenlabs.py stays env-free): `voice_id` = arg > `ELEVENLABS_VOICE_ID` > the placeholder default; `voice_settings` = arg > `_voice_settings_from_env()` (`ELEVENLABS_STABILITY`/`*_SIMILARITY_BOOST`/`*_STYLE` floats via `_env_float`, per-field fallback to `DEFAULT_VOICE_SETTINGS`) — a NATIVE Arabic voice + higher stability (0.7) is the accent fix. |
| `src/muthis/tts_elevenlabs.py` | ~129 | ElevenLabs WS provider (mirrors tts_gemini.py): `stream_pcm()` opens the stream-input WebSocket, sends BOS (key in `xi_api_key`, never logged) + the FULL text in ONE message + EOS, and feeds each PCM chunk to the player the instant it arrives — intra-AUDIO streaming of ONE text, NOT Batch-3 sentence chunking. Raises on no-audio/error-frame/disconnect/timeout so tts.py falls back. websockets lazy via the injected `ws_connect` seam; owns the EL constants (URL/voice/model/format/timeouts), re-exported by tts.py for the diagnostics/smoke scripts. `DEFAULT_VOICE_ID` is a clearly-marked PLACEHOLDER ("PASTE_NATIVE_ARABIC_VOICE_ID_HERE" — the old multilingual "Rachel" guessed the Arabic accent; unset → hard-fail to Gemini); `DEFAULT_VOICE_SETTINGS` = stability 0.7 / similarity_boost 0.8 / style 0.0 (all overridable per-field via .env, read in tts.py). |
| `src/muthis/tts_ws_player.py` | ~120 | `PcmStreamPlayer`: progressive PCM playback. `feed()` is an INSTANT loop-safe `queue.put`; ONE worker thread writes chunks FIFO to ONE sounddevice RawOutputStream (audio starts at the first chunk, never overlaps). `finish()` (async) drains via `stop()` (Pa_StopStream waits) and re-raises a playback error for fallback. sounddevice reused from mic.py (NO new dep), lazy-imported; a `stream_factory` seam makes it fakeable with no device. |
| `src/muthis/tts_gemini.py` | ~150 | Gemini TTS REST voice FALLBACK — VOICE ONLY, never reasoning/vision. stdlib urllib (blocking, run via to_thread), returns 24 kHz PCM. Takes an optional `voice` (the resolved MUTHIS_GEMINI_VOICE from tts.py; else GEMINI_TTS_VOICE then "Kore"). Request timeout configurable (`MUTHIS_GEMINI_TIMEOUT_S`, default 30 s) with exactly ONE fast retry on a urllib timeout (bare socket.timeout/TimeoutError or URLError-wrapped); any other error not retried; a double-timeout raises so tts.py degrades to provider="none" (speak() never raises). |
| `src/muthis/tts_diacritics.py` | ~83 | Speech-only Saudi-word diacritization (bug 3): `apply_diacritics(text)` vowelizes a small DATA map (أبشر→أَبْشِر, سم→سِمّ, طال عمرك→طال عُمرك) for pronunciation, applied to a COPY at the tts.py `speak()` choke point — SPEECH ONLY, NEVER in persona.py or history (vowelized history would corrupt the model's reasoning). Whole-word regex matching (Arabic letter-boundary look-arounds, longest-first) so a short key like "سم" never corrupts اسم/قسم/جسم/موسم. stdlib `re` only; importable in isolation. |
| `src/muthis/stt.py` | ~107 | The ears: ElevenLabs Scribe cloud STT (default `scribe_v2`, language pinned `ar` against Whisper-style code-switching); `transcribe()` never raises, "" on failure; httpx lazy. |
| `src/muthis/mic.py` | ~225 | True push-to-talk capture: `start()` opens a streaming sounddevice.InputStream buffering frames on the backend's callback thread; `stop()` (the orchestrator's mic seam, awaited as the turn's FIRST step) flushes and returns in-memory WAV 16 kHz mono. None ONLY on a true device failure (→ MIC_FAILED_AR); a hold under `min_record_seconds` (`MUTHIS_MIN_RECORD_SECONDS`, default 0.35 s) returns a valid-but-empty WAV → STT "" → STT_EMPTY_AR, no Claude call. `reset()` is the not-via-stop() teardown (Regression B): closes the stream FIRST (no late `_on_frames`) then clears `_frames` + `_recording` — idempotent, never raises, safe if never started; it is the single mic-reset site for the failure/cancel/timeout path. `is_recording` guards re-entry; the stream factory is injected (fake in tests → no PortAudio); sounddevice lazy. `record()` kept as a thin fixed-window wrapper over start/stop for the dev smoke scripts only. |
| `src/muthis/vision/screen_capture.py` | ~185 | The eyes: primary-monitor screenshot → PNG bytes via mss + Pillow, DPI-aware (PER_MONITOR_AWARE_V2) for true physical pixels on scaled Windows 11; lazy imports; blocking grab/encode via asyncio.to_thread; `capture()` never raises, None on failure; pixels never logged or persisted. Also `primary_monitor_size()` — a geometry-only probe (NO pixels) so the composition root can size the persona's coordinate space at startup. Injected as `ScreenCapture().capture` at the composition root (constructor default stays the stub). |
| `src/muthis/vision/downscale.py` | ~130 | The coordinate-mapping safeguard: builds the API-payload COPY of a screenshot bounded to max width 1280 so claude-sonnet-4-6 (≈1568 px / ≈1.15 MP threshold) does NOT resize it again — sent-image space == the space the model reasons in. `compute_scale_factors()` (pure: per-axis scale_x/scale_y) + `downscale_to_max_width()` (Pillow resize/re-encode via asyncio.to_thread, never raises, identity on passthrough/None). Pillow lazy; pixels never logged/persisted. Injected as the real `downscale` seam at the composition root; orchestrator default stays the passthrough stub. |
| `src/muthis/overlay/__init__.py` | ~21 | Overlay package root: exports `SidekickOverlay` + `DEFAULT_POINTER_ANIM_MS`. DRAW-ONLY (never moves mouse / clicks / types); tkinter/ctypes load lazily on the Tk thread so importing the package — and the orchestrator — stays headless-safe. |
| `src/muthis/overlay/sidekick_window.py` | ~249 | `SidekickOverlay` — the real Win11 cyan rectangle + the gliding pointer: own daemon Tk thread (§11.5), commands via queue.Queue (show/hide never block the asyncio loop), per-monitor-v2 DPI awareness so PHYSICAL coords land 1:1 on scaled displays, click-through / no-activate ex-styles (WS_EX_LAYERED\|TRANSPARENT\|NOACTIVATE\|TOOLWINDOW) + a transparentcolor key. `show()` now GLIDES an animated pointer to the bbox CENTER then draws the rectangle on ARRIVAL (pointer+rectangle share ONE canvas); `hide()` cancels the glide + clears BOTH (ghosting). Glide duration injected (`anim_duration_ms`, sourced from MUTHIS_POINTER_ANIM_MS at the composition root). The pure `dispatch_command(...)` (show/hide/close → rect/pointer/animator) is unit-tested with fakes (no Tk). Resilient: show/hide/close never raise; failed init → no-op. Implements the turn.Overlay protocol. |
| `src/muthis/overlay/rectangle_widget.py` | ~89 | Pure VIEW on the Tk thread: draws ONE cyan rectangle (unfilled, so the element stays visible) + a short Arabic caption on a dark plate at ALREADY-PHYSICAL coords; `clear()` erases it. Never scales. Exposes its `canvas` (read-only property) so the gliding PointerWidget draws on the SAME canvas (Tk -transparentcolor keys at the window level → one shared canvas; tag-scoped items keep them independent). |
| `src/muthis/overlay/pointer_widget.py` | ~67 | Pure VIEW on the Tk thread: draws the small gliding cyan ARROW (a tagged polygon, tip on the glide coordinate) on the RectangleWidget's shared canvas; `move_to()` redraws by tag (never delete-all), `clear()` erases only the pointer. A DRAWN shape only — never the OS mouse. No tkinter import (canvas duck-typed) so its unit test needs no display. |
| `src/muthis/overlay/pointer_animator.py` | ~141 | `PointerAnimator` — drives ONE ease-in-out (cosine) glide of the PointerWidget on the Tk thread via injected `schedule` (root.after), `clock` (time.monotonic) and `cursor_reader`. LOOK-ONLY: `read_cursor_pos()` calls **GetCursorPos read-only** (physical px; lazy ctypes, no new dep) as the glide START — it NEVER calls SetCursorPos/mouse_event/SendInput. A generation counter makes a replaced/cancelled glide drop any queued frame (no overlapping chains). `DEFAULT_POINTER_ANIM_MS = 500`. Fully fake-driven in tests (no window/mouse/sleep). |
| `src/muthis/hotkey.py` | ~123 | The activation: global push-to-talk listener (pynput, LISTEN-only → no Win11 elevation). Hold to talk, release to send. Configurable key (`MUTHIS_HOTKEY`, default `f9`) on its OWN background thread; key-DOWN calls `on_press` DIRECTLY (it only starts the mic — no asyncio, lowest latency), key-UP does the ONLY safe thread→loop crossing — `loop.call_soon_threadsafe(on_release)` — never a coroutine from the keyboard thread. Auto-repeat debounced via `_held` (one start per hold); a spurious release is ignored. `reset()` clears `_held` (called from the turn's reset_turn_state) so a LOST key-up — which would leave `_held` stuck True and debounce every later press into oblivion — can never permanently wedge the hotkey. Owns NO business logic (Law 11). pynput imported lazily in `start()` (CI/headless-safe). |
| `src/muthis/earcons.py` | ~107 | Pleasant lifecycle earcons (fire-and-forget, never blocking): `EarconPlayer.play(name)` plays a bundled WAV from `assets/earcons/` on a daemon thread via `winsound.PlaySound(SND_FILENAME\|SND_ASYNC)`, so it stalls neither the keyboard thread nor the loop and NEVER raises (missing file / disabled / non-Windows → silent). Two cues: `"listening"` (mic opened) + `"processing"` (turn start). Toggle `MUTHIS_EARCONS` (default on; Windows-only). The sound backend is an injected `play_sound` seam (fake in tests). WAVs are synthesized by `scripts/generate_earcons.py` (numpy — a DEV/asset dep; runtime uses winsound only). |
| `src/muthis/main.py` | ~292 | The production composition root + run-forever entry (`python -m muthis.main`). Builds the FULL real graph via the existing DI seams (real mic/STT/TTS-cascade/screen_capture/overlay + ClaudeAgent with the Saudi persona + sovereign Budget); the mic seam is `Mic().stop` (the turn ends the hold) with `Mic().start` wired to key-DOWN. Sizes the sent-image coordinate space once, warms TLS once, registers the hotkey, sources MUTHIS_POINTER_ANIM_MS (`_pointer_anim_ms`, default on a bad/empty value) into the overlay's pointer-glide duration, runs until Ctrl+C. `ActivationController` is the single activation gate (Orchestrator stays untouched): key-DOWN starts recording (refused while a turn runs; a leaked recording with NO turn — e.g. a lost key-up — is SELF-HEALED: reset then reopen, so F9 never wedges) then plays the "listening" earcon once the mic actually opened, and bridges key-UP to ONE turn (playing "processing" to mask latency). The injected `EarconPlayer` (`earcon=earcons.play`) is owned/triggered HERE, never in the orchestrator. `reset_turn_state()` is the SINGLE per-turn reset (Regression B) — mic to idle (`mic.reset`) + hotkey debounce (`listener.reset`) + `is_processing` False, all together — called in the `_run_one_turn` `finally` so EVERY path (success/raise/cancel/timeout) fully resets and the next F9 always opens fresh. Clean shutdown: stop listener → close overlay → `agent.aclose()`. `.env` loaded first (Law 5.1). |
| `tests/test_hotkey.py` | ~120 | Hold/release bridge tests (fakes only, no real keyboard): key-DOWN starts recording DIRECTLY (not on the loop), key-UP schedules the turn via a FakeLoop's `call_soon_threadsafe` (never a direct call), auto-repeat is debounced to one start per hold, `reset()` clears `_held` so a LOST key-up can't wedge the next press, a release without a press is ignored, non-target keys do nothing, the configurable char hotkey matches case-insensitively, and using the listener loads no pynput backend (lazy-import CI safety). |
| `tests/test_main_activation.py` | ~245 | Activation-gate tests (fakes only): a second activation is dropped while `is_processing` is True; the flag clears and activation works again after a turn; a turn that RAISES still resets in `finally`; the key-DOWN guard starts recording only when idle (refused during a turn). **Regression-B reset tests**: a leaked recording (is_recording True, no turn) is SELF-HEALED and reopened; a lost key-up doesn't wedge the next press; turn-end resets mic + hotkey + is_processing together; a RAISED turn resets the mic (not just is_processing) and F9 reopens; a CANCELLED turn still resets in the `finally`; two consecutive F9 turns each open a fresh mic. **Earcon tests**: F9 press plays "listening" AFTER the mic opens (no cue if the open failed); F9 release plays "processing". |
| `tests/test_earcons.py` | ~120 | EarconPlayer tests (fakes only, no audio): the injected `play_sound` backend records calls — an existing earcon plays (on a daemon thread), a disabled player / missing file is a silent no-op, `play()` is fire-and-forget (a slow backend never blocks the caller), a backend exception never propagates, and `MUTHIS_EARCONS` toggles enablement (Windows-gated). |
| `tests/test_generate_earcons.py` | ~72 | Earcon SYNTHESIS tests (numpy DEV-dep via `importorskip`; no audio): loads the by-path `scripts/generate_earcons.py` and asserts premium length (~0.5–0.9 s, not the old ~0.24/0.28 s beeps; `processing` > `listening`), a TRUE-zero onset AND tail (raised-cosine attack + release → no onset click / no end-of-buffer pop, max\|last 5 ms\| < 0.05), clipping headroom (peak ~0.28), and that `main()` writes 16-bit / mono / 44.1 kHz WAVs whose final FILE samples are click-free (last PCM frame == 0). |
| `tests/test_mic_ptt.py` | ~227 | PTT mic tests (fakes only, no PortAudio): a FakeStream delivers blocks through the real callback — start→push→stop returns all buffered frames in order (flush correctness), a sub-`min_record_seconds` tap yields a valid-but-empty WAV (NOT None), a failed stream open → None, stop-without-start → None; and end-to-end through the real `Mic().stop` seam an empty tap speaks STT_EMPTY_AR with the reasoner NEVER called (budget guard). **reset() tests**: it aborts an open hold without returning audio (stream closed first), a reset-then-start returns ONLY fresh frames (no stale leak), it is safe when never started, and never raises even if the stream close fails. |
| `src/muthis/stubs.py` | ~82 | Canned default deps (mic/stt/tts/screen_capture/downscale/overlay) for the stub-first build; each replaced by its real component via injection at the composition root. The overlay default is `StubOverlay` (show/hide no-op, logs only); the downscale default is a passthrough (bytes unchanged, identity scale) so CI never decodes an image. |
| `tests/test_orchestrator.py` | ~796 | Scripted FakeReasoner pipeline tests: end-to-end turn, budget-blocked refusal (provider never called), history growth, refresh follow-up with fresh screenshot, and Option B tool_use/tool_result pairing (a highlight turn is API-valid, two turns never orphan a tool_use, the refresh-limit branch still pairs). **Agentic-loop tests**: the dual-action point-then-explain continuation (run() called twice, both texts spoken in order, highlight drawn once, pairing then explanation in history), history stays API-valid through the loop (strict role alternation), the safety cap stops at `MAX_AGENTIC_ITERATIONS` with the spoken note, the budget closing mid-loop skips the continuation (Arabic refusal, run() not re-called), an abnormal None stop_reason ends without hanging (English warning), and an in-loop `request_screen_refresh` still hides the overlay before the fresh capture. The Recorder doubles as the Overlay seam (show/hide), asserting highlights reach the overlay as physical coords. **Bug 3 (stale-vision) tests**: one fresh frame is captured per utterance BEFORE the loop (hide→capture, not re-captured per iteration), a refresh frame reaches the follow-up iteration THEN is stripped from stored history (id/pairing kept), no stale frame survives into the next user turn (the app-switch guard), and the strip leaves the agentic loop unbroken. **Circuit-breaker tests (Fix 1)**: the `highlight_target` ack is a strict "stop pointing, explain now" directive; a 2nd highlight in a turn (next pass OR same pass) is NOT redrawn and gets `HIGHLIGHT_ALREADY_SHOWN_AR` while the explanation is still spoken and the loop ENDS; the gate resets on a new user turn (turn 2's first highlight draws again). **Hard-termination tests (Fix A)**: a reasoner that ALWAYS tries to point ends in 2 passes (NOT 4) because the post-highlight pass is forced `tool_choice="none"` → text + end_turn; `tool_choice` is "auto" on pass 1 and "none" after a highlight; a refresh follow-up is NOT forced to "none". |
| `tests/test_overlay_orchestration.py` | ~219 | Overlay step at the orchestrator↔overlay seam (fake overlay, no Tk/screen): sent→physical scale mapping (incl. per-axis scale_x≠scale_y), hide-before-EVERY-capture ordering (initial + refresh), and the LOOK-only boundary (only highlight geometry reaches the overlay; a non-highlight tool is refused). |
| `tests/test_overlay_autohide.py` | ~225 | AutoHideController + its orchestrator wiring (fakes only, no Tk/screen, no real 7 s sleep): schedule() is non-blocking then hides after an injected tiny timeout; a second schedule() before the timeout cancels-and-replaces the first (the first hide never fires early); cancel() drops a pending timer without hiding and is a no-op when idle; via run_turn a highlight arms the timer (which fires) and the next turn's capture cancels a stale timer (no orphan). Deterministic asyncio control, never real sleeps. |
| `tests/test_highlight_sync.py` | ~251 | Highlight↔audio sync (fakes only, no Tk/screen/audio, no real sleep): a logging reasoner + a unified show/hide/capture/speak order log prove the highlight is BUFFERED and drawn the instant BEFORE speak (never on ToolCall receipt), the auto-hide is armed only at that draw (injected 0 s timer, driven by hand, still pending at end-of-turn so a long synthesis can't consume it), FIRST-highlight-wins (circuit breaker — one draw, the later one suppressed), the refresh recapture stays hide-before-capture with NO pending highlight baked in, and a buffered highlight never leaks into the next turn. |
| `tests/test_pointer_animator.py` | ~114 | PointerAnimator glide logic (fakes only, no Tk/mouse/sleep): start() reads the OS cursor EXACTLY once (read-only), the glide interpolates start→target with cosine ease-in-out (midpoint = halfway), zero-duration arrives on frame 1, cancel() suppresses a queued frame + the arrival, a new glide supersedes the old (no overlapping chains, generation counter), ease endpoints, and DEFAULT_POINTER_ANIM_MS == 500. |
| `tests/test_pointer_widget.py` | ~45 | PointerWidget drawing (fake canvas, no Tk): move_to draws ONE tagged polygon with its tip on the coordinate, each redraw clears ONLY the pointer tag (never delete-all), clear() erases only the pointer — so a rectangle sharing the canvas is never disturbed. |
| `tests/test_overlay_pointer_dispatch.py` | ~79 | `dispatch_command` with fake rect/pointer/animator (no Tk/mouse): "show" starts a glide to the bbox CENTER and DEFERS the draw to arrival (its on_arrival draws the rectangle + redraws the pointer on top), "hide" cancels the glide + clears both, "close" cancels + signals stop; plus `_bbox_center`. |
| `tests/test_pointer_look_only.py` | ~52 | LOOK-only source scan (AST, not raw text — so docstring mentions are ignored): the overlay package never USES SetCursorPos/mouse_event/SendInput/ClipCursor (no OS mouse move/click), and DOES use GetCursorPos (the read-only glide start). |
| `tests/test_orchestrator_tts.py` | ~229 | Real-TTS wiring tests (buffer-then-speak): three separate sentences reach the TTS in ONE call with the full concatenated text (the anti-streaming regression guard), a stream that ends WITHOUT TurnComplete returns promptly with no never-arriving signal to await (no-hang), privacy boundary (no transcript/tool JSON to TTS), spoken budget refusal, turn survives TTS failure. |
| `tests/test_orchestrator_stt.py` | ~180 | Activation tests: mic→STT→provider wiring, early Arabic-spoken aborts (mic None / empty transcript) with zero provider calls, lazy-import CI safety. |
| `tests/test_orchestrator_persona.py` | ~159 | Orchestrator-driven wire test: the Saudi persona (NOT LOOK_SYSTEM_PROMPT), with the injected sent-image dims, is what ClaudeAgent sends as `system=`; screenshot=None carries no image block; LOOK-only tools only; transcript never reaches TTS. SDK stream faked. |
| `tests/test_screen_capture.py` | ~208 | ScreenCapture unit tests (fakes only, no real screen): faked-mss grab → real-Pillow PNG, primary monitor (not the `[0]` union), DPI awareness pinned at construction, blocking grab offloaded to a worker thread, None on failure (no raise), pixels never written to disk or logged. |
| `tests/test_screen_capture_wiring.py` | ~146 | Vision through the injected seam: the orchestrator passes the exact captured bytes (not None) into the reasoner, and re-captures + answers request_screen_refresh via assistant_content + a tool_result image; captured bytes never logged during a turn. |
| `tests/test_vision_downscale.py` | ~86 | The safeguard math (pure + real Pillow, no screen): 1920x1080→1280x720 with scale_x==scale_y==1.5 EXACTLY, per-axis independence, real `downscale_to_max_width` re-encodes a 1280x720 PNG with the factors, small-frame passthrough, None→None. |
| `tests/test_orchestrator_downscale.py` | ~105 | Wire test (fakes only): an injected fake downscale maps physical→a DISTINCT sent COPY; asserts the reasoner receives the SENT bytes (never physical) and TurnResult carries the exact scale factors, with nothing applied yet (no overlay). |
| `tests/test_tts_voice.py` | ~143 | Configurable Gemini voice (fakes only, no network): TTS resolves the voice constructor-arg > MUTHIS_GEMINI_VOICE env > DEFAULT_GEMINI_VOICE ("Kore", male) and hands it to the provider seam (captured); and tts_gemini.synthesize_pcm_blocking lands the resolved voice in the request body with its own arg > GEMINI_TTS_VOICE > "Kore" fallback. |
| `tests/test_tts_voice_elevenlabs.py` | ~120 | Configurable NATIVE-Arabic ElevenLabs voice (Fix 3; fakes only, no network): `DEFAULT_VOICE_ID` is the placeholder (the old "Rachel" id is gone) and `DEFAULT_VOICE_SETTINGS` is stability 0.7 / similarity_boost 0.8 / style 0.0; `voice_id` resolves arg > `ELEVENLABS_VOICE_ID` > placeholder; `voice_settings` resolves arg > per-field env (`ELEVENLABS_STABILITY`/`*_SIMILARITY_BOOST`/`*_STYLE`, bad/missing → documented default, no crash) > defaults; and the .env config actually reaches `tts_elevenlabs.stream_pcm` (captured kwargs). |
| `tests/test_tts_gemini_timeout.py` | ~115 | Gemini TTS timeout robustness (fakes only, no network/audio; patches urllib.request.urlopen to drive the REAL synthesize body): the request uses the configurable timeout (default 30 s, honors `MUTHIS_GEMINI_TIMEOUT_S`, invalid→default); a urllib timeout (bare socket.timeout/TimeoutError or URLError-wrapped) retries EXACTLY once then succeeds; a non-timeout error is NOT retried; and on a double-timeout speak() returns provider="none" without raising. |
| `tests/test_tts_cascade.py` | ~180 | Cascade tests (fakes only): ElevenLabs is PRIMARY (tried first; Gemini untouched when it succeeds), the falsey `MUTHIS_TRY_ELEVENLABS` rollback disables it and forces Gemini, ElevenLabs-fails→Gemini, both keys absent → provider="none", speak() never raises when both fail (last error = Gemini's, tried last); sys.modules sentinels prove SAPI/pyttsx3 never touched. |
| `tests/test_tts_ws_streaming.py` | ~263 | ElevenLabs WS streaming (fakes only, no network/device): a fake WS + fake player prove chunks are fed PROGRESSIVELY and in order (each fed before the next is received), and the full text is sent in ONE message; no-audio / error-frame raise for fallback; the real PcmStreamPlayer writes FIFO to a fake stream then drains via stop(), and re-raises a stream error; speak() uses ElevenLabs primary and falls back to Gemini on failure (never raises). |
| `tests/test_tts_diacritics.py` | ~160 | Diacritics tests (no network/audio): apply_diacritics vowelizes the key words and is SUBSTRING-SAFE (اسم/قسم/جسم/موسم/بسم untouched; still fires next to punctuation); speak() hands the diacritized COPY to BOTH ElevenLabs (primary) and Gemini (fallback) at the shared choke point WITHOUT mutating the caller's clean text; and the persona keeps the map words CLEAN (the speech forms never leak into persona.py output). |
| `tests/conftest.py` | ~24 | Autouse hermeticity fixture: clears the cloud-TTS keys (ELEVENLABS_API_KEY / GEMINI_API_KEY / MUTHIS_TRY_ELEVENLABS) AND the ElevenLabs voice-config vars (ELEVENLABS_VOICE_ID / *_MODEL_ID / *_STABILITY / *_SIMILARITY_BOOST / *_STYLE) so no test picks up the dev's real keys (a leaked key would make a real TTS() attempt a live WebSocket) and the documented voice defaults stay deterministic. |
| `ARCHITECTURE_v4_1.md` | — | The design constitution: laws, pending items, verification checklist. Read §3, §5, §20 before significant changes. |

Planned next (do not create until their build step): nothing pending for the LOOK phase.
Sentence-level TTS streaming was trialed then REVERTED — buffer-then-speak (accumulate the full reply,
speak it ONCE at end-of-turn) is the FINAL, chosen playback behavior (`src/muthis/tts_stream.py` deleted).
It removed a background consumer/queue/sentinel whose await could wedge `is_processing`.
That revert concerns LLM-TEXT chunking. Phase 1 added intra-AUDIO progressive playback: the orchestrator
still makes ONE speak() call with the full reply, and ElevenLabs streams the AUDIO back chunk-by-chunk
INSIDE that single call (no text segmentation) — NOT the reverted sentence streaming.
(`stt/elevenlabs_scribe.py` landed flat as `src/muthis/stt.py`, mirroring the flat `tts.py` precedent;
the planned `activation/hotkey_listener.py` landed flat as `src/muthis/hotkey.py` with `src/muthis/main.py`
as its composition root — completing the LOOK phase;
`vision/screen_capture.py` and the overlay (`overlay/sidekick_window.py` + `overlay/rectangle_widget.py`
+ `overlay/pointer_widget.py` + `overlay/pointer_animator.py` — the animated gliding pointer)
landed as package modules under `src/muthis/`.)

## Build & Run

```bash
# Windows 11, Python 3.11.x venv (separate from the frozen v3.0 SafeGuard venv)
python -m venv .venv && .venv\Scripts\activate
pip install "anthropic>=0.40" httpx pydantic python-dotenv websockets sounddevice pytest pytest-asyncio mss pillow "pynput==1.7.7"
# DEV/ASSET ONLY (NOT a runtime dep): numpy — used solely by scripts/generate_earcons.py
# to synthesize assets/earcons/*.wav. Runtime earcons need only winsound + those WAVs.
#   python scripts/generate_earcons.py   # (re)generate the bundled earcon WAVs

# .env (never committed): ANTHROPIC_API_KEY=...  GEMINI_API_KEY=... (PRIMARY TTS voice)
#   ELEVENLABS_API_KEY=... (STT Scribe; its TTS path is PARKED — used only via the flag below)
#   optional: MUTHIS_CLAUDE_MODEL, MUTHIS_ANTHROPIC_BASE_URL,
#             MUTHIS_TRY_ELEVENLABS (ElevenLabs is PRIMARY TTS, default ON; set falsey to force Gemini),
#             ELEVENLABS_VOICE_ID (REQUIRED for the right accent — paste a NATIVE Arabic voice id, e.g. a
#                                  Saudi/Gulf male; the default is a placeholder that hard-fails to Gemini),
#             ELEVENLABS_MODEL_ID (default model eleven_flash_v2_5),
#             ELEVENLABS_STABILITY / ELEVENLABS_SIMILARITY_BOOST / ELEVENLABS_STYLE (voice_settings floats;
#                                  defaults 0.7 / 0.8 / 0.0 — higher stability locks the Arabic accent),
#             MUTHIS_GEMINI_VOICE (Gemini fallback voice, default "Kore" male; e.g. Fenrir),
#             MUTHIS_GEMINI_TIMEOUT_S (Gemini TTS request timeout seconds, default 30; one fast retry on timeout),
#             MUTHIS_HOTKEY (push-to-talk key, default "f9"),
#             MUTHIS_POINTER_ANIM_MS (overlay pointer glide duration ms, default 500),
#             MUTHIS_EARCONS (UI lifecycle sounds, default on; Windows-only),
#             MUTHIS_MIN_RECORD_SECONDS (min hold before a tap counts as empty, default 0.35),
#             MUTHIS_RECORD_SECONDS (dev smoke scripts' fixed window only)

# Tests (no network needed)
set PYTHONPATH=src && python -m pytest tests/ -q

# Run Mut'his — the live hands-free app (LOOK phase). Idles until you HOLD the
# hotkey (default F9): hold while speaking Arabic, release to send ONE full real
# turn; Ctrl+C to quit.
set PYTHONPATH=src && python -m muthis.main
```

Smoke-test the pinned model string against the live API within 24 h of starting real integration
(Pending §16-18.1); fall back per the table in ARCHITECTURE_v4_1.md §4.2 if it 404s.

## Code Style & Conventions

- **Clarity over concision** (Clicky rule, adopted): names must be self-explanatory to a zero-context reader.
  `pending_tool` not `pt`; `detect_image_media_type` not `sniff`. No single-character names.
- **Every module ≤ 300 lines, single responsibility, importable in isolation** (Law §17.4). If a module
  approaches the limit, split it — do not compress it.
- **Stub-first** (Law §3.5): every new handler ships as a logging stub before it does anything real.
- **Comments explain WHY**, especially around Win32/Tk bridging and SDK quirks.
- **Language split** (Law §17.5): user-facing strings (voice prompts, overlay captions, error speech) are
  Arabic; logs, comments, identifiers, and commit messages are English. The two never mix in one surface.
- **Dual-action intent is TWO-PASS + tiered verbosity** (persona prompt-engineering, `persona.py`; tool_result
  in `highlight_gate.py`): a WHERE question ("وين X") is answered across TWO turns — pass 1 points
  (`highlight_target`), pass 2 dives STRAIGHT into the explanation. The persona, the `highlight_target`
  tool_result, and `tool_choice="none"` (pass 2) must all REINFORCE this: tell the model to point first, then on
  its NEXT turn START with the actual information (WHAT + WHY) with NO filler/ack ("أبشر"/"أشرت لك"/"تم"). **PASS 1
  is point-ONLY** (one job per pass): at most a one/two-word ack then `highlight_target`, and NEVER a
  screen-narration ("أشوف..."/"بأشّر على...") or any explanation — that leak put the explanation in pass 1 and
  left the forced-text pass 2 empty. NEVER word the persona as "point AND explain in the SAME response", and NEVER
  frame the tool_result as task-complete ("بنجاح") OR even open it with a completion lead ("تم وضع المؤشّر …") —
  frame it as an INTERNAL directive the user never hears ("توجيه داخلي … لا يراه المستخدم") that ORDERS the
  explanation now; both completion framings caused pass 2 to emit a bare ack. Anti-laziness is PASS-2 scoped: a
  bare ack in pass 1 is CORRECT, the turn is "lazy" only if pass 2 never delivers the WHAT+WHY. Verbosity has a SHORT ~40-60-word cap: natural and short for
  small-talk, a snappy WHAT+WHY (3-4 short sentences) when asked to point/explain/analyze, a SOFT target (never a
  hard truncation); if the topic needs more, give the core THEN offer to elaborate ("أكمّل لك أكثر؟"). On pass 1
  `tool_choice` is `auto` — NEVER force it to `any`/`tool` (that suppresses prose); pass 2 forces `none` (forbids
  tools, does NOT force one) so the explanation is emitted as text. Fix dual-action in the prompt + tool_result,
  never by forcing a tool.
- **Highlight circuit breaker — ONE point per turn** (`highlight_gate.py` + `turn.next_highlight` +
  `orchestrator`): the screenshot stays attached across the agentic loop, so Claude re-sees its own target and,
  without a brake, calls `highlight_target` again and again until the budget cap — never explaining. THREE
  layers: (1) PROMPT — the `highlight_target` tool_result is a STRICT directive (`HIGHLIGHT_ACK_TEXT_AR`: "stop
  pointing, explain now"); (2) DRAW SUPPRESSION — a per-turn `HighlightGate` (rebuilt at the top of
  `_run_turn_pipeline`, so it resets by construction) draws ONLY the first highlight, every later one suppressed
  and answered with `HIGHLIGHT_ALREADY_SHOWN_AR`; (3) HARD TERMINATION (the real fix) — once `gate.drawn`, the
  NEXT run() is made with `tool_choice="none"` (`loop_tool_choice`), so the API forbids ALL tool use and the
  model MUST emit text → end_turn → the loop ends. A prompt nudge is NEVER the loop terminator; the API is. Fix
  looping in these layers, never by detaching the image (that re-breaks point→explain).
- **One per-turn state reset — `reset_turn_state()`** (`ActivationController`, `main.py`): mic-to-idle
  (`mic.reset`), hotkey debounce (`listener.reset`), and `is_processing` are reset TOGETHER in the
  `_run_one_turn` `finally`, so EVERY path (success/raise/cancel/timeout) fully resets and the next F9 always
  opens a fresh mic. NEVER reset per-turn state in scattered sites (the bug was: `is_processing` reset in
  `finally` but mic state only inside `mic.stop()`, so a turn that died before `mic.stop()` leaked the open
  stream). `on_press` also self-heals a leaked recording (is_recording True with NO turn running → reset +
  reopen) so a lost key-up can't wedge F9.
- **Earcons are fire-and-forget and never block** (`earcons.py`, triggered in `ActivationController`): play on a
  daemon thread, never raise, and degrade to silence (missing file / `MUTHIS_EARCONS` off / non-Windows). They
  are owned/triggered from `main.py`, NEVER the orchestrator. "listening" plays only AFTER the mic confirms open;
  "processing" on turn start. Regenerate the WAVs with `scripts/generate_earcons.py` (numpy = DEV/asset dep only;
  runtime is winsound + the bundled WAVs in `assets/earcons/`). **Premium click-free synthesis**: ONE unified
  envelope per tone — a 20 ms raised-cosine ATTACK (kills the onset click), a long exponential DECAY, then a
  40 ms raised-cosine RELEASE that forces the tail to a TRUE-zero last sample. The old pop was an exponential
  decay truncated at ~10% amplitude (a discontinuity at the buffer cut); the release ramp is the fix and is
  load-bearing — never drop it. `listening` = a bright rising perfect fifth C5→G5 (two OVERLAPPING notes, so it
  reads as one gesture not two beeps); `processing` = a warm low G4 chime with a long mellow decay + a subtle
  second strike. 44.1 kHz / 16-bit mono, peak ~0.28 (clipping headroom), soft 2nd-harmonic octave for warmth —
  never harsh beeps.
- **TTS-layer diacritics are SPEECH-ONLY, never in history** (`tts_diacritics.py`): a small DATA map vowelizes
  key Saudi words (أبشر/سم/طال عمرك) on a COPY at the `tts.py` `speak()` choke point, for pronunciation only.
  The model keeps WRITING — and history keeps STORING — clean unvowelized Arabic; harakat NEVER enter
  `persona.py` or conversation history (vowelized history would corrupt the model's reasoning). Match keys as
  whole Arabic words (boundary look-arounds), never substrings, so "سم" can't corrupt اسم/قسم/جسم/موسم.
- **History stays API-valid — tool_use/tool_result pairing** (Option B): every assistant `tool_use` stored in
  history MUST be answered by a `tool_result` in the very next user message (`turn.build_tool_result_message`):
  a `highlight_target` id gets a short Arabic ack, a `request_screen_refresh` id gets the fresh screenshot.
  Never store an orphan `tool_use` (it 400s the NEXT turn) or an empty message. `claude_agent.run()` folds a
  trailing user message into the new turn so roles still alternate.
- **Fresh frame per user turn, images never persisted** (`orchestrator` + `turn.strip_images_from_history`,
  Bug 3): each NEW utterance captures ONE downscaled frame (hide→settle→capture) BEFORE the agentic loop. That
  SAME frame stays ATTACHED across the loop's iterations (it is NOT cleared mid-loop), so the point→explain
  continuation still SEES what it pointed at and never re-fires a needless `request_screen_refresh` (symptom 1);
  the frame is captured ONCE — reuse is never a re-capture. It is cleared ONLY on a serviced
  `request_screen_refresh`, whose fresh image rides its `tool_result` instead. History stays text + tool
  interactions only — the user image is never stored (the attached frame is ephemeral, never written to
  history), and a `request_screen_refresh` frame is stripped at turn-end (`STALE_SCREENSHOT_NOTE_AR`,
  id/pairing preserved). This kills the app-switch hallucination where a stale screenshot lingering in history
  made the model reason about a since-closed app.
- **Agentic loop — point THEN explain** (`orchestrator._run_turn_pipeline`): a turn that ends on
  `stop_reason == "tool_use"` is NOT the end of the turn. The orchestrator appends the tool_result pairing and
  re-calls `ClaudeAgent.run()` to fetch the continuation Muthis planned AFTER the tool call, looping WHILE the
  stop reason stays `tool_use`. The loop is bounded by `MAX_AGENTIC_ITERATIONS` (4), checks `budget.can_afford()`
  before EVERY iteration, and speaks each turn's text as it completes (Option B — continuous flow, no cross-turn
  accumulation). It ends cleanly on `end_turn`, a None stop_reason (abnormal stream → English warning), or the
  cap (spoken `AGENTIC_CAP_NOTE_AR`). The loop is owned by the orchestrator; `run()` stays ONE provider call
  (Law 11). A `request_screen_refresh` inside the loop still hides the overlay before its fresh capture.
- **Async/await throughout**; never spawn threads except where a library forces it (Tk gets its own thread,
  commands cross via `queue.Queue` — see ARCHITECTURE_v4_1.md §11.5).
- **`.env` first, imports second** at process entry. No key ever appears in code, logs, or tests.

## Do NOT

- Do not add `type_text`, `press_hotkey`, `real_click`, or `set_trust_mode` anywhere — not in schemas, not as
  stubs. LOOK-only is a hard boundary until the Trust Modes phase is explicitly opened.
- Do not touch `src/safeguard/` — v3.0 is frozen. Never import across the `safeguard`/`muthis` namespaces;
  genuinely reusable patterns are copied, not imported (ARCHITECTURE_v4_1.md §19).
- Do not add retries, locks, queues, or session timeouts inside `cloud/` wrappers — the orchestrator owns all
  lifecycles (Law 11). One `run()` call == one provider turn.
- Do not log transcripts, audio, or screenshots by default. `MUTHIS_DEBUG=1` is the only gate for transcript
  logging, and it must never default to on.
- Do not parse coordinates out of response prose. Tool calls only.
- Do not add features, refactor, or "improve" beyond what was asked.
- Do not commit `.env`, `budget.json`, `*.log`, or model files.

## Git Workflow

- Branch naming: `feature/description` or `fix/description`.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`), imperative mood, explain the why.
- Do not force-push to main.

## Self-Update Instructions

<!-- AI agents: follow these instructions to keep this file accurate. -->

When you make changes that affect the information in this file, update it:

1. **New files**: add them to the Key Files table with purpose and approximate line count.
2. **Deleted files**: remove their entries.
3. **Architecture changes**: update the Architecture section (and flag any conflict with ARCHITECTURE_v4_1.md
   to the user instead of silently resolving it).
4. **Phase changes**: if the user explicitly opens the Trust Modes phase, rewrite the LOOK-only paragraphs and
   the first "Do NOT" bullet — this is the ONLY way that boundary moves.
5. **New conventions**: if the user establishes a convention mid-session, record it under Conventions.
6. **Line count drift**: refresh counts that drift by more than 50 lines.

Do NOT update this file for minor edits or bug fixes that don't affect documented architecture or conventions.
