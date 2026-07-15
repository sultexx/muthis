"""
test_tts_session.py — the persistent ElevenLabs speech session (v5 Phase C),
fakes only: no network, no audio device, no real WebSocket.

Proves the C0 contract: successive sentences ride ONE connection inside ONE
generation (BOS → text messages → EOS), audio reaches the player PROGRESSIVELY
while feeding continues, each fed sentence is diacritized on a copy (speech
only), failures raise so the caller can degrade to buffered speak(), close()
is timeout-bounded (the internal reader can never wedge), and the tts.py
factory honors the MUTHIS_TRY_ELEVENLABS rollback + the missing-key case.

Run:  set PYTHONPATH=src && python -m pytest tests/test_tts_session.py -q
"""

from __future__ import annotations

import asyncio
import base64
import json

import pytest

from muthis.tts import TTS
from muthis.tts_session import SpeechSession


# ──────────────────────────────── Fakes ────────────────────────────────


class FakeWS:
    """A scripted stream-input endpoint: records every sent message; echoes one
    audio frame per fed sentence and an isFinal on EOS (both configurable)."""

    def __init__(self, *, echo_audio=True, ack_eos=True, fail_at=None,
                 error_frame=False):
        self.sent = []                     # decoded JSON of every send()
        self._frames: asyncio.Queue = asyncio.Queue()
        self._echo = echo_audio
        self._ack = ack_eos
        self._fail_at = fail_at            # raise on the Nth send (0-based)
        self._error_frame = error_frame

    async def send(self, payload):
        if self._fail_at is not None and len(self.sent) >= self._fail_at:
            raise ConnectionError("socket dropped")
        data = json.loads(payload)
        self.sent.append(data)
        if data.get("text") == "":                      # EOS
            if self._ack:
                await self._frames.put({"isFinal": True})
        elif "xi_api_key" not in data:                  # a fed sentence
            if self._error_frame:
                await self._frames.put({"error": "quota exceeded"})
            elif self._echo:
                pcm = base64.b64encode(("PCM:" + data["text"]).encode()).decode()
                await self._frames.put({"audio": pcm})

    async def recv(self):
        return json.dumps(await self._frames.get())


class FakeConnect:
    """ws_connect seam: an async-context-manager factory recording the URI."""

    def __init__(self, ws):
        self.ws = ws
        self.uri = None
        self.calls = 0

    def __call__(self, uri):
        self.uri = uri
        self.calls += 1
        return self

    async def __aenter__(self):
        return self.ws

    async def __aexit__(self, *exc):
        return False


class FakePlayer:
    def __init__(self):
        self.fed = []
        self.started = False
        self.finished = False

    def start(self):
        self.started = True

    def feed(self, pcm):
        self.fed.append(pcm)

    async def finish(self):
        self.finished = True

    @property
    def got_audio(self):
        return bool(self.fed)


async def _until(condition, timeout=1.0):
    """Drive the loop until `condition()` — deterministic, no real sleeps."""
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0)


def _session(ws, player, **kwargs):
    return SpeechSession(
        api_key="k", ws_connect=FakeConnect(ws),
        player_factory=lambda: player, **kwargs,
    )


# ─────────────────────────── The one-generation contract ───────────────────────────


@pytest.mark.asyncio
async def test_sentences_ride_one_connection_with_progressive_audio():
    ws, player = FakeWS(), FakePlayer()
    connect = FakeConnect(ws)
    session = SpeechSession(api_key="k", ws_connect=connect,
                            player_factory=lambda: player)
    await session.open()

    await session.feed("الجملة الأولى.")
    await _until(lambda: len(player.fed) == 1)   # audio flows WHILE we still feed
    await session.feed("والثانية.")
    await _until(lambda: len(player.fed) == 2)
    await session.close()

    assert connect.calls == 1                    # ONE connection for the whole turn
    assert [m.get("text") for m in ws.sent][0] == " "          # BOS first
    assert ws.sent[-1]["text"] == ""                            # EOS last
    fed = [m for m in ws.sent if "xi_api_key" not in m and m.get("text")]
    assert len(fed) == 2                          # both sentences, same generation
    # v7 Fix A: ONLY the first sentence forces generation (fast first audio);
    # later sentences leave chunking to the BOS chunk_length_schedule so the
    # prosody never restarts at a fed boundary (the measured pauses).
    assert fed[0].get("try_trigger_generation") is True
    assert "try_trigger_generation" not in fed[1]
    # Default feeds (streamed sentences) never carry flush — forcing a
    # boundary per feed was the baked-pauses bug.
    assert all("flush" not in m for m in fed)
    assert player.finished                        # tail drained via finish()


@pytest.mark.asyncio
async def test_flush_feed_forces_immediate_generation():
    # v7.1: a COMPLETE utterance (the pass-1 ack / a buffered pass text) is
    # fed with flush=True so ElevenLabs synthesizes the buffer NOW — measured:
    # a 4-char «أبشر» ack sat ~2.6 s under the 90-char schedule floor, playing
    # glued to the explanation instead of masking the inter-pass gap.
    ws, player = FakeWS(), FakePlayer()
    session = _session(ws, player)
    await session.open()

    await session.feed("أبشر", flush=True)        # the complete pass-1 ack
    await session.feed("الجملة المتدفقة الأولى.")   # a streamed sentence: no flush
    await session.close()

    fed = [m for m in ws.sent if "xi_api_key" not in m and m.get("text")]
    assert fed[0].get("flush") is True
    assert "flush" not in fed[1]


@pytest.mark.asyncio
async def test_bos_carries_key_and_settings_and_the_uri_does_not():
    ws, player = FakeWS(), FakePlayer()
    connect = FakeConnect(ws)
    session = SpeechSession(api_key="secret-key", ws_connect=connect,
                            player_factory=lambda: player)
    await session.open()
    await session.feed("سم.")
    await session.close()

    bos = ws.sent[0]
    assert bos["xi_api_key"] == "secret-key"
    assert "voice_settings" in bos
    # v7 Fix A: the BOS hands chunking to ElevenLabs (lookahead across feeds).
    assert bos["generation_config"]["chunk_length_schedule"] == [90, 160, 250, 290]
    assert "secret-key" not in connect.uri        # the key never rides the URI


@pytest.mark.asyncio
async def test_fed_sentences_are_diacritized_on_a_copy():
    ws, player = FakeWS(), FakePlayer()
    session = _session(ws, player)
    await session.open()
    clean = "أبشر طال عمرك."
    await session.feed(clean)
    await session.close()

    fed_text = [m for m in ws.sent if m.get("try_trigger_generation")][0]["text"]
    assert "أَبْشِر" in fed_text                  # speech copy is vowelized
    assert clean == "أبشر طال عمرك."              # the caller's text untouched


# ─────────────────────────────── Failure paths ───────────────────────────────


@pytest.mark.asyncio
async def test_error_frame_fails_the_session_and_close_raises():
    ws, player = FakeWS(error_frame=True), FakePlayer()
    session = _session(ws, player)
    await session.open()
    await session.feed("جملة.")
    with pytest.raises(RuntimeError, match="quota exceeded"):
        await session.close()
    assert not session.got_audio                  # caller may safely re-speak all
    assert player.finished                        # the player is still drained


@pytest.mark.asyncio
async def test_silent_generation_raises_no_audio():
    ws, player = FakeWS(echo_audio=False), FakePlayer()
    session = _session(ws, player)
    await session.open()
    await session.feed("جملة.")
    with pytest.raises(RuntimeError, match="no audio"):
        await session.close()


@pytest.mark.asyncio
async def test_feed_raises_when_the_socket_drops_mid_session():
    ws, player = FakeWS(fail_at=2), FakePlayer()  # BOS + 1st sentence pass, then drop
    session = _session(ws, player)
    await session.open()
    await session.feed("نجحت.")
    with pytest.raises(ConnectionError):
        await session.feed("سقطت.")               # the caller degrades to buffer


@pytest.mark.asyncio
async def test_close_is_timeout_bounded_when_the_stream_never_finishes():
    ws, player = FakeWS(ack_eos=False), FakePlayer()   # server never says isFinal
    session = _session(ws, player, close_timeout_sec=0.05)
    await session.open()
    await session.feed("جملة.")
    with pytest.raises(RuntimeError):
        await session.close()                     # the reader was CANCELLED, no hang
    assert player.finished


@pytest.mark.asyncio
async def test_open_failure_propagates_cleanly():
    class ExplodingConnect:
        def __call__(self, uri):
            return self

        async def __aenter__(self):
            raise ConnectionError("no route")

        async def __aexit__(self, *exc):
            return False

    player = FakePlayer()
    session = SpeechSession(api_key="k", ws_connect=ExplodingConnect(),
                            player_factory=lambda: player)
    with pytest.raises(ConnectionError):
        await session.open()
    assert not player.started                     # nothing leaked


# ─────────────────────────── tts.py factory wiring ───────────────────────────


def test_factory_returns_none_without_an_api_key():
    # conftest cleared ELEVENLABS_API_KEY → streaming unavailable, no crash.
    assert TTS().open_speech_session() is None


def test_factory_honors_the_rollback_flag(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    monkeypatch.setenv("MUTHIS_TRY_ELEVENLABS", "0")
    assert TTS().open_speech_session() is None


def test_factory_builds_a_session_from_the_resolved_config(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-ar-1")
    session = TTS().open_speech_session()
    assert isinstance(session, SpeechSession)
    assert "voice-ar-1" in session._uri           # the resolved voice reached the URI
