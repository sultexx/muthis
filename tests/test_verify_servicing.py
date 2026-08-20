"""
test_verify_servicing.py — DEC-108 Gate 2C: the FOUR-STATE MACHINE, driven
through the real P4 arm.

WHAT CHANGED AT THIS GATE, AND IT IS THE WHOLE FILE. At Gate 2B the verb was
serviced and NOTHING followed; the tests said so and the notes said so. The
machine exists now, so every outcome has a consequence: `RESULT_PROVEN` ADVANCES
the step through the authority, `RESULT_NOT_PROVEN_OBSERVABLE` HOLDS it, and
`RESULT_UNOBSERVABLE` falls back to the user's own word.

EVERY DRIVE GOES THROUGH `service_pass_calls`, never through the machine's pure
functions alone — those are proven in `test_step_verification.py`, and a test
that called them here would pass with the arm deleted.

THE INVARIANTS THAT MUST NOT BE RELAXED, each with its own test below:
  ① `ADVANCED` is reachable only from `VERIFYING` carrying represented evidence.
  ② No transition reads confidence, the absence of a disqualifier, or the
     disappearance of a precondition — all three are MEASURED failure modes.
  ④ The machine dies with its mode.
  ⑤ `FALLBACK` never returns to `VERIFYING` for the same step; its ONE exit is
     a committed step change, which is the user declaring completion.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from muthis.cloud.protocol import ToolCall
from muthis.kernel.deferral_notes import NAV_PLAN_TOOL, NAV_VERIFY_TOOL
from muthis.kernel.mode_transition import ADVANCE, TransitionRequest
from muthis.kernel.navigator_service import service_navigator_call
from muthis.kernel.pass_servicing import service_pass_calls
from muthis.kernel.session_mode import SessionMode
from muthis.kernel.step_verification import (
    ADVANCED, AWAITING, FALLBACK, INITIAL_STATE, RESULT_NOT_PROVEN_OBSERVABLE,
    RESULT_PROVEN, RESULT_UNOBSERVABLE, VERIFYING,
)
from muthis.kernel.turn import TurnResult
from muthis.kernel.turn_prelude import TurnPrelude
from muthis.kernel.verification_notes import (
    VERIFY_ADVANCED_AR, VERIFY_FALLBACK_AR, VERIFY_HOLDING_AR,
    VERIFY_NO_EVIDENCE_AR, VERIFY_NO_STEP_AR,
)

STEPS = [{"text": "افتح الإعدادات", "expected_result": "نافذة الإعدادات ظاهرة"},
         {"text": "اختر الشبكة", "expected_result": "قائمة الشبكات ظاهرة"}]
PLAN_ARGS = {"title": "توصيل الشبكة", "steps": STEPS}
EVIDENCE = "نافذة الإعدادات ظاهرة على الشاشة"
PROVEN = {"outcome": RESULT_PROVEN, "evidence": EVIDENCE}


def _call(args, name=NAV_VERIFY_TOOL, tool_use_id="ver_1") -> ToolCall:
    return ToolCall(name=name, args=args, tool_use_id=tool_use_id)


def _prelude(*, with_plan: bool = True, cycle_open: bool = True) -> TurnPrelude:
    """A REAL prelude with the plan started through the REAL servicing path.

    `cycle_open` drives DEC-106's transition 1 the way production does — through
    `begin_turn`, the F9 boundary — rather than by stamping the state by hand,
    so a test that passes here cannot pass with that boundary deleted."""
    prelude = TurnPrelude(session_mode=SessionMode())
    if with_plan:
        service_navigator_call(_call(PLAN_ARGS, name=NAV_PLAN_TOOL, tool_use_id="n1"),
                               authority=prelude.authority,
                               mode=prelude.session_mode)
    if cycle_open:
        prelude.begin_turn("تمام")
    return prelude


def _serviced(call: ToolCall, prelude: TurnPrelude) -> str:
    serviced = asyncio.run(service_pass_calls(
        router=None, sandbox=None, result=TurnResult(),
        precondition=None, read=None, run=None, nav=call, prelude=prelude))
    assert serviced.nav_result is not None and serviced.nav_result[0] is call
    return serviced.nav_result[1]


# ─── The three outcomes, each with its consequence ──────────────────────────

def test_PROVEN_with_evidence_ADVANCES_the_step_and_says_so():
    """TRANSITIONS 2 AND 3, end to end. The kernel advances — the user never had
    to say "next", which is the whole point of the milestone."""
    prelude = _prelude()
    mode = prelude.session_mode
    assert (mode.current_step, mode.verification) == (1, VERIFYING)

    note = _serviced(_call(PROVEN), prelude)

    assert mode.current_step == 2, "the proven step did not advance"
    assert note == VERIFY_ADVANCED_AR
    assert mode.verification == AWAITING, (
        "the frame rested in an EDGE — `ADVANCED` is passed through, never held")


def test_NOT_PROVEN_HOLDS_the_step_and_forbids_repeating_the_explanation():
    """TRANSITION 4, with DEC-106's UX ruling inside the note: the step
    explanation is NOT repeated. A repeat reads as "you did it wrong" when the
    honest state is "I have not seen it yet"."""
    prelude = _prelude()
    mode = prelude.session_mode

    note = _serviced(_call({"outcome": RESULT_NOT_PROVEN_OBSERVABLE}), prelude)

    assert mode.current_step == 1 and mode.active is True
    assert note == VERIFY_HOLDING_AR
    assert mode.verification == AWAITING, "the cycle did not close"
    assert "لا تعيد شرح الخطوة" in note, (
        "the no-repeat ruling left the note — DEC-106's UX half is load-bearing")


def test_UNOBSERVABLE_falls_back_and_the_note_SPEAKS_the_right_distinction():
    """TRANSITION 5 and DEC-106's other UX ruling. The fallback is ANNOUNCED,
    and it separates a limit in MUT'HIS's viewpoint from a failure by the USER —
    a capability boundary reported as a user error is the failure this wording
    exists to prevent."""
    prelude = _prelude()
    mode = prelude.session_mode

    note = _serviced(_call({"outcome": RESULT_UNOBSERVABLE}), prelude)

    assert mode.verification == FALLBACK
    assert mode.current_step == 1, "a fallback moved the step"
    assert note == VERIFY_FALLBACK_AR
    assert "ليس معناه أن ما فعله المستخدم فشل" in note


def test_the_fallback_note_never_quotes_the_expected_result():
    """It is INTERNAL to the plan contract. The kernel never reads it (DEC-66),
    so this holds by construction — and is asserted anyway, because the note is
    the one place a future edit would be tempted to "be helpful"."""
    prelude = _prelude()

    note = _serviced(_call({"outcome": RESULT_UNOBSERVABLE}), prelude)

    for step in STEPS:
        assert step["expected_result"] not in note
        assert step["text"] not in note


# ─── The invariants ─────────────────────────────────────────────────────────

def test_INVARIANT_1_a_PROVEN_claim_with_no_evidence_advances_NOTHING():
    """Gate 2A made it unrepresentable at the RECORD level; here is what that
    buys at the MACHINE level. The model asked for an advance and did not get
    one — and it is TOLD, so it can send the evidence next time instead of
    repeating the same payload forever."""
    prelude = _prelude()
    mode = prelude.session_mode

    note = _serviced(_call({"outcome": RESULT_PROVEN}), prelude)

    assert mode.current_step == 1, "an evidence-free claim advanced the step"
    assert note == VERIFY_NO_EVIDENCE_AR
    assert mode.verification != ADVANCED


def test_INVARIANT_1_a_verification_with_NO_CYCLE_OPEN_advances_nothing():
    """`ADVANCED` is reachable ONLY from `VERIFYING`. A plan started in the SAME
    turn is the real case: the F9 boundary ran before the mode existed, so no
    cycle is open and the strongest outcome still moves nothing."""
    prelude = _prelude(cycle_open=False)
    mode = prelude.session_mode
    assert mode.verification == AWAITING

    _serviced(_call(PROVEN), prelude)

    assert mode.current_step == 1
    assert mode.verification == AWAITING


def test_INVARIANT_5_FALLBACK_never_returns_to_VERIFYING_on_a_new_cycle():
    """The next F9 does NOT re-open the question. A boundary that did would put
    the user back inside something the kernel has already declared it cannot
    answer from this viewpoint."""
    prelude = _prelude()
    mode = prelude.session_mode
    _serviced(_call({"outcome": RESULT_UNOBSERVABLE}), prelude)
    assert mode.verification == FALLBACK

    prelude.begin_turn("سؤال جانبي")          # a second F9, the real boundary

    assert mode.verification == FALLBACK
    _serviced(_call(PROVEN), prelude)
    assert mode.current_step == 1, "a fallback step advanced on a later proof"


def test_INVARIANT_5_the_ONE_exit_from_FALLBACK_is_a_committed_step_change():
    """The user declaring completion IS an advance, and it goes through the
    authority like every other one. The reset rides on `record_progress`, so
    transitions 3 and 6 cannot be implemented — or forgotten — separately."""
    prelude = _prelude()
    mode = prelude.session_mode
    _serviced(_call({"outcome": RESULT_UNOBSERVABLE}), prelude)
    assert mode.verification == FALLBACK

    prelude.authority.request(TransitionRequest(kind=ADVANCE))

    assert mode.current_step == 2
    assert mode.verification == INITIAL_STATE == AWAITING


def test_INVARIANT_4_the_machine_dies_with_its_mode():
    """It has no home of its own: the state lives on the frame, and `leave()`
    empties the one slot. Structural rather than a rule anyone keeps."""
    prelude = _prelude()
    _serviced(_call({"outcome": RESULT_UNOBSERVABLE}), prelude)
    assert prelude.session_mode.verification == FALLBACK

    prelude.session_mode.leave()

    assert prelude.session_mode.frame is None
    assert prelude.session_mode.verification == INITIAL_STATE


def test_INVARIANT_2_the_arm_reads_no_confidence_and_no_disqualifier():
    """All three forbidden inputs are MEASURED failure modes — DEC-99's single
    false advance inferred completion from a DISAPPEARANCE, and DEC-105's Excel
    case was 10/10 wrong at confidence 99 with no visible disqualifier. A
    payload carrying all three changes nothing: the outcome is derived from
    membership and evidence alone."""
    prelude = _prelude()
    mode = prelude.session_mode

    note = _serviced(_call({"outcome": RESULT_NOT_PROVEN_OBSERVABLE,
                            "confidence": 99,
                            "no_disqualifier_visible": True,
                            "precondition_gone": True,
                            "evidence": EVIDENCE}), prelude)

    assert note == VERIFY_HOLDING_AR
    assert mode.current_step == 1


# ─── The authority still rules on the advance ───────────────────────────────

def test_a_PROVEN_LAST_step_is_refused_at_the_bound_like_any_other_advance():
    """The verification is not a special path around the authority. The proof is
    accepted, the ADVANCE is requested, and the plan's own edge refuses it — so
    the model gets the AUTHORITY's note, not an invented one."""
    prelude = _prelude()
    prelude.authority.request(TransitionRequest(kind=ADVANCE))   # to the last step
    prelude.begin_turn("تمام")
    mode = prelude.session_mode
    assert mode.current_step == mode.total_steps == 2

    note = _serviced(_call(PROVEN), prelude)

    assert mode.current_step == 2, "the last step advanced past the plan's end"
    assert note not in (VERIFY_ADVANCED_AR, VERIFY_HOLDING_AR, VERIFY_FALLBACK_AR)
    assert mode.verification == AWAITING, "the frame rested in an EDGE"


def test_the_step_pointer_moves_ONLY_through_the_authority():
    """`record_verification` is a STAMP, not a transition: it takes no plan and
    touches one field, so it cannot move a pointer even when handed the state
    that would."""
    prelude = _prelude()
    mode = prelude.session_mode

    mode.record_verification(ADVANCED)

    assert mode.current_step == 1, "a stamp moved the step"
    assert mode.verification == ADVANCED, "the stamp stored something else"


# ─── The empty and hostile cases ────────────────────────────────────────────

def test_a_verify_with_NO_ACTIVE_STEP_claims_nothing_and_points_elsewhere():
    prelude = _prelude(with_plan=False)

    note = _serviced(_call(PROVEN), prelude)

    assert note == VERIFY_NO_STEP_AR and NAV_PLAN_TOOL in note


@pytest.mark.parametrize("payload", [None, [], "RESULT_PROVEN", 7, {}, {"x": 1},
                                     {"outcome": ["RESULT_PROVEN"]}])
def test_any_payload_at_all_is_serviced_and_NEVER_raises(payload):
    """The servicer's standing law reaches the machine unchanged. Everything
    that is not a represented outcome lands on the fail-closed reading, which
    HOLDS the step — it never advances and never spends the fallback."""
    prelude = _prelude()

    note = _serviced(_call(payload), prelude)

    assert note == VERIFY_HOLDING_AR
    assert prelude.session_mode.current_step == 1
    assert prelude.session_mode.verification == AWAITING


def test_the_verb_does_NOT_route_through_the_TRANSLATION_LAYER():
    """P5's rejection, still discriminating at Gate 2C: the same call answered
    two ways, and `service_navigator_call` — which decides nothing and never
    raises — reads it as a malformed `step`."""
    prelude = _prelude()
    call = _call({"outcome": RESULT_UNOBSERVABLE})

    through_the_arm = _serviced(call, prelude)
    through_the_translator = service_navigator_call(
        call, authority=prelude.authority, mode=prelude.session_mode)

    assert through_the_arm == VERIFY_FALLBACK_AR
    assert through_the_arm != through_the_translator


def test_the_servicer_gained_NO_screenshot_parameter():
    """THE COUPLING THE TRACE FLAGGED AND THE RULING RETIRED — still absent now
    that the arm DOES something. The kernel validates representation, not truth,
    so it never needs the bytes."""
    parameters = set(inspect.signature(service_pass_calls).parameters)

    assert parameters == {"router", "sandbox", "result", "precondition", "read",
                          "run", "nav", "prelude"}
    for frame_word in ("screenshot", "frame", "image", "sent_bytes", "pixels"):
        assert frame_word not in parameters


def test_the_arm_reads_NEITHER_the_expected_result_NOR_the_evidence():
    """DEC-66 at the one place it would be most tempting to break. Two plans
    with DIFFERENT expected results, verified with the same payload, advance
    identically: if anything compared evidence to expectation they would not."""
    first = _prelude()
    second = TurnPrelude(session_mode=SessionMode())
    service_navigator_call(
        _call({"title": "مهمة أخرى",
               "steps": [{"text": "خطوة", "expected_result": "شيء مختلف تماماً"},
                         {"text": "أخرى", "expected_result": "شيء آخر"}]},
              name=NAV_PLAN_TOOL, tool_use_id="n2"),
        authority=second.authority, mode=second.session_mode)
    second.begin_turn("تمام")

    assert _serviced(_call(PROVEN), first) == _serviced(_call(PROVEN), second)
    assert first.session_mode.current_step == second.session_mode.current_step == 2


def test_a_side_question_turn_costs_the_walkthrough_NOTHING():
    """The kernel gates whether the verb is OFFERED; the MODEL decides whether to
    call it. A turn that simply does not call it opens a cycle and closes
    nothing — the step does not move, and no fallback is spent."""
    prelude = _prelude()
    mode = prelude.session_mode

    prelude.begin_turn("وش معنى هذا؟")

    assert mode.current_step == 1 and mode.verification == VERIFYING
    assert mode.active is True


def test_the_verification_state_is_NOT_the_step_and_NOT_the_clocks():
    """Three facts, three homes (DEC-104's argument, one field further on): the
    stamp touches neither clock, and neither clock touches it."""
    prelude = _prelude()
    mode = prelude.session_mode
    before = mode.frame

    mode.record_verification(FALLBACK)
    after = mode.frame

    assert after.verification == FALLBACK
    assert after.last_progress_at == before.last_progress_at
    assert after.last_activity_at == before.last_activity_at
    assert after.plan is before.plan and after.name == before.name
