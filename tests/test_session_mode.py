"""
test_session_mode.py — DEC-65's `SessionMode`, and the STRUCTURAL guards over
BOTH T1 primitives.

THREE THINGS ARE PROVEN HERE AND THEY ARE PROVEN DIFFERENTLY.

1. THE FRAME, behaviourally: what the kernel owns, and that "step 3 of 5" is
   DERIVED from the plan rather than stored beside it.
2. THE INVARIANTS, STRUCTURALLY — no privilege, no persistence, no text
   interpretation, no nesting. These are asserted as an ABSENCE OF MEANS, the
   `FetchedDomains` argument (DEC-36): a module that cannot EXPRESS a privilege
   change cannot REGRESS into one. Every scan is over the AST, never the raw
   text, because the docstrings name "taint", "capability" and "privilege" ON
   PURPOSE — a text scan would fail on the very sentences that record why the
   symbols are absent (the `test_high_impact.py` precedent).
3. THE WIRING, END TO END through the REAL `_build_orchestrator`, with a
   marker class that makes the assertion DISCRIMINATING. A test that merely
   asserted "the prelude holds a SessionMode" would stay GREEN with the entire
   production wiring deleted, because the default builds one — which is DEC-40's
   defect exactly (five of six mutations survived because every test built its
   own graph) and DEC-71's (a TypeError on every production start, 1268 green).

The allow-lists below have ONE home, here, and cover `session_mode.py` AND
`plan.py` together — an allow-list split across two files is a deny-list
wearing a disguise (DEC-21-E).
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import pathlib

import pytest

from muthis.kernel.orchestrator import Orchestrator
from muthis.kernel.plan import Plan
from muthis.kernel.session_mode import ModeFrame, SessionMode
from muthis.kernel.turn_prelude import TurnPrelude

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
MODE_PY = SRC / "muthis" / "kernel" / "session_mode.py"
PLAN_PY = SRC / "muthis" / "kernel" / "plan.py"
COMPOSITION_PY = SRC / "muthis" / "composition.py"
PRIMITIVES = (MODE_PY, PLAN_PY)


class _Clock:
    """A hand-driven clock: idle time is DRIVEN, never slept for."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _names(path: pathlib.Path) -> "set[str]":
    """Every NAME and ATTRIBUTE the module uses. AST, never text: the
    docstrings deliberately discuss the symbols that must be absent."""
    tree = _tree(path)
    return ({node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} |
            {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)})


def _imports(path: pathlib.Path) -> "set[str]":
    imported = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    return imported


# ─── 1. THE FRAME the kernel owns (DEC-65) ───────────────────────────────────

def test_an_unentered_mode_is_inactive_and_reports_an_empty_frame():
    mode = SessionMode()
    assert mode.active is False
    assert mode.frame is None
    assert mode.name is None
    assert mode.plan is None
    assert mode.current_step == 0
    assert mode.total_steps == 0
    assert mode.idle_seconds() == 0.0


def test_entering_stores_the_frame_and_stamps_the_idle_clock():
    clock = _Clock()
    mode = SessionMode(clock=clock)
    mode.enter("navigator")
    assert mode.active is True
    assert mode.name == "navigator"
    assert mode.frame is not None and mode.frame.last_progress_at == 1000.0


def test_step_and_total_are_DERIVED_from_the_plan_not_stored_beside_it():
    """"Step 3 of 5" is a STRUCTURAL FACT. Stored copies are how the number the
    kernel SPEAKS and the number it DRAWS come apart (DEC-15's reason for
    keeping `external` off `RouteImpact`)."""
    mode = SessionMode()
    plan = Plan.build("deploy", ("build", "test", "ship"))
    mode.enter("navigator", plan=plan)
    assert (mode.current_step, mode.total_steps) == (1, 3)

    # The SAME mode object now reports the new numbers, with nothing restated.
    mode.record_progress(plan=plan.advanced())
    assert (mode.current_step, mode.total_steps) == (2, 3)
    assert {f.name for f in dataclasses.fields(ModeFrame)} == {
        "name", "plan", "last_progress_at"}, "a step/total field was stored"


def test_a_mode_may_run_without_a_plan():
    """Future modes inherit this primitive; a Review mode has no steps. The
    frame reads honestly rather than reporting step 0 of 0 as a failure."""
    mode = SessionMode()
    mode.enter("review")
    assert mode.active is True and mode.plan is None
    assert (mode.current_step, mode.total_steps) == (0, 0)


def test_leaving_empties_the_slot_and_is_idempotent():
    mode = SessionMode()
    mode.enter("navigator")
    mode.leave()
    mode.leave()
    assert mode.active is False and mode.frame is None


# ─── NO NESTING — one mode at a time, and the type cannot hold two ───────────

def test_entering_while_active_REPLACES_in_one_assignment_with_nothing_to_pop_back_to():
    """DEC-65: a mode-to-mode change is ONE evaluated decision (exit and enter
    together), never two sequential operations — two would create the
    intermediate state nobody owns, the undefined THIRD state DEC-24 closed at
    `broker.py:92`."""
    mode = SessionMode()
    mode.enter("navigator", plan=Plan.build("a", ("one",)))
    mode.enter("review")

    assert mode.name == "review"
    assert mode.plan is None, "the replaced mode's plan survived the replacement"

    frames = [value for value in vars(mode).values() if isinstance(value, ModeFrame)]
    assert len(frames) == 1, f"the instance holds {len(frames)} frames, not one"
    for value in vars(mode).values():
        assert not isinstance(value, (list, tuple, set, dict)), (
            f"a collection appeared on the mode: {value!r} — a stack of frames "
            "is exactly what must stay unrepresentable")


def test_the_frame_type_cannot_reference_another_frame():
    """The other half of the property: even one slot would nest if a frame
    could hold a frame."""
    for field in dataclasses.fields(ModeFrame):
        assert "ModeFrame" not in str(field.type), (
            f"ModeFrame.{field.name} can hold another frame")
        assert not str(field.type).startswith(("list", "tuple", "set", "dict")), (
            f"ModeFrame.{field.name} is a collection")


def test_the_module_has_no_way_to_accumulate_frames():
    """STRUCTURAL: no collection is built anywhere in `session_mode.py`, so
    "keep the previous mode and pop back to it later" is not a thing a future
    edit can reach for without first introducing the means."""
    # BODIES ONLY: `__all__` is a list and `Callable[[], float]` carries an
    # empty one, and neither accumulates anything. Accumulation happens in
    # executable statements, so that is exactly where this looks.
    bodies = [statement
              for node in ast.walk(_tree(MODE_PY))
              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
              for statement in node.body]
    assert len(bodies) > 10, (
        f"the scan admitted only {len(bodies)} statements — a guard that "
        "examined nothing must never look like a guard that passed (DEC-50)")
    literals = [node for statement in bodies for node in ast.walk(statement)
                if isinstance(node, (ast.List, ast.Set, ast.Dict, ast.ListComp,
                                     ast.SetComp, ast.DictComp))]
    assert not literals, "a collection literal appeared in session_mode.py"
    for forbidden in ("append", "extend", "insert", "pop", "push", "add"):
        assert forbidden not in _names(MODE_PY), (
            f"session_mode.py gained an accumulation call: {forbidden}")


# ─── Idle time is REPORTED; expiry is T2's and belongs to no timer ───────────

def test_idle_time_grows_and_progress_resets_it():
    clock = _Clock()
    mode = SessionMode(clock=clock)
    mode.enter("navigator")
    clock.now += 42.0
    assert mode.idle_seconds() == 42.0
    mode.record_progress()
    assert mode.idle_seconds() == 0.0


def test_mode_persistence_is_INDEPENDENT_of_step_progress():
    """DEC-65: a side question answered mid-mode advances nothing and ends
    nothing — by design, not by patch. It simply never calls `record_progress`,
    and the mode is untouched by that."""
    clock = _Clock()
    mode = SessionMode(clock=clock)
    plan = Plan.build("deploy", ("build", "test"))
    mode.enter("navigator", plan=plan)
    clock.now += 600.0                      # ten minutes on one step

    assert mode.active is True, "idle time alone ended the mode"
    assert mode.current_step == 1, "idle time alone advanced the step"
    assert mode.idle_seconds() == 600.0, "the idle clock is the thing that moved"


def test_progress_on_an_inactive_mode_can_never_resurrect_one():
    mode = SessionMode()
    mode.record_progress(plan=Plan.build("x", ("a",)))
    assert mode.active is False and mode.frame is None


def test_the_module_holds_no_expiry_decision_and_no_timer():
    """DEC-65 evaluates the inactivity exit LAZILY at the next turn's start,
    NEVER by a background timer: a timer is a lifecycle outside the kernel,
    which Law 11 forbids and which DEC-47 already rejected for background
    ingestion. The absence is structural — there is no threshold to read and
    no scheduling symbol to call."""
    names = _names(MODE_PY)
    for scheduling in ("sleep", "call_later", "call_soon", "Timer", "create_task",
                       "Thread", "run_in_executor", "to_thread"):
        assert scheduling not in names, f"session_mode.py schedules: {scheduling}"
    assert not (_imports(MODE_PY) & {"asyncio", "threading", "sched", "signal"})
    # No threshold constant: every module-level assignment is documentation or
    # a name, never a number a future reader would take for a timeout.
    numbers = [node for node in ast.walk(_tree(MODE_PY))
               if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
               and isinstance(node.value.value, (int, float))
               and not isinstance(node.value.value, bool)]
    assert not numbers, "a bare numeric constant appeared — expiry is T2's"


# ─── 2. THE INVARIANTS, asserted as an ABSENCE OF MEANS ─────────────────────

@pytest.mark.parametrize("path,expected", [
    (MODE_PY, {"__future__", "dataclasses", "time", "typing", "plan"}),
    (PLAN_PY, {"__future__", "dataclasses", "typing"}),
])
def test_the_primitives_import_nothing_that_could_persist_log_or_grant(path, expected):
    assert _imports(path) == expected, (
        f"{path.name} imports beyond its declared set: {sorted(_imports(path))}")


@pytest.mark.parametrize("path", PRIMITIVES)
def test_a_mode_GRANTS_NO_PRIVILEGE_and_cannot_express_one(path):
    """DEC-65's hard invariant. Recorded because it looks obvious today and
    becomes tempting after three modes — *"in Debug mode, give the sandbox
    network"* is a CONSTITUTIONAL change (DEC-3 is the only execution carve-out
    and it does not move) and must read as one when someone proposes it. If the
    module cannot EXPRESS the change, it cannot REGRESS into it."""
    names = _names(path)
    for privilege in ("taint", "tainted", "raise_taint", "SessionTaint",
                      "capability", "capabilities", "Capability", "grant",
                      "grants", "has_grant", "privilege", "RouteImpact",
                      "read_only", "net", "fetch", "fetch_readable", "execute",
                      "sandbox", "run_code", "confirm_gate", "session_taint"):
        assert privilege not in names, (
            f"{path.name} names a privilege symbol: {privilege} — a mode changes "
            "conversational behaviour ONLY")


@pytest.mark.parametrize("path", PRIMITIVES)
def test_the_state_is_NEVER_PERSISTED_and_has_no_means_to_be(path):
    """It dies with the process — the `SessionIndex` / `SessionTaint` shape,
    and privacy-first (CONTRIBUTING.md law 6). Structural, not promised."""
    names = _names(path)
    for io_symbol in ("open", "write", "write_text", "read_text", "writelines",
                      "dump", "dumps", "load", "loads", "save", "Path", "mkdir",
                      "unlink", "json", "pickle", "shelve", "sqlite3", "os",
                      "shutil", "tempfile", "environ", "getenv"):
        assert io_symbol not in names, f"{path.name} touches persistence: {io_symbol}"


@pytest.mark.parametrize("path", PRIMITIVES)
def test_neither_primitive_has_a_logger_at_all(path):
    """Sharper here than for `FetchedDomains`, which had no domain to protect
    beyond a hostname: a `Plan` holds MODEL-AUTHORED step text that may echo
    whatever was on the user's screen. No logging import means no means."""
    assert "logging" not in _imports(path)
    for logging_symbol in ("logger", "getLogger", "warning", "debug", "exception"):
        assert logging_symbol not in _names(path), (
            f"{path.name} gained a log surface: {logging_symbol}")


@pytest.mark.parametrize("path", PRIMITIVES)
def test_no_method_anywhere_READS_step_text(path):
    """DEC-66: the kernel STORES, NUMBERS and BOUNDS-CHECKS; it never
    INTERPRETS. Retention is not comprehension — `turn_hooks` holds opaque
    callables the router never inspects (DEC-37), the router carries wrapped
    content it never parses (DEC-14). `text` is written at construction and
    returned whole, so ANY `.text` access at all is the violation."""
    attributes = [node for node in ast.walk(_tree(path))
                  if isinstance(node, ast.Attribute)]
    assert len(attributes) > 5, (
        f"the scan admitted only {len(attributes)} attribute accesses — a "
        "guard that examined nothing must never look like one that passed")
    reads = [node for node in attributes if node.attr == "text"]
    assert not reads, (
        f"{path.name} reads step text at line(s) "
        f"{sorted({node.lineno for node in reads})} — storage became interpretation")


@pytest.mark.parametrize("path", PRIMITIVES)
def test_the_primitives_call_nothing_but_their_own_methods(path):
    """THE ALLOW-LIST, not a deny-list — DEC-21-E's lesson, where a deny-list
    passed a bypass silently and the allow-list caught it with zero
    maintenance. Anything these modules call that they did not define is a new
    capability: `text.lower()`, `json.dumps()`, `logger.info()` all land here
    the moment they are written, and none of them needs to be predicted."""
    tree = _tree(path)
    defined = {node.name for node in ast.walk(tree)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    # `dataclasses.dataclass` declares the record, `dataclasses.replace` is how
    # a frozen one is edited, `_clock` is the injected time seam, and
    # `_on_change` is T3's OPAQUE observer — the DEC-37 shape, a callable this
    # module fires without ever learning what it does. Four names, written out,
    # and they are the whole exception list: this guard is what forced the
    # fourth to be DECLARED rather than slipped in beside the others.
    permitted = defined | {"dataclass", "replace", "_clock", "_on_change"}
    called = {node.func.attr for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert len(called) > 2, (
        f"the scan admitted only {sorted(called)} — a guard that examined "
        "nothing must never look like a guard that passed (DEC-50)")
    assert called <= permitted, (
        f"{path.name} calls methods it does not define: {sorted(called - permitted)}")


def test_the_public_surface_is_pinned():
    """The `SessionTaint` precedent: the surface is the contract, and an
    addition here — an `is_expired`, a `clear`, a `persist` — must be
    DECLARED rather than discovered."""
    surface = {name for name in dir(SessionMode) if not name.startswith("_")}
    assert surface == {"active", "frame", "name", "plan", "current_step",
                       "total_steps", "idle_seconds", "enter", "leave",
                       "record_progress"}, f"surface changed: {sorted(surface)}"


def test_the_frame_is_read_only_from_outside_and_frozen_within():
    mode = SessionMode()
    mode.enter("navigator")
    with pytest.raises(AttributeError):
        mode.frame = None                      # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        mode.frame.name = "other"              # type: ignore[misc]


def test_neither_primitive_speaks_to_the_model_or_the_user():
    """Zero Arabic, the `SessionTaint` check: the kernel owns the FRAME, and
    the frame is numbers and a name. Every model-facing sentence about a mode —
    the directive line, the refusal that states what was achieved — is T2's,
    where a note can be written to the standing rule."""
    for path in PRIMITIVES:
        arabic = [ch for ch in path.read_text(encoding="utf-8") if "؀" <= ch <= "ۿ"]
        assert not arabic, f"{path.name} carries Arabic — it must not speak"


# ─── 3. THE WIRING, driven through the REAL composition root ────────────────

class _MarkedMode(SessionMode):
    """A marker, so the end-to-end assertion DISCRIMINATES. Asserting only
    that the prelude holds *a* SessionMode would stay green with the whole
    production wiring deleted, because the default builds one — the exact
    shape of DEC-40's five surviving mutations."""


def test_the_orchestrator_pays_only_for_injection_and_the_prelude_holds_the_mode():
    injected = SessionMode()
    orchestrator = Orchestrator(reasoner=object(), budget=object(),
                                session_mode=injected)
    assert orchestrator._prelude.session_mode is injected
    assert "session_mode" in inspect.signature(Orchestrator.__init__).parameters


def test_an_uninjected_prelude_still_holds_a_REAL_mode_never_None():
    """Fail-safe by default, the `SessionTaint` / `PassServiced` shape: a
    consumer must never branch on absence, because that branch is where the
    injected world and the default world drift apart."""
    assert isinstance(TurnPrelude().session_mode, SessionMode)
    assert isinstance(Orchestrator(reasoner=object(), budget=object())
                      ._prelude.session_mode, SessionMode)


def test_the_REAL_build_orchestrator_builds_the_mode_and_it_reaches_the_prelude(monkeypatch):
    """END TO END through production's own helper, not a graph this test built.

    The marker is what makes it bite: delete the `SessionMode()` line, or the
    `session_mode=` argument, or the orchestrator's pass-through, and the
    prelude falls back to its own default — which is a SessionMode, but NOT
    this one."""
    from muthis import composition

    monkeypatch.setattr(composition, "SessionMode", _MarkedMode)
    orchestrator = composition._build_orchestrator(
        object(), object(), object(), object(), object(), object())

    assert isinstance(orchestrator._prelude.session_mode, _MarkedMode), (
        "the composition root's SessionMode did not reach the prelude")


def test_the_composition_root_builds_the_session_mode_and_injects_it():
    """Sultan's T1 condition, and a SOURCE scan rather than an import:
    `composition.py` is reachable from `muthis.main`, which runs `load_dotenv()`
    at module level and would pull real credentials into the test process
    (the standing rule of 2026-07-25)."""
    tree = _tree(COMPOSITION_PY)
    built = {node.targets[0].id for node in ast.walk(tree)
             if isinstance(node, ast.Assign)
             and isinstance(node.value, ast.Call)
             and getattr(node.value.func, "id", "") == "SessionMode"
             and isinstance(node.targets[0], ast.Name)}
    assert built, "the composition root no longer BUILDS a SessionMode"

    injected = [
        keyword for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Orchestrator"
        for keyword in node.keywords if keyword.arg == "session_mode"]
    assert injected, "the composition root no longer INJECTS it into the Orchestrator"
    # The value must be the mode built above — `session_mode=None` would satisfy
    # a laxer check while wiring nothing at all.
    assert all(isinstance(keyword.value, ast.Name) and keyword.value.id in built
               for keyword in injected), (
        "the Orchestrator is handed something other than the SessionMode built here")
