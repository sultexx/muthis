"""
test_tts_ws_streaming.py — ElevenLabs WebSocket PRIMARY + progressive playback.

Fakes only — no network, no audio device, fully deterministic:
  * a fake WebSocket yields audio chunks one at a time; a fake player records the
    EXACT interleaving of recv/feed, proving playback is fed PROGRESSIVELY (chunk
    i is fed before chunk i+1 is even received), in order, with no overlap,
  * the real PcmStreamPlayer is driven against a fake output stream (FIFO order +
    a drain stop(), and a stream error re-raised so the caller can fall back),
  * speak() uses ElevenLabs as PRIMARY and falls back to Gemini cleanly on any
    failure — never raising, signature unchanged.

Run:  set PYTHONPATH=src && python -m pytest tests/test_tts_ws_streaming.py -q
"""

from __future__ import annotations

import base64
import json

import pytest

from muthis import tts_elevenlabs, tts_gemini
from muthis.tts import TTS, TTSResult
from muthis.tts_ws_player import PcmStreamPlayer

C1, C2, C3 = b"AAAA", b"BBBB", b"CCCC"
FAKE_PCM = b"\x01\x02" * 256


def _b64(pcm: bytes) -> str:
    return base64.b64encode(pcm).decode("ascii")


# ──────────────────────────────── Fakes ────────────────────────────────


class FakeWS:
    """A scripted WebSocket. recv() pops the next (label, payload), logs the recv
    into a SHARED order log, and returns the payload as a JSON string."""

    def __init__(self, messages, log):
        self._messages = list(messages)
        self._log = log
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    async def recv(self):
        if not self._messages:
            raise ConnectionError("closed")   # the loop catches → break
        label, payload = self._messages.pop(0)
        self._log.append(("recv", label))
        return json.dumps(payload)


def _fake_ws_connect(ws):
    """A ws_connect seam returning an async context manager yielding `ws`."""
    class _CM:
        async def __aenter__(self):
            return ws

        async def __aexit__(self, *exc):
            return False

    def _connect(uri):
        ws.uri = uri
        return _CM()

    return _connect


class FakePlayer:
    """Records start/feed/finish into a SHARED order log (no real audio)."""

    def __init__(self, log):
        self._log = log
        self.fed = []
        self.started = False
        self.finished = 0
        self.got_audio = False

    def start(self):
        self.started = True
        self._log.append("start")

    def feed(self, pcm):
        self.fed.append(pcm)
        self.got_audio = True
        self._log.append(("feed", pcm))

    async def finish(self):
        self.finished += 1
        self._log.append("finish")


# ─────────────────── tts_elevenlabs.stream_pcm (progressive) ───────────────────


@pytest.mark.asyncio
async def test_elevenlabs_streams_chunks_progressively_in_order():
    log = []
    ws = FakeWS([
        ("c1", {"audio": _b64(C1)}),
        ("c2", {"audio": _b64(C2)}),
        ("c3", {"audio": _b64(C3)}),
        ("final", {"isFinal": True}),
    ], log)
    player = FakePlayer(log)

    await tts_elevenlabs.stream_pcm(
        "مرحبا", api_key="k", player=player, ws_connect=_fake_ws_connect(ws),
    )

    # Chunks fed in arrival order...
    assert player.fed == [C1, C2, C3]
    # ...and PROGRESSIVELY: each chunk is fed BEFORE the next is received (this is
    # the whole point — playback starts at the first bytes, not after the clip).
    assert log == [
        "start",
        ("recv", "c1"), ("feed", C1),
        ("recv", "c2"), ("feed", C2),
        ("recv", "c3"), ("feed", C3),
        ("recv", "final"),
        "finish",
    ]
    # The FULL text was sent ONCE (BOS + text + EOS), never chunked into sentences.
    assert len(ws.sent) == 3
    assert json.loads(ws.sent[1])["text"].strip() == "مرحبا"


@pytest.mark.asyncio
async def test_stream_with_no_audio_raises_so_caller_falls_back():
    log = []
    ws = FakeWS([("final", {"isFinal": True})], log)
    player = FakePlayer(log)

    with pytest.raises(RuntimeError):
        await tts_elevenlabs.stream_pcm(
            "مرحبا", api_key="k", player=player, ws_connect=_fake_ws_connect(ws),
        )
    assert player.got_audio is False
    assert "finish" in log          # player is finished even on the failure path


@pytest.mark.asyncio
async def test_error_frame_raises_so_caller_falls_back():
    log = []
    ws = FakeWS([("err", {"error": "quota_exceeded"})], log)
    player = FakePlayer(log)

    with pytest.raises(RuntimeError):
        await tts_elevenlabs.stream_pcm(
            "مرحبا", api_key="k", player=player, ws_connect=_fake_ws_connect(ws),
        )
    assert player.finished == 1      # finished in the finally even on an error frame


# ─────────────────────────── PcmStreamPlayer ───────────────────────────


class FakeStream:
    """A fake sounddevice stream: records writes + the drain stop(), no device."""

    def __init__(self):
        self.writes = []
        self.stopped = False
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False

    def write(self, data):
        self.writes.append(bytes(data))

    def stop(self):
        self.stopped = True


@pytest.mark.asyncio
async def test_pcm_stream_player_writes_in_order_then_drains():
    created = []

    def factory(sample_rate, channels):
        stream = FakeStream()
        created.append((sample_rate, channels, stream))
        return stream

    player = PcmStreamPlayer(22050, stream_factory=factory)
    player.start()
    player.feed(C1)
    player.feed(C2)
    player.feed(C3)
    await player.finish()

    sample_rate, channels, stream = created[0]
    assert (sample_rate, channels) == (22050, 1)
    assert stream.writes == [C1, C2, C3]    # FIFO order, no overlap
    assert stream.stopped is True           # drained (Pa_StopStream) before close
    assert stream.closed is True
    assert player.got_audio is True


@pytest.mark.asyncio
async def test_player_finish_reraises_stream_error_for_fallback():
    def bad_factory(sample_rate, channels):
        raise RuntimeError("no audio device")

    player = PcmStreamPlayer(22050, stream_factory=bad_factory)
    player.start()
    player.feed(C1)

    with pytest.raises(RuntimeError, match="no audio device"):
        await player.finish()


# ─────────────────────────── speak() cascade ───────────────────────────


@pytest.mark.asyncio
async def test_speak_uses_elevenlabs_primary_with_injected_seams():
    log = []
    ws = FakeWS([
        ("c1", {"audio": _b64(C1)}),
        ("c2", {"audio": _b64(C2)}),
        ("final", {"isFinal": True}),
    ], log)
    player = FakePlayer(log)
    tts = TTS(
        api_key="fake-el", gemini_api_key="fake-gem",
        ws_connect=_fake_ws_connect(ws), player_factory=lambda: player,
    )

    result = await tts.speak("مرحبا")

    assert result == TTSResult(success=True, provider="elevenlabs")
    assert player.fed == [C1, C2]   # streamed via the real _speak_elevenlabs path


@pytest.mark.asyncio
async def test_speak_falls_back_to_gemini_when_elevenlabs_fails(monkeypatch):
    def failing_connect(uri):
        raise RuntimeError("ws connect failed")

    player = FakePlayer([])
    tts = TTS(
        api_key="fake-el", gemini_api_key="fake-gem",
        ws_connect=failing_connect, player_factory=lambda: player,
    )
    async def no_play(pcm, sample_rate):
        pass

    monkeypatch.setattr(
        tts_gemini, "synthesize_pcm_blocking",
        lambda text, api_key, voice=None: FAKE_PCM,
    )
    monkeypatch.setattr(tts, "_play_pcm", no_play)

    result = await tts.speak("مرحبا")   # must NOT raise

    assert result.success is True and result.provider == "gemini"
