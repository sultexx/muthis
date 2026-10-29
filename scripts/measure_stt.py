"""
measure_stt.py — DEC-160 measurement (B): realtime transcription with Arabic. The
four B0 clips through `scribe_v2_realtime`, paced in REAL time, against the app's
own batch path on the same clips — ten runs each, interleaved.

    .venv\\Scripts\\python.exe scripts\\measure_stt.py plan    projection only, no call
    .venv\\Scripts\\python.exe scripts\\measure_stt.py run

REALTIME: the socket and its `session_started` come FIRST (in the app they would
open while F9 is held), then the clip's PCM goes out in 100 ms chunks on the clock,
the last one with `commit: true` (manual commit: the release). Measured: the last
chunk sent → `committed_transcript`. Also kept: the connect time and the first
partial, from the first chunk.
BATCH: `stt.STT._scribe_request`, the app's own request (a new connection per call,
`stt.py:91`), timed from the call to the text; the app makes it after the release.
MATCH, NEVER TEXT: each transcript is compared with the phrase B0 recorded
(`voice_b0.PLAN`) on `verbosity.normalize_ar` copies — `match` when equal, `near`
when difflib's ratio is ≥ NEAR (fixed before any run), `miss` below it, `empty` or
`failed` otherwise. Nothing else about the words is printed or stored.
Sultan authorised sending these clips; DEC-159 ⑦ records the provider's default
retention, the same on both paths (neither sends `enable_logging`).

    .venv\\Scripts\\python.exe scripts\\measure_stt.py transcripts

TRANSCRIPTS — the one exception to "never text", and only on the CONSOLE. The four
clips are scripted test phrases Sultan recorded for this purpose, and he authorised
printing their transcripts to explain the realtime miss on the search clip. One
realtime and one batch transcription per clip; each is printed beside the phrase,
with both normalised forms and the tokens that differ. The record file keeps the
classes and ratios, never the words.
"""

from __future__ import annotations

import asyncio
import base64
import difflib
import json
import sys
import time
import wave

import latency_common as lc

RUNS = 10
NEAR = 0.80
CHUNK_S = 0.1
REALTIME_URL = ("wss://api.elevenlabs.io/v1/speech-to-text/realtime?model_id=scribe_v2_realtime"
                "&language_code=ar&audio_format=pcm_16000&commit_strategy=manual")
USD_PER_HOUR = {"batch": 0.22, "realtime": 0.39}      # ElevenLabs API pricing, 2026-10-29
ERRORS = {"error", "auth_error", "quota_exceeded", "commit_throttled", "unaccepted_terms",
          "rate_limited", "queue_overflow", "resource_exhausted", "session_time_limit_exceeded",
          "input_error", "invalid_request", "chunk_size_exceeded", "insufficient_audio_activity",
          "transcriber_error"}


def match(transcript: str | None, phrase: str) -> str:
    """The ONLY thing a transcript leaves behind: its class against the phrase."""
    from muthis.kernel.verbosity import normalize_ar
    if transcript is None:
        return "failed"
    heard, said = normalize_ar(transcript), normalize_ar(phrase)
    if not heard:
        return "empty"
    if heard == said:
        return "match"
    return "near" if difflib.SequenceMatcher(None, heard, said).ratio() >= NEAR else "miss"


def clips() -> list[tuple[str, str, bytes, bytes, float]]:
    """(scenario, phrase, wav, pcm, seconds) for B0's four clips."""
    from voice_b0 import PLAN
    out = []
    for scenario in PLAN:
        path = lc.voice_drive.CLIP_HOME / f"{scenario.clip}.wav"
        with wave.open(str(path), "rb") as w:
            pcm, seconds = w.readframes(w.getnframes()), w.getnframes() / w.getframerate()
        out.append((scenario.name, scenario.phrase, path.read_bytes(), pcm, seconds))
    return out


async def realtime(api_key: str, pcm: bytes, phrase: str, keep_text: bool = False) -> dict:
    import websockets
    row: dict = {"path": "realtime", "error": None}
    step = int(16000 * 2 * CHUNK_S)
    pieces = [pcm[i:i + step] for i in range(0, len(pcm), step)]
    started = time.perf_counter()
    text = None
    try:
        async with websockets.connect(REALTIME_URL, additional_headers={"xi-api-key": api_key},
                                      open_timeout=10.0) as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=10.0))
            row["connect_ms"] = (time.perf_counter() - started) * 1000
            if hello.get("message_type") != "session_started":
                raise RuntimeError(f"no session: {hello.get('message_type')}")
            first_partial = committed = None

            async def reader():
                nonlocal first_partial, committed, text
                async for message in ws:
                    data = json.loads(message)
                    kind = data.get("message_type")
                    if kind == "partial_transcript" and first_partial is None and data.get("text"):
                        first_partial = time.perf_counter()
                    elif kind == "committed_transcript":
                        committed, text = time.perf_counter(), data.get("text") or ""
                        return
                    elif kind in ERRORS:
                        row["error"] = kind
                        return
            task = asyncio.create_task(reader())
            t_audio = time.perf_counter()
            for i, piece in enumerate(pieces):
                await asyncio.sleep(max(0.0, t_audio + i * CHUNK_S - time.perf_counter()))
                await ws.send(json.dumps({"message_type": "input_audio_chunk", "sample_rate": 16000,
                                          "audio_base_64": base64.b64encode(piece).decode("ascii"),
                                          "commit": i == len(pieces) - 1}))
            t_end = time.perf_counter()
            await asyncio.wait_for(task, timeout=15.0)
            row["end_of_audio_to_committed_ms"] = (committed - t_end) * 1000 if committed else None
            row["first_partial_from_audio_start_ms"] = ((first_partial - t_audio) * 1000
                                                        if first_partial else None)
    except Exception as exc:  # noqa: BLE001 — recorded by type
        row["error"] = row["error"] or type(exc).__name__
    row["session_s"] = time.perf_counter() - started
    row["match"] = match(text, phrase) if not row["error"] else "failed"
    if keep_text:          # `transcripts` only: printed to the console, never written
        row["text"] = text
    return row


async def batch(api_key: str, wav: bytes, phrase: str, keep_text: bool = False) -> dict:
    from muthis.stt import STT
    row: dict = {"path": "batch", "error": None}
    started = time.perf_counter()
    text = None
    try:
        text = await STT(api_key=api_key)._scribe_request(wav)
    except Exception as exc:  # noqa: BLE001 — the class and status, never the body
        response = getattr(exc, "response", None)
        row["error"] = {"type": type(exc).__name__, "status": getattr(response, "status_code", None)}
    row["request_to_text_ms"] = (time.perf_counter() - started) * 1000
    row["match"] = match(text, phrase) if not row["error"] else "failed"
    if keep_text:
        row["text"] = text
    return row


def ratio(transcript: str | None, phrase: str) -> float:
    from muthis.kernel.verbosity import normalize_ar
    return round(difflib.SequenceMatcher(None, normalize_ar(transcript or ""), normalize_ar(phrase)).ratio(), 3)


async def transcripts() -> int:
    """One batch + one realtime transcription per clip, PRINTED; the record keeps no words."""
    from muthis.kernel.verbosity import normalize_ar
    lc.console()
    api_key, material, kept = lc.key("ELEVENLABS_API_KEY"), clips(), []
    spend, before, folder = lc.Spend("transcripts"), lc.log_guard(), lc.results_dir("stt-transcripts")
    for scenario, phrase, wav, pcm, seconds in material:
        said = normalize_ar(phrase)
        print(f"\n=== {scenario} ({seconds:.2f} s of audio)\n  phrase        {phrase}\n  phrase, norm  {said}")
        for path in ("batch", "realtime"):
            spend.allow(usd=(seconds + 5.0) * USD_PER_HOUR[path] / 3600)
            row = await (batch(api_key, wav, phrase, keep_text=True) if path == "batch"
                         else realtime(api_key, pcm, phrase, keep_text=True))
            spend.add(usd=row.get("session_s", seconds) * USD_PER_HOUR[path] / 3600)
            text = row.pop("text", None)
            heard = normalize_ar(text or "")
            print(f"  {path:13} {text!r}\n  {path + ', norm':13} {heard}\n"
                  f"  {'':13} class {row['match']} · ratio {ratio(text, phrase)} · heard, not said "
                  f"{[t for t in heard.split() if t not in said.split()]} · said, not heard "
                  f"{[t for t in said.split() if t not in heard.split()]} · Latin letters "
                  f"{any('a' <= c.lower() <= 'z' for c in text or '')}"
                  f"{'  ERROR ' + str(row['error']) if row['error'] else ''}")
            kept.append({"scenario": scenario, "path": path, "match": row["match"],
                         "ratio": ratio(text, phrase), "error": row["error"]})
    out = lc.write(folder, "transcripts.json", {
        "schema": "stt-transcripts/1", "created_utc": lc.utc_stamp(), "rows": kept,
        "note": "transcripts were printed to the console only; no words are stored here",
        "spend": spend.as_dict(), "durable_log_changes": lc.log_changes(before)})
    print(f"\nspend ${spend.usd:.4f}; record {out}")
    return 0


def plan() -> dict:
    audio = sum(c[4] for c in clips())
    session = audio + 4 * 3.0                     # worst: each realtime session ~3 s past its audio
    usd = RUNS * (audio * USD_PER_HOUR["batch"] + session * USD_PER_HOUR["realtime"]) / 3600
    return {"clips": [c[0] for c in clips()], "clip_seconds": round(audio, 2), "runs": RUNS,
            "transcriptions": RUNS * 4 * 2, "projected_usd": round(usd, 4),
            "share_usd": lc.SHARES["stt"][0], "near_threshold": NEAR}


async def run() -> int:
    lc.console()
    api_key, material = lc.key("ELEVENLABS_API_KEY"), clips()
    spend, rows = lc.Spend("stt"), []
    before, folder = lc.log_guard(), lc.results_dir("stt")
    print(json.dumps(plan(), indent=1))
    for rep in range(1, RUNS + 1):
        for scenario, phrase, wav, pcm, seconds in material:
            for path in ("batch", "realtime"):
                worst = (seconds + 5.0) * USD_PER_HOUR[path] / 3600
                spend.allow(usd=worst)
                row = await (batch(api_key, wav, phrase) if path == "batch"
                             else realtime(api_key, pcm, phrase))
                billed = row.get("session_s", seconds) if path == "realtime" else seconds
                spend.add(usd=billed * USD_PER_HOUR[path] / 3600)
                rows.append({"scenario": scenario, "rep": rep, **row})
                metric = row.get("end_of_audio_to_committed_ms") or row.get("request_to_text_ms") or 0
                print(f"{scenario:9} rep {rep:2} {path:8}: {metric:6.0f} ms  {row['match']}"
                      f"{'  ' + str(row['error']) if row['error'] else ''}")
    summary = {}
    for scenario, *_ in material:
        for path, metric in (("batch", "request_to_text_ms"), ("realtime", "end_of_audio_to_committed_ms")):
            mine = [r for r in rows if r["scenario"] == scenario and r["path"] == path]
            summary[f"{scenario}/{path}"] = {
                "latency_ms": lc.stats([r.get(metric) for r in mine if not r["error"]]),
                "classes": {c: sum(r["match"] == c for r in mine) for c in
                            ("match", "near", "miss", "empty", "failed")},
                **({"connect_ms": lc.stats([r.get("connect_ms") for r in mine]),
                    "first_partial_ms": lc.stats([r.get("first_partial_from_audio_start_ms") for r in mine])}
                   if path == "realtime" else {})}
    out = lc.write(folder, "stt.json", {
        "schema": "latency-stt/1", "created_utc": lc.utc_stamp(), "plan": plan(), "summary": summary,
        "rows": rows, "spend": spend.as_dict(), "durable_log_changes": lc.log_changes(before)})
    print(f"\nspend ${spend.usd:.4f} (estimated from the published hourly rates); record {out}")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["plan"]:
        print(json.dumps(plan(), indent=1))
        sys.exit(0)
    runner = {"run": run, "transcripts": transcripts}.get(sys.argv[1] if sys.argv[1:] else "")
    sys.exit(asyncio.run(runner()) if runner else print(__doc__) or 2)
