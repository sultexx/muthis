"""
test_persona.py — the (general-purpose) Saudi persona content, the safe-fallback
resolver, and the sent-image coordinate-space injection.

No network, no SDK (persona.py imports only stdlib logging). These tests pin
down the contract the wider system relies on:

  * the conversational wrapper is casual Saudi dialect (the five markers),
  * UI / menu / technical names stay in ENGLISH verbatim (the hard rule +
    the "Sketch" / "Extrude" / "Fusion 360" examples),
  * GENERAL-PURPOSE scope: VS Code / web / files alongside Fusion 360 — مطحس no
    longer hard-centers 3D modeling,
  * the EXACT sent-image pixel dimensions are injected (the coordinate space),
  * LOOK-only honesty: it points via highlight_target and NEVER claims it
    clicked / typed / executed — and no action-tool name leaks into the prompt,
  * resolve_system_prompt uses the persona on the normal path and falls back
    LOUDLY (English warning) only when the builder is empty or raises — and the
    dims clause is appended even on the fallback path.

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

# The sent-image dimensions used throughout (a 1080p frame capped at 1280 wide).
SENT_W, SENT_H = 1280, 720

# The casual Saudi-dialect markers the persona must wear.
SAUDI_DIALECT_MARKERS = ["أبشر", "سم", "طال عمرك", "وشلونك", "عاد"]

# UI / technical names that must appear in English, verbatim, never translated.
ENGLISH_UI_TERMS = ["Sketch", "Extrude", "Fusion 360"]

# General-purpose domains that prove مطحس is NOT a Fusion-only assistant.
GENERAL_PURPOSE_MARKERS = ["VS Code", "الويب", "الملفات"]

# Action tools that LOOK-only forbids — none may even be NAMED in the prompt.
FORBIDDEN_ACTION_TOOLS = ["type_text", "press_hotkey", "real_click", "set_trust_mode"]

# Intent-aware tool guidance: the three rules the prompt must spell out so مطحس
# points only when asked WHERE, speaks only when asked to EXPLAIN, and does both
# when asked for both. Exact clauses (asserted verbatim).
WHERE_RULE = "أشّر على مكانه عبر highlight_target"            # WHERE → point
EXPLAIN_RULE = "جاوب بالكلام فقط ولا تستخدم highlight_target"  # EXPLAIN → speak only
BOTH_RULE = "سوِّ الاثنين: أشّر عبر highlight_target واشرح بصوتك"  # BOTH → point AND explain


def _prompt() -> str:
    return build_saudi_persona_prompt(SENT_W, SENT_H)


# ──────────────────────────── Content ────────────────────────────


def test_builder_returns_nonempty_string():
    prompt = _prompt()
    assert isinstance(prompt, str)
    assert prompt.strip()
    assert "مطحس" in prompt


def test_prompt_carries_saudi_dialect_markers():
    prompt = _prompt()
    for marker in SAUDI_DIALECT_MARKERS:
        assert marker in prompt, f"missing Saudi dialect marker: {marker!r}"


def test_prompt_keeps_ui_names_in_english():
    prompt = _prompt()
    # The explicit rule…
    assert "بالإنجليزية" in prompt
    # …and the concrete UI examples that must NOT be translated.
    for term in ENGLISH_UI_TERMS:
        assert term in prompt, f"missing English UI term: {term!r}"


def test_prompt_is_general_purpose_not_fusion_centric():
    prompt = _prompt()
    # Fusion 360 is still present — but as ONE capability among many…
    assert "Fusion 360" in prompt
    # …and coding / web / file management appear too, so 3D modeling is no
    # longer the centre of gravity.
    for marker in GENERAL_PURPOSE_MARKERS:
        assert marker in prompt, f"missing general-purpose marker: {marker!r}"
    # The identity line is a general assistant, not an engineering one.
    assert "مساعد صوتي ذكي عام" in prompt


def test_prompt_injects_exact_sent_image_dimensions():
    # The coordinate-space contract: the EXACT sent dims appear in the prompt…
    prompt = _prompt()
    assert str(SENT_W) in prompt and str(SENT_H) in prompt
    # …and they are dynamic — different dims produce different text.
    other = build_saudi_persona_prompt(1920, 1080)
    assert "1920" in other and "1080" in other
    assert "1280" not in other


def test_prompt_is_look_only_and_honest():
    prompt = _prompt()
    # The two permitted tools are named…
    assert "highlight_target" in prompt
    assert "request_screen_refresh" in prompt
    # …honesty clause: never claim an action it cannot perform.
    assert "لا تدّعِ" in prompt
    # …and no action-tool name leaks in (LOOK-only hard boundary).
    for tool in FORBIDDEN_ACTION_TOOLS:
        assert tool not in prompt, f"forbidden action tool leaked into prompt: {tool!r}"


def test_prompt_has_intent_aware_tool_guidance():
    prompt = _prompt()
    # The three intent rules are all present and explicit…
    assert WHERE_RULE in prompt, "missing WHERE→point rule"
    assert EXPLAIN_RULE in prompt, "missing EXPLAIN→speak-only rule"
    assert BOTH_RULE in prompt, "missing BOTH→point-and-explain rule"
    # …and they COEXIST with the unchanged persona pillars in the same prompt:
    assert "أبشر" in prompt                      # still casual Saudi dialect
    assert "بالإنجليزية" in prompt               # UI names still stay English
    assert "highlight_target" in prompt and "لا تدّعِ" in prompt  # LOOK-only honesty


# ──────────────────────────── Resolver ────────────────────────────


def test_resolve_uses_saudi_persona_on_normal_path():
    # Normal path: the resolver returns the Saudi persona verbatim, never the
    # neutral fallback.
    resolved = resolve_system_prompt(NEUTRAL_FALLBACK, SENT_W, SENT_H)
    assert resolved == build_saudi_persona_prompt(SENT_W, SENT_H)
    assert resolved != NEUTRAL_FALLBACK
    for marker in SAUDI_DIALECT_MARKERS:
        assert marker in resolved
    assert str(SENT_W) in resolved and str(SENT_H) in resolved


def test_resolve_falls_back_loudly_on_empty(monkeypatch, caplog):
    monkeypatch.setattr(persona, "build_saudi_persona_prompt", lambda w, h: "   ")
    with caplog.at_level(logging.WARNING, logger="muthis.persona"):
        resolved = resolve_system_prompt(NEUTRAL_FALLBACK, SENT_W, SENT_H)
    # The fallback body is used, with the dims clause appended so the coordinate
    # space stays defined even off the Saudi-persona path.
    assert NEUTRAL_FALLBACK in resolved
    assert str(SENT_W) in resolved and str(SENT_H) in resolved
    # The fallback must be LOUD, not silent.
    assert any(
        "falling back to LOOK_SYSTEM_PROMPT" in rec.getMessage()
        for rec in caplog.records
    ), "empty persona fallback was not logged as a WARNING"


def test_resolve_falls_back_loudly_on_exception(monkeypatch, caplog):
    def _boom(sent_width, sent_height) -> str:
        raise RuntimeError("persona construction blew up")

    monkeypatch.setattr(persona, "build_saudi_persona_prompt", _boom)
    with caplog.at_level(logging.WARNING, logger="muthis.persona"):
        resolved = resolve_system_prompt(NEUTRAL_FALLBACK, SENT_W, SENT_H)
    assert NEUTRAL_FALLBACK in resolved
    assert str(SENT_W) in resolved and str(SENT_H) in resolved
    assert any(
        "falling back to LOOK_SYSTEM_PROMPT" in rec.getMessage()
        for rec in caplog.records
    ), "raising persona fallback was not logged as a WARNING"
