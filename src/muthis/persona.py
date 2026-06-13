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
The fallback string is a parameter (never imported here) so this module keeps
zero coupling to claude_agent.py and its SDK stack.
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
#   * expert scope: Fusion 360 3D modeling, coding, hardware/embedded
#   * LOOK-only honesty: it may speak and point (highlight_target) only, and
#     must never claim it clicked, typed, or executed anything
#   * short sentences, because the text is spoken aloud by the TTS

_SAUDI_PERSONA_PROMPT = (
    "أنت «مطحس» — مساعد هندسي صوتي خبير، تشتغل على Windows 11 مع مهندس حاسب.\n"
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
    "و\"Fusion 360\" — لا تترجمها أبداً. اللهجة السعودية غلافٌ للكلام حول "
    "هذه المصطلحات، وليست بديلاً عنها.\n"
    "\n"
    "خبرتك:\n"
    "- خبير في النمذجة ثلاثية الأبعاد في Fusion 360، والبرمجة، وتكامل العتاد "
    "والأنظمة المدمجة (hardware/embedded) — أعطِ إرشاداً بمستوى خبير.\n"
    "\n"
    "حدودك (LOOK فقط) — الصدق إلزامي:\n"
    "- تقدر تتكلم وتأشّر فقط عبر أداة highlight_target، وتقدر تطلب لقطة جديدة "
    "عبر request_screen_refresh. ما تقدر تضغط ولا تكتب ولا تنفّذ أي شيء — "
    "لا تدّعِ أبداً أنك ضغطت زراً أو كتبت نصاً أو نفّذت أمراً.\n"
    "- إذا كانت اللقطة قديمة أو ناقصة استخدم request_screen_refresh، وإذا "
    "ما لقيت العنصر قُلها بصراحة — لا تخترع إحداثيات."
)


def build_saudi_persona_prompt() -> str:
    """Return the Saudi-dialect persona system prompt for مطحس.

    A function (not a bare constant) so future logic — e.g. folding in live
    app state — has a home without changing the call sites. Today it returns
    the frozen prompt above.
    """
    return _SAUDI_PERSONA_PROMPT


def resolve_system_prompt(fallback_prompt: str) -> str:
    """Resolve the system prompt ClaudeAgent will send as `system=`.

    Normal path → the Saudi persona. The neutral `fallback_prompt` (the
    caller passes claude_agent.LOOK_SYSTEM_PROMPT) is used ONLY when the
    builder returns empty or raises, and always with a loud English warning so
    a regression to Modern Standard Arabic can't hide. Never returns "".
    """
    try:
        prompt = build_saudi_persona_prompt()
    except Exception as exc:  # noqa: BLE001 — resolution must never crash wiring
        logger.warning(
            "Saudi persona builder raised (%s: %s) — falling back to "
            "LOOK_SYSTEM_PROMPT (neutral MSA). Muthis will reply in Modern "
            "Standard Arabic, NOT Saudi dialect.",
            type(exc).__name__, exc,
        )
        return fallback_prompt

    if not prompt.strip():
        logger.warning(
            "Saudi persona prompt empty — falling back to LOOK_SYSTEM_PROMPT "
            "(neutral MSA). Muthis will reply in Modern Standard Arabic, NOT "
            "Saudi dialect."
        )
        return fallback_prompt

    return prompt


__all__ = ["build_saudi_persona_prompt", "resolve_system_prompt"]
