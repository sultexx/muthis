"""
latency_common.py — what DEC-160's standalone latency measurements share:
results OUTSIDE the repository, keys read from `.env` by `dotenv_values` (never
placed in os.environ, never printed), the console logging posture, spend caps
that fail CLOSED, the statistics, and the one ElevenLabs generation the voice
and number measurements both time.

NEVER THE DURABLE LOG: no `configure_logging`, no `muthis.main`, no file handler
(`tests/test_no_script_attaches_the_durable_log.py`), and each measurement
snapshots `~/.muthis/logs` before and after (`harness.prodlog`) and records any
change. Nothing here imports the app's composition root.

THE CAPS ARE THE BRIEF'S, SPLIT IN ADVANCE (DEC-160): $0.50 of provider spend and
15,000 ElevenLabs characters across every measurement of the round. Each script
holds its own SHARE, and a call is refused BEFORE it is made when its worst case
would cross the share — so the round can stop short, and can never overspend.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import json
import logging
import pathlib
import statistics
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "scripts")]

from harness import prodlog  # noqa: E402
import voice_drive  # noqa: E402  (CLIP_HOME, _outside_repo; imports nothing of the app)

SHARES = {  # usd, ElevenLabs characters — sums: $0.49 ≤ $0.50, 4,200 ≤ 15,000
    "reasoner": (0.27, 0),
    "stt": (0.05, 0),
    "voice_start": (0.16, 4_000),
    "numbers_probe": (0.01, 200),
}
TTS_USD_PER_CHAR = 0.04 / 1000            # Flash/Turbo v2.5, ElevenLabs API pricing 2026-10-29


def console() -> None:
    """The scripts' posture: `configure_logging()` minus the file."""
    from muthis.logging_policy import silence_third_party_http_logs
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    silence_third_party_http_logs()


def key(name: str) -> str:
    from dotenv import dotenv_values
    value = (dotenv_values(REPO / ".env").get(name) or "").strip()
    if not value:
        raise SystemExit(f"{name} is empty in .env")
    return value


def utc_stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def results_dir(kind: str) -> pathlib.Path:
    folder = voice_drive._outside_repo(voice_drive.CLIP_HOME / "results" / f"{kind}-{utc_stamp()}")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write(folder: pathlib.Path, name: str, data: dict) -> pathlib.Path:
    out = voice_drive._outside_repo(folder / name)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def stats(values) -> dict:
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {"n": len(values), "median": round(statistics.median(values), 1),
            "min": round(min(values), 1), "max": round(max(values), 1)}


class Spend:
    """A running ledger against ONE share. `allow` is called BEFORE a call with
    that call's worst case, and refuses — the measurement stops — rather than
    let the share be crossed."""

    def __init__(self, share: str) -> None:
        self.share = share
        self.usd_cap, self.chars_cap = SHARES[share]
        self.usd = 0.0
        self.chars = 0

    def allow(self, *, usd: float = 0.0, chars: int = 0) -> None:
        if self.usd + usd > self.usd_cap or self.chars + chars > self.chars_cap:
            raise SystemExit(f"STOPPED before the next call: the {self.share} share would be crossed "
                             f"(spent ${self.usd:.4f} of ${self.usd_cap:.2f}, "
                             f"{self.chars} of {self.chars_cap} characters)")

    def add(self, *, usd: float = 0.0, chars: int = 0) -> None:
        self.usd += usd
        self.chars += chars

    def as_dict(self) -> dict:
        return {"share": self.share, "usd": round(self.usd, 6), "usd_cap": self.usd_cap,
                "elevenlabs_chars": self.chars, "chars_cap": self.chars_cap}


def log_guard() -> dict:
    return prodlog.snapshot()


def log_changes(before: dict) -> list:
    return prodlog.changes(before, prodlog.snapshot())


# ─── ONE ElevenLabs generation, timed at the provider (no player, no device) ────

def tts_uri(voice_id: str, *, extra: str = "") -> str:
    from muthis.tts_elevenlabs import build_uri, DEFAULT_MODEL_ID, DEFAULT_OUTPUT_FORMAT
    return build_uri(voice_id, DEFAULT_MODEL_ID, DEFAULT_OUTPUT_FORMAT) + extra


async def tts_generate(api_key: str, uri: str, text: str, *, schedule=(90, 160, 250, 290),
                       idle_s: float = 0.0, keep_audio: bool = False) -> dict:
    """Connect, send the app's BOS, optionally idle (a PRE-OPENED socket), then
    send `text` exactly as a complete reply is fed (`tts_session.feed`: the
    diacritized copy, flush, try_trigger_generation) and time it to the first
    audio frame. Returns timings, the characters sent, and errors by TYPE."""
    import websockets
    from muthis.tts_diacritics import apply_diacritics
    from muthis.tts_elevenlabs import DEFAULT_VOICE_SETTINGS
    out = {"error": None, "chars_sent": 0}
    payload = apply_diacritics(text) + " "
    started = time.perf_counter()
    pcm = bytearray()
    try:
        async with websockets.connect(uri, open_timeout=5.0) as ws:
            out["connect_ms"] = (time.perf_counter() - started) * 1000
            await ws.send(json.dumps({"text": " ", "voice_settings": dict(DEFAULT_VOICE_SETTINGS),
                                      "generation_config": {"chunk_length_schedule": list(schedule)},
                                      "xi_api_key": api_key}))
            if idle_s:
                await asyncio.sleep(idle_s)
            sent = time.perf_counter()
            await ws.send(json.dumps({"text": payload, "flush": True, "try_trigger_generation": True}))
            out["chars_sent"] = 1 + len(payload)
            while True:   # the end-of-stream goes AFTER the first audio, as close() sends it last
                data = json.loads(await asyncio.wait_for(ws.recv(), timeout=15.0))
                if data.get("error"):
                    out["error"] = f"provider_error:{str(data.get('error'))[:80]}"
                    break
                if data.get("audio"):
                    chunk = base64.b64decode(data["audio"])
                    if "first_audio_ms" not in out:
                        out["first_audio_ms"] = (time.perf_counter() - sent) * 1000
                        out["first_chunk_ms_of_audio"] = len(chunk) / (22050 * 2) * 1000
                        await ws.send(json.dumps({"text": ""}))
                    pcm.extend(chunk)
                if data.get("isFinal"):
                    break
            out["final_ms"] = (time.perf_counter() - sent) * 1000
            out["close"] = {"code": ws.close_code, "reason": (ws.close_reason or "")[:120]}
    except Exception as exc:  # noqa: BLE001 — recorded by type, the run continues
        out["error"] = out["error"] or f"{type(exc).__name__}:{str(exc)[:120]}"
    out["audio_ms"] = len(pcm) / (22050 * 2) * 1000
    if keep_audio:
        out["pcm"] = bytes(pcm)
    return out
