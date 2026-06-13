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
wires the Orchestrator with the real mic/STT/TTS/screen-capture seams. The
overlay and the hotkey stay as stubs (not wired here).

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

from muthis.budget import Budget                                    # noqa: E402
from muthis.cloud.claude_agent import ClaudeAgent, LOOK_SYSTEM_PROMPT  # noqa: E402
from muthis.mic import Mic                                          # noqa: E402
from muthis.orchestrator import Orchestrator                        # noqa: E402
from muthis.persona import resolve_system_prompt                    # noqa: E402
from muthis.stt import STT                                          # noqa: E402
from muthis.tts import TTS                                          # noqa: E402
from muthis.vision.screen_capture import ScreenCapture             # noqa: E402


async def main() -> None:
    # Resolve the persona and inject it through the existing seam. If the
    # builder ever returns empty, resolve_system_prompt logs a LOUD English
    # warning and falls back to LOOK_SYSTEM_PROMPT — watch the log for it.
    persona_prompt = resolve_system_prompt(LOOK_SYSTEM_PROMPT)

    agent = ClaudeAgent(system_prompt=persona_prompt)  # reads ANTHROPIC_API_KEY
    await agent.warm_up_tls()  # optional: warm the TLS session before the call

    budget = Budget()
    if not budget.can_afford():
        print("الميزانية اليومية انتهت — جرّب بكرة أو ارفع MUTHIS_DAILY_BUDGET_USD.")
        await agent.aclose()
        return

    mic = Mic()
    orchestrator = Orchestrator(
        reasoner=agent,
        budget=budget,
        mic=mic.record,                          # REAL mic
        stt=STT().transcribe,                    # REAL Scribe STT (Arabic-pinned)
        tts=TTS().speak,                         # REAL TTS (ElevenLabs → Gemini fallback)
        screen_capture=ScreenCapture().capture,  # REAL primary-monitor PNG (DPI-aware)
        # overlay stays a stub → no cyan rectangle drawn yet (overlay phase).
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
