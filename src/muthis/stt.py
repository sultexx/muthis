# src/muthis/stt.py
"""
STT — ElevenLabs Scribe cloud transcription: the "ears" of Mut'his v4.1.

Cloud-only by law (~0 VRAM): the local-Whisper reference (reference/asr.py)
is deliberately NOT used. The one lesson carried over from that era —
without copying any code — is that Whisper-family models code-switch Arabic
tech talk into English unless the language is pinned, hence the hard
language_code="ar" below (never auto-detect).

Design contract (mirrors tts.py):
  - Stateless across calls. API key + model are injected at __init__,
    falling back to env (.env loaded once at process entry).
  - transcribe() NEVER raises — returns "" on any failure so the
    orchestrator can speak a retry prompt without try/except sprawl.
  - httpx is lazy-imported (already in the venv as the anthropic SDK's
    HTTP stack), so this module stays importable in isolation.
  - Privacy: the transcript is NEVER logged unless MUTHIS_DEBUG=1, and the
    audio never touches disk. The transcript's only consumer is the
    orchestrator → Claude; it must never be routed to any TTS.

Environment variables:
  ELEVENLABS_API_KEY       : required (same key as TTS; absent → always "")
  ELEVENLABS_STT_MODEL_ID  : optional override (default scribe_v2)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("stt")

SCRIBE_ENDPOINT = "https://api.elevenlabs.io/v1/speech-to-text"
DEFAULT_STT_MODEL_ID = "scribe_v2"

# Pinned Arabic — auto-detect invites the Whisper code-switching failure.
ARABIC_LANGUAGE_CODE = "ar"

# Fail fast; the orchestrator speaks a retry line instead of hanging the PTT.
REQUEST_TIMEOUT_SEC = 20.0


class STT:
    """Transcribe one WAV utterance to Arabic text via ElevenLabs Scribe."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        self.model_id = (
            model_id or os.getenv("ELEVENLABS_STT_MODEL_ID") or DEFAULT_STT_MODEL_ID
        )
        if not self.api_key:
            logger.warning(
                "[STT] No ELEVENLABS_API_KEY in environment — "
                "transcribe() will always return ''."
            )

    async def transcribe(self, audio_wav: bytes) -> str:
        """WAV bytes → Arabic text. Never raises; "" means 'heard nothing'."""
        if not audio_wav:
            logger.warning("[STT] empty audio — nothing to transcribe")
            return ""
        if not self.api_key:
            logger.warning("[STT] transcribe skipped — no API key")
            return ""

        try:
            text = await self._scribe_request(audio_wav)
        except Exception as e:
            logger.error("[STT] Scribe failed (%s: %s)", type(e).__name__, e)
            logger.debug("Scribe error detail", exc_info=True)
            return ""

        # Transcript logging is gated (privacy law) — length is always safe.
        if os.getenv("MUTHIS_DEBUG") == "1":
            logger.info("[STT] transcript: %r", text)
        else:
            logger.info("[STT] Scribe OK (%d chars)", len(text))
        return text

    async def _scribe_request(self, audio_wav: bytes) -> str:
        # Lazy import — missing lib degrades to "", not an import-time crash.
        import httpx

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SEC) as client:
            response = await client.post(
                SCRIBE_ENDPOINT,
                headers={"xi-api-key": self.api_key},  # header only, never logged
                data={
                    "model_id": self.model_id,
                    "language_code": ARABIC_LANGUAGE_CODE,
                },
                files={"file": ("utterance.wav", audio_wav, "audio/wav")},
            )
            response.raise_for_status()
            payload = response.json()

        return (payload.get("text") or "").strip()


__all__ = ["STT", "DEFAULT_STT_MODEL_ID", "ARABIC_LANGUAGE_CODE"]
