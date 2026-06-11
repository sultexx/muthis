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
PTT press → mic capture → STT (ElevenLabs Scribe) → ClaudeAgent.run()
   → TextDelta stream → ElevenLabs Flash v2.5 TTS (streaming playback)
   → ToolCall(highlight_target) → cyan rectangle + Arabic caption (Tk overlay)
   → TurnComplete(usage, cost) → budget.py
```

- **One asyncio event loop, one PriorityQueue, one dispatcher** (orchestrator.py owns them — Law §3.3).
- **CloudReasoner protocol** (`cloud/protocol.py`): every provider hides behind the same three events —
  `TextDelta`, `ToolCall`, `TurnComplete`. The orchestrator never knows which vendor answered (Law §3.7).
- **Single-path v1**: Claude only. The speed-path (Gemini) and the router are deferred until the single path
  is boringly reliable in daily use.
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
| `ARCHITECTURE_v4_1.md` | — | The design constitution: laws, pending items, verification checklist. Read §3, §5, §20 before significant changes. |

Planned next (do not create until their build step): `orchestrator.py`, `budget.py`,
`activation/hotkey_listener.py`, `tts/elevenlabs_streamer.py`, `stt/elevenlabs_scribe.py`,
`overlay/sidekick_window.py`, `overlay/rectangle_widget.py`, `vision/screen_capture.py`.

## Build & Run

```bash
# Windows 11, Python 3.11.x venv (separate from the frozen v3.0 SafeGuard venv)
python -m venv .venv && .venv\Scripts\activate
pip install "anthropic>=0.40" httpx pydantic python-dotenv pytest pytest-asyncio

# .env (never committed): ANTHROPIC_API_KEY=...   optional: MUTHIS_CLAUDE_MODEL, MUTHIS_ANTHROPIC_BASE_URL

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
