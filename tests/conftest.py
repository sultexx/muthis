"""
Shared test fixtures.

Hermeticity guard: clear the cloud-TTS env keys before EVERY test so no test ever
picks up the developer's real keys from the environment. This matters now that
ElevenLabs is the PRIMARY TTS — a leaked ELEVENLABS_API_KEY would otherwise make
a test that builds a real TTS() attempt a live WebSocket. The voice-config vars
are cleared too so the documented defaults are deterministic regardless of the
developer's .env. Tests inject the keys/voice they need explicitly via env or
constructor args.

The overlay NEON-styling vars (colors / glow / label) are cleared for the same
reason: OverlayStyle.from_env() must return the documented neon defaults in every
test regardless of the developer's shell; the styling tests set their own values
via monkeypatch AFTER this autouse fixture runs.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_cloud_tts_env(monkeypatch):
    for var in (
        "ELEVENLABS_API_KEY", "GEMINI_API_KEY", "MUTHIS_TRY_ELEVENLABS",
        "ELEVENLABS_VOICE_ID", "ELEVENLABS_MODEL_ID", "ELEVENLABS_STABILITY",
        "ELEVENLABS_SIMILARITY_BOOST", "ELEVENLABS_STYLE",
        # Overlay neon styling — deterministic defaults for from_env().
        "MUTHIS_COLOR_LINE", "MUTHIS_COLOR_ARROW", "MUTHIS_COLOR_CIRCLE",
        "MUTHIS_COLOR_RECT", "MUTHIS_COLOR_POINTER", "MUTHIS_COLOR_HIGHLIGHT",
        "MUTHIS_GLOW", "MUTHIS_GLOW_WIDTH", "MUTHIS_GLOW_INTENSITY",
        "MUTHIS_CORE_WIDTH", "MUTHIS_LABEL_FONT", "MUTHIS_LABEL_SIZE",
        "MUTHIS_LABEL_PLATE",
        # Status-indicator per-state colors + corner (batch 2-A).
        "MUTHIS_STATUS_LISTENING", "MUTHIS_STATUS_THINKING",
        "MUTHIS_STATUS_SPEAKING", "MUTHIS_STATUS_CORNER",
        # Sentence-streaming rollback flag (v5 C2) — default OFF must hold in
        # every test regardless of the developer's .env.
        "MUTHIS_STREAM_TTS",
    ):
        monkeypatch.delenv(var, raising=False)
