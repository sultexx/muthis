"""
test_tts_voice_elevenlabs.py — the configurable NATIVE-Arabic ElevenLabs voice.

The accent fix is data, not code: the old "Rachel" was a multilingual NON-native
voice that GUESSED the Arabic accent (Egyptian/Saudi drift). The real fix is a
native Arabic voice id + a higher stability, BOTH supplied from .env. These tests
pin that the config is read from .env (with documented defaults) and is NOT
hardcoded magic — and that it actually reaches the provider seam.

No network: os.getenv lives in tts.py, so config resolution is asserted on the
TTS instance directly, plus one wire-through that captures the kwargs handed to
tts_elevenlabs.stream_pcm. The env is cleared by the autouse conftest guard, so
the "defaults" assertions are deterministic regardless of the developer's .env.

Run:  set PYTHONPATH=src && python -m pytest tests/test_tts_voice_elevenlabs.py -q
"""

from __future__ import annotations

import pytest

from muthis import tts_elevenlabs
from muthis.tts import TTS
from muthis.tts_elevenlabs import DEFAULT_VOICE_ID, DEFAULT_VOICE_SETTINGS


# ─────────────────────── Documented defaults (the placeholder) ───────────────────────


def test_default_voice_id_is_a_placeholder_not_a_real_voice():
    # The default MUST be a clearly-marked placeholder — a real id would silently
    # restore the accent-drifting "Rachel" behaviour. The hard-fail (→ Gemini) is
    # intended when ELEVENLABS_VOICE_ID is unset.
    assert DEFAULT_VOICE_ID == "PASTE_NATIVE_ARABIC_VOICE_ID_HERE"
    assert DEFAULT_VOICE_ID != "21m00Tcm4TlvDq8ikWAM"   # the old "Rachel" id is gone


def test_default_voice_settings_lock_the_accent_and_expose_style():
    # Higher stability (0.7) locks the accent; style is exposed (neutral 0.0);
    # similarity_boost stays configurable. All three are the documented defaults.
    assert DEFAULT_VOICE_SETTINGS == {
        "stability": 0.7, "similarity_boost": 0.8, "style": 0.0,
    }


# ─────────────────────── voice_id resolution (arg > env > default) ───────────────────────


def test_voice_id_defaults_to_placeholder_when_env_unset():
    assert TTS().voice_id == DEFAULT_VOICE_ID


def test_voice_id_read_from_env(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "saudi_native_123")
    assert TTS().voice_id == "saudi_native_123"


def test_constructor_voice_id_beats_env(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "from_env")
    assert TTS(voice_id="from_ctor").voice_id == "from_ctor"


# ─────────────────────── voice_settings resolution (env > default) ───────────────────────


def test_voice_settings_default_to_documented_values_when_env_unset():
    # No env → the documented defaults reach voice_settings, including style.
    assert TTS().voice_settings == DEFAULT_VOICE_SETTINGS


def test_voice_settings_read_each_field_from_env(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_STABILITY", "0.85")
    monkeypatch.setenv("ELEVENLABS_SIMILARITY_BOOST", "0.6")
    monkeypatch.setenv("ELEVENLABS_STYLE", "0.3")
    assert TTS().voice_settings == {
        "stability": 0.85, "similarity_boost": 0.6, "style": 0.3,
    }


def test_voice_settings_fall_back_per_field_on_bad_or_missing_value(monkeypatch):
    # Only stability is set (and valid); similarity/style fall back to defaults.
    monkeypatch.setenv("ELEVENLABS_STABILITY", "0.9")
    monkeypatch.setenv("ELEVENLABS_STYLE", "not-a-float")   # bad → default, no crash
    settings = TTS().voice_settings
    assert settings["stability"] == 0.9
    assert settings["similarity_boost"] == DEFAULT_VOICE_SETTINGS["similarity_boost"]
    assert settings["style"] == DEFAULT_VOICE_SETTINGS["style"]


def test_constructor_voice_settings_beats_env(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_STABILITY", "0.85")
    explicit = {"stability": 0.1, "similarity_boost": 0.2, "style": 0.0}
    assert TTS(voice_settings=explicit).voice_settings == explicit


# ─────────────────────── wire-through to the provider seam ───────────────────────


@pytest.mark.asyncio
async def test_env_voice_config_reaches_stream_pcm(monkeypatch):
    # End-to-end (no network): the .env voice id + settings are what _speak_elevenlabs
    # hands to tts_elevenlabs.stream_pcm — not the hardcoded defaults.
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "saudi_native_123")
    monkeypatch.setenv("ELEVENLABS_STABILITY", "0.75")
    monkeypatch.setenv("ELEVENLABS_STYLE", "0.2")

    captured: dict = {}

    async def _capture_stream_pcm(text, **kwargs):
        captured.update(kwargs)
        captured["text"] = text

    # tts.py calls tts_elevenlabs.stream_pcm; it's the same singleton module object.
    monkeypatch.setattr(tts_elevenlabs, "stream_pcm", _capture_stream_pcm)

    tts = TTS(api_key="fake-el")
    result = await tts.speak("مرحبا")

    assert result.success and result.provider == "elevenlabs"
    assert captured["voice_id"] == "saudi_native_123"
    assert captured["voice_settings"] == {
        "stability": 0.75, "similarity_boost": 0.8, "style": 0.2,
    }
