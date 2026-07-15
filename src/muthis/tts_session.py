# src/muthis/tts_session.py
"""
SpeechSession — ONE persistent ElevenLabs generation, fed sentence-by-sentence
(v5 Phase C, the approved C0 expansion).

WHY: sentence-streaming over speak() would open a NEW WebSocket per sentence —
the literal Batch-3 failure (audible inter-sentence gaps). The stream-input
protocol accepts successive text messages inside ONE generation, so this
session keeps ONE connection: `open()` sends the BOS (key + voice settings),
each `feed(sentence)` rides the SAME generation (with try_trigger_generation
so audio starts early), and `close()` sends the EOS and drains the tail.
Prosody stays continuous — the synthesis never restarts between sentences.

THE INTERNAL READER IS NOT THE BATCH-3 WEDGE: audio frames arrive WHILE
sentences are still being fed, so a reader task drains them into the SAME
progressive `PcmStreamPlayer` (playback starts on the first chunk). Unlike the
reverted design, this task is (a) owned INSIDE the TTS layer, (b) bounded —
`close()` awaits it under `asyncio.timeout` and CANCELS it on expiry — and
(c) never awaited by anything on the `is_processing` path except that bounded
close. It cannot outlive the session.

Diacritics choke point EXTENDED here: each fed sentence is vowelized on a COPY
(`apply_diacritics`) exactly like tts.py's speak() — speech-only, the clean
text/history are never touched.

Config arrives as ARGS (env reading stays in tts.py — `TTS.open_speech_session`
is the factory); `ws_connect`/`player_factory` are the same DI seams the
buffered path uses, so tests drive everything with fakes (no network/device).
Any failure RAISES so the caller (turn_pass C2) degrades to buffered speak().
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Callable, Optional

from .tts_diacritics import apply_diacritics
from .tts_elevenlabs import (
    DEFAULT_MODEL_ID,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_VOICE_ID,
    DEFAULT_VOICE_SETTINGS,
    WS_TOTAL_TIMEOUT_SEC,
    build_uri,
    default_ws_connect,
)
from .tts_ws_player import PcmStreamPlayer

logger = logging.getLogger("tts")

# DIAG(v7): temporary timing probes for the mid-sentence-pause investigation.
# Sentence CONTENT is never logged — only lengths and the boundary punctuation.
_diag = logging.getLogger("muthis.diag")


class SpeechSession:
    """One ElevenLabs generation over one WebSocket: open → feed()* → close."""

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str = DEFAULT_VOICE_ID,
        model_id: str = DEFAULT_MODEL_ID,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        voice_settings: Optional[dict] = None,
        ws_connect: Optional[Callable[[str], object]] = None,
        player_factory: Optional[Callable[[], object]] = None,
        close_timeout_sec: float = WS_TOTAL_TIMEOUT_SEC,
    ) -> None:
        self._api_key = api_key
        self._uri = build_uri(voice_id, model_id, output_format)
        self._settings = voice_settings or dict(DEFAULT_VOICE_SETTINGS)
        self._sample_rate = sample_rate  # DIAG(v7): PCM-seconds math in the chunk log
        # v7 Fix A: only the FIRST sentence forces generation (fast first audio);
        # afterwards ElevenLabs owns the chunking via the BOS chunk_length_schedule.
        self._first_feed = True
        self._connect = ws_connect or default_ws_connect
        self._player_factory = player_factory or (lambda: PcmStreamPlayer(sample_rate))
        self._close_timeout = close_timeout_sec
        self._cm = None            # the async-context-manager connection
        self._ws = None
        self._player = None
        self._reader: Optional[asyncio.Task] = None
        self._error: Optional[BaseException] = None

    @property
    def got_audio(self) -> bool:
        """True once any PCM reached the player — the caller's double-speak
        guard: a failed session that already PLAYED audio must not be re-spoken."""
        return bool(self._player is not None and self._player.got_audio)

    # ─────────────────────────────── Lifecycle ───────────────────────────────

    async def open(self) -> None:
        """Connect and send the BOS (key travels ONLY here, never in the URI),
        then start the player + the bounded reader. Raises on any failure so
        the caller stays on the buffered path."""
        self._cm = self._connect(self._uri)
        try:
            self._ws = await self._cm.__aenter__()
            await self._ws.send(json.dumps({
                "text": " ",
                "voice_settings": self._settings,
                # v7 Fix A (measured, diag 2026-07-15): per-feed forced generation
                # baked pauses INTO the audio at every fed boundary. This schedule
                # hands chunking to ElevenLabs, which buffers ACROSS feeds with
                # lookahead — prosody stays continuous between sentences.
                "generation_config": {"chunk_length_schedule": [90, 160, 250, 290]},
                "xi_api_key": self._api_key,
            }))
        except BaseException:
            await self._abandon_ws()
            raise
        _diag.info("[DIAG] session BOS sent t=%.3f", time.monotonic())
        self._player = self._player_factory()
        self._player.start()
        self._reader = asyncio.create_task(self._read_audio())

    async def feed(self, sentence: str, *, flush: bool = False) -> None:
        """One sentence into the SAME generation — diacritized on a COPY
        (speech-only; the caller's clean text is untouched). `flush=True` is
        for a COMPLETE utterance (the pass-1 ack, a buffered pass text):
        ElevenLabs synthesizes the buffer NOW instead of holding it under the
        chunk-length schedule — measured (v7.1): a 4-char «أبشر» ack sat ~2.6 s
        below the 90-char floor, defeating the gap mask; a flush boundary
        between separate utterances is natural. Streamed mid-pass sentences
        must NOT flush (per-feed forcing was the baked-pauses bug, Fix A).
        Raises on a dead session/connection so the caller degrades to
        buffered speak()."""
        if self._error is not None:
            raise RuntimeError(f"speech session already failed: {self._error}")
        _diag.info("[DIAG] session feed t=%.3f len=%d flush=%s ender=%r",
                   time.monotonic(), len(sentence), flush, sentence[-1:])
        payload: dict = {"text": apply_diacritics(sentence) + " "}
        if flush:
            payload["flush"] = True
        if self._first_feed:
            # First audio should not wait for the 90-char schedule floor; later
            # sentences must NOT force chunk boundaries (the measured pauses).
            payload["try_trigger_generation"] = True
            self._first_feed = False
        await self._ws.send(json.dumps(payload))

    async def close(self) -> None:
        """EOS → drain the reader under a timeout (cancel on expiry) → release
        the socket → drain the player tail. Raises if the generation failed or
        produced no audio at all."""
        _diag.info("[DIAG] session EOS sent t=%.3f", time.monotonic())
        try:
            try:
                async with asyncio.timeout(self._close_timeout):
                    await self._ws.send(json.dumps({"text": ""}))
                    if self._reader is not None:
                        await self._reader
                        _diag.info("[DIAG] session reader drained t=%.3f", time.monotonic())
            except BaseException as exc:
                if self._reader is not None and not self._reader.done():
                    self._reader.cancel()
                    try:
                        await self._reader
                    except BaseException:  # noqa: BLE001 — cancelled reader
                        pass
                if self._error is None:
                    self._error = exc
        finally:
            await self._abandon_ws()
            if self._player is not None:
                await self._player.finish()   # tail drains; may raise → fallback
            _diag.info("[DIAG] session closed (player drained) t=%.3f", time.monotonic())
        if self._error is not None:
            raise RuntimeError(f"speech session failed: {self._error}")
        if not self.got_audio:
            raise RuntimeError("speech session produced no audio.")

    # ─────────────────────────────── Internals ───────────────────────────────

    async def _read_audio(self) -> None:
        """The BOUNDED internal reader: audio frames → player, the instant they
        arrive, while feed() keeps sending. Ends on isFinal / error frame /
        disconnect; close() cancels it on timeout — it cannot outlive the
        session or wedge anything."""
        while True:
            try:
                msg = await self._ws.recv()
            except Exception:
                return                        # closed — close() judges the outcome
            try:
                data = json.loads(msg)
            except (json.JSONDecodeError, TypeError):
                continue
            if data.get("error"):
                self._error = RuntimeError(f"ElevenLabs error: {data['error']}")
                return
            audio_b64 = data.get("audio")
            if audio_b64:
                pcm = base64.b64decode(audio_b64)
                _diag.info("[DIAG] session audio-chunk t=%.3f bytes=%d (%.3fs of PCM)",
                           time.monotonic(), len(pcm), len(pcm) / (2.0 * self._sample_rate))
                self._player.feed(pcm)
            if data.get("isFinal"):
                _diag.info("[DIAG] session isFinal t=%.3f", time.monotonic())
                return

    async def _abandon_ws(self) -> None:
        """Release the connection context, swallowing close-time noise."""
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:                 # noqa: BLE001 — already tearing down
                pass
            self._cm = None


__all__ = ["SpeechSession"]
