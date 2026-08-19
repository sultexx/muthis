# tests/test_step_expected_result.py
"""
`Step.expected_result` — DEC-107 Gate 1: the field exists, it is written ONCE,
and there is no path anywhere in `src/` that writes it a second time.

WHY IMMUTABILITY IS THE LOAD-BEARING PROPERTY AND NOT HYGIENE. The advance rule
compares a screen against the EXPECTED result, and "expected" means written in
advance. A model that could re-word the field AFTER a look would bring it into
agreement with what it just saw — the same circularity the field exists to
remove, arriving one cycle late. It leaves no trace: the field is still present,
still non-empty, and now matches the screen exactly.

THE PREVENTION IS THE STRUCTURE; THIS FILE IS THE PROOF. Sultan's ruling: NO AST
PARSING AT RUNTIME. `Step` is frozen, it is constructed at exactly ONE site, and
every `Plan` edit carries existing `Step` OBJECTS through by identity. This guard
states that as an ABSENCE OF MEANS over the whole source tree — the
`FetchedDomains` argument (DEC-36), the same shape `test_session_mode.py` uses
for privilege, persistence and text interpretation.

AND IT IS ARGUMENT-AWARE, WHICH IS THE WHOLE REASON IT IS A NEW GUARD RATHER
THAN A REUSE. `dataclasses.replace` is ALREADY on the DEC-65/66 allow-list —
`test_the_primitives_call_nothing_but_their_own_methods` permits exactly
`dataclass`, `replace`, `_clock` and `_on_change` — because `plan.py` calls it
six times for `Plan`'s sake. So `replace(step, expected_result=...)` is a
construction that passes the existing NAME-based guard in SILENCE. It is legal
Python and it was legal here until this file existed. A guard that scanned names
would never see it; one that reads KEYWORD ARGUMENTS sees it everywhere.

THE POSITIVE CONTROL IS NOT CEREMONY (Sultan's requirement, and DEC-50's rule).
"No write path exists" and "the field was never plumbed in at all" produce the
IDENTICAL empty scan. So the creation site is asserted to EXIST — at AST level
and behaviourally — before any absence below is allowed to mean anything.

Run:  set PYTHONDONTWRITEBYTECODE=1 && set PYTHONPATH=src && python -m pytest tests/test_step_expected_result.py -q
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib

import pytest

from muthis.kernel.plan import Plan, Step

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
PLAN_PY = SRC / "muthis" / "kernel" / "plan.py"
MODE_PY = SRC / "muthis" / "kernel" / "session_mode.py"
PRIMITIVES = (PLAN_PY, MODE_PY)

FIELD = "expected_result"

# The two call sites inside `plan.py` that may name the field: the ONE `Step`
# construction, and `build`'s forwarding into it. Written out rather than
# derived, so adding a third is a decision someone makes here on purpose.
PERMITTED_WRITERS = {"Step", "with_step_inserted"}


def _modules() -> "list[pathlib.Path]":
    return sorted(SRC.rglob("*.py"))


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _func_name(call: ast.Call) -> str:
    """The called name, however it was spelled: `Step(...)`,
    `dataclasses.replace(...)` and `self.with_step_inserted(...)` all reduce to
    one string, so a write cannot hide behind an import alias or an attribute."""
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _calls_naming_the_field(path: pathlib.Path) -> "list[ast.Call]":
    return [node for node in ast.walk(_tree(path)) if isinstance(node, ast.Call)
            and any(kw.arg == FIELD for kw in node.keywords)]


# ═══ THE POSITIVE CONTROLS — asserted FIRST, because every absence below is
# ═══ meaningless without them ════════════════════════════════════════════════

def test_the_guard_is_looking_at_a_real_source_tree():
    """A glob that silently matched nothing would make every assertion in this
    file pass while examining NOTHING, and would look exactly like a healthy
    guard — `test_module_line_ceiling.py`'s lesson, which exists because that
    is how a breach actually got through."""
    modules = _modules()

    assert SRC.is_dir(), f"the source tree is not where this guard looks: {SRC}"
    assert len(modules) > 50, (
        f"only {len(modules)} module(s) found under {SRC} — the guard is "
        "examining almost nothing, which is indistinguishable from passing")
    assert PLAN_PY in modules, "plan.py is not in the scanned set"


def test_the_CREATION_PATH_DOES_write_the_field_at_the_AST_level():
    """SULTAN'S CONTROL. Absence of a write path and absence of the FIELD are
    the same empty scan, so the one permitted write is proven to exist before
    any 'no other writes' claim is allowed to carry weight.

    It is asserted as EXACTLY ONE `Step` construction naming the field — not
    'at least one' — because that count is what makes the single-construction
    claim in `plan.py`'s docstring checkable rather than aspirational."""
    constructions = [c for c in _calls_naming_the_field(PLAN_PY)
                     if _func_name(c) == "Step"]

    assert len(constructions) == 1, (
        f"plan.py constructs `Step` with {FIELD} at {len(constructions)} sites, "
        "expected exactly 1 — the single-creation-site property is what the "
        "immutability proof rests on")


def test_the_CREATION_PATH_DOES_write_the_field_behaviourally():
    """The other half of the control: the AST proves the line is WRITTEN, this
    proves it ARRIVES. A constructor that named the field and dropped it would
    satisfy the scan above and store nothing."""
    plan = Plan.build("مسار", [
        {"text": "افتح المجلد", "expected_result": "المجلد مفتوح على الشاشة"},
        {"text": "احفظ الملف", "expected_result": "الملف ظاهر في القائمة"},
    ])

    assert [s.expected_result for s in plan.steps] == [
        "المجلد مفتوح على الشاشة", "الملف ظاهر في القائمة"]
    assert plan.steps[0].text == "افتح المجلد", "the two fields were swapped"


# ═══ THE ABSENCE OF MEANS — over ALL of `src/`, not just the primitives ══════

def test_NO_module_outside_plan_py_ever_names_the_field_as_an_argument():
    """THE MUTATION THAT MATTERS MOST, and it is legal Python.

    `dataclasses.replace(step, expected_result=...)` returns a `Step` with a
    rewritten result and raises nothing. The existing allow-list cannot see it
    because `replace` is a PERMITTED NAME there. This is the check that does,
    and it runs over every module in `src/` because a write from a caller is
    the same defect at a different address."""
    offenders = {path.relative_to(SRC).as_posix(): sorted(
                     {f"{_func_name(c)}:{c.lineno}" for c in calls})
                 for path in _modules() if path != PLAN_PY
                 and (calls := _calls_naming_the_field(path))}

    assert not offenders, (
        f"{FIELD} is passed as an argument outside plan.py: {offenders} — it is "
        "written ONCE, at construction. If this is a Gate 2 verifier READING "
        "the field, read it; do not rebuild the step")


def test_inside_plan_py_only_the_construction_and_its_forwarder_name_it():
    """The same rule one level in. A `replace(step, expected_result=...)` added
    INSIDE `plan.py` would pass the check above by living in the one exempt
    file, so the exemption is narrowed to two named call sites."""
    writers = {_func_name(call) for call in _calls_naming_the_field(PLAN_PY)}

    assert writers == PERMITTED_WRITERS, (
        f"plan.py names {FIELD} at {sorted(writers)}; permitted: "
        f"{sorted(PERMITTED_WRITERS)} — a third writer is a second write path")


def test_no_replace_call_anywhere_unpacks_its_keywords():
    """THE BYPASS THE KEYWORD SCAN WOULD BE BLIND TO, closed by shape.

    `replace(step, **{"expected_result": x})` carries no `arg` for the scans
    above to read. Rather than teach them to constant-fold a dict, the
    construction itself is forbidden — DEC-21-E's discipline, where the
    ALLOW-LIST closed a bypass a deny-list had passed in silence."""
    offenders = []
    for path in _modules():
        for node in ast.walk(_tree(path)):
            if (isinstance(node, ast.Call) and _func_name(node) == "replace"
                    and any(kw.arg is None for kw in node.keywords)):
                offenders.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno}")

    assert not offenders, (
        f"a `replace` call unpacks **kwargs at {offenders} — that makes every "
        f"keyword scan in this file blind to a {FIELD} write")


def test_nothing_in_src_reaches_for_the_frozen_dataclass_ESCAPE_HATCH():
    """`object.__setattr__(step, "expected_result", x)` writes THROUGH a frozen
    dataclass without raising. There is no legitimate use of it in this tree
    today, so the absence is asserted rather than the specific abuse — a rule
    over the MECHANISM, not over the one spelling someone happens to try
    (DEC-93's property-versus-category lesson)."""
    offenders = [f"{path.relative_to(SRC).as_posix()}:{node.lineno}"
                 for path in _modules() for node in ast.walk(_tree(path))
                 if isinstance(node, ast.Attribute) and node.attr == "__setattr__"]

    assert not offenders, (
        f"the frozen-record escape hatch is reachable at {offenders}")


def test_no_module_anywhere_ASSIGNS_to_the_field():
    """The direct spelling. `step.expected_result = x` already raises at
    runtime because the record is frozen — this states it as an absence too, so
    the day someone un-freezes `Step` the guard does not quietly go with it."""
    offenders = [f"{path.relative_to(SRC).as_posix()}:{node.lineno}"
                 for path in _modules() for node in ast.walk(_tree(path))
                 if isinstance(node, ast.Attribute) and node.attr == FIELD
                 and isinstance(node.ctx, ast.Store)]

    assert not offenders, f"{FIELD} is assigned at {offenders}"


@pytest.mark.parametrize("path", PRIMITIVES)
def test_the_primitives_never_READ_the_field_either(path):
    """DEC-66, extended to the new field exactly as it stands for `text`: the
    kernel STORES, NUMBERS and BOUNDS-CHECKS, and never INTERPRETS.

    SCOPED TO THE PRIMITIVES ON PURPOSE, and the scope is a design statement.
    A Gate 2 verifier MUST read this field — that is what it is for — so a
    tree-wide read ban would be a guard the next gate has to delete, and a
    guard deleted to make progress teaches that guards yield. The permanent
    property is that the modules holding the plan never look inside it."""
    reads = [node.lineno for node in ast.walk(_tree(path))
             if isinstance(node, ast.Attribute) and node.attr == FIELD]

    assert not reads, (
        f"{path.name} reads {FIELD} at line(s) {sorted(set(reads))} — storage "
        "became interpretation")


# ═══ THE RUNTIME HALF — what the language itself refuses ═════════════════════

def test_a_direct_write_raises_because_the_record_is_FROZEN():
    """The language-level prevention, driven rather than assumed."""
    step = Plan.build("t", [{"text": "a", "expected_result": "b"}]).steps[0]

    assert dataclasses.is_dataclass(Step)
    assert Step.__dataclass_params__.frozen is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        step.expected_result = "rewritten after a look"          # type: ignore[misc]


def test_a_step_carries_its_result_UNCHANGED_through_every_plan_edit():
    """THE PROPERTY THE WHOLE GATE IS FOR, driven end to end.

    Every edit rebuilds the PLAN and carries `Step` OBJECTS through by
    identity, so the result written at authoring time survives reordering,
    deletion, insertion and every move of the pointer. Asserted by OBJECT
    IDENTITY, not by value: two steps that merely compare equal would pass a
    value check while the plan had quietly rebuilt them."""
    plan = Plan.build("مسار", [
        {"text": "خطوة أولى", "expected_result": "النتيجة الأولى"},
        {"text": "خطوة ثانية", "expected_result": "النتيجة الثانية"},
        {"text": "خطوة ثالثة", "expected_result": "النتيجة الثالثة"},
    ])
    original = {step.id: step for step in plan.steps}

    plan = plan.with_steps_reordered([s.id for s in reversed(plan.steps)])
    plan = plan.with_current(plan.steps[0].id)
    plan = plan.advanced()
    plan = plan.moved_back()
    plan = plan.with_step_inserted("خطوة رابعة",
                                   expected_result="النتيجة الرابعة", at=1)
    plan = plan.without_step(plan.steps[-1].id)

    survivors = [s for s in plan.steps if s.id in original]
    assert survivors, "the edits emptied the plan — the test proves nothing"
    for step in survivors:
        assert step is original[step.id], (
            f"step {step.id} was REBUILT by a plan edit; a rebuild is where a "
            "rewritten expected_result would enter unseen")


def test_build_REFUSES_a_step_with_no_expected_result_rather_than_defaulting():
    """DEC-91's remedy, in its own words: "defaulting the missing field would
    re-create, inside our own code, the exact silence the module exists to
    close." A `KeyError` here is the loud failure the provider will not give
    us — and `""` would have satisfied every structural check downstream."""
    with pytest.raises(KeyError):
        Plan.build("t", [{"text": "a step with no declared result"}])

    with pytest.raises(TypeError):
        Plan(title="t").with_step_inserted("a step")             # type: ignore[call-arg]
