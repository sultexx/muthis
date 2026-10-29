"""
tts_numbers_ab.py — the BY-EAR number test (DEC-159 ⑥, DEC-160), for Sultan to run
himself. Twelve fixed Arabic sentences that carry numbers, spoken by the app's voice
on `eleven_flash_v2_5`, scored blind.

    .venv\\Scripts\\python.exe scripts\\tts_numbers_ab.py plan     the table and the projection
    .venv\\Scripts\\python.exe scripts\\tts_numbers_ab.py probe    ONE call each for arms B and D
    .venv\\Scripts\\python.exe scripts\\tts_numbers_ab.py run      generate, listen, score, reveal

ARMS — the text and the URI are the only things that change:
  A  as-is: digits as the model writes them, Western AND Arabic-Indic
  B  provider normalization: `apply_text_normalization=on`, on the same digits —
     ONLY if its probe call is accepted (ElevenLabs' models page: off by default on
     Flash v2.5, enterprise-only to enable)
  C  a kernel normalizer: the same sentences with the numbers written in WORDS
     (hand-written below — Sultan reviews that column with `plan` before running)
  D  `language_code=ar`, on the same digits
Each item is generated TWICE (the provider is not deterministic). Every take is
then played once, in one random order, with its written reference on screen and its
arm hidden: 1 correct · 2 understandable but off · 3 garbled (r replays). Only then
are the arms revealed. Each take's latency — text sent → first audio frame, on a
cold socket — is recorded, with the characters each arm bills.
Clips and scores stay in `~/Desktop/muthis_voice/results/numbers-ab-<stamp>/`.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import sys
import wave

import latency_common as lc

TAKES = 2
CAP_CHARS = 15_000
SENTENCES = (  # (written with Western digits, the same sentence in words)
    ("السنة الكبيسة فيها 366 يوم.", "السنة الكبيسة فيها ثلاثمية وستة وستين يوم."),
    ("نزل الإصدار سنة 2024.", "نزل الإصدار سنة ألفين وأربعة وعشرين."),
    ("آخر إصدار من بايثون هو 3.13.", "آخر إصدار من بايثون هو ثلاثة نقطة ثلاثة عشر."),
    ("شوف السطر 12.", "شوف السطر اثنا عشر."),
    ("نسبة النجاح 85%.", "نسبة النجاح خمسة وثمانين بالمية."),
    ("الاجتماع الساعة 10:30.", "الاجتماع الساعة عشر ونص."),
    ("الموعد يوم 29/10/2026.", "الموعد يوم تسعة وعشرين شهر عشرة ألفين وستة وعشرين."),
    ("السعر 1,250 ريال.", "السعر ألف ومتين وخمسين ريال."),
    ("خله في حدود 40-60 كلمة.", "خله في حدود أربعين إلى ستين كلمة."),
    ("رقم الجوال 0551234567.", "رقم الجوال صفر خمسة خمسة واحد اثنين ثلاثة أربعة خمسة ستة سبعة."),
    ("قيمة باي تقريبًا 3.14.", "قيمة باي تقريبًا ثلاثة فاصلة واحد أربعة."),
    ("عندك 3 أخطاء في الكود.", "عندك ثلاث أخطاء في الكود."),
)
ARMS = {"A": "", "B": "&apply_text_normalization=on", "C": "", "D": "&language_code=ar"}


def to_indic(text: str) -> str:
    """The Arabic-Indic writing of a Western-digit sentence: digits, and the
    decimal, thousands and percent signs that sit inside a number."""
    text = re.sub(r"(?<=\d)\.(?=\d)", "٫", text)
    text = re.sub(r"(?<=\d),(?=\d)", "٬", text).replace("%", "٪")
    return text.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def items(arms) -> list[dict]:
    """Every (arm, sentence, script) the run generates — words have one script."""
    out = []
    for number, (digits, words) in enumerate(SENTENCES, 1):
        for arm in arms:
            forms = [("words", words)] if arm == "C" else [("western", digits), ("indic", to_indic(digits))]
            out += [{"arm": arm, "sentence": number, "script": s, "text": t, "reference": digits}
                    for s, t in forms]
    return out


def chars(text: str) -> int:
    from muthis.tts_diacritics import apply_diacritics
    return 1 + len(apply_diacritics(text) + " ")


def plan(arms=("A", "B", "C", "D")) -> dict:
    total = TAKES * sum(chars(i["text"]) for i in items(arms))
    return {"arms": list(arms), "takes": TAKES, "generations": TAKES * len(items(arms)),
            "projected_chars": total, "projected_usd": round(total * lc.TTS_USD_PER_CHAR, 4),
            "cap_chars": CAP_CHARS}


async def probe(api_key: str, voice: str, spend: lc.Spend) -> dict:
    """ONE call per optional arm: accepted means audio came back with no error."""
    verdicts = {}
    for arm in ("B", "D"):
        text = SENTENCES[0][0]
        spend.allow(usd=chars(text) * lc.TTS_USD_PER_CHAR, chars=chars(text))
        row = await lc.tts_generate(api_key, lc.tts_uri(voice, extra=ARMS[arm]), text)
        spend.add(usd=row["chars_sent"] * lc.TTS_USD_PER_CHAR, chars=row["chars_sent"])
        verdicts[arm] = {"accepted": not row["error"] and row["audio_ms"] > 0, "error": row["error"],
                         "close": row.get("close"), "first_audio_ms": row.get("first_audio_ms")}
    return verdicts


def play(pcm: bytes) -> None:
    import numpy
    import sounddevice
    sounddevice.play(numpy.frombuffer(pcm, dtype=numpy.int16), samplerate=22050)
    sounddevice.wait()


async def run() -> int:
    lc.console()
    api_key, voice = lc.key("ELEVENLABS_API_KEY"), lc.key("ELEVENLABS_VOICE_ID")
    folder, before = lc.results_dir("numbers-ab"), lc.log_guard()
    verdicts = await probe(api_key, voice, lc.Spend("numbers_probe"))
    arms = [a for a in ARMS if a in ("A", "C") or verdicts[a]["accepted"]]
    projection = plan(arms)
    print(json.dumps({"probe": verdicts, **projection}, ensure_ascii=False, indent=1))
    if projection["projected_chars"] > CAP_CHARS:
        print("STOPPED: the projection is over the character cap")
        return 2
    input("Press Enter to generate every take (nothing plays yet). ")
    takes, billed = [], {a: 0 for a in arms}
    for item in items(arms):
        for take in range(1, TAKES + 1):
            row = await lc.tts_generate(api_key, lc.tts_uri(voice, extra=ARMS[item["arm"]]),
                                        item["text"], keep_audio=True)
            billed[item["arm"]] += row["chars_sent"]
            pcm = row.pop("pcm", b"")
            name = f"{item['arm']}-{item['sentence']:02}-{item['script']}-{take}.wav"
            with wave.open(str(lc.voice_drive._outside_repo(folder / name)), "wb") as w:
                w.setnchannels(1), w.setsampwidth(2), w.setframerate(22050), w.writeframes(pcm)
            takes.append({**item, "take": take, "file": name, "pcm": pcm, **row})
            print(f"  generated {len(takes)}: first audio {row.get('first_audio_ms') or 0:5.0f} ms "
                  f"{row['error'] or ''}")
    order = list(range(len(takes)))
    random.shuffle(order)
    print("\nBlind listening. 1 = correct · 2 = understandable but off · 3 = garbled · r = replay")
    for position, index in enumerate(order, 1):
        take = takes[index]
        print(f"\n[{position}/{len(order)}] the reference: {take['reference']}")
        answer = "r"
        while answer == "r":
            play(take["pcm"])
            answer = input("  score (1/2/3, r): ").strip().lower()
            while answer not in ("1", "2", "3", "r"):
                answer = input("  1, 2, 3 or r: ").strip().lower()
        take["score"] = int(answer)
    reveal = {}
    for arm in arms:
        mine = [t for t in takes if t["arm"] == arm]
        reveal[arm] = {"scores": {s: sum(t["score"] == s for t in mine) for s in (1, 2, 3)},
                       "by_script": {sc: {s: sum(t["score"] == s for t in mine if t["script"] == sc)
                                          for s in (1, 2, 3)} for sc in sorted({t["script"] for t in mine})},
                       "first_audio_ms": lc.stats([t.get("first_audio_ms") for t in mine]),
                       "chars_billed": billed[arm]}
    for take in takes:
        take.pop("pcm", None)
    out = lc.write(folder, "numbers_ab.json", {
        "schema": "numbers-ab/1", "created_utc": lc.utc_stamp(), "probe": verdicts, "plan": projection,
        "reveal": reveal, "takes": takes, "durable_log_changes": lc.log_changes(before)})
    print("\n" + json.dumps(reveal, ensure_ascii=False, indent=1) + f"\nrecord {out}")
    return 0


async def probe_only() -> int:
    lc.console()
    spend, folder, before = lc.Spend("numbers_probe"), lc.results_dir("numbers-probe"), lc.log_guard()
    verdicts = await probe(lc.key("ELEVENLABS_API_KEY"), lc.key("ELEVENLABS_VOICE_ID"), spend)
    out = lc.write(folder, "probe.json", {"schema": "numbers-probe/1", "created_utc": lc.utc_stamp(),
                                          "verdicts": verdicts, "spend": spend.as_dict(),
                                          "durable_log_changes": lc.log_changes(before)})
    print(json.dumps(verdicts, ensure_ascii=False, indent=1) + f"\nrecord {out}")
    return 0


if __name__ == "__main__":
    command = sys.argv[1:2]
    if command == ["plan"]:
        for digits, words in SENTENCES:
            print(f"{digits}  |  {to_indic(digits)}  |  {words}")
        print(json.dumps(plan(), indent=1))
        sys.exit(0)
    runner = {"probe": probe_only, "run": run}.get(command[0] if command else "")
    sys.exit(asyncio.run(runner()) if runner else print(__doc__) or 2)
