# scripts/diag_whiteboard.py
"""
DIAG(v7 Phase 2) — ONE full REAL whiteboard turn with a SCRIPTED question.
NEVER run in CI.

Drives the same production pipeline as scripts/diag_full_turn.py (real screen
capture → Claude with the Saudi persona → real overlay → real TTS with
MUTHIS_STREAM_TTS honored), but the scripted question asks for a CONCEPT
explained by DRAWING, so the expected flow is the whiteboard:

    pass 0 (auto):  mandatory spoken ack + draw_shapes(dim_screen=true)
                    → the screen fades dark (the board) → neon shapes on top
                    → the ack FED (flush) into the ONE turn generation
    pass 1 (none):  the explanation, sentence-streamed over the dim board
    turn end:       undim_screen fades the lights back on at SPEECH END;
                    the shapes keep their 7 s auto-hide grace, then clear

The temporary [DIAG] probes were REMOVED (2026-07-16, Sultan-approved) —
verify by EYE and EAR plus the printed summary:
  * the dim fades in WITH the draw (before the first audio) and fades out
    at speech end;
  * NO capture ever happens while the screen is dimmed (Claude must never
    see a dimmed screen — the ghosting rule);
  * the process exits 0 (the v7.2 Tcl teardown fix holds with the second
    Toplevel active).

Privacy: the question is a hardcoded script constant; the screenshot goes to
Claude for this turn only, never to disk. Costs ONE real Claude turn
(2 passes) + TTS — budget-gated like production.

Needs in .env: ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
               (GEMINI_API_KEY optional — TTS fallback only).

Run:  .venv\\Scripts\\python.exe scripts\\diag_whiteboard.py
"""

import asyncio
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()  # Law 5.1: .env before any muthis import that reads keys

from muthis.kernel.budget import Budget                                       # noqa: E402
from muthis.cloud.claude_agent import ClaudeAgent, LOOK_SYSTEM_PROMPT  # noqa: E402
from muthis.kernel.orchestrator import Orchestrator                           # noqa: E402
from muthis.overlay import SidekickOverlay                             # noqa: E402
from muthis.persona import resolve_system_prompt                      # noqa: E402
from muthis.tts import TTS                                             # noqa: E402
from muthis.vision.downscale import (                                  # noqa: E402
    DEFAULT_VISION_MAX_WIDTH, compute_scale_factors, downscale_to_max_width,
)
from muthis.vision.screen_capture import (                             # noqa: E402
    ScreenCapture, primary_monitor_size,
)

# A CONCEPT question that no on-screen element answers — the persona's
# whiteboard rule (وضع السبورة) should elicit draw_shapes + dim_screen=true.
SCRIPTED_QUESTION = "اشرح لي على السبورة بالرسم وش الفرق بين الـ RAM والـ Storage؟"

# Long enough to SEE the full choreography: un-dim at speech end, then the
# shapes' 7 s grace, then the auto-hide clears the board's chalk.
POST_TURN_WATCH_SECONDS = 9.0


async def main() -> None:
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
        tts=TTS().speak,
        screen_capture=ScreenCapture().capture,
        downscale=downscale_to_max_width,
        overlay=overlay,
    )

    print("Driving ONE real whiteboard turn — WATCH the dim + chalk, LISTEN...")
    result = await orchestrator.run_turn(SCRIPTED_QUESTION)

    print("\n──────── turn summary ────────")
    print(f"budget_blocked={result.budget_blocked} timed_out={result.timed_out}")
    for call in result.tool_calls:
        print(f"tool={call.name} dim_screen={call.args.get('dim_screen')} "
              f"shapes={len(call.args.get('shapes', []) or [])}")
    print(f"tokens in/out = {result.input_tokens}/{result.output_tokens}  cost={result.cost_usd:.6f} USD")
    print(f"reply: {result.spoken_text}")  # assistant-authored — safe to print

    if result.tool_calls:
        await asyncio.sleep(POST_TURN_WATCH_SECONDS)
    overlay.close()
    await agent.aclose()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic-safe Windows console
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
