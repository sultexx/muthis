"""
test_persona.py — the Saudi persona content + safe-fallback resolver.

No network, no SDK (persona.py imports only stdlib logging). These tests pin
down the contract the wider system relies on:

  * the conversational wrapper is casual Saudi dialect (the five markers),
  * UI / menu / technical names stay in ENGLISH verbatim (the hard rule +
    the "Sketch" / "Extrude" / "Fusion 360" examples),
  * LOOK-only honesty: it points via highlight_target and NEVER claims it
    clicked / typed / executed — and no action-tool name leaks into the prompt,
  * resolve_system_prompt uses the persona on the normal path and falls back
    LOUDLY (English warning) only when the builder is empty or raises.

Run:  pytest tests/test_persona.py -q
"""

from __future__ import annotations

import logging

import pytest

from muthis import persona
from muthis.persona import build_saudi_persona_prompt, resolve_system_prompt

# A sentinel neutral fallback — stands in for claude_agent.LOOK_SYSTEM_PROMPT so
# this test never imports the SDK stack.
NEUTRAL_FALLBACK = "NEUTRAL_MSA_FALLBACK_PROMPT"

# The casual Saudi-dialect markers the persona must wear.
SAUDI_DIALECT_MARKERS = ["أبشر", "سم", "طال عمرك", "وشلونك", "عاد"]

# UI / technical names that must appear in English, verbatim, never translated.
ENGLISH_UI_TERMS = ["Sketch", "Extrude", "Fusion 360"]

# Action tools that LOOK-only forbids — none may even be NAMED in the prompt.
FORBIDDEN_ACTION_TOOLS = ["type_text", "press_hotkey", "real_click", "set_trust_mode"]


# ──────────────────────────── Content ────────────────────────────


def test_builder_returns_nonempty_string():
    prompt = build_saudi_persona_prompt()
    assert isinstance(prompt, str)
    assert prompt.strip()
    assert "مطحس" in prompt


def test_prompt_carries_saudi_dialect_markers():
    prompt = build_saudi_persona_prompt()
    for marker in SAUDI_DIALECT_MARKERS:
        assert marker in prompt, f"missing Saudi dialect marker: {marker!r}"


def test_prompt_keeps_ui_names_in_english():
    prompt = build_saudi_persona_prompt()
    # The explicit rule…
    assert "بالإنجليزية" in prompt
    # …and the concrete UI examples that must NOT be translated.
    for term in ENGLISH_UI_TERMS:
        assert term in prompt, f"missing English UI term: {term!r}"


def test_prompt_states_expert_scope():
    prompt = build_saudi_persona_prompt()
    assert "Fusion 360" in prompt
    assert "hardware/embedded" in prompt


def test_prompt_is_look_only_and_honest():
    prompt = build_saudi_persona_prompt()
    # The two permitted tools are named…
    assert "highlight_target" in prompt
    assert "request_screen_refresh" in prompt
    # …honesty clause: never claim an action it cannot perform.
    assert "لا تدّعِ" in prompt
    # …and no action-tool name leaks in (LOOK-only hard boundary).
    for tool in FORBIDDEN_ACTION_TOOLS:
        assert tool not in prompt, f"forbidden action tool leaked into prompt: {tool!r}"


# ──────────────────────────── Resolver ────────────────────────────


def test_resolve_uses_saudi_persona_on_normal_path():
    # Normal path: the resolver returns the Saudi persona verbatim, never the
    # neutral fallback.
    resolved = resolve_system_prompt(NEUTRAL_FALLBACK)
    assert resolved == build_saudi_persona_prompt()
    assert resolved != NEUTRAL_FALLBACK
    for marker in SAUDI_DIALECT_MARKERS:
        assert marker in resolved


def test_resolve_falls_back_loudly_on_empty(monkeypatch, caplog):
    monkeypatch.setattr(persona, "build_saudi_persona_prompt", lambda: "   ")
    with caplog.at_level(logging.WARNING, logger="muthis.persona"):
        resolved = resolve_system_prompt(NEUTRAL_FALLBACK)
    assert resolved == NEUTRAL_FALLBACK
    # The fallback must be LOUD, not silent.
    assert any(
        "falling back to LOOK_SYSTEM_PROMPT" in rec.getMessage()
        for rec in caplog.records
    ), "empty persona fallback was not logged as a WARNING"


def test_resolve_falls_back_loudly_on_exception(monkeypatch, caplog):
    def _boom() -> str:
        raise RuntimeError("persona construction blew up")

    monkeypatch.setattr(persona, "build_saudi_persona_prompt", _boom)
    with caplog.at_level(logging.WARNING, logger="muthis.persona"):
        resolved = resolve_system_prompt(NEUTRAL_FALLBACK)
    assert resolved == NEUTRAL_FALLBACK
    assert any(
        "falling back to LOOK_SYSTEM_PROMPT" in rec.getMessage()
        for rec in caplog.records
    ), "raising persona fallback was not logged as a WARNING"
