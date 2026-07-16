# scripts/diag_full_turn.py
"""
DIAG(v7) — ONE full REAL turn with a SCRIPTED question. NEVER run in CI.

Measures the "stop-and-go" complaint end to end: the same production pipeline
as scripts/smoke_live_turn.py (real screen capture → Claude with the Saudi
persona → real overlay draw → real TTS with MUTHIS_STREAM_TTS honored), but
the mic/STT stage is SKIPPED — `run_turn()` is driven with a hardcoded
WHERE-question so the two-pass point→explain flow fires deterministically:

    pass 0 (tool_choice=auto):  short ack + highlight_target → draw → BUFFERED
                                speak of the ack (blocks the loop while playing)
    pass 1 (tool_choice=none):  the explanation, sentence-STREAMED

The temporary [DIAG] timing probes were REMOVED (2026-07-16, Sultan-approved)
once the v7 audio work landed; verification is now by EAR (no audible gap
between the pass-0 ack and the pass-1 explanation) plus the printed summary.

Privacy: the question is a hardcoded script constant (not user speech); the
screenshot goes to Claude for this turn only, never to disk. Costs ONE real
Claude turn (2 passes) + TTS — budget-gated like production.

Needs in .env: ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
               (GEMINI_API_KEY optional — TTS fallback only).

Run:  .venv\\Scripts\\python.exe scripts\\diag_full_turn.py
"""

import asyncio
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()  # Law 5.1: .env before any muthis import that reads keys

from muthis.budget import Budget                                       # noqa: E402
from muthis.cloud.claude_agent import ClaudeAgent, LOOK_SYSTEM_PROMPT  # noqa: E402
from muthis.orchestrator import Orchestrator                           # noqa: E402
from muthis.overlay import SidekickOverlay                             # noqa: E402
from muthis.persona import resolve_system_prompt                      # noqa: E402
from muthis.tts import TTS                                             # noqa: E402
from muthis.vision.downscale import (                                  # noqa: E402
    DEFAULT_VISION_MAX_WIDTH, compute_scale_factors, downscale_to_max_width,
)
from muthis.vision.screen_capture import (                             # noqa: E402
    ScreenCapture, primary_monitor_size,
)

# A WHERE-question about a UI element that ALWAYS exists on Windows 11, so the
# two-pass dual-action (point → explain) fires on any desktop.
SCRIPTED_QUESTION = "وين زر ابدأ في شريط المهام؟"


async def main() -> None:
    # Same startup as the production composition root (smoke_live_turn.py).
    physical = primary_monitor_size()
    if physical is not None:
        sent_width, sent_height, _sx, _sy = compute_scale_factors(
            physical[0], physical[1], DEFAULT_VISION_MAX_WIDTH)
    else:
        sent_width = DEFAULT_VISION_MAX_WIDTH
        sent_height = round(DEFAULT_VISION_MAX_WIDTH * 9 / 16)
    persona_prompt = resolve_system_prompt(LOOK_SYSTEM_PROMPT, sent_width, sent_height)

    agent = ClaudeAgent(system_prompt=persona_prompt)
    await agent.warm_up_tls()

    budget = Budget()
    if not budget.can_afford():
        print("Budget gate closed — raise MUTHIS_DAILY_BUDGET_USD or try tomorrow.")
        await agent.aclose()
        return

    overlay = SidekickOverlay()
    orchestrator = Orchestrator(
        reasoner=agent,
        budget=budget,
        tts=TTS().speak,                         # REAL buffered path (pass-0 ack)
        screen_capture=ScreenCapture().capture,  # REAL primary-monitor PNG
        downscale=downscale_to_max_width,        # REAL payload COPY
        overlay=overlay,                         # REAL neon overlay
        # mic/stt seams intentionally left as stubs — run_turn() is driven
        # directly below, so no microphone is opened.
    )

    print("Driving ONE real two-pass turn — WATCH the overlay, LISTEN for the gap...")
    result = await orchestrator.run_turn(SCRIPTED_QUESTION)

    print("\n──────── turn summary ────────")
    print(f"budget_blocked={result.budget_blocked} timed_out={result.timed_out}")
    print(f"tool_calls={[call.name for call in result.tool_calls]}")
    print(f"tokens in/out = {result.input_tokens}/{result.output_tokens}  cost={result.cost_usd:.6f} USD")
    print(f"reply: {result.spoken_text}")  # assistant-authored — safe to print

    if result.tool_calls:
        await asyncio.sleep(3.0)  # keep the rectangle visible long enough to SEE
    overlay.close()
    await agent.aclose()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic-safe Windows console
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
