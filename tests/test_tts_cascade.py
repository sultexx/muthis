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

    def fake_gemini_synthesis(text, api_key, voice=None):
        assert api_key == "fake-gemini-key"
        return FAKE_PCM

    async def capture_play(pcm, sample_rate):
        played.append(pcm)

    monkeypatch.setattr(tts, "_speak_elevenlabs", simulate_elevenlabs_outage)
    monkeypatch.setattr(tts_gemini, "synthesize_pcm_blocking", fake_gemini_synthesis)
    monkeypatch.setattr(tts, "_play_pcm", capture_play)

    result = await tts.speak("زر الحفظ فوق يسار")

    assert result == TTSResult(success=True, provider="gemini")
    assert len(played) == 1            # the Gemini audio reached playback
    assert played[0] == FAKE_PCM       # the raw PCM reached the player


@pytest.mark.asyncio
async def test_both_keys_absent_returns_none_without_crash():
    tts = TTS()    # no constructor keys + env cleared by fixture
    result = await tts.speak("اختبار")
    assert result.success is False
    assert result.provider == "none"


@pytest.mark.asyncio
async def test_gemini_failure_degrades_to_none(monkeypatch):
    tts = TTS(api_key=None, gemini_api_key="fake-gemini-key")

    def gemini_explodes(text, api_key, voice=None):
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


# ──────────────────────────────────────────────────────────────────────────
# New cascade: ElevenLabs PRIMARY (progressive), Gemini FALLBACK
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_elevenlabs_is_primary_by_default(monkeypatch):
    """ElevenLabs is tried FIRST and, when it succeeds, Gemini is NEVER touched —
    the flag now defaults ON (ElevenLabs is primary)."""
    monkeypatch.delenv("MUTHIS_TRY_ELEVENLABS", raising=False)  # default = on now
    played = []
    tts = TTS(api_key="fake-elevenlabs-key", gemini_api_key="fake-gemini-key")
    assert tts.try_elevenlabs is True

    async def elevenlabs_ok(text):
        played.append("el")

    def forbidden_gemini(text, api_key, voice=None):
        raise AssertionError("Gemini must NOT run when ElevenLabs succeeds")

    monkeypatch.setattr(tts, "_speak_elevenlabs", elevenlabs_ok)
    monkeypatch.setattr(tts_gemini, "synthesize_pcm_blocking", forbidden_gemini)

    result = await tts.speak("زر الحفظ فوق يسار")

    assert result == TTSResult(success=True, provider="elevenlabs")
    assert played == ["el"]            # ElevenLabs played; Gemini never reached


@pytest.mark.asyncio
async def test_disabling_flag_forces_gemini(monkeypatch):
    """The rollback switch: try_elevenlabs=False (a falsey MUTHIS_TRY_ELEVENLABS)
    disables the primary entirely and forces Gemini — ElevenLabs never runs."""
    played = []
    tts = TTS(api_key="fake-el", gemini_api_key="fake-gem", try_elevenlabs=False)
    assert tts.try_elevenlabs is False

    def fake_gemini_synthesis(text, api_key, voice=None):
        assert api_key == "fake-gem"
        return FAKE_PCM

    def forbidden_elevenlabs(text):
        raise AssertionError("ElevenLabs must NOT run while disabled")

    async def capture_play(pcm, sample_rate):
        played.append(pcm)

    monkeypatch.setattr(tts_gemini, "synthesize_pcm_blocking", fake_gemini_synthesis)
    monkeypatch.setattr(tts, "_speak_elevenlabs", forbidden_elevenlabs)
    monkeypatch.setattr(tts, "_play_pcm", capture_play)

    result = await tts.speak("زر الحفظ فوق يسار")

    assert result == TTSResult(success=True, provider="gemini")
    assert len(played) == 1            # only the Gemini audio reached playback


@pytest.mark.asyncio
async def test_speak_never_raises_when_both_providers_fail(monkeypatch):
    """The contract survives the new order: BOTH providers exploding still returns
    TTSResult(provider='none') — speak() never raises."""
    tts = TTS(api_key="fake-el", gemini_api_key="fake-gem", try_elevenlabs=True)

    async def elevenlabs_down(text):
        raise RuntimeError("el down")

    def gemini_down(text, api_key, voice=None):
        raise RuntimeError("gem down")

    monkeypatch.setattr(tts, "_speak_elevenlabs", elevenlabs_down)
    monkeypatch.setattr(tts_gemini, "synthesize_pcm_blocking", gemini_down)

    result = await tts.speak("اختبار")   # must NOT raise

    assert isinstance(result, TTSResult)
    assert result.success is False and result.provider == "none"
    assert "gem down" in (result.error or "")  # last error retained (Gemini tried last)
