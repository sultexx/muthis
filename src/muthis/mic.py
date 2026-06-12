# src/muthis/mic.py
"""
Mic — fixed-duration microphone capture (the interim PTT stand-in).

Records MUTHIS_RECORD_SECONDS (default 5 s) of mono 16-bit 16 kHz audio and
returns it as in-memory WAV bytes — Scribe's preferred input shape. TRUE
push-to-talk (record exactly while Ctrl+Shift+Space is held) arrives with
the hotkey phase; until then a fixed window keeps the wiring honest and the
seam identical, so swapping in hold-to-record later touches only this file.

Design contract:
  - record() NEVER raises — returns None on any failure (no device, device
    busy, missing lib) so the orchestrator can speak a user-facing Arabic
    failure line instead of crashing the loop.
  - sounddevice (PortAudio) is lazy-imported: the test suite and CI never
    import it and never open a real device.
  - The blocking capture runs in asyncio.to_thread, off the event loop.
  - Audio stays in memory only — never written to disk, never logged.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import wave
from typing import Optional

logger = logging.getLogger("mic")

SAMPLE_RATE = 16000      # plenty for speech; keeps Scribe uploads small
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2   # 16-bit PCM
DEFAULT_RECORD_SECONDS = 5.0


class Mic:
    """One fixed-window capture per call; stateless between calls."""

    def __init__(self, *, record_seconds: Optional[float] = None) -> None:
        env_value = os.getenv("MUTHIS_RECORD_SECONDS")
        self.record_seconds = (
            record_seconds
            if record_seconds is not None
            else float(env_value) if env_value else DEFAULT_RECORD_SECONDS
        )

    async def record(self) -> Optional[bytes]:
        """Capture one utterance as WAV bytes. None = mic unavailable (the
        orchestrator speaks the Arabic failure line; nothing crashes)."""
        try:
            return await asyncio.to_thread(self._record_blocking)
        except Exception as e:
            logger.error("[mic] capture failed (%s: %s)", type(e).__name__, e)
            logger.debug("mic error detail", exc_info=True)
            return None

    def _record_blocking(self) -> bytes:
        # Lazy import — tests/CI must never load PortAudio or open a device.
        import sounddevice

        frame_count = int(self.record_seconds * SAMPLE_RATE)
        logger.info(
            "[mic] recording %.1fs @ %d Hz mono", self.record_seconds, SAMPLE_RATE,
        )
        recording = sounddevice.rec(
            frame_count,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
        )
        sounddevice.wait()
        return self._to_wav(recording.tobytes())

    @staticmethod
    def _to_wav(pcm: bytes) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH_BYTES)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(pcm)
        return buffer.getvalue()


__all__ = ["Mic", "SAMPLE_RATE", "DEFAULT_RECORD_SECONDS"]
