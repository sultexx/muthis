# src/muthis/tts.py
"""
TTS — text-to-speech for Mut'his v4.1: ElevenLabs WebSocket primary + local
SAPI fallback.

This is the "tongue" of Mut'his — the boundary where the agent's Arabic
response becomes audible. Everything heavy is cloud (ElevenLabs); the local
paths exist only so the sidekick can still speak when the network drops.

Design contract:
  - Stateless across calls. API key + voice config are injected at __init__.
  - Uses network + audio output only — zero GPU/VRAM, so it never contends
    with the user's Blender/YOLO workloads and can overlap freely with any
    other pipeline stage.
  - Blocking audio playback (winsound) and blocking SAPI are wrapped in
    asyncio.to_thread so the event loop never freezes.
  - Never raises from `speak()` — returns TTSResult with a clear success/
    provider field so the orchestrator can react (log, mark "صوت احتياطي",
    etc.) without try/except sprawl.

Resilience cascade:
  Path A : ElevenLabs WebSocket  (low-latency cloud, Arabic-capable model)
  Path B : Windows SAPI via win32com.client  (offline; Arabic voice if installed)
  Path C : pyttsx3                            (cross-platform SAPI wrapper)
  None   : TTSResult(success=False, provider="none")

Privacy:
  This wrapper is the LAST place before text leaves the device. The caller
  MUST pass only the agent's synthesized response — never user transcriptions,
  account numbers, or any PII. We do not inspect the text here; that policy
  is the orchestrator's responsibility.

Environment variables (.env is loaded once at process entry, before imports):
  ELEVENLABS_API_KEY   : required for cloud TTS (absent → local fallback only)
  ELEVENLABS_VOICE_ID  : optional override (final Arabic voice selection pending)
  ELEVENLABS_MODEL_ID  : optional override (default = eleven_flash_v2_5)
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
from typing import Any, Optional

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
    provider: str               # "elevenlabs" | "local" | "none"
    error:    Optional[str] = None


# ─── TTS ──────────────────────────────────────────────────────────────────────

class TTS:
    """
    Speak text through ElevenLabs WebSocket (primary) or local SAPI
    (fallback). Stateless beyond config; safe to share across the process.
    """

    def __init__(
        self,
        *,
        api_key:        Optional[str]  = None,
        voice_id:       Optional[str]  = None,
        model_id:       Optional[str]  = None,
        output_format:  str            = DEFAULT_OUTPUT_FORMAT,
        sample_rate:    int            = DEFAULT_SAMPLE_RATE,
        voice_settings: Optional[dict] = None,
    ) -> None:
        # Load via os.getenv — .env was loaded once at process entry.
        self.api_key       = api_key  or os.getenv("ELEVENLABS_API_KEY")
        self.voice_id      = voice_id or os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID
        self.model_id      = model_id or os.getenv("ELEVENLABS_MODEL_ID") or DEFAULT_MODEL_ID
        self.output_format = output_format
        self.sample_rate   = sample_rate
        self.voice_settings = voice_settings or dict(DEFAULT_VOICE_SETTINGS)

        if not self.api_key:
            logger.warning(
                "[TTS] No ELEVENLABS_API_KEY in environment — "
                "every speak() will use local fallback only."
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

        # ── Path A: ElevenLabs ───────────────────────────────────────
        if self.api_key:
            try:
                await self._speak_elevenlabs(text)
                logger.info("[TTS] ElevenLabs OK (%d chars)", len(text))
                return TTSResult(success=True, provider="elevenlabs")
            except Exception as e:
                logger.warning(
                    "[TTS] ElevenLabs failed (%s: %s) — falling back to local.",
                    type(e).__name__, e,
                )
                logger.debug("ElevenLabs error detail", exc_info=True)

        # ── Path B & C: local TTS ────────────────────────────────────
        try:
            await self._speak_local(text)
            logger.info("[TTS] Local TTS OK (%d chars)", len(text))
            return TTSResult(success=True, provider="local")
        except Exception as e:
            logger.error("[TTS] All TTS providers failed: %s", e)
            return TTSResult(success=False, provider="none", error=str(e))

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

    def _pcm_to_wav(self, pcm: bytes) -> bytes:
        """Wrap raw 16-bit mono PCM in a WAV container (in-memory)."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)              # 16-bit
            wf.setframerate(self.sample_rate)
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

    # ───────────────────── Local SAPI fallback (Paths B & C) ─────────────────

    async def _speak_local(self, text: str) -> None:
        await asyncio.to_thread(self._speak_local_blocking, text)

    def _speak_local_blocking(self, text: str) -> None:
        """Try SAPI via win32com first (Path B); pyttsx3 as Path C."""
        last_error: Optional[Exception] = None

        # ── Path B: direct Windows SAPI through COM ──
        if sys.platform == "win32":
            try:
                self._sapi_speak_blocking(text)
                return
            except Exception as e:
                last_error = e
                logger.debug("SAPI direct failed: %s", e)

        # ── Path C: pyttsx3 (cross-platform SAPI / eSpeak wrapper) ──
        try:
            import pyttsx3
            engine = pyttsx3.init()
            self._try_set_arabic_voice_pyttsx3(engine)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
            return
        except Exception as e:
            last_error = e

        raise RuntimeError(
            f"All local TTS engines failed; last error: {last_error}"
        )

    def _sapi_speak_blocking(self, text: str) -> None:
        """Windows SAPI via COM. Picks an Arabic voice if one is installed."""
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        self._try_set_arabic_voice_sapi(speaker)
        speaker.Speak(text)

    @staticmethod
    def _try_set_arabic_voice_sapi(speaker: Any) -> None:
        try:
            voices = speaker.GetVoices()
            for i in range(voices.Count):
                voice = voices.Item(i)
                desc = (voice.GetDescription() or "").lower()
                if (
                    "arabic" in desc
                    or "naayf" in desc
                    or "hoda"   in desc
                    or "ar-"    in desc
                ):
                    speaker.Voice = voice
                    return
        except Exception:
            pass  # leave default voice

    @staticmethod
    def _try_set_arabic_voice_pyttsx3(engine: Any) -> None:
        try:
            for v in engine.getProperty("voices"):
                blob = (
                    str(getattr(v, "id", "")) + " "
                    + str(getattr(v, "name", ""))
                ).lower()
                if "arabic" in blob or "ar-" in blob or "ar_" in blob:
                    engine.setProperty("voice", v.id)
                    return
        except Exception:
            pass


__all__ = [
    "TTS",
    "TTSResult",
]
