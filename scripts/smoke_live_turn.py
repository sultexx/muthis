# scripts/smoke_live_turn.py
"""
Manual smoke test — ONE live PTT turn end to end. NEVER run in CI.

Simulates a single push-to-talk press, then drives the REAL pipeline:
    real mic  →  ElevenLabs Scribe STT (Arabic)
              →  real primary-monitor screen capture (mss + Pillow, DPI-aware)
              →  Claude (claude-sonnet-4-6) WITH the Saudi persona injected
              →  real TTS (ElevenLabs, Gemini voice fallback)
مطحس now SEES the screen each turn. You should HEAR it answer in Saudi dialect.

This is the production composition root in miniature: it resolves the persona
and injects it through ClaudeAgent's EXISTING system_prompt parameter, then
wires the Orchestrator with the real mic/STT/TTS/screen-capture/overlay seams.
Only the hotkey stays a stub (not wired here) — you SEE the cyan rectangle when
مطحس points, and it is hidden before every screenshot so Claude never sees it.

Privacy: the user transcript goes ONLY to Claude, and the screenshot is sent to
Claude for the turn only — never written to disk. This script never prints the
transcript (handle_activation does not even return it); it prints مطحس's own
reply, the tool-call count, token usage, and cost — never the transcript.

Needs in .env:
    ANTHROPIC_API_KEY     (reasoning)
    ELEVENLABS_API_KEY    (STT + primary TTS)
    GEMINI_API_KEY        (optional — TTS voice fallback only)
  optional: MUTHIS_CLAUDE_MODEL, MUTHIS_RECORD_SECONDS, MUTHIS_DAILY_BUDGET_USD

Run:  .venv\\Scripts\\python.exe scripts\\smoke_live_turn.py
"""

import asyncio
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

# Law 5.1: .env loaded once, BEFORE the muthis imports that read keys at
# import/instantiation time.
load_dotenv()

from muthis.kernel.budget import Budget                                    # noqa: E402
from muthis.cloud.claude_agent import ClaudeAgent, LOOK_SYSTEM_PROMPT  # noqa: E402
from muthis.mic import Mic                                          # noqa: E402
from muthis.kernel.orchestrator import Orchestrator                        # noqa: E402
from muthis.persona import resolve_system_prompt                    # noqa: E402
from muthis.stt import STT                                          # noqa: E402
from muthis.tts import TTS                                          # noqa: E402
from muthis.vision.downscale import (                               # noqa: E402
    DEFAULT_VISION_MAX_WIDTH, compute_scale_factors, downscale_to_max_width,
)
from muthis.vision.screen_capture import (                          # noqa: E402
    ScreenCapture, primary_monitor_size,
)
from muthis.overlay import SidekickOverlay                          # noqa: E402


async def main() -> None:
    # Size the persona's coordinate space ONCE at startup: probe the primary
    # monitor's physical resolution (geometry only — no pixels grabbed) and
    # derive the EXACT dims of the downscaled COPY that every turn will send.
    # The resolution is static for the session, so these dims never change and
    # don't need re-injecting per turn. If the probe fails (headless host),
    # fall back to a 16:9 frame at the configured max width.
    physical = primary_monitor_size()
    if physical is not None:
        sent_width, sent_height, _scale_x, _scale_y = compute_scale_factors(
            physical[0], physical[1], DEFAULT_VISION_MAX_WIDTH,
        )
    else:
        sent_width = DEFAULT_VISION_MAX_WIDTH
        sent_height = round(DEFAULT_VISION_MAX_WIDTH * 9 / 16)

    # Resolve the persona (with the sent-image dims) and inject it through the
    # existing seam. If the builder ever returns empty, resolve_system_prompt
    # logs a LOUD English warning and falls back to LOOK_SYSTEM_PROMPT.
    persona_prompt = resolve_system_prompt(LOOK_SYSTEM_PROMPT, sent_width, sent_height)

    agent = ClaudeAgent(system_prompt=persona_prompt)  # reads ANTHROPIC_API_KEY
    await agent.warm_up_tls()  # optional: warm the TLS session before the call

    budget = Budget()
    if not budget.can_afford():
        print("الميزانية اليومية انتهت — جرّب بكرة أو ارفع MUTHIS_DAILY_BUDGET_USD.")
        await agent.aclose()
        return

    mic = Mic()
    overlay = SidekickOverlay()                  # REAL cyan rectangle (DPI-aware, click-through)
    orchestrator = Orchestrator(
        reasoner=agent,
        budget=budget,
        mic=mic.record,                          # REAL mic
        stt=STT().transcribe,                    # REAL Scribe STT (Arabic-pinned)
        tts=TTS().speak,                         # REAL TTS (ElevenLabs → Gemini fallback)
        screen_capture=ScreenCapture().capture,  # REAL primary-monitor PNG (DPI-aware)
        downscale=downscale_to_max_width,        # REAL payload COPY (≤ max width)
        overlay=overlay,                         # REAL overlay (hidden before each capture)
    )

    print(f"محاكاة ضغطة PTT — سجّل {mic.record_seconds:.0f} ثوانٍ. تكلّم بالعربية الآن...")
    result = await orchestrator.handle_activation()

    print("\n──────── ملخص الدورة ────────")
    if result.budget_blocked:
        print("الحالة: رُفضت الدورة (الميزانية مقفلة) — استمع للرسالة الصوتية.")
    elif not result.spoken_text:
        print("الحالة: ما وصل رد من Claude (فشل مايك/تفريغ صوتي؟) — استمع للرسالة الصوتية.")
    else:
        # spoken_text is مطحس's OWN reply (assistant output) — safe to show.
        print(f"رد مطحس: {result.spoken_text}")
    print(f"أدوات مُنفّذة (highlight_target): {len(result.tool_calls)}")
    print(f"التوكنز: إدخال={result.input_tokens} / إخراج={result.output_tokens}")
    print(f"التكلفة: {result.cost_usd:.6f} USD | المتبقي اليوم: {budget.remaining_usd():.4f} USD")
    print(f"انتهت بسبب timeout؟ {result.timed_out}")

    if result.tool_calls:
        # Keep the cyan rectangle on screen briefly so you can SEE where مطحس
        # pointed before we tear the overlay down.
        print("المستطيل معروض الآن — انظر للشاشة... (3 ثوانٍ)")
        await asyncio.sleep(3.0)

    overlay.close()       # stop the overlay's Tk thread
    await agent.aclose()  # release the shared httpx client (composition root owns shutdown)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic on the Windows console
    except Exception:
        pass
    # English pipeline logs (mic/STT/TTS/orchestrator). Transcript is NOT logged
    # unless MUTHIS_DEBUG=1 — keep it off here.
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
