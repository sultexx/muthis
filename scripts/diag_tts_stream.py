# scripts/diag_tts_stream.py
"""
DIAG(v7) — TTS-chunking diagnostic, ISOLATED from Claude. NEVER run in CI.

Drives the exact v5-C2 streaming path — SentenceSplitter → SpeechSession
(ONE persistent ElevenLabs generation, real network + real audio device) —
with a SCRIPTED Arabic reply that contains every boundary pattern suspected
of causing the mid-sentence pauses:

    '.'  ordinary sentence end          (control — should sound natural)
    '؛'  Arabic semicolon               (splits MID-sentence by definition)
    4.1  decimal number                 (the guard — must NOT split)
    ...  ellipsis                       (splits at the FIRST dot)
    \\n   newline                        (splits even mid-logical-sentence)
    ١.   Arabic-Indic list numeral      (emitted as a standalone "sentence")
    >200 chars with NO punctuation      (the safety valve — cuts at an
                                         arbitrary stream-fragment edge)

Fragments are pushed at a realistic Claude cadence (~90 Arabic chars/sec) so
generation-vs-playback races surface as AUDIBLE mid-speech gaps (the
temporary [DIAG] probes that once timestamped them were removed 2026-07-16,
Sultan-approved); this script prints the segmentation summary.

Cost: ONE ElevenLabs generation (~a few hundred characters). Needs in .env:
    ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID   (MUTHIS_STREAM_TTS not required
    here — the session is built directly, mirroring turn_pass._open_streamer).

Run:  .venv\\Scripts\\python.exe scripts\\diag_tts_stream.py
"""

import asyncio
import logging
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()  # Law 5.1: .env before any muthis import that reads keys

from muthis.speech_stream import SENTENCE_ENDERS, SentenceSplitter  # noqa: E402
from muthis.tts import TTS                                          # noqa: E402

# One sentence per suspected boundary pattern (see module docstring). The text
# is a hardcoded diagnostic asset — it is Mut'his-style Arabic, NOT user data.
SCRIPTED_REPLY = (
    "هلا والله، أبشر بالشرح كامل."
    " أول خطوة افتح القائمة؛ وبعدها اختر الإعدادات من تحت."
    " الإصدار 4.1 أسرع من الإصدار 3.9 بشكل واضح."
    " خلني أشوف الشاشة... تمام، وضحت الصورة!"
    "\nنجرب سطر جديد بعد فاصل الأسطر."
    " ١. افتح المشروع من القائمة الرئيسية."
    " وهنا كلام طويل جدا من غير أي علامة ترقيم إطلاقا يمثل شرحا متواصلا "
    "يواصل بلا توقف حتى يتجاوز حد المئتي حرف الذي يفرغ المخزن قسرا عند "
    "حافة عشوائية من حواف البث وليس عند نهاية جملة حقيقية مما يقطع الكلام "
    "في منتصفه تماما ويسبب وقفة غير طبيعية."
)

# Claude streams Arabic at roughly this cadence; pacing the push keeps the
# generation-vs-playback race realistic instead of dumping the text at once.
FRAGMENT_CHARS = 18
FRAGMENT_INTERVAL_S = 0.2


def classify(sentence: str) -> str:
    """English tag for the summary table: which splitter rule emitted this."""
    ender = sentence[-1:]
    if ender not in SENTENCE_ENDERS:
        return "VALVE (200-char run, arbitrary cut)"
    return {".": "dot", "؟": "question", "!": "exclaim",
            "؛": "SEMICOLON (mid-sentence)", "\n": "NEWLINE"}.get(ender, "?")


async def main() -> None:
    session = TTS().open_speech_session()
    if session is None:
        print("Streaming session unavailable (ElevenLabs disabled/unkeyed) — nothing to measure.")
        return

    splitter = SentenceSplitter()
    fed: list[str] = []
    print(f"Feeding {len(SCRIPTED_REPLY)} chars at ~{FRAGMENT_CHARS / FRAGMENT_INTERVAL_S:.0f} chars/s — LISTEN for pauses...")
    start = time.monotonic()
    await session.open()
    try:
        for i in range(0, len(SCRIPTED_REPLY), FRAGMENT_CHARS):
            for sentence in splitter.push(SCRIPTED_REPLY[i:i + FRAGMENT_CHARS]):
                fed.append(sentence)
                await session.feed(sentence)
            await asyncio.sleep(FRAGMENT_INTERVAL_S)
        for sentence in splitter.flush():
            fed.append(sentence)
            await session.feed(sentence)
        await session.close()  # drains the audio tail; raises on failure
    except Exception as exc:  # noqa: BLE001 — diagnostic: report, don't mask
        print(f"SESSION FAILED: {exc!r} (got_audio={session.got_audio})")

    print(f"\n──── segmentation summary ({time.monotonic() - start:.1f}s wall) ────")
    print(f"{len(SCRIPTED_REPLY)} chars → {len(fed)} feeds:")
    for index, sentence in enumerate(fed):
        print(f"  feed[{index}] len={len(sentence):3d} ender={sentence[-1:]!r:6} rule={classify(sentence)}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic-safe Windows console
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
