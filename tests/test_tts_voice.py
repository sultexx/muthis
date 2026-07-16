"""
test_tts_voice.py — the configurable Gemini voice (male default). No network.

Two layers, both with fakes only:
  * TTS config — TTS resolves the Gemini voice as constructor arg > env
    (MUTHIS_GEMINI_VOICE) > DEFAULT_GEMINI_VOICE ("Kore", male) and passes it
    down to the provider. The provider seam is monkeypatched to capture the
    voice; playback is stubbed so no audio device is touched.
  * Provider body — tts_gemini.synthesize_pcm_blocking puts the resolved voice
    into the request body (urlopen monkeypatched to capture it), with its own
    arg > GEMINI_TTS_VOICE > DEFAULT_GEMINI_TTS_VOICE fallback chain.

Run:  set PYTHONPATH=src && python -m pytest tests/test_tts_voice.py -q
"""

from __future__ import annotations

import base64
import json

import pytest

from muthis import tts_gemini
from muthis.tts import DEFAULT_GEMINI_VOICE, TTS

FAKE_PCM = b"\x01\x02" * 64


# ─────────────────────────── TTS-level (config) ───────────────────────────


def _capture_voice(captured):
    """A fake provider that records the voice it was handed and returns PCM."""
    def _synth(text, api_key, voice=None):
        captured["voice"] = voice
        return FAKE_PCM
    return _synth


async def _no_play(self, pcm, sample_rate):
    pass


def _wire_tts(monkeypatch, captured, **kwargs):
    monkeypatch.setattr(tts_gemini, "synthesize_pcm_blocking", _capture_voice(captured))
    monkeypatch.setattr(TTS, "_play_pcm", _no_play)
    return TTS(gemini_api_key="fake-gemini-key", **kwargs)


@pytest.mark.asyncio
async def test_gemini_voice_defaults_to_male_kore(monkeypatch):
    # Unset env → the male default "Kore" is what reaches the provider.
    monkeypatch.delenv("MUTHIS_GEMINI_VOICE", raising=False)
    captured: dict = {}
    tts = _wire_tts(monkeypatch, captured)

    assert DEFAULT_GEMINI_VOICE == "Kore"
    assert tts.gemini_voice == "Kore"
    result = await tts.speak("مرحبا")

    assert result.success and result.provider == "gemini"
    assert captured["voice"] == "Kore"


@pytest.mark.asyncio
async def test_gemini_voice_honors_env_override(monkeypatch):
    # MUTHIS_GEMINI_VOICE set → that voice reaches the provider (easy Fenrir swap).
    monkeypatch.setenv("MUTHIS_GEMINI_VOICE", "Fenrir")
    captured: dict = {}
    tts = _wire_tts(monkeypatch, captured)

    assert tts.gemini_voice == "Fenrir"
    await tts.speak("مرحبا")
    assert captured["voice"] == "Fenrir"


@pytest.mark.asyncio
async def test_constructor_voice_beats_env(monkeypatch):
    # DI seam: an explicit constructor voice wins over the env var.
    monkeypatch.setenv("MUTHIS_GEMINI_VOICE", "Fenrir")
    captured: dict = {}
    tts = _wire_tts(monkeypatch, captured, gemini_voice="Charon")

    assert tts.gemini_voice == "Charon"
    await tts.speak("مرحبا")
    assert captured["voice"] == "Charon"


# ─────────────────────────── Provider-level (body) ───────────────────────────


class _FakeResponse:
    def __init__(self, payload_bytes: bytes) -> None:
        self._payload = payload_bytes

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._payload


def _fake_urlopen(captured):
    """Capture the POSTed request body and return a minimal valid audio payload."""
    def _open(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        pcm_b64 = base64.b64encode(FAKE_PCM).decode("ascii")
        payload = {"candidates": [{"content": {"parts": [{"inlineData": {"data": pcm_b64}}]}}]}
        return _FakeResponse(json.dumps(payload).encode("utf-8"))
    return _open


def _voice_in_body(captured) -> str:
    return (captured["body"]["generationConfig"]["speechConfig"]
            ["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"])


def test_passed_voice_lands_in_request_body(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen(captured))

    pcm = tts_gemini.synthesize_pcm_blocking("مرحبا", "key", "Puck")

    assert pcm == FAKE_PCM
    assert _voice_in_body(captured) == "Puck"


def test_provider_voice_resolution_param_over_env_over_default(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen(captured))

    # Explicit voice wins even over the env override.
    monkeypatch.setenv("GEMINI_TTS_VOICE", "EnvVoice")
    tts_gemini.synthesize_pcm_blocking("hi", "k", "ParamVoice")
    assert _voice_in_body(captured) == "ParamVoice"

    # No voice arg → the GEMINI_TTS_VOICE env override.
    tts_gemini.synthesize_pcm_blocking("hi", "k")
    assert _voice_in_body(captured) == "EnvVoice"

    # No arg, no env → the module default ("Kore", the provider-level fallback).
    monkeypatch.delenv("GEMINI_TTS_VOICE", raising=False)
    tts_gemini.synthesize_pcm_blocking("hi", "k")
    assert _voice_in_body(captured) == tts_gemini.DEFAULT_GEMINI_TTS_VOICE
