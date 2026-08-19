# src/muthis/kernel/navigator_service.py
"""
Navigator v1's SERVICING — one tool call in, one Arabic tool_result out
(DEC-65/DEC-66, T4).

A TRANSLATION LAYER, AND NOTHING ELSE. A model-facing call arrives; this turns it
into a `TransitionRequest`, hands it to the ONE evaluation point, and renders the
outcome. It decides nothing — every allow/refuse ruling lives in `ModeAuthority`.

AND IT **CANNOT** BYPASS THAT POINT, WHICH IS A PROPERTY RATHER THAN A HABIT.
`ModeAuthority`'s public surface is exactly `request` (T2), so this module is
handed no mutator to call: it reads the FRAME directly — a read surface that
cannot change state — and every WRITE goes through the authority. The asymmetry
came out of measuring T4 rather than out of designing T2, and it is stronger than
what T2 set out to build: a later "convenience" accessor on the authority would
quietly undo it, so both halves are pinned by test.

THE MODEL CARRIES NO MACHINE IDENTIFIER — DEC-71's ruling, applied BY DESIGN here
rather than after three rounds of live failure. `jump` arrives as the 1-BASED STEP
NUMBER the user and the model both already say aloud ("go back to step two"), and
the KERNEL maps it to that step's stable id by asking the plan. **An identifier
that never crosses the boundary cannot fail the round trip it is put through** —
which is the first time this lesson has been paid forward instead of backward.
It is also why a delete cannot corrupt a jump: the number is resolved against the
plan AS IT IS NOW, and the id it resolves to is the one the authority moves to.

NEVER RAISES, and the arguments are why: they are model-authored JSON and may be
anything. A missing `steps`, a string where a list belongs, a step number of -4 —
each becomes an ordinary Arabic note. That is `parse_shapes_args`'s discipline
applied to a different malformed payload, and it is the reason no branch here
validates by exception.

EVERY NOTE OBEYS THE STANDING NOTE LAW (AGENTS.md, ruled in DEC-58) — what WAS
accomplished, TERMINAL or TRANSIENT, and the valid NEXT STEP. **The SUCCESS notes
obey it too**, and that is deliberate: M3's live cost came from a note that
reported a deferral without reporting the state reached, so a note saying only
"done" would repeat the defect in the cheerful direction.

Sibling imports plus stdlib; importable in isolation. Holds no state.
"""

from __future__ import annotations

from typing import Any, Optional

from ..cloud.protocol import ToolCall
from .ack_scope import ACK_SCOPE_AR
from .deferral_notes import NAV_PLAN_TOOL
from .mode_surfaces import refusal_note
from .mode_transition import (
    ADVANCE, BACK, ENTER, JUMP, LEAVE, ModeAuthority, TransitionRequest,
)
from .plan import Plan
from .verbosity import DIRECTIVE_OPEN_AR

# A spoken walkthrough longer than this is a document, not a mode: the user
# cannot hold it and the indicator cannot show it. Bounded here rather than in
# the schema, because a schema is a request and a bound is the kernel's.
MAX_STEPS = 12
MAX_STEP_CHARS = 160

# The model-facing action words → the kernel's request kinds. A table, so an
# unknown action is REFUSED by lookup rather than falling into a nearby branch.
_ACTIONS = {"advance": ADVANCE, "back": BACK, "jump": JUMP, "done": LEAVE}

_PLAN_STARTED_AR = (
    f"{DIRECTIVE_OPEN_AR} بدأتُ المسار وفيه {{total}} خطوات، وأنت الآن على "
    "الخطوة الأولى وهي معروضة للمستخدم على الشاشة. لا تُنشئ المسار مرة أخرى. "
    "اشرح الخطوة الحالية وحدها، وانتظر المستخدم قبل أن تطلب التقدّم. "
    f"{ACK_SCOPE_AR}.)"
)

_MOVED_AR = (
    f"{DIRECTIVE_OPEN_AR} صرتَ على الخطوة {{current}} من {{total}}، والمؤشّر على "
    "الشاشة يعرضها الآن. اشرح هذه الخطوة وحدها، ولا تطلب حركة ثانية في هذه "
    f"الجولة. {ACK_SCOPE_AR}.)"
)

_FINISHED_AR = (
    f"{DIRECTIVE_OPEN_AR} انتهى المسار وزال المؤشّر من الشاشة، وما عاد فيه خطوات. "
    "لا تذكر أرقام خطوات بعد الآن. أكمل ردك عاديًا. "
    f"{ACK_SCOPE_AR}.)"
)

_BAD_STEPS_AR = (
    f"{DIRECTIVE_OPEN_AR} ما بدأ أي مسار لأن الخطوات وصلت ناقصة أو بصيغة غير "
    "مفهومة، فما تغيّر شي وما صار خطأ. أعِد الطلب مرة واحدة وكل خطوة فيها نصّها "
    "ونتيجتها المتوقّعة، أو أكمل الشرح بلا مسار إن كانت المهمة خطوة واحدة.)"
)

# DEC-107's boundary, and it is a SEPARATE note on purpose: "you sent no steps"
# and "one of your steps is incomplete" are different mistakes with different
# repairs, and a model told only the first would resend the same payload.
_BAD_RESULT_AR = (
    f"{DIRECTIVE_OPEN_AR} ما بدأ أي مسار لأن فيه خطوة بلا نصّ أو بلا نتيجة "
    "متوقّعة، فما تغيّر شي وما صار خطأ. كل خطوة لازم تحمل نصّها ونتيجتها "
    "المتوقّعة — وش يقدر المستخدم يشوفه على الشاشة إذا خلّص الخطوة. أعِد الطلب "
    "مرة واحدة بالخطوات كاملة.)"
)

_BAD_ACTION_AR = (
    f"{DIRECTIVE_OPEN_AR} ما تغيّر شي لأن الحركة المطلوبة غير معروفة. الحركات "
    "المتاحة هي advance و back و jump و done، ولا شيء غيرها. أعِد الطلب مرة "
    "واحدة بحركة منها.)"
)


def _one_line(raw: Any) -> str:
    """A model-authored string, narrowed to ONE bounded line — or empty."""
    return " ".join(raw.split())[:MAX_STEP_CHARS] if isinstance(raw, str) else ""


def _clean_step(item: Any) -> Optional[dict]:
    """ONE model-authored step, defensively narrowed — or None if what arrived
    is not a step.

    `.get()` HERE AND SUBSCRIPTS IN `plan.py`, AND THE DIFFERENCE IS THE POINT.
    This is the model boundary, where a missing key is ORDINARY INPUT that must
    become a spoken note; `Plan.build` is our own construction, where a missing
    key is a programming error and DEC-91's loud `KeyError` is correct. The same
    absence means two different things on the two sides of this function.

    NOTHING IS COERCED AND NOTHING IS DEFAULTED. A `{"text": ...}` with no
    result is refused rather than filled in with `""` — an empty expected result
    would satisfy every structural check downstream while carrying no
    description at all, which is the silence DEC-107 Gate 1 exists to close."""
    if not isinstance(item, dict):
        return None
    text = _one_line(item.get("text"))
    expected_result = _one_line(item.get("expected_result"))
    if not text or not expected_result:
        return None
    return {"text": text, "expected_result": expected_result}


def _start(args: dict, authority: ModeAuthority) -> str:
    """`navigator__plan` — build the plan, then ask to ENTER with it.

    ONE INCOMPLETE STEP INVALIDATES THE WHOLE PLAN (DEC-107). The v6 discipline
    DROPPED a malformed entry and started a shorter walkthrough, which is silent
    partial acceptance: the model asked for five steps, the user got four, and
    nothing anywhere said so. A plan is refused whole, and the model is told
    which repair to make."""
    raw = args.get("steps")
    if not isinstance(raw, (list, tuple)) or not raw:
        return _BAD_STEPS_AR
    cleaned = [_clean_step(item) for item in raw]
    if None in cleaned:
        return _BAD_RESULT_AR
    steps = cleaned[:MAX_STEPS]
    title = _one_line(args.get("title"))
    outcome = authority.request(TransitionRequest(
        kind=ENTER, mode_name=title or "المسار", plan=Plan.build(title, steps)))
    if not outcome.applied:
        return outcome.note_ar or refusal_note(outcome.reason or "")
    return _PLAN_STARTED_AR.format(total=len(steps))


def _move(args: dict, authority: ModeAuthority, mode: Any) -> str:
    """`navigator__step` — advance / back / jump / done, all one request."""
    action = args.get("action")
    kind = _ACTIONS.get(action) if isinstance(action, str) else None
    if kind is None:
        return _BAD_ACTION_AR
    step_id: Optional[str] = None
    if kind == JUMP:
        # THE NUMBER → THE STABLE ID, resolved by the KERNEL against the plan AS
        # IT IS NOW. Out of range simply resolves to nothing and the authority's
        # own bounds check writes the note — this function invents no refusal.
        plan = mode.plan
        number = args.get("step_number")
        if (plan is not None and isinstance(number, int)
                and not isinstance(number, bool) and 1 <= number <= plan.total):
            step_id = plan.steps[number - 1].id
    outcome = authority.request(TransitionRequest(kind=kind, step_id=step_id))
    if not outcome.applied:
        return outcome.note_ar or refusal_note(outcome.reason or "")
    if kind == LEAVE:
        return _FINISHED_AR
    return _MOVED_AR.format(current=mode.current_step, total=mode.total_steps)


def service_navigator_call(call: ToolCall, *, authority: ModeAuthority,
                           mode: Any) -> str:
    """ONE navigator call, serviced. Never raises.

    BOTH objects, and the asymmetry is the design (see the module docstring):
    the FRAME is read directly, every WRITE goes through the authority. They
    always describe the same mode because the caller holds them from one
    `TurnPrelude`, which builds the authority OVER the injected frame."""
    args = call.args if isinstance(call.args, dict) else {}
    if call.name == NAV_PLAN_TOOL:
        return _start(args, authority)
    return _move(args, authority, mode)


__all__ = ["MAX_STEPS", "MAX_STEP_CHARS", "service_navigator_call"]
