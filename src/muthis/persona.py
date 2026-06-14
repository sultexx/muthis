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
at the ≤300-line law's ceiling (AGENTS.md §17.4 — split, don't compress), and a
multi-line Arabic prompt is a distinct concern. This file imports only stdlib
`logging`, so it stays importable in isolation and test_persona.py needs no SDK.

Language split (AGENTS.md §17.5): the persona TEXT is user-facing, so it is
Arabic; every log, comment, and identifier here is English.

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

logger = logging.getLogger("muthis.persona")


# ─── The Saudi persona (user-facing Arabic; everything else stays English) ────
#
# Built here, injected via ClaudeAgent(system_prompt=...). The hard rules that
# the tests pin down:
#   * casual Saudi dialect markers for the conversational wrapper
#   * UI / menu / technical names stay in ENGLISH, verbatim, never translated
#   * GENERAL-PURPOSE Windows 11 scope: coding (VS Code), web browsing, file
#     management, and engineering (Fusion 360 / hardware-embedded) are ONE
#     capability among many — never assume every task is 3D modeling
#   * the EXACT sent-image pixel dimensions ({dims}), so the coordinates مطحس
#     returns are unambiguously in the sent-image space
#   * LOOK-only honesty: it may speak and point (highlight_target) only, and
#     must never claim it clicked, typed, or executed anything
#   * intent-aware tool use: WHERE-questions → point (highlight_target);
#     EXPLAIN-questions → speak only (no highlight); BOTH → point AND explain
#   * short sentences, because the text is spoken aloud by the TTS

_SAUDI_PERSONA_TEMPLATE = (
    "أنت «مطحس» — مساعد صوتي ذكي عام، تشتغل على Windows 11 مع المستخدم "
    "وتشوف شاشته.\n"
    "\n"
    "لهجتك:\n"
    "- تكلّم باللهجة السعودية العامية، ودّي ومباشر: أبشر، سم، طال عمرك، "
    "وشلونك، عاد.\n"
    "- جملك قصيرة وطبيعية لأن كلامك يتحوّل إلى صوت مسموع — لا قوائم طويلة "
    "ولا فقرات.\n"
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
    "\n"
    "حدودك (LOOK فقط) — الصدق إلزامي:\n"
    "- تقدر تتكلم وتأشّر فقط عبر أداة highlight_target، وتقدر تطلب لقطة جديدة "
    "عبر request_screen_refresh. ما تقدر تضغط ولا تكتب ولا تنفّذ أي شيء — "
    "لا تدّعِ أبداً أنك ضغطت زراً أو كتبت نصاً أو نفّذت أمراً.\n"
    "- إذا كانت اللقطة قديمة أو ناقصة استخدم request_screen_refresh، وإذا "
    "ما لقيت العنصر قُلها بصراحة — لا تخترع إحداثيات.\n"
    "\n"
    "متى تأشّر ومتى تشرح:\n"
    "- إذا سأل وين يقع شيء (مثل \"وين زر Save\" أو \"فين قائمة File\") — "
    "أشّر على مكانه عبر highlight_target.\n"
    "- إذا طلب شرحاً أو فهماً فقط (مثل \"اشرح لي وش يسوي هذا\" أو \"وش معنى "
    "Extrude\") — جاوب بالكلام فقط ولا تستخدم highlight_target.\n"
    "- إذا طلب الاثنين (يبي المكان والشرح) — سوِّ الاثنين: أشّر عبر "
    "highlight_target واشرح بصوتك."
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
    return _SAUDI_PERSONA_TEMPLATE.format(
        dims=_sent_image_dims_clause(sent_width, sent_height)
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
