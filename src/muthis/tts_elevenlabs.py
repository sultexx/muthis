# src/muthis/tts_elevenlabs.py
"""
ElevenLabs TTS — PRIMARY voice via the streaming WebSocket.

Mirrors tts_gemini.py (one provider module) but, instead of collect-then-play, it
streams audio back PROGRESSIVELY: the FULL assistant text is sent ONCE, and each
PCM chunk is fed to the player the instant it arrives — so audio starts at the
first bytes (~436ms), not after the whole clip. This is intra-audio streaming of
ONE text, NOT the sentence-chunking rolled back in Batch 3: there is no LLM-text
segmentation here, no per-sentence request.

VOICE ONLY — never reasoning/vision. The API key travels ONLY inside the BOS
message (xi_api_key), never in the URL and never logged.

stream_pcm() raises on any failure (no audio / error frame / disconnect / total
timeout) so the caller (tts.py) can fall back to Gemini. websockets is imported
lazily via the injected ws_connect seam, so this module is importable without it
and tests drive it with a fake WS (no network).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Callable, Optional

logger = logging.getLogger("tts")

ELEVENLABS_WS_BASE = "wss://api.elevenlabs.io/v1/text-to-speech"

# PLACEHOLDER — you MUST paste a NATIVE Arabic voice id here via .env
# (ELEVENLABS_VOICE_ID) or the constructor. Pick one from your ElevenLabs Voice
# Library with Language = Arabic (e.g. a Saudi/Gulf male voice). The old default
# "Rachel" was a multilingual NON-native voice that GUESSED the Arabic accent,
# which is what caused the Egyptian/Saudi drift. With this placeholder unset the
# WS call fails fast and the TTS cascades to Gemini (the intended hard-fail).
DEFAULT_VOICE_ID = "PASTE_NATIVE_ARABIC_VOICE_ID_HERE"
# Flash v2.5 = lowest-latency multilingual model — the v4.1 streaming choice.
DEFAULT_MODEL_ID = "eleven_flash_v2_5"
# PCM (no decoder) → straight to the progressive player.
DEFAULT_OUTPUT_FORMAT = "pcm_22050"
DEFAULT_SAMPLE_RATE = 22050

# Higher `stability` LOCKS the accent (less expressive drift); `style` 0.0 keeps
# it neutral (no exaggeration). A native Arabic voice + higher stability is what
# actually fixes the accent drift. All three are overridable per-field via .env
# (ELEVENLABS_STABILITY / ELEVENLABS_SIMILARITY_BOOST / ELEVENLABS_STYLE) — the
# reading lives in tts.py so this module stays a pure, env-free function.
DEFAULT_VOICE_SETTINGS = {"stability": 0.7, "similarity_boost": 0.8, "style": 0.0}

# Fail fast and fall back rather than freezing the turn.
WS_CONNECT_TIMEOUT_SEC = 5.0
WS_TOTAL_TIMEOUT_SEC = 30.0


def build_uri(voice_id: str, model_id: str, output_format: str) -> str:
    """The stream-input WebSocket URI (no key in it — the key rides in the BOS)."""
    return (
        f"{ELEVENLABS_WS_BASE}/{voice_id}/stream-input"
        f"?model_id={model_id}&output_format={output_format}"
    )


def default_ws_connect(uri: str):
    """Default ws_connect seam: an async-context-manager WebSocket connection.
    websockets is imported lazily so the TTS stack stays importable without it."""
    import websockets

    return websockets.connect(uri, open_timeout=WS_CONNECT_TIMEOUT_SEC)


async def stream_pcm(
    text: str,
    *,
    api_key: str,
    player,
    voice_id: str = DEFAULT_VOICE_ID,
    model_id: str = DEFAULT_MODEL_ID,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    voice_settings: Optional[dict] = None,
    ws_connect: Optional[Callable[[str], object]] = None,
    total_timeout_sec: float = WS_TOTAL_TIMEOUT_SEC,
) -> None:
    """Send the FULL text once and feed each PCM chunk to `player` as it arrives.

    Raises on any failure so tts.py can fall back to Gemini. The player is
    start()ed here and ALWAYS finish()ed (drains the tail) even on error."""
    connect = ws_connect or default_ws_connect
    settings = voice_settings or dict(DEFAULT_VOICE_SETTINGS)
    uri = build_uri(voice_id, model_id, output_format)

    player.start()
    try:
        async with asyncio.timeout(total_timeout_sec):
            async with connect(uri) as ws:
                # BOS (config + key) → the FULL text (one message) → EOS.
                await ws.send(json.dumps({
                    "text": " ",
                    "voice_settings": settings,
                    "xi_api_key": api_key,
                }))
                await ws.send(json.dumps({
                    "text": text + " ",
                    "try_trigger_generation": True,
                }))
                await ws.send(json.dumps({"text": ""}))

                # Feed each PCM chunk to the player the instant it arrives.
                while True:
                    try:
                        msg = await ws.recv()
                    except Exception:
                        break  # ConnectionClosed / normal end of stream
                    try:
                        data = json.loads(msg)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if data.get("error"):
                        raise RuntimeError(f"ElevenLabs error: {data['error']}")
                    audio_b64 = data.get("audio")
                    if audio_b64:
                        player.feed(base64.b64decode(audio_b64))
                    if data.get("isFinal"):
                        break
    finally:
        await player.finish()

    if not player.got_audio:
        raise RuntimeError("ElevenLabs returned no audio data.")


__all__ = [
    "stream_pcm", "build_uri", "default_ws_connect",
    "ELEVENLABS_WS_BASE", "DEFAULT_VOICE_ID", "DEFAULT_MODEL_ID",
    "DEFAULT_OUTPUT_FORMAT", "DEFAULT_SAMPLE_RATE", "DEFAULT_VOICE_SETTINGS",
    "WS_CONNECT_TIMEOUT_SEC", "WS_TOTAL_TIMEOUT_SEC",
]
