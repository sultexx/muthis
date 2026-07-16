# scripts/diag_interrupt.py
"""
DIAG(v7 Phase 3) — Smart Interruption live test. NEVER run in CI.

Drives ONE real whiteboard turn (the longest audio we produce), waits until
the voice has AUDIBLY played for a while past the mandated 3-second mark,
then fires the production interruption path exactly as a barge-in press
would:  orchestrator.interrupt_turn()  →  turn task cancel — silence FIRST,
cancel SECOND (the approved ordering).

What to verify in the console output (the temporary [DIAG] probes were
removed 2026-07-16, Sultan-approved — the script's own prints remain):
  * signal→silence latency (the printed measurement) is well under 500 ms;
  * the board/shapes/captions vanish INSTANTLY with the overlay hide;
  * turn-voice finish never re-speaks (no buffered-speak lines after abort);
  * the process exits 0 — no orphan task, no Tcl panic, silent player.

Cost: ONE real Claude turn (2 passes) + partial TTS — budget-gated like
production. Needs .env: ANTHROPIC_API_KEY, ELEVENLABS_API_KEY,
ELEVENLABS_VOICE_ID, MUTHIS_STREAM_TTS=1.

Run:  .venv\\Scripts\\python.exe scripts\\diag_interrupt.py
"""

import asyncio
import logging
import pathlib
import sys
import time

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

SCRIPTED_QUESTION = "اشرح لي على السبورة بالرسم وش الفرق بين الـ RAM والـ Storage؟"

MIN_SECONDS_BEFORE_INTERRUPT = 3.0   # the mandate: interrupt at the 3+ s mark
MIN_AUDIBLE_SECONDS = 2.0            # …and only once the voice is truly playing
WAIT_CAP_SECONDS = 60.0


def _played_seconds(orchestrator) -> float:
    """Best-effort read of the live turn's heard-audio clock (diag only)."""
    turn_voice = getattr(orchestrator, "_active_turn_voice", None)
    session = getattr(turn_voice, "_session", None)
    played = getattr(session, "played_seconds", None)
    try:
        return played() if played is not None else 0.0
    except Exception:
        return 0.0


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
        reasoner=agent, budget=budget, tts=TTS().speak,
        screen_capture=ScreenCapture().capture,
        downscale=downscale_to_max_width, overlay=overlay,
    )

    print("Driving ONE whiteboard turn — the INTERRUPT fires once audio is rolling...")
    start = time.monotonic()
    turn_task = asyncio.create_task(orchestrator.run_turn(SCRIPTED_QUESTION))

    # Wait for: past the 3 s mark AND ≥2 s of audio actually heard (cap 60 s).
    while time.monotonic() - start < WAIT_CAP_SECONDS and not turn_task.done():
        elapsed = time.monotonic() - start
        if elapsed >= MIN_SECONDS_BEFORE_INTERRUPT and \
                _played_seconds(orchestrator) >= MIN_AUDIBLE_SECONDS:
            break
        await asyncio.sleep(0.05)

    if turn_task.done():
        print("Turn finished before the interrupt window — rerun (provider was fast).")
        overlay.close()
        await agent.aclose()
        return

    heard = _played_seconds(orchestrator)
    print(f"\n>>> INTERRUPT at t={time.monotonic() - start:.2f}s "
          f"(heard {heard:.2f}s of audio) — silencing…")
    interrupt_t0 = time.monotonic()
    await orchestrator.interrupt_turn()      # silence FIRST …
    silence_t = time.monotonic() - interrupt_t0
    turn_task.cancel()                       # … cancel SECOND
    await asyncio.gather(turn_task, return_exceptions=True)
    teardown_t = time.monotonic() - interrupt_t0

    print(f">>> signal→silence  : {silence_t * 1000:.0f} ms")
    print(f">>> signal→teardown : {teardown_t * 1000:.0f} ms")
    print(">>> Listen: the room must be SILENT and the screen CLEAR now.")
    await asyncio.sleep(2.0)                 # human verification window

    # Prove the pipeline survives: one clean follow-up turn with the
    # interrupted-context note riding it (watch the reply acknowledge nothing
    # was fully heard — and no stale board/captions anywhere).
    print("\nRunning the follow-up turn (carries the interruption note)…")
    result = await orchestrator.run_turn("طيب باختصار، وش أهم فرق واحد؟")
    print(f"follow-up reply: {result.spoken_text}")

    overlay.close()
    await agent.aclose()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic-safe Windows console
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
