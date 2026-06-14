# src/muthis/mic.py
"""
Mic — true push-to-talk capture: record exactly while the hotkey is held.

start() opens a streaming sounddevice.InputStream and buffers frames on the
audio backend's OWN callback thread; stop() closes the stream, flushes the
final frames, and returns the utterance as in-memory WAV bytes (mono 16-bit
16 kHz — Scribe's preferred shape). This REPLACES the old fixed-N-seconds
window: the hotkey's on_press starts the stream, and the turn's first step
awaits stop() (the orchestrator's mic seam), so the recording spans the whole
hold with no fixed duration.

Capture-result contract — read together with orchestrator.handle_activation,
which is intentionally NOT modified. The orchestrator maps falsy audio to
MIC_FAILED_AR and an empty transcript to STT_EMPTY_AR, so the two tap/failure
cases must stay distinct here:
  - stop() returns None ONLY when the stream never ran (no device, busy, lib
    missing) — a TRUE hardware failure → the orchestrator speaks MIC_FAILED_AR.
  - stop() returns a VALID-but-empty WAV when the hold was shorter than
    min_record_seconds (a quick accidental tap). It is non-None (so it is NOT a
    hardware failure) but carries no audio, so STT transcribes it to "" and the
    orchestrator speaks STT_EMPTY_AR and makes NO Claude call (budget guard).
  - stop() returns a full WAV otherwise.

Flush correctness (never a half-written buffer): the InputStream callback COPIES
each block (PortAudio reuses the same buffer between callbacks), and stop() calls
stream.stop() — which PortAudio guarantees returns only AFTER the last callback
has finished — BEFORE reading the frame list. So the buffer is always complete
when we assemble the WAV.

sounddevice (PortAudio) is lazy-imported inside the default stream factory: the
test suite and CI never import it and never open a real device (a fake stream
factory is injected instead). Audio stays in memory only — never disk, never
logged.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import wave
from typing import Any, Callable, List, Optional

logger = logging.getLogger("mic")

SAMPLE_RATE = 16000      # plenty for speech; keeps Scribe uploads small
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2   # 16-bit PCM
BYTES_PER_SECOND = SAMPLE_RATE * SAMPLE_WIDTH_BYTES * CHANNELS

# A hold shorter than this is treated as an accidental tap: empty capture, no
# Claude call. Override via MUTHIS_MIN_RECORD_SECONDS at the composition root.
DEFAULT_MIN_RECORD_SECONDS = 0.35

# Fixed window for the dev smoke scripts' record() convenience ONLY (the live
# app uses hold/release start()/stop()). Override via MUTHIS_RECORD_SECONDS.
DEFAULT_RECORD_SECONDS = 5.0

# A stream factory takes the per-block callback and returns an object exposing
# start()/stop()/close(): sounddevice.InputStream in production, a fake in tests.
StreamFactory = Callable[[Callable[..., None]], Any]


def _env_float(name: str, override: Optional[float], default: float) -> float:
    """Resolve a float setting: an explicit override wins, then the env var,
    then the default. Keeps the constructor readable for the two such settings."""
    if override is not None:
        return override
    value = os.getenv(name)
    return float(value) if value else default


def _default_stream_factory(callback: Callable[..., None]) -> Any:
    """Real PortAudio input stream. sounddevice is imported HERE (lazy) so module
    import — and the whole test suite — never touches an audio device."""
    import sounddevice
    return sounddevice.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        callback=callback,
    )


class Mic:
    """Streaming hold-to-talk capture. One hold at a time; is_recording guards
    re-entry. Stateless between holds (the frame buffer resets on each start)."""

    def __init__(
        self,
        *,
        min_record_seconds: Optional[float] = None,
        record_seconds: Optional[float] = None,
        stream_factory: Optional[StreamFactory] = None,
    ) -> None:
        self.min_record_seconds = _env_float(
            "MUTHIS_MIN_RECORD_SECONDS", min_record_seconds, DEFAULT_MIN_RECORD_SECONDS,
        )
        self.record_seconds = _env_float(
            "MUTHIS_RECORD_SECONDS", record_seconds, DEFAULT_RECORD_SECONDS,
        )
        # Injected so tests drive a fake stream and never open a device.
        self._stream_factory = stream_factory or _default_stream_factory
        self._stream: Any = None
        self._frames: List[bytes] = []
        self._recording = False

    @property
    def is_recording(self) -> bool:
        """True between a successful start() and its stop(). Read by the
        activation guard to refuse a second overlapping hold."""
        return self._recording

    # ─────────────────────────── Hold lifecycle ───────────────────────────

    def start(self) -> None:
        """Begin a hold. Runs on the KEYBOARD thread, so it must NOT touch the
        asyncio loop — it only opens the audio stream. Idempotent; never raises:
        a failed open leaves is_recording False, so the matching stop() returns
        None and the orchestrator speaks MIC_FAILED_AR."""
        if self._recording:
            return
        self._frames = []
        try:
            self._stream = self._stream_factory(self._on_frames)
            self._stream.start()
            self._recording = True
            logger.info("[mic] recording started @ %d Hz mono", SAMPLE_RATE)
        except Exception as e:
            logger.error("[mic] start failed (%s: %s)", type(e).__name__, e)
            logger.debug("mic start error detail", exc_info=True)
            self._stream = None
            self._recording = False

    async def stop(self) -> Optional[bytes]:
        """End the hold and return the utterance as WAV bytes. This is the
        orchestrator's mic seam — awaited as the FIRST step of the turn. The
        brief blocking close runs off the loop in a worker thread. See the
        module docstring for the None / empty-WAV / full-WAV contract."""
        if not self._recording:
            return None
        return await asyncio.to_thread(self._stop_blocking)

    def _stop_blocking(self) -> Optional[bytes]:
        self._recording = False
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                # PortAudio guarantees no callback runs after stop() returns, so
                # the frame list is complete once this returns — the flush
                # guarantee against reading a half-written buffer.
                stream.stop()
                stream.close()
            except Exception as e:
                logger.error("[mic] stop failed (%s: %s)", type(e).__name__, e)
                logger.debug("mic stop error detail", exc_info=True)
                return None
        pcm = b"".join(self._frames)
        self._frames = []
        seconds = len(pcm) / BYTES_PER_SECOND
        if seconds < self.min_record_seconds:
            # Accidental tap: a valid-but-empty WAV (NOT None) → STT yields "" →
            # STT_EMPTY_AR, no Claude call. None is reserved for a true failure.
            logger.info(
                "[mic] hold too short (%.2fs < %.2fs) — empty capture",
                seconds, self.min_record_seconds,
            )
            return self._to_wav(b"")
        logger.info("[mic] captured %.2fs", seconds)
        return self._to_wav(pcm)

    def _on_frames(self, indata: Any, *_: Any) -> None:
        """sounddevice callback — runs on the audio backend's OWN thread. bytes()
        COPIES the block: PortAudio reuses the indata buffer between callbacks,
        so we snapshot it now or it is overwritten before stop() reads it.
        (bytes() also accepts the raw-bytes blocks the test's fake stream pushes.)"""
        self._frames.append(bytes(indata))

    # ─────────────────────── Dev-only convenience ─────────────────────────

    async def record(self) -> Optional[bytes]:
        """Fixed-window capture (record_seconds) built ON TOP of start()/stop()
        — for the manual smoke scripts only. The live app uses hold/release
        (start on key-down, stop when the turn begins), never this."""
        self.start()
        await asyncio.sleep(self.record_seconds)
        return await self.stop()

    # ───────────────────────────── Helpers ────────────────────────────────

    @staticmethod
    def _to_wav(pcm: bytes) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH_BYTES)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(pcm)
        return buffer.getvalue()


__all__ = [
    "Mic", "SAMPLE_RATE", "BYTES_PER_SECOND",
    "DEFAULT_MIN_RECORD_SECONDS", "DEFAULT_RECORD_SECONDS",
]
