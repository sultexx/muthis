"""
test_verify_servicing.py — DEC-108 Gate 2B: the THIRD verb, serviced at P4.

THE CALL SITE IS THE RULING (DEC-108), and three of its four grounds are
assertable right here rather than described:

  · NO FRAME IS NEEDED, so none is taken — `service_pass_calls` gains no
    `screenshot` parameter, and the coupling the trace flagged is never
    incurred. Asserted against the real signature.
  · IT SITS BESIDE ITS SIBLINGS, in the arm that already services the two mode
    verbs, so the third verb costs no new pattern.
  · IT DOES NOT ROUTE THROUGH `navigator_service.py`. That module is a
    translation layer that decides nothing and never raises — P5 was rejected on
    that law — and the test below drives BOTH paths with the same call to show
    they are genuinely different answers rather than the same one twice.

The fourth ground — servicing runs AFTER the sync point — is a property of
`turn_pass.py:272` and is already pinned where that ordering lives.

NOTHING ADVANCES HERE. Gate 2B wires the verb; the four-state machine is Gate
2C's. A test at the bottom holds the walkthrough still through a `RESULT_PROVEN`
with evidence, which is the strongest possible claim, so the day the machine
lands that test changes DELIBERATELY.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from muthis.cloud.protocol import ToolCall
from muthis.kernel.deferral_notes import (
    NAV_PLAN_TOOL, NAV_STEP_TOOL, NAV_VERIFY_TOOL, VERIFY_NO_EVIDENCE_AR,
    VERIFY_NO_STEP_AR, VERIFY_READ_AR, verification_note,
)
from muthis.kernel.navigator_service import service_navigator_call
from muthis.kernel.pass_servicing import service_pass_calls
from muthis.kernel.session_mode import SessionMode
from muthis.kernel.step_verification import (
    FAIL_CLOSED_OUTCOME, RESULT_PROVEN, RESULT_UNOBSERVABLE,
)
from muthis.kernel.turn import TurnResult
from muthis.kernel.turn_prelude import TurnPrelude

STEPS = [{"text": "افتح الإعدادات", "expected_result": "نافذة الإعدادات ظاهرة"},
         {"text": "اختر الشبكة", "expected_result": "قائمة الشبكات ظاهرة"}]
PLAN_ARGS = {"title": "توصيل الشبكة", "steps": STEPS}
EVIDENCE = "نافذة الإعدادات ظاهرة على الشاشة"


def _call(args, name=NAV_VERIFY_TOOL, tool_use_id="ver_1") -> ToolCall:
    return ToolCall(name=name, args=args, tool_use_id=tool_use_id)


def _prelude(*, with_plan: bool) -> TurnPrelude:
    """A REAL prelude, and the plan is started through the REAL servicing path —
    never by reaching into `SessionMode` — so the mode under test is the one
    production builds."""
    prelude = TurnPrelude(session_mode=SessionMode())
    if with_plan:
        service_navigator_call(_call(PLAN_ARGS, name=NAV_PLAN_TOOL, tool_use_id="n1"),
                               authority=prelude.authority,
                               mode=prelude.session_mode)
    return prelude


def _serviced(call: ToolCall, prelude: TurnPrelude) -> str:
    """Through the REAL `service_pass_calls`, never the note function alone: the
    branch under test lives at the call site, and a test that called
    `verification_note` directly would pass with that branch deleted."""
    serviced = asyncio.run(service_pass_calls(
        router=None, sandbox=None, result=TurnResult(),
        precondition=None, read=None, run=None, nav=call, prelude=prelude))
    assert serviced.nav_result is not None
    assert serviced.nav_result[0] is call
    return serviced.nav_result[1]


# ─── The three notes, through the real arm ──────────────────────────────────

def test_a_verify_with_an_active_step_is_READ_and_the_outcome_named_back():
    note = _serviced(_call({"outcome": RESULT_UNOBSERVABLE}), _prelude(with_plan=True))

    assert note == VERIFY_READ_AR.format(outcome=RESULT_UNOBSERVABLE)
    assert RESULT_UNOBSERVABLE in note, "the model is not told how it was read"


def test_a_PROVEN_claim_WITH_evidence_is_read_as_PROVEN():
    """The positive control for the pair below: a guard that could never report
    an advance would satisfy every downgrade assertion while making verification
    impossible."""
    note = _serviced(_call({"outcome": RESULT_PROVEN, "evidence": EVIDENCE}),
                     _prelude(with_plan=True))

    assert note == VERIFY_READ_AR.format(outcome=RESULT_PROVEN)


def test_a_PROVEN_claim_with_NO_evidence_is_TOLD_it_was_downgraded():
    """THE SILENT-FAILURE GUARD. Gate 2A made the evidence-free advance
    unrepresentable; if the model were never told, it would keep sending the same
    payload and reading the same neutral answer — DEC-91's measured failure (a
    provider accepting what it cannot honour, with no error at all) re-created in
    our own code, which DEC-107 refused once already."""
    note = _serviced(_call({"outcome": RESULT_PROVEN}), _prelude(with_plan=True))

    assert note == VERIFY_NO_EVIDENCE_AR
    assert RESULT_PROVEN in note and FAIL_CLOSED_OUTCOME in note, (
        "the downgrade note no longer names what was asked and what was read")
    assert note != VERIFY_READ_AR.format(outcome=FAIL_CLOSED_OUTCOME), (
        "the downgrade is being reported as an ordinary reading")


def test_a_verify_with_NO_ACTIVE_STEP_claims_nothing_and_points_elsewhere():
    """`mode.current_step` is 0 with no plan and with no mode at all, so one
    existing read covers both. The note claims nothing and names the verb that
    would apply — the standing note law, which exists because a refusal that
    reports only what did NOT happen produces a retry loop."""
    note = _serviced(_call({"outcome": RESULT_PROVEN, "evidence": EVIDENCE}),
                     _prelude(with_plan=False))

    assert note == VERIFY_NO_STEP_AR
    assert NAV_PLAN_TOOL in note


@pytest.mark.parametrize("payload", [None, [], "RESULT_PROVEN", 7, {}, {"x": 1},
                                     {"outcome": ["RESULT_PROVEN"]}])
def test_any_payload_at_all_is_serviced_and_NEVER_raises(payload):
    """The servicer's standing law reaches the new arm unchanged: these are
    model-authored JSON arguments and may be anything. Everything that is not a
    represented outcome lands on the fail-closed reading."""
    note = _serviced(_call(payload), _prelude(with_plan=True))

    assert note == VERIFY_READ_AR.format(outcome=FAIL_CLOSED_OUTCOME)


# ─── The ruling's shape, asserted at the site ───────────────────────────────

def test_the_verb_does_NOT_route_through_the_TRANSLATION_LAYER():
    """P5's rejection, made discriminating. The SAME call is driven through both
    paths: the arm answers it as a verification, and `service_navigator_call` —
    which decides nothing and never raises — answers it as a malformed `step`.
    Two different answers is what proves the branch exists; if the arm were ever
    removed, this file's other tests would fail with THAT string."""
    prelude = _prelude(with_plan=True)
    call = _call({"outcome": RESULT_UNOBSERVABLE})

    through_the_arm = _serviced(call, prelude)
    through_the_translator = service_navigator_call(
        call, authority=prelude.authority, mode=prelude.session_mode)

    assert through_the_arm != through_the_translator
    assert through_the_arm == VERIFY_READ_AR.format(outcome=RESULT_UNOBSERVABLE)


def test_the_servicer_gained_NO_screenshot_parameter():
    """THE COUPLING THE TRACE FLAGGED AND THE RULING RETIRED. The kernel
    validates REPRESENTATION, not truth, so it never needs the bytes — and the
    absence is pinned, because "add the frame while you are here" is the obvious
    next edit and it would put the model's input inside the verifier."""
    parameters = set(inspect.signature(service_pass_calls).parameters)

    assert parameters == {"router", "sandbox", "result", "precondition", "read",
                          "run", "nav", "prelude"}
    for frame_word in ("screenshot", "frame", "image", "sent_bytes", "pixels"):
        assert frame_word not in parameters, (
            f"the verifier reached for the frame: {frame_word}")


def test_the_note_function_reads_NEITHER_the_expected_result_NOR_the_evidence():
    """DEC-66 at the one place it would be most tempting to break. Two steps with
    DIFFERENT expected results, verified with the same payload, must produce the
    SAME note: if anything compared the evidence to the expected result, these
    two would diverge."""
    first = _serviced(_call({"outcome": RESULT_PROVEN, "evidence": EVIDENCE}),
                      _prelude(with_plan=True))
    other_plan = TurnPrelude(session_mode=SessionMode())
    service_navigator_call(
        _call({"title": "مهمة أخرى",
               "steps": [{"text": "خطوة", "expected_result": "شيء مختلف تماماً"}]},
              name=NAV_PLAN_TOOL, tool_use_id="n2"),
        authority=other_plan.authority, mode=other_plan.session_mode)
    second = _serviced(_call({"outcome": RESULT_PROVEN, "evidence": EVIDENCE}),
                       other_plan)

    assert first == second


# ─── Gate 2B stops here: NOTHING advances ───────────────────────────────────

def test_servicing_a_PROVEN_verification_moves_NO_STEP_at_gate_2B():
    """The strongest claim the model can make, serviced in full, and the
    walkthrough does not move: no state is kept, no step advances, no fallback
    is entered. THE FOUR-STATE MACHINE IS GATE 2C's — and the day it lands, this
    test changes deliberately rather than silently."""
    prelude = _prelude(with_plan=True)
    mode = prelude.session_mode
    assert (mode.current_step, mode.total_steps) == (1, 2)

    _serviced(_call({"outcome": RESULT_PROVEN, "evidence": EVIDENCE}), prelude)

    assert mode.current_step == 1, "the verification advanced a step"
    assert mode.active is True and mode.total_steps == 2


def test_the_kernel_keeps_NO_verification_state_anywhere():
    """Two identical verifications in a row produce two identical answers: the
    kernel remembers nothing between them, which is what "no VERIFYING state"
    means when it is asserted rather than described."""
    prelude = _prelude(with_plan=True)
    payload = {"outcome": RESULT_PROVEN, "evidence": EVIDENCE}

    assert _serviced(_call(payload), prelude) == _serviced(_call(payload), prelude)
    assert not [name for name in dir(prelude.session_mode)
                if "verif" in name.lower()], "a verification surface appeared"


def test_the_note_function_is_TOTAL_over_the_whole_enumeration():
    """Every member of the closed enumeration produces a note, so no outcome can
    arrive at a branch that has nothing to say. Driven directly here — the arm
    is covered above — because the point is COVERAGE of the enumeration."""
    from muthis.kernel.step_verification import OUTCOMES

    notes = {outcome: verification_note({"outcome": outcome, "evidence": EVIDENCE},
                                        has_active_step=True)
             for outcome in OUTCOMES}

    assert len(set(notes.values())) == len(OUTCOMES), (
        "two outcomes are reported with the same wording — the model cannot "
        "tell how it was read")
    for outcome, note in notes.items():
        assert outcome in note
