# scripts/smoke_stt.py
"""
Manual smoke test — REAL microphone capture + ElevenLabs Scribe STT.
NEVER run in CI.

Loads .env, records MUTHIS_RECORD_SECONDS (default 5 s) from the default
input device, sends the WAV to Scribe (language pinned to Arabic), and
prints the transcript. Speak Arabic clearly while it records.

Needs ELEVENLABS_API_KEY in .env and a working microphone.

Run:  .venv\\Scripts\\python.exe scripts\\smoke_stt.py
"""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()  # BEFORE constructing STT — __init__ reads the key from env

from muthis.mic import Mic  # noqa: E402
from muthis.stt import STT  # noqa: E402


async def main() -> None:
    mic = Mic()
    print(f"تكلم بالعربية الآن — أسجّل {mic.record_seconds:.0f} ثوانٍ...")
    audio = await mic.record()
    if not audio:
        print("فشل التقاط الصوت — تأكد أن المايكروفون موصول وغير مستخدم.")
        return

    print(f"(captured {len(audio)} WAV bytes — transcribing via Scribe...)")
    transcript = await STT().transcribe(audio)
    if transcript:
        print(f"النص: {transcript}")
    else:
        print("لم يصل نص — تحقق من ELEVENLABS_API_KEY أو تكلم أقرب للمايكروفون.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic on Windows console
    except Exception:
        pass
    asyncio.run(main())
