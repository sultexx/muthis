# Mut'his (مطحس) — Agent Instructions

<!-- This is the single source of truth for all AI coding agents (Claude Code, Cursor, Copilot, Gemini CLI). -->
<!-- CLAUDE.md points here. On Windows, symlinks need Developer Mode (`mklink CLAUDE.md AGENTS.md` in an elevated
     cmd); if unavailable, keep CLAUDE.md as a one-line file: "Read AGENTS.md — it is the single source of truth." -->
<!-- Full design rationale lives in ARCHITECTURE_v4_1.md. When this file and the architecture doc disagree on
     CURRENT scope, this file wins; when they disagree on LAWS, the architecture doc wins. -->

## Overview

Arabic-first voice sidekick for Windows 11. The user presses **Ctrl+Shift+Space** (push-to-talk), speaks Arabic,
and Mut'his answers with streamed Arabic speech (ElevenLabs) while pointing at on-screen UI elements with a
**cyan rectangle overlay**. Reasoning + vision: **Claude Sonnet** (`claude-sonnet-4-6`) via the official
`anthropic` SDK with SSE streaming.

**CURRENT PHASE: LOOK-only.** Mut'his speaks and points. It does **not** click, type, press hotkeys, or touch
the clipboard. Trust Modes (ASSIST / AUTOPILOT) are designed in ARCHITECTURE_v4_1.md §12 but are **not in scope
yet** — do not build them, do not stub them, do not add their tools to any schema.

Hardware target: Windows 11, RTX 4060 8 GB. The app must use ~0 GB VRAM and never compete with the user's
Blender/YOLO workloads. Everything heavy is cloud.

## Architecture

```
PTT press → mic capture (fixed window until the hotkey phase) →
   STT (ElevenLabs Scribe, language pinned "ar") → ClaudeAgent.run()
   → TextDelta stream → ElevenLabs Flash v2.5 TTS (buffer-then-speak today;
     sentence streaming is the follow-up; Gemini TTS = voice-only fallback)
   → ToolCall(highlight_target) → cyan rectangle + Arabic caption (Tk overlay)
   → TurnComplete(usage, cost) → budget.py
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
inside the wrapper — history is the orchestrator's (Law 11: wrappers own no lifecycles, locks, or events).

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `src/muthis/cloud/protocol.py` | ~98 | `CloudReasoner` protocol + the three response events. Zero third-party deps; importable in isolation. |
| `src/muthis/cloud/claude_agent.py` | ~278 | Quality-path wrapper: `anthropic` SDK streaming, vision payload build, media-type sniffing, LOOK-only tool schemas, Arabic system prompt, TLS warmup, cost annotation. |
| `tests/cloud/test_claude_agent.py` | ~169 | Fake-session integration test (§15 step 8): asserts event sequence, partial-JSON buffering, cost math, and that no action tool is offered. |
| `src/muthis/budget.py` | ~229 | Sovereign daily spend gate (Rule 10): UTC-date-keyed `budget.json` ledger, `can_afford` pre-flight + `record_turn` consuming `TurnComplete.cost_usd`, limit from `MUTHIS_DAILY_BUDGET_USD`. Boolean contract, no exceptions. |
| `tests/test_budget.py` | ~150 | Deterministic budget tests: limit gating, accumulation + persistence, date rollover via injected clock, corrupt-ledger recovery, env-driven limit. |
| `src/muthis/orchestrator.py` | ~297 | The heart: owns the loop, queue, history, 90 s session bound. Budget gate before EVERY provider call; handle_activation: mic→STT→run_turn with Arabic-spoken early aborts; buffered TextDelta→TTS per message; highlight_target→overlay (LOOK-only enforced); request_screen_refresh answered via tool_result follow-up. |
| `src/muthis/turn.py` | ~57 | TurnResult + injected-dependency type aliases (MicFn/SttFn/TtsFn/...) + user-facing Arabic constants. Split from orchestrator under the ≤300-line law; orchestrator re-exports. |
| `src/muthis/persona.py` | ~116 | The Saudi-dialect persona system prompt for «مطحس» + `resolve_system_prompt()`. Injected into ClaudeAgent through its EXISTING `system_prompt` seam at the composition root (claude_agent.py untouched); falls back to LOOK_SYSTEM_PROMPT with a LOUD English warning ONLY if the builder is empty/raises. stdlib-only, importable in isolation. |
| `tests/test_persona.py` | ~130 | Persona tests (no SDK): Saudi dialect markers (أبشر/سم/طال عمرك/وشلونك/عاد), the "UI names stay English" rule + Sketch/Extrude/Fusion 360, LOOK-only honesty + no action-tool name leak, and the loud empty/raise fallback. |
| `src/muthis/tts.py` | ~291 | The tongue: ElevenLabs Flash v2.5 WebSocket TTS (collect-then-play) cascading to Gemini TTS; `speak()` never raises, returns TTSResult(provider="elevenlabs"\|"gemini"\|"none"). SAPI/pyttsx3 removed. |
| `src/muthis/tts_gemini.py` | ~112 | Gemini TTS REST voice fallback — VOICE ONLY, never reasoning/vision. stdlib urllib (blocking, run via to_thread), returns 24 kHz PCM. |
| `src/muthis/stt.py` | ~107 | The ears: ElevenLabs Scribe cloud STT (default `scribe_v2`, language pinned `ar` against Whisper-style code-switching); `transcribe()` never raises, "" on failure; httpx lazy. |
| `src/muthis/mic.py` | ~87 | Fixed-window mic capture (lazy sounddevice → in-memory WAV 16 kHz mono); interim PTT stand-in until the hotkey phase; `record()` never raises, None on failure. |
| `src/muthis/stubs.py` | ~58 | Canned default deps (mic/stt/tts/screen_capture/overlay) for the stub-first build; each deleted as its real component lands. |
| `tests/test_orchestrator.py` | ~215 | Scripted FakeReasoner pipeline tests: end-to-end turn, budget-blocked refusal (provider never called), history growth, refresh follow-up with fresh screenshot. |
| `tests/test_orchestrator_tts.py` | ~170 | Real-TTS wiring tests: buffer-then-speak exactly once, privacy boundary (no transcript/tool JSON to TTS), spoken budget refusal, turn survives TTS failure. |
| `tests/test_orchestrator_stt.py` | ~180 | Activation tests: mic→STT→provider wiring, early Arabic-spoken aborts (mic None / empty transcript) with zero provider calls, lazy-import CI safety. |
| `tests/test_orchestrator_persona.py` | ~155 | Orchestrator-driven wire test: the Saudi persona (NOT LOOK_SYSTEM_PROMPT) is what ClaudeAgent sends as `system=`; screenshot=None carries no image block; LOOK-only tools only; transcript never reaches TTS. SDK stream faked. |
| `tests/test_tts_cascade.py` | ~110 | Cascade tests: ElevenLabs failure → Gemini tried; both keys absent → provider="none" no crash; sys.modules sentinels prove SAPI/pyttsx3 never touched. |
| `ARCHITECTURE_v4_1.md` | — | The design constitution: laws, pending items, verification checklist. Read §3, §5, §20 before significant changes. |

Planned next (do not create until their build step):
`activation/hotkey_listener.py`, `tts/elevenlabs_streamer.py` (sentence-streaming playback),
`overlay/sidekick_window.py`, `overlay/rectangle_widget.py`, `vision/screen_capture.py`.
(`stt/elevenlabs_scribe.py` landed flat as `src/muthis/stt.py`, mirroring the flat `tts.py` precedent.)

## Build & Run

```bash
# Windows 11, Python 3.11.x venv (separate from the frozen v3.0 SafeGuard venv)
python -m venv .venv && .venv\Scripts\activate
pip install "anthropic>=0.40" httpx pydantic python-dotenv websockets sounddevice pytest pytest-asyncio

# .env (never committed): ANTHROPIC_API_KEY=...  ELEVENLABS_API_KEY=... (TTS+STT)
#   GEMINI_API_KEY=... (TTS voice fallback ONLY)
#   optional: MUTHIS_CLAUDE_MODEL, MUTHIS_ANTHROPIC_BASE_URL, MUTHIS_RECORD_SECONDS

# Tests (no network needed)
set PYTHONPATH=src && python -m pytest tests/ -q
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
