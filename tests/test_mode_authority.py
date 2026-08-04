"""
test_mode_authority.py — DEC-65's SINGLE TRANSITION AUTHORITY (T2).

THREE PROPERTIES, EACH PROVEN IN THE FORM IT IS CLAIMED IN.

1. ONE EVALUATION POINT, structurally: `request` is the authority's only public
   method — there is no `advance()` or `exit_now()` to reach for — and NO module
   in `src/` outside `mode_transition.py` calls the mode's mutators at all. The
   second half is the one that matters: a side door added in `turn_prelude.py`
   or a future Navigator would satisfy every behavioural test here while
   defeating the design.

2. EVERY REFUSAL CARRIES ALL THREE OBLIGATIONS, driven as a PROPERTY over the
   whole reason set rather than as a list of pinned strings — so a reason added
   later without a compliant note fails HERE rather than in a live run. That
   distinction is DEC-41's: asserting a law's words separately is not asserting
   the law.

3. NESTING IS UNREPRESENTABLE THROUGH THE AUTHORITY, observed rather than
   argued: a recording frame proves the mode is never seen INACTIVE between two
   modes, which is what "one evaluated decision, never two operations" means at
   runtime (the undefined third state DEC-24 closed).

The three exits, the lazy expiry and the directive-marker constraint live in
`test_mode_exits.py`.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib

import pytest

from muthis.kernel.mode_surfaces import (
    AT_END, AT_START, BLOCKED, NO_MODE, NO_PLAN, UNKNOWN_STEP, UNNAMED_MODE,
    refusal_note,
)
from muthis.kernel.mode_transition import (
    ADVANCE, BACK, CONTROL_KINDS, EDIT_PLAN, ENTER, EXIT_WORD, EXPIRE, JUMP,
    LEAVE, ModeAuthority, TransitionConditions, TransitionRequest,
)
from muthis.kernel.plan import Plan
from muthis.kernel.session_mode import SessionMode
from muthis.trust.confirm_gate import DIRECTIVE_MARKER_AR

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
TRANSITION_PY = SRC / "muthis" / "kernel" / "mode_transition.py"
SURFACES_PY = SRC / "muthis" / "kernel" / "mode_surfaces.py"

ALL_KINDS = (ENTER, LEAVE, ADVANCE, BACK, JUMP, EDIT_PLAN, EXIT_WORD, EXPIRE)
ALL_REASONS = (NO_MODE, UNNAMED_MODE, NO_PLAN, AT_END, AT_START, UNKNOWN_STEP,
               BLOCKED)
# The mutators the authority exists to be the only caller of.
MUTATORS = ("enter", "leave", "record_progress")


def _guiding(steps=("stage", "commit", "push")) -> "tuple[SessionMode, ModeAuthority]":
    mode = SessionMode()
    authority = ModeAuthority(mode=mode)
    authority.request(TransitionRequest(
        kind=ENTER, mode_name="navigator", plan=Plan.build("deploy", steps)))
    return mode, authority


class _Blocking:
    """A conditions seam that always blocks — the stub's opposite."""

    def __call__(self) -> TransitionConditions:
        return TransitionConditions(confirmation_pending=True)


# ─── 1. ONE EVALUATION POINT ─────────────────────────────────────────────────

def test_request_is_the_authoritys_only_public_method():
    """No side door. A `jump()` convenience added here would be a second
    evaluation point wearing a helper's name."""
    surface = {name for name in dir(ModeAuthority) if not name.startswith("_")}
    assert surface == {"request"}, f"a side door appeared: {sorted(surface)}"


def test_nothing_in_src_outside_the_authority_calls_the_modes_mutators():
    """THE STRUCTURAL HALF, and the one a behavioural test cannot reach.

    `enter` / `leave` / `record_progress` shipped inert at T1 precisely so this
    could be true at T2. A direct call from `turn_prelude.py`, or from a future
    Navigator servicing a tool, would bypass the conditions, the bounds checks
    and the refusal notes all at once — and every test in this file would still
    pass."""
    modules = sorted(SRC.rglob("*.py"))
    assert len(modules) > 50, (
        f"the scan admitted only {len(modules)} modules — a guard that examined "
        "nothing must never look like one that passed (DEC-50)")
    offenders = {}
    for module in modules:
        called = {node.func.attr
                  for node in ast.walk(ast.parse(module.read_text(encoding="utf-8")))
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        hits = called & set(MUTATORS)
        if hits and module != TRANSITION_PY:
            offenders[str(module.relative_to(SRC))] = sorted(hits)
    assert not offenders, f"the one evaluation point is bypassed: {offenders}"

    # THE POSITIVE CONTROL: the authority really does call them, so the scan
    # above cannot be passing because it is looking for something absent.
    authority_calls = {
        node.func.attr
        for node in ast.walk(ast.parse(TRANSITION_PY.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert set(MUTATORS) <= authority_calls, (
        "the authority no longer calls the mutators — the scan proves nothing")


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_every_kind_crosses_the_same_point_and_returns_a_decision(kind):
    """Advance, back, jump, plan-edit, enter, leave, the exit word and expiry —
    no special paths. Each is a request, and each comes back as a decision."""
    _mode, authority = _guiding()
    outcome = authority.request(TransitionRequest(
        kind=kind, mode_name="review", step_id="s2", plan=Plan.build("p", ("a",))))
    assert isinstance(outcome.applied, bool)
    assert outcome.applied or outcome.note_ar, "a refusal was swallowed"


def test_an_unrecognised_kind_is_refused_and_never_treated_as_a_jump():
    """FAIL-CLOSED. The kind table is the whole vocabulary; anything else must
    stop here rather than fall through to the nearest branch."""
    _mode, authority = _guiding()
    outcome = authority.request(TransitionRequest(kind="teleport", step_id="s3"))
    assert outcome.applied is False
    assert _mode_step(_mode) == 1, "an unknown kind moved the plan"


def _mode_step(mode: SessionMode) -> int:
    return mode.current_step


# ─── The conditions: named now, stubbed now, and CONTROL is exempt ──────────

def test_the_conditions_are_the_RouteImpact_shape_and_default_to_blocking_nothing():
    """STUB-FIRST: both DEC-65 conditions are named and NOTHING SETS THEM YET.
    The shape is a frozen record of kernel facts with a predicate over them and
    no behaviour — `RouteImpact`'s, which is what DEC-65 asked for."""
    assert [f.name for f in dataclasses.fields(TransitionConditions)] == [
        "confirmation_pending", "sandbox_running"]
    assert TransitionConditions().blocking() is False
    assert TransitionConditions(confirmation_pending=True).blocking() is True
    assert TransitionConditions(sandbox_running=True).blocking() is True


def test_a_blocking_condition_refuses_a_MODEL_request_transiently():
    _mode, _ = _guiding()
    mode = SessionMode()
    authority = ModeAuthority(mode=mode, conditions=_Blocking())
    authority.request(TransitionRequest(kind=ENTER, mode_name="navigator",
                                        plan=Plan.build("d", ("a", "b"))))
    assert mode.active is False, "a blocked ENTER still started a mode"


@pytest.mark.parametrize("kind", sorted(CONTROL_KINDS))
def test_a_blocking_condition_can_NEVER_hold_the_user_in_a_mode(kind):
    """THE ASYMMETRY, and it is a security property rather than a convenience.

    If a pending condition could block the exit word or the expiry, a model
    could TRAP the user in a mode simply by keeping one pending — which is
    exactly what DEC-65's model-independent exit 1 exists to make impossible.
    Being trapped is a CONTROL problem, not a content one."""
    mode = SessionMode()
    ModeAuthority(mode=mode).request(TransitionRequest(kind=ENTER,
                                                       mode_name="navigator"))
    assert mode.active is True

    blocked = ModeAuthority(mode=mode, conditions=_Blocking())
    # The discriminating pair: the same conditions object refuses a MODEL
    # request in the same breath, so this is not a dead seam.
    assert blocked.request(TransitionRequest(kind=ADVANCE)).reason == BLOCKED
    assert blocked.request(TransitionRequest(kind=kind)).applied is True
    assert mode.active is False


# ─── 2. EVERY REFUSAL CARRIES ALL THREE OBLIGATIONS ─────────────────────────

@pytest.mark.parametrize("reason", ALL_REASONS)
def test_every_refusal_note_states_achieved_terminality_and_the_next_step(reason):
    """The standing note law (AGENTS.md, ruled in DEC-58), as a PROPERTY over the
    whole reason set. A refusal reporting only what did NOT happen produces a
    retry loop — M3 paid for that across four live runs."""
    note = refusal_note(reason, current=2, total=5)
    assert note, "a reason produced no note at all"
    assert DIRECTIVE_MARKER_AR in note, (
        "the note is not marked, so it would reach the DEC-16 approval detector")
    assert "\n" not in note, "a multi-line note defeats the line-wise strip"

    # (1) what WAS accomplished — every one of these changed nothing, and says so.
    assert "ما تغيّر شي" in note
    # (2) TERMINAL or TRANSIENT, and never silent about which.
    terminal = ("لا تعِد" in note) or ("لا تطلب" in note)
    transient = "مؤقّت" in note
    assert terminal != transient, f"note is neither or both: {note}"
    # (3) a valid NEXT STEP, named — "do not do X" leaves a model with no
    # sanctioned move, and the helpful move is usually the wrong one.
    assert any(verb in note for verb in
               ("ابدأ", "أنشئ", "أكمل", "اطلب", "أعِد", "ترجع", "تُنهي", "تقدّم"))


def test_the_blocked_note_is_the_only_TRANSIENT_one():
    """Both stub conditions resolve on their own, and every other refusal is a
    statement about the plan that retrying cannot change."""
    assert "مؤقّت" in refusal_note(BLOCKED)
    for reason in ALL_REASONS:
        if reason != BLOCKED:
            assert "مؤقّت" not in refusal_note(reason), reason


def test_an_unknown_reason_falls_back_to_the_note_that_CLAIMS_NOTHING():
    """DEC-35: a refusal that misreports its reason turns a terminal condition
    into a retryable one. Inventing a state is worse than admitting none."""
    assert refusal_note("something_new") == refusal_note(BLOCKED)


@pytest.mark.parametrize("kind,reason", [
    (ADVANCE, AT_END), (BACK, AT_START), (JUMP, UNKNOWN_STEP),
])
def test_a_bounds_refusal_names_its_own_reason_and_carries_the_REAL_numbers(kind, reason):
    mode, authority = _guiding(("only",))
    outcome = authority.request(TransitionRequest(kind=kind, step_id="s404"))
    assert outcome.applied is False and outcome.reason == reason
    assert "1" in outcome.note_ar, "the note lost the kernel's own numbers"
    assert mode.current_step == 1, "a refused move changed the plan anyway"


@pytest.mark.parametrize("kind,reason", [
    (ADVANCE, NO_MODE), (LEAVE, NO_MODE), (JUMP, NO_MODE), (EDIT_PLAN, NO_MODE),
])
def test_a_transition_with_no_mode_running_is_refused_and_reported(kind, reason):
    authority = ModeAuthority(mode=SessionMode())
    outcome = authority.request(TransitionRequest(kind=kind, step_id="s1"))
    assert (outcome.applied, outcome.reason) == (False, reason)


def test_a_mode_without_a_plan_refuses_a_move_rather_than_inventing_one():
    mode = SessionMode()
    authority = ModeAuthority(mode=mode)
    authority.request(TransitionRequest(kind=ENTER, mode_name="review"))
    assert authority.request(TransitionRequest(kind=ADVANCE)).reason == NO_PLAN
    assert mode.active is True, "a refused move ended the mode"


def test_an_unnamed_mode_is_refused_because_an_invisible_mode_is_worse_than_none():
    """T3 draws the frame; a nameless mode would run while the indicator showed
    nothing, and the indicator is the deterministic backstop the whole design
    rests on."""
    mode = SessionMode()
    outcome = ModeAuthority(mode=mode).request(TransitionRequest(kind=ENTER))
    assert (outcome.applied, outcome.reason) == (False, UNNAMED_MODE)
    assert mode.active is False


# ─── 3. NESTING IS UNREPRESENTABLE THROUGH THE AUTHORITY ────────────────────

class _Recording(SessionMode):
    """Records every state the frame passes through, so "never two operations"
    can be OBSERVED rather than argued from the source."""

    def __init__(self) -> None:
        super().__init__()
        self.observed: "list[object]" = []

    def enter(self, name, *, plan=None):        # type: ignore[override]
        super().enter(name, plan=plan)
        self.observed.append(self.name)

    def leave(self):                            # type: ignore[override]
        super().leave()
        self.observed.append(None)


def test_mode_to_mode_is_ONE_decision_with_no_state_in_between():
    mode = _Recording()
    authority = ModeAuthority(mode=mode)
    authority.request(TransitionRequest(kind=ENTER, mode_name="navigator"))
    authority.request(TransitionRequest(kind=ENTER, mode_name="review"))

    assert mode.observed == ["navigator", "review"], (
        f"the mode passed through {mode.observed} — a None between the two is "
        "the intermediate state nobody owns (DEC-24)")
    assert mode.name == "review" and mode.plan is None


def test_no_function_in_the_authority_calls_both_enter_and_leave():
    """The structural twin of the test above: a `leave()` added before the
    `enter()` would make the observation fail, and this makes it fail EARLIER
    and for a reason a reader can act on."""
    tree = ast.parse(TRANSITION_PY.read_text(encoding="utf-8"))
    for func in [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        calls = {node.func.attr for node in ast.walk(func)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        assert not {"enter", "leave"} <= calls, (
            f"{func.name} performs a mode change as TWO operations")


# ─── A mode still grants no privilege ───────────────────────────────────────

@pytest.mark.parametrize("path", [TRANSITION_PY, SURFACES_PY])
def test_the_authority_grants_no_privilege_and_holds_no_lifecycle(path):
    """The T1 invariant, carried forward: the authority reads two booleans about
    kernel state. It classifies no trust, holds no capability and schedules
    nothing. AST, never text — the docstrings discuss these on purpose."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = ({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} |
             {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)})
    for forbidden in ("capability", "capabilities", "grant", "grants", "has_grant",
                      "taint", "tainted", "raise_taint", "RouteImpact", "net",
                      "fetch", "execute", "sleep", "Timer", "create_task",
                      "Thread", "call_later", "interrupt", "interrupt_turn"):
        assert forbidden not in names, f"{path.name} names {forbidden}"
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & {"asyncio", "threading", "sched", "os", "json", "pickle"})
