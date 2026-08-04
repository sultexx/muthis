# Mut'his (مطحس)

**An Arabic-first voice sidekick for Windows 11 that looks at your screen, explains what it sees, and points at it — and never touches your machine.**

You hold **F9**, speak Arabic, and let go. Mut'his takes a screenshot, understands it, answers out loud in Arabic, and draws a cyan rectangle around the thing it is talking about. It can also read a local text file, run code in a throwaway container, search the web, open one of your own documents and answer from it, and walk you through a task step by step.

It cannot click. It cannot type. It cannot press a key or touch your clipboard. That is not a gap in the roadmap.

---

## LOOK-only is the product, not a limitation

Most screen assistants are built to *act for you*. Mut'his is built to *teach you*, and the difference is architectural rather than cosmetic.

An assistant that clicks has to be trusted with your session. Every feature after that point is a negotiation about how much control to hand over, and every bug is a bug that can move your mouse. An assistant that only speaks and points has nothing to negotiate. It can be wrong out loud — which you will notice and correct — but it cannot be wrong *and* silently reorganise your files.

So the boundary is permanent and stated as law:

> **Zero control over the user's session, system, and input devices.** No clicking, no typing, no hotkeys, no clipboard.

The tools that would move that boundary — `type_text`, `press_hotkey`, `real_click`, `set_trust_mode` — are banned from the codebase entirely. Not deferred, not stubbed, not behind a flag. "Trust Modes", the one mechanism ever designed to open it, was **cancelled from the product vision** rather than postponed. Adding any of them is a change to the product's identity and needs an explicit signed decision, not a pull request.

One carve-out exists, and it proves the rule rather than weakening it: code the model writes may execute **inside a Mut'his-owned container** — no network by default, no access to your files without per-run consent, killable instantly with F9. The container is not your session. The mouse-and-keyboard boundary above is untouched by it.

There is a second boundary that matters just as much. Once Mut'his can read a web page or one of your documents, **hostile text can enter a turn**. So everything external arrives wrapped as untrusted data with a fresh unforgeable delimiter, raises a session-sticky taint flag in the same breath, and any high-impact call made afterwards needs your spoken approval on the *next* turn. The model never participates in authorising itself.

And when retrieval misses — which at real-world recall is the *expected* case, not the exception — Mut'his is required to say **«ما لقيت هذا في المستند»** ("I didn't find this in the document") rather than fill the gap. A confident fabrication is the failure that matters here, because a miss looks exactly like an answer.

---

## What it can do

| Capability | What it means |
|---|---|
| **See and point** | Screenshot → understanding → Arabic speech + a cyan rectangle on the real element |
| **Draw** | Arrows, circles, rectangles, numbered step badges, and a dimmed "whiteboard" behind concept drawings |
| **Read a file** | Reads a local text file so explanations cite real content and real line numbers, never pixels |
| **Run code** | Executes model-written code in a throwaway container, then explains the actual output |
| **Search the web** | Searches and reads pages through a hardened, credential-free fetcher |
| **Open your documents** | Indexes a PDF in RAM and answers from it — the index dies with the process |
| **Guide you** | Holds a plan and walks you through it step by step, pointing at each step |
| **Be interrupted** | Press F9 while it is speaking and it stops in ~100 ms, mid-sentence, and listens |

---

## Architecture at a glance

```
F9 held → microphone capture → speech-to-text (Arabic, pinned)
   → Claude Sonnet with the screenshot (streaming)
      → tool call: point / draw / read / run / search / open / plan
      → the ONE buffered draw is applied, THEN speech begins   (sync point)
      → Arabic speech out (one continuous generation per turn) + live captions
   → repeat while the model still wants a tool (max 4 passes, budget-checked each time)
```

Some load-bearing choices:

- **One asyncio event loop, and the orchestrator owns every lifecycle.** Provider wrappers own no retries, no locks, no timers. One call is one turn.
- **Structured tool calls, never parsed prose.** Coordinates never come from a regular expression over the model's text.
- **Draw first, then speak.** The single buffered drawing is applied at a fixed sync point so the pointer never lands after the sentence that refers to it.
- **The kernel owns the facts.** A plugin may not declare its own provenance, its own cost, its own impact, or that its own result is safe. Security a plugin author can weaken is not security.
- **≤300 lines per module.** At the ceiling you split; compressing to fit is forbidden, and a guard test enforces it.
- **The screen is the only sensor.** No transcripts, audio, or screenshots are logged. Third-party HTTP logging is silenced at the composition root, because an HTTP client that logs full URLs writes your search query into a log file.

Reasoning and vision run in the cloud. The machine target is a Windows 11 laptop with an RTX 4060, and the app is designed to use roughly **zero VRAM** so it never competes with real GPU work.

---

## Setup

**Requirements:** Windows 11, Python 3.11+ (3.14 recommended), a microphone, and API keys for Anthropic, ElevenLabs, and Google.

```bash
python -m venv .venv && .venv\Scripts\activate

pip install "anthropic>=0.40" httpx pydantic python-dotenv websockets \
            sounddevice pytest pytest-asyncio mss pillow "pynput==1.7.7"

# web research: readable-text extraction
pip install trafilatura lxml

# document Q&A: PDF text + the pinned local embedding model
pip install pypdf onnxruntime tokenizers huggingface_hub

# the plugin SDK and the `muthis` CLI, installed once
pip install -e sdk
```

Copy `.env.example` to `.env` and fill it in. **Read the two entries under "learned the hard way" first** — both fail silently rather than loudly, and between them they account for more confused debugging than anything else in this project.

```bash
# run the tests (no network needed)
set PYTHONPATH=src && python -m pytest tests/ -q
python -m pytest sdk/tests -q

# run Mut'his — idles until you HOLD F9
set PYTHONPATH=src && python -m muthis.main
```

Hold F9, speak Arabic, release. Ctrl+C to quit.

---

## Repository map

| Path | What lives there |
|---|---|
| `src/muthis/kernel/` | The turn machinery — orchestrator, passes, draw gate, budget, tool router |
| `src/muthis/broker/` | Capability grants, the hardened fetcher, search providers, document indexing |
| `src/muthis/overlay/` | The Tk overlay: rectangles, shapes, captions, status light |
| `src/muthis_plugins/` | The tools themselves, each a plugin over the SDK |
| `sdk/` | `muthis-sdk` — the plugin contract and conformance kit |
| `scripts/` | `diag_*.py` live-test scripts (never run in CI) |
| `docs/reports/` | One closure report per phase, with its commit ledger |

## Documentation

- **`AGENTS.md`** — the single source of truth: laws, current scope, and every file's purpose.
- **`DECISIONS.md`** — the signed decision ledger. Append-only; a past entry is superseded, never rewritten.
- **`CONTRIBUTING.md`** — the acceptance conditions a change must meet.
- **`PROJECT_STATE.md`** — the compressed current-state snapshot.

Every architectural decision in this project was written down at the moment it was made, including the ones that turned out to be wrong and the measurements that refuted them. If you want to know *why* something is the way it is, the ledger will tell you.

---

## Status

Working software, actively developed, and not packaged for general installation. It is developed and tested on one machine against one hardware target. There is no installer, no auto-update, and no support commitment.

## License

[Apache License 2.0](LICENSE).

Apache-2.0 was chosen over MIT because it answers the patent question explicitly rather than leaving it silent, and because its **trademark clause** is the only lever this project has over its own boundary: a licence cannot stop a fork from adding real clicking, but it can stop that fork from calling itself Mut'his.

**No licence preserves LOOK-only.** If you fork this and teach it to click, that is legally permitted and architecturally the opposite of the point. Do not call the result Mut'his.
