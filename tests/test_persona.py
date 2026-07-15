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
  * dual-action intent (TWO-PASS): a WHERE question points (highlight_target) on
    pass 1, then explains on the NEXT turn starting with the info (no filler) —
    pointing never replaces explaining,
  * verbosity SHORT cap (~40-60 words): concise small-talk, a snappy WHAT/WHY
    answer (~40-60 words / 3-4 short sentences) when asked to point / explain /
    analyze, with an explicit offer-to-elaborate — the earlier ~250-word soft cap
    (and the older 2-3 sentence / ~180-char cap) is GONE,
  * anti-laziness: a pointing reply never collapses to a bare acknowledgement,
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

# Dual-action intent is now TWO-PASS: a WHERE question is answered across two
# turns — pass 1 points, pass 2 dives straight into the explanation (start with
# the info, NO filler). An EXPLAIN-only question speaks with no highlight.
WHERE_RULE = "أشّر على مكانه عبر highlight_target"             # WHERE → still points
EXPLAIN_RULE = "جاوب بالكلام فقط ولا تستخدم highlight_target"   # EXPLAIN-only → speak only
TWO_PASS_NEXT_TURN = "في دورك التالي"                          # explain on the NEXT turn
TWO_PASS_START_WITH_INFO = "ابدأ بالمعلومة"                    # pass 2 starts with the info
DUAL_ACTION_NOT_ENOUGH = "مجرّد التأشير بدون شرح ما يكفي"       # pointing alone never suffices
# The OLD single-response wording must be GONE (it conflicted with the two-pass flow).
REMOVED_SAME_TURN_RULE = "لازم تسوّي الاثنين في نفس الدور"

# PASS 1 is point-ONLY (one job per pass): at most a one/two-word ack then the
# tool call, and NEVER any screen-narration — the leak that put the explanation
# into pass 1 and left pass 2 empty. The exact leaked phrases ("أشوف..."/"بأشّر
# على...") are now NAMED as forbidden examples.
ONE_JOB_PER_PASS = "ولكلّ دور وظيفة واحدة فقط"
PASS1_ACK_ONLY = "كلمة أو كلمتين"                       # the one/two-word ack cap
PASS1_NO_NARRATION = "ممنوع تصف الشاشة"                  # no screen-narration in pass 1
PASS1_FORBIDDEN_NARRATION = ["أشوف شاشتك", "بأشّر على"]  # the leaked phrases, now forbidden

# Anti-laziness: the explanation turn must never collapse to a bare ack.
ANTI_LAZINESS_RULE = "ممنوع الكسل"
ANTI_LAZINESS_PHRASE = "أشرت لك"   # a filler ack the rule now forbids by name

# The verbosity SHORT cap (~40-60 words) REPLACES the earlier ~250-word soft cap:
# a snappy WHAT/WHY answer (3-4 short sentences) with an explicit offer-to-
# elaborate when the topic needs more — natural for voice, never a lazy one-liner.
VERBOSITY_SECTION = "قاعدة الإسهاب — مختصر ومركّز (حوالي 40-60 كلمة)"
VERBOSITY_SMALLTALK = "في الدردشة العامة والتأكيدات البسيطة"
SHORT_CAP_TARGET = "في حدود 40-60 كلمة"                # the ~40-60-word target
WHAT_RULE = "الـ WHAT"                                  # still covers WHAT…
WHY_RULE = "والـ WHY"                                   # …and WHY
ELABORATE_OFFER = "أكمّل لك أكثر؟"                      # the explicit offer-to-elaborate

# The earlier ~250-word soft-cap wording is GONE now that the cap is ~40-60 words.
REMOVED_250_FIGURE = "250"
REMOVED_OLD_SOFT_SECTION = "كثيف ومفيد بسقف ليّن حوالي 250 كلمة"

# The exact OLD strict-brevity cap strings — these must STILL be absent.
REMOVED_CAP_BUDGET = "بحدود 180 حرف"
REMOVED_CAP_SENTENCES = "جملتين أو ثلاث"
REMOVED_CAP_SECTION = "قاعدة صارمة — الاختصار"

# Phase B-2: the draw-TOOL SELECTION rule. Two draw tools for two purposes —
# highlight_target LOCATES one UI element (where-is), draw_shapes ILLUSTRATES
# geometry / math / diagram — and BOTH share the SAME two-pass discipline. The
# rule is HONEST: shapes are approximate region support, never pixel-perfect.
TOOL_SELECT_SECTION = "اختيار أداة الرسم"                              # the new section header
TOOL_SELECT_HIGHLIGHT = "highlight_target: للإشارة إلى عنصر واجهة"      # UI element → highlight_target
TOOL_SELECT_SHAPES = "draw_shapes: للشرح الهندسي أو الرياضي أو التخطيطي"  # geometry/math/diagram → draw_shapes
TOOL_SELECT_INTENT = "اتبع نيّة المستخدم"                               # both apply → follow intent
TOOL_SELECT_BOTH_PASSES = "نفس الدورين للأداتين"                        # SAME two-pass on BOTH tools
TOOL_SELECT_HONESTY = "دعم بصري تقريبي"                                 # shapes are approximate, not pixel-perfect


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


def test_prompt_requires_point_then_explain_across_two_passes():
    # (a) A WHERE question is answered across TWO turns: pass 1 points, pass 2
    # dives STRAIGHT into the explanation (next turn, start with the info, no
    # filler). The old single-response "do both in the SAME turn" wording is GONE.
    prompt = _prompt()
    assert WHERE_RULE in prompt, "missing WHERE→point clause"
    assert TWO_PASS_NEXT_TURN in prompt, "missing the 'explain on your NEXT turn' wording"
    assert TWO_PASS_START_WITH_INFO in prompt, "missing the 'start with the info' wording"
    assert DUAL_ACTION_NOT_ENOUGH in prompt, "missing 'pointing alone is not enough'"
    # The conflicting single-response instruction must NOT survive.
    assert REMOVED_SAME_TURN_RULE not in prompt, "old single-response wording survived"
    # The EXPLAIN-only path still exists (speak with no highlight)…
    assert EXPLAIN_RULE in prompt, "missing EXPLAIN-only→speak clause"
    # …and the rules COEXIST with the unchanged persona pillars in the same prompt:
    assert "أبشر" in prompt                      # still casual Saudi dialect
    assert "بالإنجليزية" in prompt               # UI names still stay English
    assert "highlight_target" in prompt and "لا تدّعِ" in prompt  # LOOK-only honesty


def test_pass1_is_ack_only_and_forbids_narration():
    # The dual-action FIX: pass 1 (the pointing turn) is ACK-ONLY — at most a
    # one/two-word ack then highlight_target, and it must NEVER describe the
    # screen or narrate the action. This is what stopped the explanation leaking
    # into pass 1 (which then left the forced-text pass 2 empty).
    prompt = _prompt()
    assert ONE_JOB_PER_PASS in prompt, "missing the one-job-per-pass framing"
    assert PASS1_ACK_ONLY in prompt, "missing the pass-1 one/two-word ack cap"
    assert PASS1_NO_NARRATION in prompt, "missing the pass-1 no-narration rule"
    for phrase in PASS1_FORBIDDEN_NARRATION:
        assert phrase in prompt, f"missing forbidden pass-1 narration example: {phrase!r}"
    # Pass 2 still owns the explanation (next turn, start with the info); the two
    # passes never collapse into one response.
    assert TWO_PASS_NEXT_TURN in prompt and TWO_PASS_START_WITH_INFO in prompt
    assert REMOVED_SAME_TURN_RULE not in prompt, "old single-response wording survived"
    # …and it coexists with the unchanged pillars in the SAME prompt:
    assert "أبشر" in prompt                                      # casual Saudi dialect
    assert "بالإنجليزية" in prompt                               # UI names stay English
    assert "highlight_target" in prompt and "لا تدّعِ" in prompt  # LOOK-only honesty


def test_prompt_selects_draw_tool_by_intent():
    # Phase B-2: the persona teaches WHICH draw tool to use — highlight_target to
    # LOCATE a UI element (button/icon/menu/field), draw_shapes to ILLUSTRATE
    # geometry / math / diagram — with an intent tie-breaker when both could apply.
    prompt = _prompt()
    assert TOOL_SELECT_SECTION in prompt, "missing the draw-tool selection section"
    assert TOOL_SELECT_HIGHLIGHT in prompt, "missing 'UI element → highlight_target' rule"
    assert TOOL_SELECT_SHAPES in prompt, "missing 'geometry/math/diagram → draw_shapes' rule"
    assert TOOL_SELECT_INTENT in prompt, "missing the both-apply → follow-intent tie-breaker"
    # The SAME two-pass discipline governs BOTH tools (draw first, explain next
    # turn starting with the info) — it is not a highlight-only rule.
    assert TOOL_SELECT_BOTH_PASSES in prompt, "two-pass discipline not extended to draw_shapes"
    assert TWO_PASS_NEXT_TURN in prompt and TWO_PASS_START_WITH_INFO in prompt
    # HONEST accuracy: shapes are approximate region support, never pixel-perfect —
    # the spoken explanation carries the teaching.
    assert TOOL_SELECT_HONESTY in prompt, "missing the honest 'approximate, not pixel-perfect' note"
    # draw_shapes is a LOOK-only draw tool, so it is NOT one of the forbidden
    # action tools (it displays an overlay, it never clicks/types/executes).
    assert "draw_shapes" in prompt
    for tool in FORBIDDEN_ACTION_TOOLS:
        assert tool not in prompt, f"forbidden action tool leaked into prompt: {tool!r}"
    # The rule ADDS to — never DUPLICATES — the existing pillars: each governing
    # section appears exactly once, and the untouched pillars still coexist here.
    assert prompt.count(TOOL_SELECT_SECTION) == 1, "draw-tool selection section duplicated"
    assert prompt.count(VERBOSITY_SECTION) == 1, "verbosity ~40-60-word section duplicated"
    assert prompt.count("حدودك (LOOK فقط)") == 1, "LOOK-only section duplicated"
    assert SHORT_CAP_TARGET in prompt                            # ~40-60-word cap intact
    assert "أبشر" in prompt                                      # casual Saudi dialect intact
    assert "بالإنجليزية" in prompt                               # UI names stay English intact
    assert "highlight_target" in prompt and "لا تدّعِ" in prompt  # LOOK-only honesty intact


def test_prompt_drops_the_old_brevity_cap():
    # (c) The old 2-3 sentence / ~180-char strict-brevity cap is GONE — neither
    # the section header, the sentence count, nor the char budget survive.
    prompt = _prompt()
    assert REMOVED_CAP_BUDGET not in prompt, "old ~180-char cap still present"
    assert REMOVED_CAP_SENTENCES not in prompt, "old 2-3 sentence cap still present"
    assert REMOVED_CAP_SECTION not in prompt, "old strict-brevity section still present"


def test_prompt_has_short_word_cap_policy():
    # (d) The verbosity policy is now a SHORT ~40-60-word cap: concise small-talk,
    # a snappy WHAT/WHY answer (~40-60 words / 3-4 short sentences) with an explicit
    # offer to elaborate — and the earlier ~250-word figure is GONE.
    prompt = _prompt()
    assert VERBOSITY_SECTION in prompt, "missing short-cap verbosity section header"
    assert VERBOSITY_SMALLTALK in prompt, "missing the concise small-talk tier"
    assert SHORT_CAP_TARGET in prompt, "missing the ~40-60-word target clause"
    assert WHAT_RULE in prompt and WHY_RULE in prompt, "missing the WHAT/WHY coverage"
    assert ELABORATE_OFFER in prompt, "missing the explicit offer-to-elaborate"
    # The earlier ~250-word soft cap is fully gone (figure + section wording).
    assert REMOVED_250_FIGURE not in prompt, "old ~250-word figure survived the short-cap change"
    assert REMOVED_OLD_SOFT_SECTION not in prompt, "old soft-cap section header survived"
    # …and it coexists with EVERY existing pillar in the SAME prompt:
    for marker in SAUDI_DIALECT_MARKERS:
        assert marker in prompt, f"verbosity policy dropped Saudi marker {marker!r}"
    assert "بالإنجليزية" in prompt                               # UI names stay English
    assert "highlight_target" in prompt and "لا تدّعِ" in prompt  # LOOK-only honesty
    assert WHERE_RULE in prompt and EXPLAIN_RULE in prompt        # intent rules survive


def test_prompt_has_anti_laziness_rule():
    # (b) The anti-laziness rule forbids collapsing the EXPLANATION turn to a bare
    # filler ack ("أشرت لك" / "تم") — مطحس must start with the info (WHAT + WHY).
    prompt = _prompt()
    assert ANTI_LAZINESS_RULE in prompt, "missing the anti-laziness rule"
    assert ANTI_LAZINESS_PHRASE in prompt, "anti-laziness rule must name a forbidden filler ack"


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


# ─────────────────── Internal-directive obedience (v5 B3) ───────────────────


def test_persona_orders_obedience_to_internal_directives():
    # Verbosity directives ride the USER message (option A — the system prompt
    # is frozen at the composition root), so the persona must teach the model:
    # a line opening with the internal-directive marker is a SYSTEM order —
    # obey it (reply-length directives beat the default verbosity cap) and
    # never read it aloud.
    prompt = _prompt()
    assert "(توجيه داخلي" in prompt
    assert "لا تقرأه بصوت عالٍ" in prompt
    assert "تتقدّم على قاعدة الإسهاب" in prompt


# ─────────────────── Center-targeting nudge (v6 Phase A) ────────────────────


def test_prompt_has_center_targeting_nudge():
    # v6-A4: measured at 1400px the model boxed the balloon WITH its string,
    # drifting the rectangle center off the element — the persona now orders
    # aiming at the element's CENTER with a tight, no-extras box.
    prompt = _prompt()
    assert "مركز العنصر المستهدف" in prompt
    assert "لا حافته" in prompt
    assert "بلا توسيع" in prompt


# ─────────────────── Numbered-steps selection rule (v6 B3) ──────────────────


def test_prompt_selects_step_badges_for_sequential_howto():
    # A multi-step "how do I..." → ONE draw_shapes call carrying step badges
    # in execution order (auto-numbered ١٢٣ by list order), then the explain
    # pass walks the steps in the same order.
    prompt = _prompt()
    assert "step" in prompt
    assert "بترتيب التنفيذ" in prompt
    assert "تترقّم تلقائياً" in prompt
    assert "بنفس الترتيب" in prompt
