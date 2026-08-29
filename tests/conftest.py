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
        # Live-captions rollback flag (v6 C) — cleared so the documented
        # default (ON) holds deterministically.
        "MUTHIS_CAPTIONS",
        # Cinematic-spotlight knobs (v6 D) — default OFF / alpha 0.30.
        "MUTHIS_FOCUS_DIM", "MUTHIS_FOCUS_ALPHA",
        # Whiteboard rollback flag (v7 Phase 2) — cleared so the documented
        # default (ON) holds deterministically.
        "MUTHIS_WHITEBOARD",
        # Barge-in rollback flag (v7 Phase 3) — cleared, documented default ON.
        "MUTHIS_BARGE_IN",
        # Search-provider selection + keys (V2 Phase-2 M2, DEC-18): cleared for
        # the same reason as the TTS keys — a developer's real key in the shell
        # would otherwise pick a LIVE provider (and change which one answers) in
        # a test that must deterministically see "no provider configured".
        "MUTHIS_SEARCH_PROVIDER", "TAVILY_API_KEY", "TAVILY_BASE_URL",
        "BRAVE_API_KEY", "BRAVE_BASE_URL", "SEARXNG_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _durable_log_never_touches_the_real_home(monkeypatch, tmp_path):
    """No test may write the durable log into the DEVELOPER'S OWN HOME.

    Same hermeticity concern as the key-clearing fixture above, one surface
    over. `configure_logging()` now attaches a rotating file log under
    `~/.muthis/logs/`, and three existing tests call it with no directory — so
    without this the suite writes its own noise into a real user path AND leaves
    a live handler on the root logger for every test that follows.

    The module attribute is patched rather than the constant imported into a
    test module, so a test that deliberately asserts the SHIPPED default (it
    lives outside the repo) still reads the real value it bound at import."""
    monkeypatch.setattr("muthis.logging_policy.LOG_DIR", tmp_path / "muthis-logs")
