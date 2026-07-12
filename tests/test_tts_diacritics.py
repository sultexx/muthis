"""
test_tts_diacritics.py — speech-only Saudi-word diacritization (bug 3).

Two guarantees are pinned here:

  1. apply_diacritics vowelizes the key persona words for the TTS engines, and
     does it with WHOLE-WORD matching so short keys like "سم" NEVER corrupt
     larger words (اسم / قسم / جسم / موسم / بسم).

  2. The diacritics are SPEECH-ONLY: speak() sends the vowelized COPY to whichever
     engine runs (ElevenLabs PRIMARY, Gemini FALLBACK — the shared choke point),
     but the caller's clean text is never mutated, and the harakat NEVER appear in
     persona.py output — which the model reads and writes back into history.
     Baking tashkeel into the prompt/history would corrupt the model's reasoning,
     so that boundary is asserted explicitly.

No network, no audio device: the engine seams are monkeypatched and the text they
receive is captured. Env keys are cleared by tests/conftest.py.

Run:  pytest tests/test_tts_diacritics.py -q
"""

from __future__ import annotations

import re

import pytest

from muthis import persona, tts_gemini
from muthis.tts import TTS, TTSResult
from muthis.tts_diacritics import apply_diacritics

# Arabic short-vowel marks (tashkeel) + superscript alef. Their PRESENCE proves
# text was diacritized; the speech FORMS' ABSENCE in persona output is the hard
# boundary. NB: a blanket "no harakat" check on the persona would be WRONG —
# ordinary written Arabic carries incidental tanwin/shadda (أبداً، تدّعِ); the
# real guard is that the speech-only MAP FORMS never leak in (see last test).
_HARAKAT_RE = re.compile(r"[ً-ْٰ]")


def _has_harakat(text: str) -> bool:
    return bool(_HARAKAT_RE.search(text))


# ──────────────────────────── the pure helper ────────────────────────────


def test_key_words_get_diacritized():
    assert apply_diacritics("أبشر") == "أَبْشِر"
    assert apply_diacritics("سم") == "سِمّ"
    assert apply_diacritics("طال عمرك") == "طال عُمرك"


def test_diacritics_apply_inside_a_sentence():
    out = apply_diacritics("أبشر، سم طال عمرك يا الغالي")
    assert "أَبْشِر" in out
    assert "سِمّ" in out
    assert "طال عُمرك" in out


@pytest.mark.parametrize("word", ["اسم", "قسم", "جسم", "موسم", "بسم"])
def test_substring_match_never_corrupts_larger_words(word):
    """The سم trap: a naive str.replace would mangle these. Whole-word matching
    leaves them byte-for-byte untouched, alone and inside a sentence."""
    assert apply_diacritics(word) == word
    assert apply_diacritics(f"هذا {word} واضح") == f"هذا {word} واضح"


def test_standalone_word_fires_next_to_punctuation():
    # Bounded by punctuation / brackets (NOT Arabic letters) → it MUST still fire.
    assert apply_diacritics("سم.") == "سِمّ."
    assert apply_diacritics("(سم)") == "(سِمّ)"


def test_apply_is_a_no_op_when_there_is_nothing_to_change():
    assert apply_diacritics("") == ""
    src = "نص بدون كلمات مفتاحية"
    assert apply_diacritics(src) == src   # no keys present → identical string


# ──────────────────── speech-only at the TTS choke point ────────────────────


@pytest.mark.asyncio
async def test_elevenlabs_receives_the_diacritized_copy(monkeypatch):
    """PRIMARY path: the text handed to ElevenLabs is the vowelized COPY."""
    seen = {}
    tts = TTS(api_key="fake-el", gemini_api_key="fake-gem")

    async def capture_elevenlabs(text):
        seen["text"] = text

    monkeypatch.setattr(tts, "_speak_elevenlabs", capture_elevenlabs)

    result = await tts.speak("أبشر، وين زر الحفظ")

    assert result == TTSResult(success=True, provider="elevenlabs")
    assert _has_harakat(seen["text"]), "ElevenLabs got un-diacritized text"
    assert "أَبْشِر" in seen["text"]


@pytest.mark.asyncio
async def test_gemini_fallback_also_receives_the_diacritized_copy(monkeypatch):
    """FALLBACK path: Gemini gets the vowelized COPY too — the diacritics live at
    the shared choke point, so both engines benefit."""
    seen = {}
    tts = TTS(api_key=None, gemini_api_key="fake-gem")   # ElevenLabs unkeyed → Gemini

    def capture_gemini(text, api_key, voice=None):
        seen["text"] = text
        return b"\x01\x02" * 64

    monkeypatch.setattr(tts_gemini, "synthesize_pcm_blocking", capture_gemini)
    monkeypatch.setattr(tts, "_play_wav_blocking", lambda wav: None)

    result = await tts.speak("سم طال عمرك")

    assert result == TTSResult(success=True, provider="gemini")
    assert "سِمّ" in seen["text"] and "طال عُمرك" in seen["text"]


@pytest.mark.asyncio
async def test_speak_does_not_mutate_the_caller_text(monkeypatch):
    """Diacritization is on a COPY: the clean string the caller passed in is
    untouched, so what the orchestrator keeps (and could store to history) stays
    clean unvowelized text."""
    seen = {}
    tts = TTS(api_key="fake-el", gemini_api_key="fake-gem")

    async def capture_elevenlabs(text):
        seen["text"] = text

    monkeypatch.setattr(tts, "_speak_elevenlabs", capture_elevenlabs)

    clean = "أبشر"
    await tts.speak(clean)

    assert clean == "أبشر"              # the caller's value was never mutated
    assert not _has_harakat(clean)       # …and is still clean
    assert _has_harakat(seen["text"])    # only the engine's COPY is vowelized


# ──────────── the hard boundary: diacritics never reach the model ────────────


def test_persona_keeps_map_words_clean_never_voweled():
    """The model READS the persona and WRITES into history; both must stay clean
    unvowelized Arabic. If the speech forms ever leaked into persona.py the model
    would imitate them and corrupt its own output — so the persona names the key
    words in CLEAN form only, never in their speech (map-value) form."""
    prompt = persona.build_saudi_persona_prompt(1280, 720)
    # Clean keys ARE present (that is what the model reads/writes)…
    for clean in ("أبشر", "سم", "طال عمرك"):
        assert clean in prompt, f"persona dropped clean key {clean!r}"
    # …and the SPEECH-only vowelized forms are NOWHERE in the persona.
    for voweled in ("أَبْشِر", "سِمّ", "طال عُمرك"):
        assert voweled not in prompt, f"speech-only form {voweled!r} leaked into persona"
    # Proof the persona is the CLEAN source: applying the speech map WOULD change
    # it (the clean keys are present and would get vowelized for speech).
    assert apply_diacritics(prompt) != prompt
