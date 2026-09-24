# tests/test_confirm_gate_state.py
"""
The STATE extraction's guards — `trust/confirm_gate_state.py`, the confirm gate's
memory, moved out of `confirm_gate.py` ahead of DEC-143.

The move's argument is `call_binding.py`'s: POLICY versus MECHANISM. The gate keeps
what it DECIDES — whether a call is refused and whether it is released — and the
state module keeps what it REMEMBERS. These tests make that shape STRUCTURAL rather
than promised, and each fails if its property is lost:

  * the state module is pure stdlib and importable in isolation;
  * it holds NO policy and NO logger — it decides nothing, and every log line stays
    in the gate, on the gate's logger, so the durable log reads the same;
  * the old home stopped doing the work: the gate's CODE no longer touches the
    moved state or builds a `_Pending` — a copy left behind would pass every
    behavioural test, which is why this is asserted and not assumed;
  * the gate OWNS its one state — built in its constructor, never injected — and
    no subclass of the gate exists in `src/`, so the router's default gate and the
    composition root's gate are ONE gate. DEC-40's measured failure (production
    running one object while the suite tests another) is unrepresentable here,
    not merely avoided.

Behavioural equivalence was proven outside the suite and is recorded in the
commit: 169,759 lockstep steps against the base gate, identical, with two
non-equivalent negative controls that DIVERGED.

Run:  set PYTHONPATH=src && python -m pytest tests/test_confirm_gate_state.py -q
"""

from __future__ import annotations

import ast
import inspect
import pathlib

from muthis.trust import confirm_gate, confirm_gate_state
from muthis.trust.confirm_gate import ConfirmGate
from muthis.trust.confirm_gate_state import GateState

GATE = pathlib.Path(confirm_gate.__file__)
STATE = pathlib.Path(confirm_gate_state.__file__)
SRC_MUTHIS = GATE.resolve().parents[1]


def _code_names(path: pathlib.Path) -> set[str]:
    """Every name the CODE uses — never the prose, which discusses the moved
    fields on purpose."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return ({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
            | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names})


def test_the_state_module_is_pure_stdlib_and_importable_in_isolation():
    tree = ast.parse(STATE.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "the state module reaches a sibling — it must stand alone"
            mods.add((node.module or "").split(".")[0])
    assert mods <= {"__future__", "dataclasses", "typing"}, (
        f"the state module grew a dependency: {sorted(mods)}")


def test_the_state_module_holds_NO_policy_and_NO_logger():
    """It REMEMBERS; it never decides. A detector, a note, a binding, a
    classification or a logger here would mean the move took policy along with the
    mechanism — and a logger would let a line leave the gate's own channel."""
    names = _code_names(STATE)
    for forbidden in ("detect_confirmation", "APPROVAL_WORDS_AR", "confirm_note",
                      "spoken_request", "canonical_call", "call_fingerprint",
                      "high_impact", "tainted", "logging", "logger", "getLogger"):
        assert forbidden not in names, f"{forbidden} reached the state module"


def test_the_old_home_stopped_doing_the_work():
    """The move is only real if the gate no longer touches what moved: its CODE
    names none of the old private fields and builds no `_Pending`, and
    `dataclasses` — imported for those alone — is gone."""
    names = _code_names(GATE)
    for moved in ("_pending", "_missed", "_spoken", "_observed_this_turn",
                  "_Pending", "dataclasses"):
        assert moved not in names, f"{moved} is still handled in the gate — a copy was left behind"


def test_the_gate_OWNS_one_state_it_builds_itself():
    """No injection seam: the constructor takes nothing, and each gate builds its
    own state, so two gates never share one."""
    assert list(inspect.signature(ConfirmGate.__init__).parameters) == ["self"]
    first, second = ConfirmGate(), ConfirmGate()
    assert isinstance(first._state, GateState)
    assert first._state is not second._state


def test_no_subclass_of_the_gate_exists_and_every_router_builds_the_same_one():
    """DEC-40's condition, made unrepresentable: production must never run one gate
    while the suite's default routers build another. No class in `src/` derives
    from `ConfirmGate`, and the router's default and the composition root both
    construct the ONE class, with no arguments."""
    subclasses: list[str] = []
    constructions: dict[str, list[int]] = {}
    for path in SRC_MUTHIS.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef) and any(
                    getattr(base, "id", getattr(base, "attr", None)) == "ConfirmGate"
                    for base in node.bases):
                subclasses.append(f"{path.name}:{node.name}")
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "ConfirmGate":
                constructions.setdefault(path.name, []).append(len(node.args) + len(node.keywords))
    assert subclasses == [], f"a second gate class exists: {subclasses}"
    assert constructions.get("tool_router.py") == [0], constructions
    assert constructions.get("composition.py") == [0], constructions
