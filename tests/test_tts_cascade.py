"""
test_tts_cascade.py — the ElevenLabs → Gemini → none cascade. No network.

Both provider transports are monkeypatched at their seams
(TTS._speak_elevenlabs / tts_gemini.synthesize_pcm_blocking) and playback is
captured, so no socket is ever opened and no audio device is touched.
sys.modules sentinels prove the REMOVED SAPI/pyttsx3 paths are never called.

Run:  pytest tests/test_tts_cascade.py -q
"""

from __future__ import annotations

import sys

import pytest

from muthis import tts_gemini
from muthis.tts import TTS, TTSResult

FAKE_PCM = b"\x01\x02" * 256


class _ForbiddenModule:
    """Explodes on ANY attribute access — proves a module is never touched."""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        raise AssertionError(
            f"{self._name} must NEVER be used — SAPI/pyttsx3 were removed"
        )


@pytest.fixture(autouse=True)
def no_local_engines(monkeypatch):
    """Every test in this file proves the local engines stay untouched."""
    monkeypatch.setitem(sys.modules, "win32com", _ForbiddenModule("win32com"))
    monkeypatch.setitem(
        sys.modules, "win32com.client", _ForbiddenModule("win32com.client"),
    )
    monkeypatch.setitem(sys.modules, "pyttsx3", _ForbiddenModule("pyttsx3"))


@pytest.fixture(autouse=True)
def no_env_keys(monkeypatch):
    """Keys come ONLY from constructor args — never from the dev's real env."""
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.mark.asyncio
async def test_gemini_tried_when_elevenlabs_fails(monkeypatch):
    played = []
    tts = TTS(api_key="fake-elevenlabs-key", gemini_api_key="fake-gemini-key")

    async def simulate_elevenlabs_outage(text):
        raise RuntimeError("simulated ElevenLabs outage")

    def fake_gemini_synthesis(text, api_key):
        assert api_key == "fake-gemini-key"
        return FAKE_PCM

    monkeypatch.setattr(tts, "_speak_elevenlabs", simulate_elevenlabs_outage)
    monkeypatch.setattr(tts_gemini, "synthesize_pcm_blocking", fake_gemini_synthesis)
    monkeypatch.setattr(tts, "_play_wav_blocking", played.append)

    result = await tts.speak("زر الحفظ فوق يسار")

    assert result == TTSResult(success=True, provider="gemini")
    assert len(played) == 1            # the Gemini audio reached playback
    assert FAKE_PCM in played[0]       # PCM made it into the WAV container


@pytest.mark.asyncio
async def test_both_keys_absent_returns_none_without_crash():
    tts = TTS()    # no constructor keys + env cleared by fixture
    result = await tts.speak("اختبار")
    assert result.success is False
    assert result.provider == "none"


@pytest.mark.asyncio
async def test_gemini_failure_degrades_to_none(monkeypatch):
    tts = TTS(api_key=None, gemini_api_key="fake-gemini-key")

    def gemini_explodes(text, api_key):
        raise RuntimeError("simulated Gemini outage")

    monkeypatch.setattr(tts_gemini, "synthesize_pcm_blocking", gemini_explodes)

    result = await tts.speak("اختبار")

    assert result.success is False
    assert result.provider == "none"
    assert "simulated Gemini outage" in (result.error or "")


@pytest.mark.asyncio
async def test_empty_text_short_circuits_all_providers():
    tts = TTS(api_key="fake", gemini_api_key="fake")
    result = await tts.speak("   ")
    assert result == TTSResult(success=False, provider="none", error="empty text")
