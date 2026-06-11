# scripts/smoke_tts.py
"""
Manual smoke test — REAL ElevenLabs Arabic audio. NEVER run in CI.

Loads .env (ELEVENLABS_API_KEY), then speaks one Arabic sentence through the
real cascade (ElevenLabs WS → SAPI → pyttsx3) and prints the TTSResult.
Without a key it must still degrade to local TTS — no crash.

Run:  .venv\\Scripts\\python.exe scripts\\smoke_tts.py
"""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()  # BEFORE constructing TTS — __init__ reads the key from env

from muthis.tts import TTS  # noqa: E402  (import after .env on purpose)

SMOKE_TEXT_AR = "مرحباً! أنا مُذهِل، مساعدك الصوتي. هذا اختبار للنطق العربي الحقيقي."

if __name__ == "__main__":
    result = asyncio.run(TTS().speak(SMOKE_TEXT_AR))
    print(f"TTSResult: success={result.success} provider={result.provider}"
          + (f" error={result.error}" if result.error else ""))
