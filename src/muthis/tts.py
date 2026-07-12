# src/muthis/tts.py
"""
TTS — text-to-speech for Mut'his v4.1: ElevenLabs WebSocket PRIMARY with TRUE
progressive playback + Gemini TTS FALLBACK.

This is the "tongue" of Mut'his — the boundary where the agent's Arabic response
becomes audible. Everything heavy is cloud. The old Windows SAPI/pyttsx3 paths
are REMOVED; when both cloud providers are unavailable the sidekick stays silent
and reports provider="none" — the orchestrator handles that honestly.

Latency leap (Phase 1): ElevenLabs streams audio back PROGRESSIVELY — the FULL
assistant text is sent once over the WebSocket and each PCM chunk plays the
instant it arrives (PcmStreamPlayer via sounddevice), so audio starts at the
first bytes (~436ms) instead of after the whole clip. This is intra-audio
streaming of ONE text, NOT the sentence-chunking rolled back in Batch 3.

Design contract:
  - Stateless across calls. API keys + voice config are injected at __init__.
  - Network + audio output only — zero GPU/VRAM; overlaps freely with any stage.
  - The event loop is NEVER blocked: WS receive is async; the blocking sounddevice
    writes live in the player's worker thread; the Gemini HTTP call + winsound run
    inside asyncio.to_thread.
  - speak() NEVER raises — returns TTSResult(success, provider) so the orchestrator
    reacts (log, "صوت احتياطي") without try/except sprawl. Signature UNCHANGED, so
    the orchestrator and the DI seam are untouched.

Resilience cascade (ElevenLabs primary; Gemini fallback):
  Path A : ElevenLabs WebSocket  (PRIMARY — progressive; see tts_elevenlabs.py)
  Path B : Gemini TTS REST       (FALLBACK — collect-then-play, timeout + 1 retry;
                                  see tts_gemini.py)
  None   : TTSResult(success=False, provider="none")

Privacy:
  The LAST place before text leaves the device. Pass ONLY the agent's synthesized
  response — never user transcriptions or PII. That policy is the orchestrator's.

Pronunciation (speech-only diacritics):
  Right before text reaches EITHER engine, speak() runs it through a small Saudi-
  word diacritics map (tts_diacritics.apply_diacritics) on a COPY — for SPEECH
  ONLY. The clean text مطحس actually wrote is never altered, and the harakat
  NEVER enter conversation history (that would corrupt the model's reasoning).
  See tts_diacritics.py.

Environment variables (.env is loaded once at process entry, before imports):
  ELEVENLABS_API_KEY / *_VOICE_ID / *_MODEL_ID : PRIMARY (absent → Gemini only).
                          *_VOICE_ID MUST be a NATIVE Arabic voice id, or the
                          accent drifts (the default is a placeholder → Gemini).
  ELEVENLABS_STABILITY / *_SIMILARITY_BOOST / *_STYLE : voice_settings floats;
                          higher stability (~0.7) locks the Arabic accent
  MUTHIS_TRY_ELEVENLABS : set falsey ("0"/"false") to DISABLE the primary and
                          force Gemini — a one-env rollback (default ON now)
  GEMINI_API_KEY        : FALLBACK voice (absent → primary only)
  MUTHIS_GEMINI_VOICE   : Gemini voice name (default "Kore", male)
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
import wave
from dataclasses import dataclass
from typing import Callable, Optional

from . import tts_elevenlabs, tts_gemini
from .tts_diacritics import apply_diacritics
from .tts_ws_player import PcmStreamPlayer
# Re-exported so existing importers (diagnostics / smoke scripts) keep working.
from .tts_elevenlabs import (  # noqa: F401
    DEFAULT_MODEL_ID, DEFAULT_OUTPUT_FORMAT, DEFAULT_SAMPLE_RATE,
    DEFAULT_VOICE_ID, DEFAULT_VOICE_SETTINGS, ELEVENLABS_WS_BASE,
    WS_CONNECT_TIMEOUT_SEC, WS_TOTAL_TIMEOUT_SEC,
)

logger = logging.getLogger("tts")

DEFAULT_GEMINI_VOICE = "Kore"  # FALLBACK Gemini voice (male); MUTHIS_GEMINI_VOICE to override


def _env_flag(name: str, *, default: bool) -> bool:
    """Parse a truthy/falsey env flag; absent → `default`."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    """Parse a float env var; absent/blank/non-numeric → `default` (with a warning
    on a bad value). Config never crashes a run-forever app."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("[TTS] %s=%r is not a float — using default %s", name, raw, default)
        return default


def _voice_settings_from_env() -> dict:
    """Build ElevenLabs voice_settings from .env, falling back per-field to the
    documented DEFAULT_VOICE_SETTINGS. A NATIVE Arabic voice (ELEVENLABS_VOICE_ID)
    plus a higher stability is what fixes the accent drift. os.getenv lives HERE
    (tts.py), so tts_elevenlabs.py stays a pure, env-free function (DI intact)."""
    return {
        "stability": _env_float("ELEVENLABS_STABILITY", DEFAULT_VOICE_SETTINGS["stability"]),
        "similarity_boost": _env_float(
            "ELEVENLABS_SIMILARITY_BOOST", DEFAULT_VOICE_SETTINGS["similarity_boost"]),
        "style": _env_float("ELEVENLABS_STYLE", DEFAULT_VOICE_SETTINGS["style"]),
    }


# ─── Result model ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TTSResult:
    success:  bool
    provider: str               # "elevenlabs" | "gemini" | "none"
    error:    Optional[str] = None


# ─── TTS ──────────────────────────────────────────────────────────────────────

class TTS:
    """Speak text through ElevenLabs WebSocket (PRIMARY, progressive) with Gemini
    TTS REST as fallback. Stateless beyond config; safe to share across the
    process."""

    def __init__(
        self,
        *,
        api_key:        Optional[str]      = None,
        gemini_api_key: Optional[str]      = None,
        gemini_voice:   Optional[str]      = None,
        voice_id:       Optional[str]      = None,
        model_id:       Optional[str]      = None,
        output_format:  str                = DEFAULT_OUTPUT_FORMAT,
        sample_rate:    int                = DEFAULT_SAMPLE_RATE,
        voice_settings: Optional[dict]     = None,
        try_elevenlabs: Optional[bool]     = None,
        ws_connect:     Optional[Callable] = None,
        player_factory: Optional[Callable] = None,
    ) -> None:
        # Load via os.getenv — .env was loaded once at process entry.
        self.api_key        = api_key or os.getenv("ELEVENLABS_API_KEY")
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.gemini_voice   = gemini_voice or os.getenv("MUTHIS_GEMINI_VOICE") or DEFAULT_GEMINI_VOICE
        self.voice_id       = voice_id or os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID
        self.model_id       = model_id or os.getenv("ELEVENLABS_MODEL_ID") or DEFAULT_MODEL_ID
        self.output_format  = output_format
        self.sample_rate    = sample_rate
        # Constructor arg wins → else .env (ELEVENLABS_STABILITY/*_SIMILARITY_BOOST/
        # *_STYLE) → else the documented DEFAULT_VOICE_SETTINGS.
        self.voice_settings = voice_settings or _voice_settings_from_env()
        # ElevenLabs is now PRIMARY (default ON). A falsey MUTHIS_TRY_ELEVENLABS
        # disables it and forces Gemini — a one-env rollback, no code change.
        self.try_elevenlabs = (_env_flag("MUTHIS_TRY_ELEVENLABS", default=True)
                               if try_elevenlabs is None else try_elevenlabs)
        # DI seams (real defaults) so tests drive the WS + playback with fakes.
        self._ws_connect = ws_connect
        self._player_factory = player_factory or (lambda: PcmStreamPlayer(self.sample_rate))

        if not self.gemini_api_key and not (self.try_elevenlabs and self.api_key):
            logger.warning(
                "[TTS] No ElevenLabs (primary) and no GEMINI_API_KEY — "
                "every speak() will return provider='none'.")
        elif not (self.try_elevenlabs and self.api_key):
            logger.warning("[TTS] ElevenLabs primary disabled/unkeyed — Gemini only.")

    # ─────────────────────────── Public API ───────────────────────────

    async def speak(self, text: str) -> TTSResult:
        """Speak `text`. Never raises — returns TTSResult. Uses no GPU."""
        text = (text or "").strip()
        if not text:
            return TTSResult(success=False, provider="none", error="empty text")

        # Diacritize a COPY for SPEECH ONLY (bug 3). `text` stays the clean,
        # unvowelized string مطحس actually wrote (what logs/lengths reflect);
        # `speech_text` carries the harakat that ONLY the TTS engines see. Never
        # let speech_text reach persona.py or history — see tts_diacritics.py.
        speech_text = apply_diacritics(text)

        last_error: Optional[str] = None

        # ── Path A (PRIMARY): ElevenLabs WebSocket — progressive playback ─
        if self.try_elevenlabs and self.api_key:
            try:
                await self._speak_elevenlabs(speech_text)
                logger.info("[TTS] ElevenLabs OK (%d chars)", len(text))
                return TTSResult(success=True, provider="elevenlabs")
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning("[TTS] ElevenLabs failed (%s) — falling back.", last_error)
                logger.debug("ElevenLabs error detail", exc_info=True)

        # ── Path B (FALLBACK): Gemini TTS (collect-then-play; timeout + retry) ─
        if self.gemini_api_key:
            try:
                pcm = await asyncio.to_thread(
                    tts_gemini.synthesize_pcm_blocking, speech_text,
                    self.gemini_api_key, self.gemini_voice,
                )
                wav_bytes = self._pcm_to_wav(pcm, tts_gemini.GEMINI_SAMPLE_RATE)
                await asyncio.to_thread(self._play_wav_blocking, wav_bytes)
                logger.info("[TTS] Gemini OK (%d chars)", len(text))
                return TTSResult(success=True, provider="gemini")
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning("[TTS] Gemini failed (%s).", last_error)
                logger.debug("Gemini error detail", exc_info=True)

        logger.error("[TTS] No TTS provider available/working.")
        return TTSResult(
            success=False, provider="none",
            error=last_error or "no cloud TTS provider configured",
        )

    # ───────────────── ElevenLabs WebSocket (Path A — progressive) ─────────────────

    async def _speak_elevenlabs(self, text: str) -> None:
        """Stream the full text once and play each PCM chunk as it arrives. Raises
        on any failure so speak() falls back to Gemini. Thin glue over
        tts_elevenlabs.stream_pcm + a PcmStreamPlayer (both injectable for tests)."""
        await tts_elevenlabs.stream_pcm(
            text,
            api_key=self.api_key,
            player=self._player_factory(),
            voice_id=self.voice_id,
            model_id=self.model_id,
            output_format=self.output_format,
            voice_settings=self.voice_settings,
            ws_connect=self._ws_connect,
        )

    # ───────────────── Gemini playback helpers (winsound, full buffer) ─────────────────

    def _pcm_to_wav(self, pcm: bytes, sample_rate: Optional[int] = None) -> bytes:
        """Wrap raw 16-bit mono PCM in a WAV container (in-memory). Used by the
        Gemini fallback (24 kHz)."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)              # 16-bit
            wf.setframerate(sample_rate or self.sample_rate)
            wf.writeframes(pcm)
        return buf.getvalue()

    def _play_wav_blocking(self, wav_bytes: bytes) -> None:
        """Play a COMPLETE WAV clip. ALWAYS invoked via asyncio.to_thread. The
        Gemini fallback is collect-then-play, so winsound (full-buffer) is fine
        here — the progressive path is ElevenLabs', not this one."""
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
            return

        # Non-Windows fallback (mostly for CI/dev) — temp file + system player.
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
    "DEFAULT_GEMINI_VOICE",
]
