# src/muthis/tts.py
"""
TTS — text-to-speech for Mut'his v4.1: ElevenLabs WebSocket primary +
Gemini TTS cloud fallback (voice fallback only — NOT a reasoning path).

This is the "tongue" of Mut'his — the boundary where the agent's Arabic
response becomes audible. Everything heavy is cloud. The old Windows
SAPI/pyttsx3 local paths are REMOVED (robotic, no real Arabic); when both
cloud providers are unavailable the sidekick stays silent and reports
provider="none" — the orchestrator handles that honestly.

Design contract:
  - Stateless across calls. API keys + voice config are injected at __init__.
  - Uses network + audio output only — zero GPU/VRAM, so it never contends
    with the user's Blender/YOLO workloads and can overlap freely with any
    other pipeline stage.
  - Blocking audio playback (winsound) and the blocking Gemini HTTP call
    are wrapped in asyncio.to_thread so the event loop never freezes.
  - Never raises from `speak()` — returns TTSResult with a clear success/
    provider field so the orchestrator can react (log, mark "صوت احتياطي",
    etc.) without try/except sprawl.

Resilience cascade:
  Path A : ElevenLabs WebSocket  (low-latency cloud, Arabic-capable model)
  Path B : Gemini TTS REST       (intelligent Arabic voice — VOICE FALLBACK
                                  ONLY, never reasoning; see tts_gemini.py)
  None   : TTSResult(success=False, provider="none")

Privacy:
  This wrapper is the LAST place before text leaves the device. The caller
  MUST pass only the agent's synthesized response — never user transcriptions,
  account numbers, or any PII. We do not inspect the text here; that policy
  is the orchestrator's responsibility.

Environment variables (.env is loaded once at process entry, before imports):
  ELEVENLABS_API_KEY   : primary cloud TTS (absent → Gemini fallback only)
  ELEVENLABS_VOICE_ID  : optional override (final Arabic voice selection pending)
  ELEVENLABS_MODEL_ID  : optional override (default = eleven_flash_v2_5)
  GEMINI_API_KEY       : fallback voice (absent → no fallback, provider="none")
  GEMINI_TTS_MODEL / GEMINI_TTS_VOICE : optional overrides (see tts_gemini.py)
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import sys
import wave
from dataclasses import dataclass
from typing import Optional

from . import tts_gemini

logger = logging.getLogger("tts")


# ─── ElevenLabs config ────────────────────────────────────────────────────────

ELEVENLABS_WS_BASE = "wss://api.elevenlabs.io/v1/text-to-speech"

# Placeholder voice — override via .env (ELEVENLABS_VOICE_ID) or constructor.
# Final voice selection is pending (will try 2-3 Arabic voices live).
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # "Rachel" — multilingual capable

# Flash v2.5 = lowest-latency multilingual model — the v4.1 streaming choice.
DEFAULT_MODEL_ID = "eleven_flash_v2_5"

# PCM is simpler than MP3 (no decoder needed; ship straight to winsound).
DEFAULT_OUTPUT_FORMAT = "pcm_22050"
DEFAULT_SAMPLE_RATE   = 22050

DEFAULT_VOICE_SETTINGS = {
    "stability":        0.5,
    "similarity_boost": 0.8,
}

# Fail fast and fall back rather than freezing the demo.
WS_CONNECT_TIMEOUT_SEC = 5.0
WS_TOTAL_TIMEOUT_SEC   = 30.0


# ─── Result model ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TTSResult:
    success:  bool
    provider: str               # "elevenlabs" | "gemini" | "none"
    error:    Optional[str] = None


# ─── TTS ──────────────────────────────────────────────────────────────────────

class TTS:
    """
    Speak text through ElevenLabs WebSocket (primary) or Gemini TTS REST
    (voice fallback only — NOT a reasoning path). Stateless beyond config;
    safe to share across the process.
    """

    def __init__(
        self,
        *,
        api_key:        Optional[str]  = None,
        gemini_api_key: Optional[str]  = None,
        voice_id:       Optional[str]  = None,
        model_id:       Optional[str]  = None,
        output_format:  str            = DEFAULT_OUTPUT_FORMAT,
        sample_rate:    int            = DEFAULT_SAMPLE_RATE,
        voice_settings: Optional[dict] = None,
    ) -> None:
        # Load via os.getenv — .env was loaded once at process entry.
        self.api_key        = api_key  or os.getenv("ELEVENLABS_API_KEY")
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.voice_id      = voice_id or os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID
        self.model_id      = model_id or os.getenv("ELEVENLABS_MODEL_ID") or DEFAULT_MODEL_ID
        self.output_format = output_format
        self.sample_rate   = sample_rate
        self.voice_settings = voice_settings or dict(DEFAULT_VOICE_SETTINGS)

        if not self.api_key and not self.gemini_api_key:
            logger.warning(
                "[TTS] No ELEVENLABS_API_KEY and no GEMINI_API_KEY — "
                "every speak() will return provider='none'."
            )
        elif not self.api_key:
            logger.warning(
                "[TTS] No ELEVENLABS_API_KEY — Gemini voice fallback only."
            )

    # ─────────────────────────── Public API ───────────────────────────

    async def speak(self, text: str) -> TTSResult:
        """
        Speak `text`. Never raises — returns TTSResult.
        Uses no GPU; safe to run alongside any other pipeline stage.
        """
        text = (text or "").strip()
        if not text:
            return TTSResult(success=False, provider="none", error="empty text")

        last_error: Optional[str] = None

        # ── Path A: ElevenLabs ───────────────────────────────────────
        if self.api_key:
            try:
                await self._speak_elevenlabs(text)
                logger.info("[TTS] ElevenLabs OK (%d chars)", len(text))
                return TTSResult(success=True, provider="elevenlabs")
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    "[TTS] ElevenLabs failed (%s) — falling back to Gemini.",
                    last_error,
                )
                logger.debug("ElevenLabs error detail", exc_info=True)

        # ── Path B: Gemini TTS (voice fallback only — NOT reasoning) ─
        if self.gemini_api_key:
            try:
                pcm = await asyncio.to_thread(
                    tts_gemini.synthesize_pcm_blocking, text, self.gemini_api_key,
                )
                wav_bytes = self._pcm_to_wav(pcm, tts_gemini.GEMINI_SAMPLE_RATE)
                await asyncio.to_thread(self._play_wav_blocking, wav_bytes)
                logger.info("[TTS] Gemini fallback OK (%d chars)", len(text))
                return TTSResult(success=True, provider="gemini")
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.error("[TTS] Gemini fallback failed (%s)", last_error)
                logger.debug("Gemini error detail", exc_info=True)

        logger.error("[TTS] No TTS provider available/working.")
        return TTSResult(
            success=False, provider="none",
            error=last_error or "no cloud TTS provider configured",
        )

    # ───────────────────── ElevenLabs WebSocket (Path A) ─────────────────────

    async def _speak_elevenlabs(self, text: str) -> None:
        # Lazy import — missing lib triggers fallback, not a hard crash.
        try:
            import websockets
        except ImportError as e:
            raise RuntimeError(
                "websockets library not installed — cannot use ElevenLabs WS."
            ) from e

        uri = (
            f"{ELEVENLABS_WS_BASE}/{self.voice_id}/stream-input"
            f"?model_id={self.model_id}"
            f"&output_format={self.output_format}"
        )

        pcm_buffer = bytearray()

        # Hard timeout caps the worst case — fall back instead of hanging.
        async with asyncio.timeout(WS_TOTAL_TIMEOUT_SEC):
            async with websockets.connect(
                uri, open_timeout=WS_CONNECT_TIMEOUT_SEC,
            ) as ws:
                # BOS — initial config with API key + voice settings
                await ws.send(json.dumps({
                    "text":           " ",      # protocol requires non-empty
                    "voice_settings": self.voice_settings,
                    "xi_api_key":     self.api_key,
                }))

                # The actual text — single chunk (spoken responses are short)
                await ws.send(json.dumps({
                    "text":                   text + " ",
                    "try_trigger_generation": True,
                }))

                # EOS — empty text signals end of input, server flushes & closes
                await ws.send(json.dumps({"text": ""}))

                # Drain audio chunks
                while True:
                    try:
                        msg = await ws.recv()
                    except Exception:
                        # ConnectionClosed or similar — normal end of stream
                        break

                    try:
                        data = json.loads(msg)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    if data.get("error"):
                        raise RuntimeError(f"ElevenLabs error: {data['error']}")

                    audio_b64 = data.get("audio")
                    if audio_b64:
                        pcm_buffer.extend(base64.b64decode(audio_b64))

                    if data.get("isFinal"):
                        break

        if not pcm_buffer:
            raise RuntimeError("ElevenLabs returned no audio data.")

        # Wrap PCM in WAV header and play via winsound (blocking → thread).
        wav_bytes = self._pcm_to_wav(bytes(pcm_buffer))
        await asyncio.to_thread(self._play_wav_blocking, wav_bytes)

    def _pcm_to_wav(self, pcm: bytes, sample_rate: Optional[int] = None) -> bytes:
        """Wrap raw 16-bit mono PCM in a WAV container (in-memory).
        sample_rate: 22050 (ElevenLabs default) or 24000 (Gemini)."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)              # 16-bit
            wf.setframerate(sample_rate or self.sample_rate)
            wf.writeframes(pcm)
        return buf.getvalue()

    def _play_wav_blocking(self, wav_bytes: bytes) -> None:
        """Play WAV bytes. ALWAYS invoked from asyncio.to_thread."""
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
            return

        # Non-Windows fallback (mostly for CI/dev) — temp file + system player
        import tempfile
        import subprocess
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp_path = f.name
        try:
            cmd = (
                ["afplay", tmp_path] if sys.platform == "darwin"
                else ["aplay", "-q", tmp_path]
            )
            subprocess.run(cmd, check=True)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

__all__ = [
    "TTS",
    "TTSResult",
]
