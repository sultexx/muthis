# src/muthis/tts_ws_player.py
"""
PcmStreamPlayer — progressive PCM playback for the streaming TTS path.

This is what turns ElevenLabs into "audio starts at the first bytes (~436ms)"
instead of "wait for the whole clip": feed() hands raw PCM chunks to a SINGLE
worker thread that writes them — in FIFO order — to ONE sounddevice output stream
as they arrive. Playback therefore begins on the first chunk and never overlaps
(one source → one queue → one consumer → one stream).

Threading contract:
  * feed(pcm)  — called from the asyncio loop; a thread-safe queue.put, INSTANT,
                 so the event loop is never blocked.
  * start()    — spawns the worker, which OPENS the output stream and drains the
                 queue (the blocking sounddevice writes live here, off-loop).
  * finish()   — async: signals end-of-stream then awaits the worker via
                 asyncio.to_thread(join), so the loop stays free while the tail
                 drains. Re-raises any playback error so the caller can fall back.

sounddevice is reused (already pinned for mic.py) — NO new dependency. It is
imported lazily inside the worker, so importing this module stays headless-safe;
a stream_factory seam lets tests drive the whole thing with a fake stream (no
real audio device).
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("tts")

# DIAG(v7): temporary timing probes for the mid-sentence-pause investigation.
# Every [DIAG] line (and this logger) is removed once the audio work lands.
_diag = logging.getLogger("muthis.diag")

# Pushed onto the queue to tell the worker "no more audio — drain & stop".
_EOS = object()


def _default_stream_factory(sample_rate: int, channels: int):
    """Open a blocking sounddevice RawOutputStream for 16-bit mono PCM. Imported
    lazily so this module stays importable on a headless box; sounddevice is
    already pinned in the venv (mic.py)."""
    import sounddevice as sd

    return sd.RawOutputStream(
        samplerate=sample_rate, channels=channels, dtype="int16",
    )


class PcmStreamPlayer:
    """Plays raw 16-bit mono PCM chunks progressively, in arrival order."""

    def __init__(
        self,
        sample_rate: int,
        channels: int = 1,
        *,
        stream_factory: Optional[Callable[[int, int], object]] = None,
    ) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._stream_factory = stream_factory or _default_stream_factory
        self._queue: "queue.Queue" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._error: Optional[BaseException] = None
        self._got_audio = False
        # Playback horizon (worker-thread-owned, read-only elsewhere): when
        # the first chunk hit the device and how many PCM seconds followed.
        self._first_write_t: Optional[float] = None
        self._audio_written_s = 0.0

    @property
    def got_audio(self) -> bool:
        """True once at least one non-empty chunk was fed — lets the caller treat
        a silent stream as a failure and fall back."""
        return self._got_audio

    def played_seconds(self) -> float:
        """Estimated seconds of audio the user has HEARD so far (v7 Phase 2 —
        the caption pacer's clock): wall time since the first device write,
        with starvation gaps excluded (the worker re-anchors the horizon past
        them), capped at the PCM actually written. 0.0 before audio starts.
        Loop-safe: plain float reads of worker-owned fields."""
        first_write = self._first_write_t
        if first_write is None:
            return 0.0
        return min(time.monotonic() - first_write, self._audio_written_s)

    def start(self) -> None:
        """Spawn the worker thread (it opens the stream and drains the queue)."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="muthis-tts-player", daemon=True,
        )
        self._thread.start()

    def feed(self, pcm: bytes) -> None:
        """Queue one PCM chunk for playback. INSTANT and loop-safe (a queue.put);
        the worker thread does the blocking write. Empty chunks are ignored."""
        if not pcm:
            return
        self._got_audio = True
        self._queue.put(pcm)

    async def finish(self) -> None:
        """Signal end-of-stream and await the worker (the tail drains) WITHOUT
        blocking the event loop. Re-raises a playback error so the caller can fall
        back to the next provider."""
        self._queue.put(_EOS)
        if self._thread is not None:
            await asyncio.to_thread(self._thread.join)
            self._thread = None
        if self._error is not None:
            raise self._error

    def _run(self) -> None:
        """Worker thread: open the stream, write chunks FIFO until EOS, then stop()
        — PortAudio's Pa_StopStream waits for pending audio to play, so the tail is
        never clipped. Any error is captured and surfaced via finish()."""
        # first_write_t + audio_written_s form the playback horizon
        # (first_write + seconds of PCM written). If the wall clock passes
        # that horizon while we are still waiting on the queue, the device had
        # nothing left to play — an audible gap (starvation). They live on
        # self so played_seconds() (the caption pacer, v7 Phase 2) can read
        # them from the asyncio side (float reads are GIL-atomic).
        try:
            with self._stream_factory(self._sample_rate, self._channels) as stream:
                while True:
                    wait_t0 = time.monotonic()
                    chunk = self._queue.get()
                    waited_s = time.monotonic() - wait_t0
                    if chunk is _EOS:
                        _diag.info("[DIAG] player EOS t=%.3f audio_written=%.3fs",
                                   time.monotonic(), self._audio_written_s)
                        break
                    now = time.monotonic()
                    if self._first_write_t is None:
                        self._first_write_t = now
                        _diag.info("[DIAG] player first-write t=%.3f bytes=%d", now, len(chunk))
                    else:
                        deficit_s = now - (self._first_write_t + self._audio_written_s)
                        if deficit_s > 0.02:
                            _diag.warning(
                                "[DIAG] player STARVED ~%dms (queue wait %dms) t=%.3f",
                                round(deficit_s * 1000), round(waited_s * 1000), now)
                            # Re-anchor the playback horizon past this gap, so
                            # only NEW gaps warn (one real pause used to repeat
                            # as a phantom deficit on every later write) and
                            # played_seconds() never counts silence as speech.
                            self._first_write_t += deficit_s
                    self._audio_written_s += len(chunk) / (2.0 * self._sample_rate * self._channels)
                    stream.write(chunk)
                stream.stop()  # drain pending audio before the context closes
        except BaseException as exc:  # noqa: BLE001 — surfaced to the caller via finish()
            self._error = exc
            logger.warning("[tts] PCM stream player failed: %s", exc)


__all__ = ["PcmStreamPlayer"]
