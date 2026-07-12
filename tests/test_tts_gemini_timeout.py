"""
test_tts_gemini_timeout.py — Gemini TTS timeout robustness. No network, no audio.

The network seam (urllib.request.urlopen) is monkeypatched, so these tests
exercise the REAL synthesize_pcm_blocking body: the configurable timeout
(MUTHIS_GEMINI_TIMEOUT_S, default 30 s), the single fast retry on a urllib
timeout, and the clean speak()-level degradation when both attempts time out.
Deterministic; no socket is ever opened and no audio device is touched.

Run:  pytest tests/test_tts_gemini_timeout.py -q
"""

from __future__ import annotations

import base64
import json
import socket
import urllib.error

import pytest

from muthis import tts_gemini
from muthis.tts import TTS, TTSResult

FAKE_PCM = b"\x01\x02" * 256


# ─── fakes (no network) ──────────────────────────────────────────────────────

class _FakeResponse:
    """Minimal context-manager stand-in for an http.client response."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def _audio_payload(pcm: bytes) -> bytes:
    """Encode `pcm` exactly as the Gemini speech endpoint would return it."""
    b64 = base64.b64encode(pcm).decode("ascii")
    return json.dumps({
        "candidates": [
            {"content": {"parts": [{"inlineData": {"data": b64}}]}},
        ],
    }).encode("utf-8")


@pytest.fixture(autouse=True)
def _clean_tts_env(monkeypatch):
    """Config comes only from explicit args/sets — never the dev's real env."""
    for var in (
        "GEMINI_API_KEY", "ELEVENLABS_API_KEY", "MUTHIS_TRY_ELEVENLABS",
        "MUTHIS_GEMINI_TIMEOUT_S", "GEMINI_TTS_MODEL", "GEMINI_TTS_VOICE",
    ):
        monkeypatch.delenv(var, raising=False)


# ─── A) configurable timeout ─────────────────────────────────────────────────

def test_timeout_defaults_to_30s(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["timeout"] = timeout
        return _FakeResponse(_audio_payload(FAKE_PCM))

    monkeypatch.setattr(tts_gemini.urllib.request, "urlopen", fake_urlopen)

    pcm = tts_gemini.synthesize_pcm_blocking("مرحبا", "fake-key", "Puck")

    assert pcm == FAKE_PCM
    assert captured["timeout"] == tts_gemini.DEFAULT_REQUEST_TIMEOUT_SEC == 30.0


def test_timeout_honors_env_override(monkeypatch):
    monkeypatch.setenv("MUTHIS_GEMINI_TIMEOUT_S", "15")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["timeout"] = timeout
        return _FakeResponse(_audio_payload(FAKE_PCM))

    monkeypatch.setattr(tts_gemini.urllib.request, "urlopen", fake_urlopen)

    tts_gemini.synthesize_pcm_blocking("مرحبا", "fake-key", "Puck")

    assert captured["timeout"] == 15.0


def test_invalid_timeout_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("MUTHIS_GEMINI_TIMEOUT_S", "not-a-number")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["timeout"] = timeout
        return _FakeResponse(_audio_payload(FAKE_PCM))

    monkeypatch.setattr(tts_gemini.urllib.request, "urlopen", fake_urlopen)

    tts_gemini.synthesize_pcm_blocking("مرحبا", "fake-key", "Puck")

    assert captured["timeout"] == 30.0


# ─── B) one fast retry on timeout ────────────────────────────────────────────

_TIMEOUT_FORMS = [
    pytest.param(socket.timeout("read timed out"), id="socket.timeout"),
    pytest.param(TimeoutError("read timed out"), id="TimeoutError"),
    pytest.param(urllib.error.URLError(socket.timeout("c")), id="URLError-socket"),
    pytest.param(urllib.error.URLError(TimeoutError("c")), id="URLError-TimeoutError"),
]


@pytest.mark.parametrize("timeout_exc", _TIMEOUT_FORMS)
def test_retries_once_on_timeout_then_succeeds(monkeypatch, timeout_exc):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise timeout_exc
        return _FakeResponse(_audio_payload(FAKE_PCM))

    monkeypatch.setattr(tts_gemini.urllib.request, "urlopen", fake_urlopen)

    pcm = tts_gemini.synthesize_pcm_blocking("مرحبا", "fake-key", "Puck")

    assert pcm == FAKE_PCM
    assert calls["n"] == 2          # original + EXACTLY one retry, not more


def test_non_timeout_error_is_not_retried(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        raise urllib.error.URLError("connection refused")   # reason is a str

    monkeypatch.setattr(tts_gemini.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(urllib.error.URLError):
        tts_gemini.synthesize_pcm_blocking("مرحبا", "fake-key", "Puck")

    assert calls["n"] == 1          # only timeouts get the retry


# ─── C) clean failure: speak() never raises ──────────────────────────────────

@pytest.mark.asyncio
async def test_speak_clean_failure_when_gemini_times_out_twice(monkeypatch):
    calls = {"n": 0}

    def always_timeout(request, timeout=None):
        calls["n"] += 1
        raise socket.timeout("read timed out")

    monkeypatch.setattr(tts_gemini.urllib.request, "urlopen", always_timeout)

    tts = TTS(gemini_api_key="fake-gemini-key")   # ElevenLabs parked (flag off)
    result = await tts.speak("اختبار")            # must NOT raise

    assert isinstance(result, TTSResult)
    assert result.success is False
    assert result.provider == "none"
    assert calls["n"] == 2          # one original + one retry, then give up
