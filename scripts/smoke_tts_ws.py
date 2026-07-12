# scripts/smoke_tts_ws.py
"""
Manual smoke test — ElevenLabs WebSocket PRIMARY with progressive playback.
Run it yourself with your real .env ELEVENLABS_API_KEY. NEVER run in CI.

It speaks ONE short Arabic sentence through the LIVE ElevenLabs WebSocket and you
should hear smooth, seamless audio start ALMOST IMMEDIATELY (not after the whole
clip). It prints the measured time-to-first-audio so you can compare against the
~436ms diagnostic baseline.

This goes through the real cascade: ElevenLabs primary → Gemini fallback. If you
hear audio but provider != "elevenlabs", the primary fell back (run
diagnose_elevenlabs.py to see why — key/quota/network).

NEVER prints the API key. Uses the same DI seams as production.

    .venv\\Scripts\\python.exe scripts\\smoke_tts_ws.py
    .venv\\Scripts\\python.exe scripts\\smoke_tts_ws.py "النص العربي الذي تريد سماعه"
"""

import asyncio
import logging
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv  # noqa: E402

from muthis.tts import TTS  # noqa: E402
from muthis.tts_ws_player import PcmStreamPlayer  # noqa: E402
from muthis.tts_elevenlabs import DEFAULT_SAMPLE_RATE  # noqa: E402

DEFAULT_SENTENCE = "السلام عليكم، أنا مطحس. جاهز أساعدك في أي وقت."


async def main() -> None:
    load_dotenv()  # standalone script: load .env ourselves (never committed)
    import os
    if not os.getenv("ELEVENLABS_API_KEY"):
        print("🔑 لا يوجد ELEVENLABS_API_KEY في .env — لا يمكن التشغيل.")
        return

    sentence = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SENTENCE

    # A player that timestamps the FIRST audio chunk — the latency we care about.
    timing: dict = {}

    def player_factory():
        player = PcmStreamPlayer(DEFAULT_SAMPLE_RATE)
        original_feed = player.feed

        def timed_feed(pcm):
            if pcm and "first" not in timing:
                timing["first"] = time.perf_counter()
            original_feed(pcm)

        player.feed = timed_feed   # instance-level wrap; never moves real audio
        return player

    tts = TTS(player_factory=player_factory)   # ElevenLabs primary (default ON)

    print(f"🔊 إرسال الجملة عبر ElevenLabs WebSocket: «{sentence}»")
    print("   استمع: يجب أن يبدأ الصوت فوراً تقريباً ويتدفّق بسلاسة...")
    t0 = time.perf_counter()
    result = await tts.speak(sentence)
    total_ms = (time.perf_counter() - t0) * 1000

    if "first" in timing:
        ttfa_ms = (timing["first"] - t0) * 1000
        print(f"🎧 زمن أول بايت صوتي: {ttfa_ms:.0f}ms (الأساس من التشخيص ~436ms).")
    print(f"⏱️  الزمن الكلّي (شمل التشغيل): {total_ms:.0f}ms.")
    print(f"✅ النتيجة: provider={result.provider}, success={result.success}")
    if result.provider != "elevenlabs":
        print("⚠️ لم يُستخدم ElevenLabs (سقط إلى Gemini أو فشل) — "
              "شغّل scripts/diagnose_elevenlabs.py لمعرفة السبب.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Arabic on the Windows console
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nأُلغي.")
    except Exception as e:   # never crash the smoke run
        print(f"\n❌ خطأ غير متوقّع: {type(e).__name__}: {e}")
