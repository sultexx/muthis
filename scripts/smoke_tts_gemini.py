# scripts/smoke_tts_gemini.py
"""
Manual smoke test — REAL Gemini TTS Arabic audio (the fallback path).
NEVER run in CI.

Loads .env, then DELIBERATELY drops ELEVENLABS_API_KEY from the process
environment so the cascade is forced onto the Gemini fallback. You should
hear an intelligent Arabic voice (not robotic SAPI — that path is gone)
and see provider=gemini printed.

Needs GEMINI_API_KEY in .env. Without it the cascade reports
provider=none — no crash (that is also worth seeing once).

Run:  .venv\\Scripts\\python.exe scripts\\smoke_tts_gemini.py
"""

import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()  # BEFORE constructing TTS — __init__ reads keys from env

# Force the fallback: pretend ElevenLabs is unkeyed for this process only.
os.environ.pop("ELEVENLABS_API_KEY", None)

from muthis.tts import TTS  # noqa: E402  (import after .env on purpose)

SMOKE_TEXT_AR = "مرحباً! أنا مُذهِل، وهذا صوت Gemini الاحتياطي. أتكلم العربية بطلاقة."

if __name__ == "__main__":
    result = asyncio.run(TTS().speak(SMOKE_TEXT_AR))
    print(f"TTSResult: success={result.success} provider={result.provider}"
          + (f" error={result.error}" if result.error else ""))
    if result.provider != "gemini":
        print("EXPECTED provider=gemini — check GEMINI_API_KEY in .env "
              "(or GEMINI_TTS_MODEL if the preview id rotated).")
