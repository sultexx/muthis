"""
measure_voice_start.py — DEC-160 measurement (C): voice start on `eleven_flash_v2_5`,
text sent → the first audio frame, at the PROVIDER only (no player, no device).

    .venv\\Scripts\\python.exe scripts\\measure_voice_start.py plan    projection only
    .venv\\Scripts\\python.exe scripts\\measure_voice_start.py run

VARIANTS, ten runs each, round-robin:
  settings — `today` (`tts_session.py`: the BOS chunk_length_schedule [90,160,250,290],
             the reply fed with flush + try_trigger_generation, as `speak_or_feed`
             sends a complete reply) · `auto_mode` (the URI's auto_mode=true) ·
             `small_first` (the schedule's first value at 50, the rest unchanged)
  socket   — `cold`: connect + BOS + text, the connect timed apart · `preopened`:
             connected, BOS sent, then 4 s idle before the text — the app ALREADY
             opens the socket at turn start (`kernel/orchestrator.py:199`), about
             that long before B0's first feed
The same fixed sentence every run, diacritized as the app sends it; the app's
voice (ELEVENLABS_VOICE_ID) and default settings (`.env` carries no override).

    .venv\\Scripts\\python.exe scripts\\measure_voice_start.py probe   ONE eleven_v4_turbo call

THE eleven_v4_turbo PROBE (its own 6,000-character share, `latency_common.ROUNDS`):
ElevenLabs documents v4 Turbo on the Text to Dialogue websocket only. The probe asks
the app's stream-input endpoint once, with `language_code=ar`; a variant is added
here only if it is accepted. On 2026-10-29 it was REFUSED at the handshake (HTTP 400
`unsupported_model`), before any text was sent, so it cost no characters.
"""

from __future__ import annotations

import asyncio
import json
import sys

import latency_common as lc

RUNS = 10
IDLE_S = 4.0
SENTENCE = "السنة الكبيسة فيها يوم زيادة، يصير فبراير تسعة وعشرين يوم."
SETTINGS = {"today": ("", (90, 160, 250, 290)),
            "auto_mode": ("&auto_mode=true", (90, 160, 250, 290)),
            "small_first": ("", (50, 160, 250, 290))}
SOCKETS = {"cold": 0.0, "preopened": IDLE_S}


def chars_per_call() -> int:
    from muthis.tts_diacritics import apply_diacritics
    return 1 + len(apply_diacritics(SENTENCE) + " ")


def plan() -> dict:
    calls = RUNS * len(SETTINGS) * len(SOCKETS)
    chars = calls * chars_per_call()
    return {"variants": [f"{s}/{k}" for s in SETTINGS for k in SOCKETS], "runs": RUNS,
            "calls": calls, "chars_per_call": chars_per_call(), "projected_chars": chars,
            "projected_usd": round(chars * lc.TTS_USD_PER_CHAR, 4), "share": lc.SHARES["voice_start"]}


async def probe() -> int:
    """ONE call: eleven_v4_turbo with language_code=ar on the app's stream-input endpoint."""
    lc.console()
    api_key, voice = lc.key("ELEVENLABS_API_KEY"), lc.key("ELEVENLABS_VOICE_ID")
    spend, before, folder = lc.Spend("v4_turbo"), lc.log_guard(), lc.results_dir("v4-probe")
    spend.allow(usd=chars_per_call() * lc.TTS_USD_PER_CHAR, chars=chars_per_call())
    row = await lc.tts_generate(api_key, lc.tts_uri(voice, extra="&language_code=ar", model=lc.V4_TURBO),
                                SENTENCE)
    spend.add(usd=row["chars_sent"] * lc.TTS_USD_PER_CHAR, chars=row["chars_sent"])
    verdict = {"model": lc.V4_TURBO, "uri_extra": "&language_code=ar",
               "accepted": not row["error"] and row["audio_ms"] > 0,
               **{k: row.get(k) for k in ("error", "rejected", "close", "first_audio_ms", "chars_sent")}}
    out = lc.write(folder, "probe.json", {"schema": "v4-probe/1", "created_utc": lc.utc_stamp(),
                                          "verdict": verdict, "spend": spend.as_dict(),
                                          "durable_log_changes": lc.log_changes(before)})
    print(json.dumps(verdict, ensure_ascii=False, indent=1) + f"\nrecord {out}")
    return 0


async def run() -> int:
    lc.console()
    api_key, voice = lc.key("ELEVENLABS_API_KEY"), lc.key("ELEVENLABS_VOICE_ID")
    spend, rows, per_call = lc.Spend("voice_start"), [], chars_per_call()
    before, folder = lc.log_guard(), lc.results_dir("voice-start")
    print(json.dumps(plan(), indent=1))
    for rep in range(1, RUNS + 1):
        for setting, (extra, schedule) in SETTINGS.items():
            for socket, idle in SOCKETS.items():
                spend.allow(usd=per_call * lc.TTS_USD_PER_CHAR, chars=per_call)
                row = await lc.tts_generate(api_key, lc.tts_uri(voice, extra=extra), SENTENCE,
                                            schedule=schedule, idle_s=idle)
                spend.add(usd=row["chars_sent"] * lc.TTS_USD_PER_CHAR, chars=row["chars_sent"])
                if socket == "cold" and row.get("first_audio_ms") is not None:
                    row["connect_plus_first_audio_ms"] = row["connect_ms"] + row["first_audio_ms"]
                rows.append({"setting": setting, "socket": socket, "rep": rep, **row})
                print(f"{setting:11} {socket:9} rep {rep:2}: first audio {row.get('first_audio_ms') or 0:6.0f} ms"
                      f" (connect {row.get('connect_ms') or 0:5.0f}, first chunk "
                      f"{row.get('first_chunk_ms_of_audio') or 0:5.0f} ms of audio) {row['error'] or ''}")
    keys = ("first_audio_ms", "connect_ms", "connect_plus_first_audio_ms", "first_chunk_ms_of_audio",
            "final_ms", "audio_ms")
    summary = {f"{s}/{k}": {key: lc.stats([r.get(key) for r in rows
                                           if r["setting"] == s and r["socket"] == k and not r["error"]])
                            for key in keys} | {"errors": sum(1 for r in rows if r["setting"] == s
                                                              and r["socket"] == k and r["error"])}
               for s in SETTINGS for k in SOCKETS}
    out = lc.write(folder, "voice_start.json", {
        "schema": "latency-voice-start/1", "created_utc": lc.utc_stamp(), "plan": plan(),
        "sentence_chars": len(SENTENCE), "summary": summary, "rows": rows, "spend": spend.as_dict(),
        "durable_log_changes": lc.log_changes(before)})
    print(f"\nspend {spend.chars} characters (${spend.usd:.4f}); record {out}")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["plan"]:
        print(json.dumps(plan(), indent=1))
        sys.exit(0)
    runner = {"run": run, "probe": probe}.get(sys.argv[1] if sys.argv[1:] else "")
    sys.exit(asyncio.run(runner()) if runner else print(__doc__) or 2)
