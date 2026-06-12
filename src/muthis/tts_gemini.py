# src/muthis/tts_gemini.py
"""
Gemini TTS — VOICE FALLBACK ONLY — NOT a reasoning path.

This module exists solely so Mut'his can still speak intelligent Arabic when
ElevenLabs is down or unkeyed. It calls the Gemini *speech-generation*
endpoint (responseModalities=["AUDIO"]) and returns raw PCM bytes. It never
sends screenshots, never offers tools, never reads model TEXT output —
Claude (claude-sonnet-4-6) remains the ONLY reasoning/vision path
(AGENTS.md "Single-path v1"). Do not import or call any Gemini text/vision
capability from anywhere in this codebase.

stdlib-only (urllib) so the TTS stack stays importable in isolation; the
blocking HTTP call is always run inside asyncio.to_thread by the caller
(tts.py) — never on the event loop.

Environment variables (.env is loaded once at process entry):
  GEMINI_API_KEY    : required for this fallback (absent → caller skips path)
  GEMINI_TTS_MODEL  : optional override (default below; change if it 404s)
  GEMINI_TTS_VOICE  : optional override (default "Kore" — Arabic-capable)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.request

logger = logging.getLogger("tts_gemini")

GEMINI_TTS_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# TTS-ONLY model id (speech generation). NEVER swap in a text/vision Gemini
# id here — that would breach the Claude-only reasoning law.
# Current per ai.google.dev/gemini-api/docs/speech-generation (2026-06);
# "gemini-2.5-flash-preview-tts" is the older fallback if this 404s.
DEFAULT_GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"

# Prebuilt multilingual voice; Arabic is auto-detected from the text.
DEFAULT_GEMINI_TTS_VOICE = "Kore"

# The speech-generation endpoint returns base64 PCM: s16le, mono, 24 kHz.
GEMINI_SAMPLE_RATE = 24000

# Fail fast and let tts.py degrade to provider="none" instead of hanging.
REQUEST_TIMEOUT_SEC = 30.0


def synthesize_pcm_blocking(text: str, api_key: str) -> bytes:
    """
    Synthesize `text` and return the COMPLETE 24 kHz mono s16le PCM clip
    (collect-then-play — same shape as the ElevenLabs path; true streaming
    is the documented follow-up). Blocking: call via asyncio.to_thread.
    Raises on any failure; tts.py catches and reports provider="none".
    """
    model = os.getenv("GEMINI_TTS_MODEL") or DEFAULT_GEMINI_TTS_MODEL
    voice = os.getenv("GEMINI_TTS_VOICE") or DEFAULT_GEMINI_TTS_VOICE

    body = json.dumps({
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice},
                },
            },
        },
    }).encode("utf-8")

    request = urllib.request.Request(
        GEMINI_TTS_ENDPOINT.format(model=model),
        data=body,
        headers={
            "Content-Type": "application/json",
            # Key travels in this header ONLY — never in the URL, never logged.
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SEC) as response:
        payload = json.loads(response.read().decode("utf-8"))

    try:
        audio_b64 = (
            payload["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
        )
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Gemini TTS returned no audio (model={model})") from e

    pcm = base64.b64decode(audio_b64)
    if not pcm:
        raise RuntimeError("Gemini TTS returned empty audio data.")

    logger.info(
        "[tts_gemini] synthesized %d PCM bytes (model=%s voice=%s)",
        len(pcm), model, voice,
    )
    return pcm


__all__ = [
    "synthesize_pcm_blocking",
    "GEMINI_SAMPLE_RATE",
    "DEFAULT_GEMINI_TTS_MODEL",
    "DEFAULT_GEMINI_TTS_VOICE",
]
