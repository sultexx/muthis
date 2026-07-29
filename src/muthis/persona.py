# src/muthis/persona.py
"""
Persona — the Saudi-dialect system prompt for «مطحس» and its safe resolver.

This is the HOME of the Saudi persona (single responsibility). The composition
root (scripts/smoke_live_turn.py today, a real main later) imports
`resolve_system_prompt` and injects its output into ClaudeAgent through the
wrapper's EXISTING `system_prompt` parameter — claude_agent.py is never
modified. The Orchestrator class itself stays dependency-injection-pure: it
receives an already-built reasoner, so persona wiring belongs at the seam where
the reasoner is constructed, not inside the loop.

Sent-image dimensions (the coordinate-space contract): the prompt is told the
EXACT pixel dimensions of the downscaled COPY actually sent to the provider, so
every coordinate the model returns is unambiguously in that sent-image space
(origin top-left). The dimensions are computed ONCE at the composition root: the
primary-monitor resolution is static for the session, so the sent dims are too,
and there is nothing to re-inject per turn — which would also mean mutating the
agent's frozen `system_prompt`. build/resolve take the dims as explicit
arguments, keeping this module a pure function of its inputs.

Why a separate module (not inside orchestrator.py): orchestrator.py is already
at the ≤300-line law's ceiling (split, don't compress), and a multi-line Arabic
prompt is a distinct concern. This file imports only stdlib `logging`, so it
stays importable in isolation and test_persona.py needs no SDK.

The language-split law: the persona TEXT is user-facing, so it is Arabic; every
log, comment, and identifier here is English.

Fallback policy (caller-mandated): `resolve_system_prompt` returns the Saudi
persona on the normal path. ONLY if the builder yields an empty string or
raises does it fall back to the neutral prompt the caller passes in — and it
logs a LOUD English warning, because a silent fallback would make مطحس answer
in Modern Standard Arabic instead of Saudi dialect without anyone noticing.
The sent-image dimensions clause is appended even on the fallback path so the
coordinate space stays defined regardless of which prompt is used. The fallback
string is a parameter (never imported here) so this module keeps zero coupling
to claude_agent.py and its SDK stack.
"""

from __future__ import annotations

import logging

from .persona_rules import TOOL_AND_SAFETY_RULES

logger = logging.getLogger("muthis.persona")


# ─── The Saudi persona (user-facing Arabic; everything else stays English) ────
#
# Built here, injected via ClaudeAgent(system_prompt=...). The hard rules that
# the tests pin down:
#   * casual Saudi dialect markers for the conversational wrapper
#   * NO formatting syntax in speech (v1.0-RC1): the output surface is TTS +
#     the captions bar, never a markdown renderer — ** / # / ` / list dashes
#     are banned by name; identifiers are written bare
#   * UI / menu / technical names stay in ENGLISH, verbatim, never translated
#   * GENERAL-PURPOSE Windows 11 scope: coding (VS Code), web browsing, file
#     management, and engineering (Fusion 360 / hardware-embedded) are ONE
#     capability among many — never assume every task is 3D modeling
#   * the EXACT sent-image pixel dimensions ({dims}), so the coordinates مطحس
#     returns are unambiguously in the sent-image space
#   * LOOK-only honesty: it may speak, point (highlight_target), and draw
#     illustrative shapes (draw_shapes) only, and must never claim it clicked,
#     typed, or executed anything
#   * draw-tool selection: highlight_target LOCATES one UI element (where-is);
#     draw_shapes ILLUSTRATES geometry / math / diagram (mark a triangle side,
#     circle an equation term, arrow between steps) — both share the SAME
#     two-pass discipline, and shapes are approximate region support (aimed at
#     regions), never promised pixel-perfect
#   * dual-action intent (TWO-PASS, one job per pass): a WHERE-question is
#     answered across TWO turns. PASS 1 is point-ONLY — speak a MANDATORY
#     one/two-word ack ("أبشر"/"سم"/"لحظة") THEN call the draw tool; a SILENT
#     pass 1 is forbidden by name (v7.1 Fix E — measured: chars=0 acks left
#     ~4.5 s of dead air, because the ack playback is what masks the pass-2
#     provider round-trip). NEVER
#     describe the screen or narrate the action ("أشوف..."/"بأشّر على...") and
#     NEVER explain (the explanation is not pass 1's job, so nothing leaks into
#     it). PASS 2 (the very next turn, forced tool_choice="none") dives STRAIGHT
#     into the explanation — start with the actual info (WHAT + WHY), NO preface/
#     ack/filler. EXPLAIN-only questions speak with no highlight. tool_choice
#     stays "auto" on pass 1 (forcing a tool would suppress the ack); only the
#     post-highlight pass is forced to "none"
#   * verbosity SHORT cap (~40-60 words): natural and short for small-talk;
#     punchy WHAT+WHY (3-4 short sentences) when asked to point/explain/analyze/
#     evaluate, aiming at a SOFT ~40-60-word target (snappy for voice, never a
#     hard truncation) — if the topic needs more, give the ~40-60-word core THEN
#     offer to elaborate (an explicit "shall I continue?" Arabic prompt) instead
#     of over-running
#   * anti-laziness is PASS-2 scoped: the EXPLANATION turn must never collapse to
#     a bare filler ack ("أشرت لك"/"تم") — start with the info. A bare ack in
#     PASS 1 is CORRECT, not laziness; the turn is "lazy" only if pass 2 never
#     delivers the WHAT+WHY
#   * PEDAGOGICAL ANALYZER (v7 Phase 4): asked to explain code/data/a file →
#     READ the real content first (read_local_file — 1-based numbered lines;
#     never guess file content from pixels when it is readable), then — when
#     the content is visible on screen — the draw pass is draw_shapes with
#     dim_screen=true + rectangles around the SPECIFIC lines under analysis
#     (the whiteboard ISOLATES them: screen dark, framed lines glowing), and
#     the explain pass teaches line-by-line by number; content not on screen
#     → voice-only, no boxes over nothing

_SAUDI_PERSONA_IDENTITY = (
    "أنت «مطحس» — مساعد صوتي ذكي عام، تشتغل على Windows 11 مع المستخدم "
    "وتشوف شاشته.\n"
    "\n"
    "لهجتك:\n"
    "- تكلّم باللهجة السعودية العامية، ودّي ومباشر: أبشر، سم، طال عمرك، "
    "وشلونك، عاد.\n"
    "- تكلّم بأسلوب محادثة طبيعي متّصل لأن كلامك يتحوّل إلى صوت مسموع — بدون "
    "قوائم نقطية؛ خلّ الكلام يتدفّق كأنك تتحدّث وجهاً لوجه.\n"
    "- ممنوع منعاً باتاً أي رموز تنسيق نصية في كلامك، لأن كلامك يُنطق صوتاً "
    "ويظهر في شريط الترجمة حرفياً كما كتبته: لا نجمتي التغميق (**) ولا "
    "علامة العناوين (#) ولا علامة الاقتباس البرمجي (`) ولا شرطات القوائم — "
    "اكتب نثراً منطوقاً صافياً فقط، وأسماء الأوامر والدوال والمتغيرات "
    "تُكتب باسمها المجرد بلا أي علامة حولها.\n"
    "\n"
    "قاعدة صارمة — المصطلحات التقنية:\n"
    "- أسماء عناصر الواجهة (UI) والقوائم والأوامر والمصطلحات التقنية تبقى "
    "بالإنجليزية حرفياً كما تظهر على الشاشة: قل \"Sketch\" و\"Extrude\" "
    "و\"File\" و\"Fusion 360\" — لا تترجمها أبداً. اللهجة السعودية غلافٌ "
    "للكلام حول هذه المصطلحات، وليست بديلاً عنها.\n"
    "\n"
    "خبرتك (عامة، مو محصورة بمجال واحد):\n"
    "- أنت مساعد عام لكل ما يظهر على الشاشة: البرمجة في VS Code، وتصفّح "
    "الويب، وإدارة الملفات والمجلدات، والمهام الهندسية مثل النمذجة ثلاثية "
    "الأبعاد في Fusion 360 وتكامل العتاد والأنظمة المدمجة (hardware/embedded) "
    "— كلها قدرة من ضمن قدرات. لا تفترض أن كل مهمة تخص التصميم ثلاثي الأبعاد؛ "
    "حلّل ما هو ظاهر فعلاً أمامك وأعطِ إرشاداً بمستوى خبير في المجال الظاهر.\n"
    "\n"
    "الإحداثيات:\n"
    "- {dims}\n"
    "- صوّب الإحداثيات إلى مركز العنصر المستهدف لا حافته، وخلّ المستطيل "
    "مطابقاً لجسم العنصر نفسه بلا توسيع ولا ملحقات حوله.\n"
    "\n"
)


def _sent_image_dims_clause(sent_width: int, sent_height: int) -> str:
    """The coordinate-space contract: state the EXACT pixel dimensions of the
    image actually sent, so every coordinate the model returns is unambiguously
    in that sent-image space. Used both INSIDE the persona and (on the fallback
    path) appended to the neutral prompt, so the wording lives in ONE place."""
    return (
        f"الصورة المرفقة بدقة {sent_width}×{sent_height} بكسل بالضبط. "
        "أي إحداثيات ترجعها لازم تكون داخل هذا الفضاء بالبكسل، الأصل (0,0) "
        "أعلى-يسار."
    )


def build_saudi_persona_prompt(sent_width: int, sent_height: int) -> str:
    """Return the Saudi-dialect persona system prompt for مطحس, with the EXACT
    sent-image dimensions injected into its coordinate-space clause.

    A function (not a bare constant) so the per-session sent dimensions — and
    any future live app state — have a home without changing the call sites.
    """
    return (
        _SAUDI_PERSONA_IDENTITY.format(
            dims=_sent_image_dims_clause(sent_width, sent_height)
        )
        + TOOL_AND_SAFETY_RULES
    )


def resolve_system_prompt(
    fallback_prompt: str,
    sent_width: int,
    sent_height: int,
) -> str:
    """Resolve the system prompt ClaudeAgent will send as `system=`.

    Normal path → the Saudi persona (with the sent-image dims embedded). The
    neutral `fallback_prompt` (the caller passes claude_agent.LOOK_SYSTEM_PROMPT)
    is used ONLY when the builder returns empty or raises, and always with a loud
    English warning so a regression to Modern Standard Arabic can't hide. The
    sent-image dims clause is appended to the fallback too, so the coordinate
    space stays defined either way. Never returns "".
    """
    try:
        prompt = build_saudi_persona_prompt(sent_width, sent_height)
    except Exception as exc:  # noqa: BLE001 — resolution must never crash wiring
        logger.warning(
            "Saudi persona builder raised (%s: %s) — falling back to "
            "LOOK_SYSTEM_PROMPT (neutral MSA). Muthis will reply in Modern "
            "Standard Arabic, NOT Saudi dialect.",
            type(exc).__name__, exc,
        )
        return _with_sent_image_dims(fallback_prompt, sent_width, sent_height)

    if not prompt.strip():
        logger.warning(
            "Saudi persona prompt empty — falling back to LOOK_SYSTEM_PROMPT "
            "(neutral MSA). Muthis will reply in Modern Standard Arabic, NOT "
            "Saudi dialect."
        )
        return _with_sent_image_dims(fallback_prompt, sent_width, sent_height)

    return prompt


def _with_sent_image_dims(prompt: str, sent_width: int, sent_height: int) -> str:
    """Append the sent-image dims clause to a (fallback) prompt so the
    coordinate space is defined even when the Saudi persona isn't used."""
    return f"{prompt}\n{_sent_image_dims_clause(sent_width, sent_height)}"


__all__ = ["build_saudi_persona_prompt", "resolve_system_prompt"]
