# scripts/diag_pedagogy.py
"""
DIAG(v7 Phase 4) — ONE full REAL Pedagogical-Analyzer turn with a SCRIPTED
question. NEVER run in CI.

Drives the same production pipeline as scripts/diag_whiteboard.py (real screen
capture → Claude with the Saudi persona → real overlay → real TTS with
MUTHIS_STREAM_TTS honored) PLUS the Phase 4 read_local_file seam. The script
opens the bundled ESP32 sample (assets/samples/esp32_logic.ino) in Notepad so
the code is VISIBLE on screen, then asks Mut'his to explain that exact file.

Expected flow (the persona's mandatory pedagogy method):

    pass 0 (auto):  read_local_file(path=...) → the tool_result carries the
                    REAL numbered file content
    pass 1 (auto):  mandatory spoken ack + ONE draw_shapes(dim_screen=true)
                    with rectangles around the analyzed lines → the screen
                    fades dark and the framed lines glow isolated
    pass 2 (none):  the line-by-line audio explanation over the dim board
    turn end:       lights back at speech end; shapes keep the 7 s grace

Verify by EYE and EAR plus the printed summary below:
  * the read fired with the sample's path (printed by the logging wrapper);
  * the whiteboard dimmed WITH the boxes (before the explanation audio);
  * the explanation cites line numbers / the actual identifiers (LIMIT_C,
    readCelsius) — proof it read the FILE, not the pixels;
  * the process exits 0 (Tk teardown clean).

Privacy: the question is a hardcoded script constant; the screenshot goes to
Claude for this turn only, never to disk. Costs ONE real Claude turn
(3 passes) + TTS — budget-gated like production.

Needs in .env: ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
               (GEMINI_API_KEY optional — TTS fallback only).

Run:  .venv\\Scripts\\python.exe scripts\\diag_pedagogy.py
"""

import asyncio
import logging
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()  # Law 5.1: .env before any muthis import that reads keys

from muthis.budget import Budget                                       # noqa: E402
from muthis.cloud.claude_agent import ClaudeAgent, LOOK_SYSTEM_PROMPT  # noqa: E402
from muthis.file_reader import FileReader                              # noqa: E402
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

# The sample lives in an esp32_logic/ sketch folder (the Arduino IDE moved it
# there on first open — sketches must sit in a folder named after the .ino).
SAMPLE = (pathlib.Path(__file__).resolve().parents[1]
          / "assets" / "samples" / "esp32_logic" / "esp32_logic.ino")

# The path is spoken INSIDE the scripted question (as a user would name the
# file they are looking at) so read_local_file has an exact target.
SCRIPTED_QUESTION = (
    f"يا مطحس، افتحت قدامي ملف {SAMPLE} على الشاشة — "
    "اقرأه واشرح لي منطقه."
)

# Long enough to SEE the choreography: un-dim at speech end, then the shapes'
# 7 s grace, then the auto-hide clears the boxes.
POST_TURN_WATCH_SECONDS = 9.0

# Notepad needs a beat to open and settle before the screen capture.
NOTEPAD_SETTLE_SECONDS = 2.5


def _logged_reader():
    """The REAL FileReader wrapped so the console shows the read firing
    (path + returned length only — never the content)."""
    real = FileReader()

    async def read(args):
        print(f">>> read_local_file fired: path={args.get('path')!r} "
              f"range={args.get('start_line')}-{args.get('end_line')}")
        content = await real.read(args)
        print(f">>> read_local_file returned {len(content)} chars")
        return content

    return read


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

    print(f"Opening the sample in Notepad: {SAMPLE}")
    notepad = subprocess.Popen(["notepad.exe", str(SAMPLE)])
    await asyncio.sleep(NOTEPAD_SETTLE_SECONDS)

    overlay = SidekickOverlay()
    orchestrator = Orchestrator(
        reasoner=agent,
        budget=budget,
        tts=TTS().speak,
        screen_capture=ScreenCapture().capture,
        downscale=downscale_to_max_width,
        overlay=overlay,
        read_file=_logged_reader(),
    )

    print("Driving ONE real pedagogy turn — WATCH the dim + boxes, LISTEN...")
    try:
        result = await orchestrator.run_turn(SCRIPTED_QUESTION)

        print("\n──────── turn summary ────────")
        print(f"budget_blocked={result.budget_blocked} timed_out={result.timed_out}")
        for call in result.tool_calls:
            extra = ""
            if call.name == "read_local_file":
                extra = f" path={call.args.get('path')!r}"
            elif call.name == "draw_shapes":
                shapes = call.args.get("shapes", []) or []
                kinds = ",".join(s.get("kind", "?") for s in shapes)
                extra = f" dim_screen={call.args.get('dim_screen')} shapes=[{kinds}]"
            print(f"tool={call.name}{extra}")
        print(f"tokens in/out = {result.input_tokens}/{result.output_tokens}  "
              f"cost={result.cost_usd:.6f} USD")
        print(f"reply: {result.spoken_text}")  # assistant-authored — safe to print

        names = [call.name for call in result.tool_calls]
        dimmed = any(call.name == "draw_shapes" and call.args.get("dim_screen")
                     for call in result.tool_calls)
        print("\n──────── pedagogy checklist ────────")
        print(f"read_local_file called : {'PASS' if 'read_local_file' in names else 'FAIL'}")
        print(f"whiteboard (dim) drawn : {'PASS' if dimmed else 'FAIL'}")
        print(f"explanation spoken     : {'PASS' if result.spoken_text.strip() else 'FAIL'}")

        if result.tool_calls:
            await asyncio.sleep(POST_TURN_WATCH_SECONDS)
    finally:
        overlay.close()
        await agent.aclose()
        notepad.terminate()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic-safe Windows console
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
