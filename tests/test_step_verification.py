"""
test_step_verification.py — DEC-108 Gate 2A: the THREE-WAY OUTCOME, and the
proof that it is the ONLY thing this module can produce.

TWO HALVES, PROVEN TWO WAYS — the `test_session_mode.py` shape, because the
properties here are the same KIND of property.

1. THE CONTRACT, BEHAVIOURALLY, AS A COMPLETE TRUTH TABLE. `outcome` is a pure
   function of two fields, so "fail-closed" is not sampled here — it is
   ENUMERATED. Every member of the closed enumeration, with and without
   evidence, plus the payload shapes a model can actually send.
2. THE LIMITS, STRUCTURALLY, AS AN ABSENCE OF MEANS. No authority, no plan, no
   mode, no persistence, no logger, no interpretation. Every scan is over the
   AST and never the raw text, because the module's docstring names the symbols
   that must be absent ON PURPOSE — a text scan would fail on the very sentences
   that record why they are missing (the `test_high_impact.py` precedent).

THE LOAD-BEARING TEST IS `test_a_hand_built_record_still_cannot_hold_an
_evidence_free_PROVEN`. Everything else could be satisfied by a module that
merely CHECKS well; that one is satisfied only by a module in which the bad
value has no slot to live in.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib

import pytest

from muthis.kernel.step_verification import (
    EVIDENCE_ARG, FAIL_CLOSED_OUTCOME, MAX_CLAIM_CHARS, MAX_EVIDENCE_CHARS,
    OUTCOME_ARG, OUTCOMES, RESULT_NOT_PROVEN_OBSERVABLE, RESULT_PROVEN,
    RESULT_UNOBSERVABLE, StepVerification, verification_from,
)

MODULE_PY = (pathlib.Path(__file__).resolve().parent.parent / "src" / "muthis"
             / "kernel" / "step_verification.py")

EVIDENCE = "ملف muthis_test.txt ظاهر داخل مجلد Destination"


def _tree() -> ast.Module:
    return ast.parse(MODULE_PY.read_text(encoding="utf-8"))


def _names() -> "set[str]":
    tree = _tree()
    return ({node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} |
            {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)})


def _imports() -> "set[str]":
    imported = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return imported


def _function_bodies() -> "list[ast.stmt]":
    return [statement
            for node in ast.walk(_tree())
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for statement in node.body]


# ─── 1. THE CONTRACT, as a COMPLETE truth table ─────────────────────────────

def test_the_enumeration_is_closed_and_is_DEC_106s_three_outcomes():
    """The three names are model-facing strings and a rename is a model-visible
    change, so they are pinned literally rather than derived from themselves."""
    assert OUTCOMES == ("RESULT_PROVEN", "RESULT_NOT_PROVEN_OBSERVABLE",
                        "RESULT_UNOBSERVABLE")
    assert len(set(OUTCOMES)) == 3


def test_the_positive_control_PROVEN_WITH_EVIDENCE_really_does_come_out_PROVEN():
    """FIRST, AND IT IS NOT CEREMONY. Every assertion below says some payload is
    NOT an advance, and a module that could never produce one would satisfy all
    of them while making verification impossible — the same absence with the
    opposite meaning (DEC-107 Gate 4's control, one gate later)."""
    verification = verification_from({OUTCOME_ARG: RESULT_PROVEN,
                                      EVIDENCE_ARG: EVIDENCE})

    assert verification.outcome == RESULT_PROVEN
    assert verification.evidence == EVIDENCE


@pytest.mark.parametrize("evidence", [None, "", "   ", "\n\t ", 0, [], {}, False])
def test_PROVEN_without_usable_evidence_is_never_an_advance(evidence):
    """FAIL-CLOSED. Whitespace is not evidence and neither is a list: the field
    is narrowed exactly as a step's text is (`navigator_service._one_line`), so
    everything that narrows to empty is empty."""
    verification = verification_from({OUTCOME_ARG: RESULT_PROVEN,
                                      EVIDENCE_ARG: evidence})

    assert verification.outcome == FAIL_CLOSED_OUTCOME
    assert verification.outcome != RESULT_PROVEN
    assert verification.claimed == RESULT_PROVEN, (
        "the CLAIM is kept — a caller that wants to know an advance was asked "
        "for and not licensed must not have to re-derive it")


def test_the_missing_evidence_KEY_is_the_same_as_an_empty_one():
    """The likeliest real payload: the model picks the strongest outcome and
    simply does not send the field. DEC-91's lesson is that a `required` in a
    tool schema is a declaration the provider may ignore in silence, so the
    absence must be handled HERE and not assumed away there."""
    assert verification_from({OUTCOME_ARG: RESULT_PROVEN}).outcome == FAIL_CLOSED_OUTCOME


@pytest.mark.parametrize("outcome", [RESULT_NOT_PROVEN_OBSERVABLE, RESULT_UNOBSERVABLE])
def test_the_two_NON_ADVANCING_outcomes_carry_no_evidence_requirement(outcome):
    """Neither asks the model to point at anything: "not there yet" and "this
    screen cannot settle it" are statements about what is ABSENT. Requiring
    evidence for them would ask for a description of nothing."""
    assert verification_from({OUTCOME_ARG: outcome}).outcome == outcome
    assert verification_from({OUTCOME_ARG: outcome, EVIDENCE_ARG: ""}).outcome == outcome
    assert verification_from(
        {OUTCOME_ARG: outcome, EVIDENCE_ARG: EVIDENCE}).outcome == outcome, (
        "evidence sent anyway must not change a non-advancing outcome")


@pytest.mark.parametrize("claimed", [
    "PROVEN", "result_proven", "RESULT PROVEN", "RESULT_PROVEN ", "ADVANCE",
    "RESULT_NOT_PROVEN", "", None, 3, True, ["RESULT_PROVEN"],
    {"outcome": "RESULT_PROVEN"},
])
def test_anything_outside_the_CLOSED_enumeration_fails_closed(claimed):
    """Membership, never a resemblance. `"RESULT_PROVEN "` with a trailing space
    is the interesting row: it narrows to the real member and is admitted, which
    is why the assertion below is about the OUTCOME rather than about the
    string — a near-miss that is not a member gets the fail-closed outcome and a
    whitespace variant of a member does not become a fourth answer."""
    verification = verification_from({OUTCOME_ARG: claimed,
                                      EVIDENCE_ARG: EVIDENCE})

    assert verification.outcome in OUTCOMES
    if verification.claimed not in OUTCOMES:
        assert verification.outcome == FAIL_CLOSED_OUTCOME


@pytest.mark.parametrize("payload", [
    None, [], "", "RESULT_PROVEN", 0, 3.5, True, {}, {"other": 1},
    {OUTCOME_ARG: {"nested": RESULT_PROVEN}}, ({OUTCOME_ARG: RESULT_PROVEN},),
])
def test_NO_payload_shape_can_raise_and_every_one_yields_an_outcome(payload):
    """TOTAL BY CONSTRUCTION — `navigator_service.py`'s "NEVER RAISES", for the
    same reason: these are model-authored JSON arguments and may be anything.
    A verifier that raised would turn a malformed payload into a dead turn."""
    verification = verification_from(payload)

    assert verification.outcome in OUTCOMES
    assert verification.outcome != RESULT_PROVEN, (
        "a payload that is not even a mapping produced an ADVANCE")


def test_the_fail_closed_destination_is_the_RECOVERABLE_non_advancing_outcome():
    """BOTH non-advancing outcomes would satisfy "never advance", so the choice
    between them is real and is recorded rather than left to the value.
    `RESULT_UNOBSERVABLE` is DEC-106's declared CAPABILITY BOUNDARY — a claim
    about the VIEWPOINT whose state has one exit, the user's own declaration
    (invariant ⑤). A malformed payload says nothing about the viewpoint, so
    spending an unrecoverable fallback on one would answer a question nobody
    asked. The retry holds the step and asks again at the next F9."""
    assert FAIL_CLOSED_OUTCOME == RESULT_NOT_PROVEN_OBSERVABLE
    assert FAIL_CLOSED_OUTCOME in OUTCOMES and FAIL_CLOSED_OUTCOME != RESULT_PROVEN


def test_both_model_authored_strings_are_BOUNDED_and_neither_is_interpreted():
    """DEC-66: the kernel STORES, NUMBERS and BOUNDS-CHECKS. Bounding is
    permitted; reading is not. The evidence survives whole up to its bound and
    is never parsed, matched or compared to the expected result."""
    long_evidence = "ب" * (MAX_EVIDENCE_CHARS + 500)
    verification = verification_from({OUTCOME_ARG: RESULT_PROVEN,
                                      EVIDENCE_ARG: long_evidence})

    assert len(verification.evidence) == MAX_EVIDENCE_CHARS
    assert verification.outcome == RESULT_PROVEN
    assert len(verification_from(
        {OUTCOME_ARG: "x" * (MAX_CLAIM_CHARS + 50)}).claimed) == MAX_CLAIM_CHARS


def test_a_multi_line_evidence_becomes_ONE_line():
    """The `_one_line` discipline the plan's steps already get: a model-authored
    string reaches the kernel as one bounded line, so nothing downstream has to
    care where it came from."""
    verification = verification_from(
        {OUTCOME_ARG: RESULT_PROVEN, EVIDENCE_ARG: " الملف\n\n ظاهر \t هناك "})

    assert verification.evidence == "الملف ظاهر هناك"


# ─── 2. THE LIMITS, asserted as an ABSENCE OF MEANS ─────────────────────────

def test_a_hand_built_record_still_cannot_hold_an_evidence_free_PROVEN():
    """THE LOAD-BEARING TEST. Everything above could be satisfied by a module
    that merely CHECKS well at its entry point; this one is satisfied only by a
    type in which the bad value has NO SLOT TO LIVE IN.

    The most hostile caller available — one that skips `verification_from`
    entirely and builds the record by hand — still cannot produce an advance
    without evidence, because `outcome` is DERIVED and there is nothing to
    assign. This is `SessionMode`'s no-nesting method (made impossible to
    EXPRESS rather than blocked) and DEC-107 Gate 4's, one gate later."""
    hostile = StepVerification(claimed=RESULT_PROVEN, evidence="")

    assert hostile.outcome == FAIL_CLOSED_OUTCOME
    assert "outcome" not in {field.name for field in
                             dataclasses.fields(StepVerification)}, (
        "an `outcome` FIELD appeared — the advance became assignable")


def test_neither_field_has_a_default_so_construction_cannot_omit_the_evidence():
    """`frozen=True` was not enough for DEC-107 and a default would not be
    enough here: an `evidence: str = ""` would make the empty case the one a
    caller reaches by writing LESS."""
    for field in dataclasses.fields(StepVerification):
        assert field.default is dataclasses.MISSING, f"{field.name} gained a default"
        assert field.default_factory is dataclasses.MISSING, (
            f"{field.name} gained a default factory")
    assert [field.name for field in dataclasses.fields(StepVerification)] == [
        "claimed", "evidence"]


def test_the_record_is_frozen_so_evidence_cannot_be_removed_after_the_fact():
    verification = verification_from({OUTCOME_ARG: RESULT_PROVEN,
                                      EVIDENCE_ARG: EVIDENCE})
    with pytest.raises(dataclasses.FrozenInstanceError):
        verification.evidence = ""                       # type: ignore[misc]


def test_RESULT_PROVEN_is_never_RETURNED_or_ASSIGNED_inside_any_function_body():
    """THE STRUCTURAL FORM OF FAIL-CLOSED, and it is what makes the derivation
    the ONLY exit. Inside every function body the name appears as a COMPARISON
    OPERAND and nowhere else, so the single path by which an advance leaves this
    module is `return self.claimed` — which both checks run in front of."""
    bodies = _function_bodies()
    returns = [node for statement in bodies for node in ast.walk(statement)
               if isinstance(node, ast.Return)]
    assert len(returns) > 3, (
        f"the scan admitted only {len(returns)} returns — a guard that examined "
        "nothing must never look like a guard that passed (DEC-50)")

    for node in returns:
        assert "RESULT_PROVEN" not in {name.id for name in ast.walk(node)
                                       if isinstance(name, ast.Name)}, (
            f"line {node.lineno} RETURNS the advance directly")
    for statement in bodies:
        if isinstance(statement, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            assert "RESULT_PROVEN" not in {name.id for name in ast.walk(statement)
                                           if isinstance(name, ast.Name)}, (
                f"line {statement.lineno} ASSIGNS the advance")


def test_the_module_imports_nothing_that_could_ACT():
    """It is handed a mapping and returns a value. No authority, no mode, no
    plan, no clock and no router crosses this boundary — so "it cannot advance a
    step" is not a rule anyone must keep; there is nothing here to advance one
    WITH. `navigator_service.py`'s asymmetry, one module further in."""
    assert _imports() == {"__future__", "dataclasses", "typing"}


def test_it_holds_NO_AUTHORITY_NO_PLAN_and_NO_MODE_and_cannot_express_one():
    """DEC-108 ruling ①, as an absence rather than a promise: the machine
    produces the outcome and grants itself no transition authority and no plan
    advancement. If the module cannot NAME the means, it cannot REGRESS into
    using them."""
    names = _names()
    for forbidden in ("ModeAuthority", "TransitionRequest", "SessionMode",
                      "ModeFrame", "Plan", "authority", "request", "enter",
                      "leave", "advance", "jump", "record_progress",
                      "record_activity", "current_step", "total_steps",
                      "with_step_inserted", "expected_result", "frame",
                      "session_mode", "_on_change"):
        assert forbidden not in names, (
            f"step_verification.py names a means it must not have: {forbidden}")


def test_it_calls_nothing_but_its_own_functions_and_a_declared_allow_list():
    """THE ALLOW-LIST, not a deny-list (DEC-21-E, where a deny-list passed a
    bypass in silence). `dataclass` declares the record; `get` reads the model's
    mapping; `join` and `split` are the one-line narrowing. Four names, written
    out — anything else this module learns to call lands here the moment it is
    written, and none of it has to be predicted."""
    tree = _tree()
    defined = {node.name for node in ast.walk(tree)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    permitted = defined | {"dataclass", "get", "join", "split"}
    called = {node.func.attr for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}

    assert len(called) > 2, (
        f"the scan admitted only {sorted(called)} — a guard that examined "
        "nothing must never look like a guard that passed (DEC-50)")
    assert called <= permitted, (
        f"step_verification.py calls methods it does not define: "
        f"{sorted(called - permitted)}")


def test_it_mutates_NOTHING_it_is_given():
    """No attribute is ever assigned anywhere in the module, so a caller's
    mapping, a frame or a plan handed in by a future edit could not be written
    to even if one arrived."""
    tree = _tree()
    attribute_writes = [node for node in ast.walk(tree)
                        if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Attribute)
                                for target in node.targets)]
    assert not attribute_writes, "the module writes to an attribute"
    assert "setattr" not in _names() and "__setattr__" not in _names()


def test_it_has_no_logger_and_no_persistence_and_has_no_means_to_gain_one():
    """The `SessionMode`/`Plan` argument, and it is sharper here: the evidence
    is MODEL-AUTHORED TEXT DESCRIBING THE USER'S SCREEN. No logging import means
    no means; no file surface means it dies with the process."""
    assert "logging" not in _imports()
    names = _names()
    for surface in ("logger", "getLogger", "warning", "debug", "exception",
                    "open", "write", "write_text", "read_text", "dump", "dumps",
                    "load", "loads", "Path", "json", "pickle", "os", "environ"):
        assert surface not in names, f"step_verification.py gained: {surface}"


def test_the_public_surface_is_pinned():
    """The `SessionTaint` precedent: the surface is the contract, and an
    addition — an `apply`, an `advance`, a `state` — must be DECLARED rather
    than discovered."""
    import muthis.kernel.step_verification as module

    assert set(module.__all__) == {
        "EVIDENCE_ARG", "FAIL_CLOSED_OUTCOME", "MAX_CLAIM_CHARS",
        "MAX_EVIDENCE_CHARS", "OUTCOMES", "OUTCOME_ARG",
        "RESULT_NOT_PROVEN_OBSERVABLE", "RESULT_PROVEN", "RESULT_UNOBSERVABLE",
        "StepVerification", "verification_from",
    }
    for state_word in ("AWAITING", "VERIFYING", "ADVANCED", "FALLBACK"):
        assert state_word not in module.__all__, (
            "a STATE appeared in Gate 2A — the state machine is Gate 2B's")
