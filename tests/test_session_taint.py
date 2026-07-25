# tests/test_session_taint.py
"""
DEC-15 — session-sticky taint, raised at the router, enforced nowhere yet.

T4 RAISES and RECORDS; the confirmation gate that reads this state lands at T5
with the high-impact classification, because those are ONE concern (DEC-16).

THE CENTRAL INVARIANT under test: wrapping (DEC-14) and raising (DEC-15) are two
consequences of ONE classification, applied in ONE branch. If they could drift
apart, the milestone's worst hole opens — content WRAPPED but not RAISED leaves
the session looking clean, so T5's confirmation never fires on a session that has
already ingested adversarial content. It is tested in BOTH directions (every wrap
raised, every raise wrapped) as an EQUALITY per route type, plus structurally, so
a mutation that produces one without the other goes RED.

Everything here is mutation-verified (DEC-12): decoupling the raise from the
wrap, making the raise conditional on `is_error`, raising for `read_local_file`,
rebuilding the state per turn (the SandboxGate pattern — the mis-wiring DEC-15 is
most likely to suffer), adding a clearing method, and persisting to disk each
turn a test RED.

Run:  set PYTHONPATH=src && python -m pytest tests/test_session_taint.py -q
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import logging
import pathlib

from muthis.kernel.core_router import build_core_router
from muthis.kernel.session_taint import SessionTaint
from muthis.kernel.tool_router import ToolRouter, namespaced_name
from muthis_sdk import ToolDescriptor, ToolPlugin, ToolResult

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
TAINT_PY = SRC / "muthis" / "kernel" / "session_taint.py"
ROUTER_PY = SRC / "muthis" / "kernel" / "tool_router.py"
CORE_ROUTER_PY = SRC / "muthis" / "kernel" / "core_router.py"
COMPOSITION_PY = SRC / "muthis" / "composition.py"

OPEN_MARKER = "محتوى خارجي غير موثوق"     # named independently of the module


class _Plugin(ToolPlugin):
    def __init__(self, name, text="نتيجة", is_error=False, raises=False):
        self._name, self._text = name, text
        self._is_error, self._raises = is_error, raises

    def descriptors(self):
        return [ToolDescriptor(
            name=self._name,
            schema={"name": self._name, "description": "d", "input_schema": {}},
            kernel_serviced=False)]

    async def execute(self, tool, args, ctx):
        if self._raises:
            raise RuntimeError("contract breach")
        return ToolResult(text_ar=self._text, is_error=self._is_error)


def _service(router, tool, args=None):
    return asyncio.run(router.service(tool, args or {}))


# ─── Raisers ─────────────────────────────────────────────────────────────────

def test_a_tainted_route_raises_the_session_taint():
    """The mechanism is tool-AGNOSTIC: it keys off the kernel-side mount
    classification, so `web.search` and `web.fetch` raise the moment T6 mounts
    them taint=True — no per-tool list to keep in sync, nothing for T6 to
    remember. Both names are exercised here as the routes they will be."""
    for tool_name in ("search_web", "fetch_page"):
        taint = SessionTaint()
        router = ToolRouter(session_taint=taint)
        router.mount(_Plugin(tool_name), namespace="web",
                     provenance="web:test", taint=True)

        assert taint.tainted is False              # clean before
        _service(router, namespaced_name("web", tool_name))
        assert taint.tainted is True, f"{tool_name} did not raise taint"


def test_the_raise_is_recorded_once_in_english_naming_the_provenance(caplog):
    taint = SessionTaint()
    router = ToolRouter(session_taint=taint)
    router.mount(_Plugin("echo"), namespace="demo", provenance="mcp:demo",
                 taint=True)

    with caplog.at_level(logging.INFO):
        for _ in range(3):
            _service(router, namespaced_name("demo", "echo"))

    records = [r for r in caplog.records if "session-taint" in r.getMessage()]
    assert len(records) == 1, "the record must land ONCE per session, not per call"
    assert "mcp:demo" in records[0].getMessage()


def test_raising_an_already_raised_taint_is_a_no_op_and_never_throws():
    taint = SessionTaint()
    taint.raise_taint("mcp:demo")
    taint.raise_taint("mcp:demo")          # idempotent
    taint.raise_taint("web:other")         # a second source changes nothing
    assert taint.tainted is True


# ─── The NON-raiser: the highest-value regression test in T4 ─────────────────

def test_read_local_file_never_raises_the_session_taint():
    """A user-chosen file on the user's OWN machine is not external content.
    Raising here would taint EVERY teaching session — the read is the V1
    pedagogy spine — and would violate zero-behaviour-change outright."""
    async def fake_read(args):
        return f"محتوى {args['path']}"

    taint = SessionTaint()
    router = build_core_router(read_file=fake_read, session_taint=taint)

    outcome = _service(router, "read_local_file", {"path": "lesson.py"})

    assert outcome.result.text_ar == "محتوى lesson.py"   # byte-identical V1 seam
    assert outcome.taint is False
    assert taint.tainted is False, "a local read must NEVER taint the session"


def test_the_degraded_read_and_a_refusal_do_not_raise_either():
    """The failure paths of the untainted route are still untainted: an absent
    files seam and an unrouted/kernel-serviced refusal leave the session clean."""
    taint = SessionTaint()
    router = build_core_router(read_file=None, session_taint=taint)

    _service(router, "read_local_file", {"path": "x.py"})   # degraded note
    _service(router, "no_such_tool", {})                    # unrouted
    _service(router, "highlight_target", {})                # kernel-serviced

    assert taint.tainted is False


# ─── The coupling: one classification, both consequences ────────────────────

def _wrapped(outcome) -> bool:
    return OPEN_MARKER in outcome.result.text_ar


def test_wrapping_and_raising_are_the_same_decision_for_every_route_type():
    """BOTH DIRECTIONS AT ONCE, as an EQUALITY per route type: a result is
    wrapped IF AND ONLY IF this call raised the session taint. Asserting two
    separate facts would let a mutation satisfy one and skip the other."""
    cases = [
        ("untainted core read",   lambda t: build_core_router(
            read_file=_fake_read, session_taint=t), "read_local_file"),
        ("untainted plugin",      lambda t: _mounted(t, _Plugin("local"), False), "demo__local"),
        ("tainted plugin",        lambda t: _mounted(t, _Plugin("web"), True), "demo__web"),
        ("tainted error result",  lambda t: _mounted(
            t, _Plugin("web", text="تعذّر", is_error=True), True), "demo__web"),
        ("tainted raising plugin", lambda t: _mounted(
            t, _Plugin("web", raises=True), True), "demo__web"),
        ("untainted raising plugin", lambda t: _mounted(
            t, _Plugin("local", raises=True), False), "demo__local"),
    ]
    for label, build, tool in cases:
        taint = SessionTaint()
        outcome = _service(build(taint), tool, {"path": "x.py"})
        assert _wrapped(outcome) == taint.tainted, (
            f"{label}: wrapped={_wrapped(outcome)} but raised={taint.tainted} — "
            "the wrap and the raise have drifted apart")
        # and both agree with the flag the caller was handed
        assert outcome.taint == taint.tainted, label


async def _fake_read(args):
    return f"محتوى {args.get('path')}"


def _mounted(taint, plugin, tainted):
    router = ToolRouter(session_taint=taint)
    router.mount(plugin, namespace="demo", provenance="demo:test", taint=tainted)
    return router


def test_the_router_raises_and_wraps_under_exactly_one_condition():
    """STRUCTURAL half of the same invariant. Both calls must sit in ONE branch
    of `_outcome_for`: a SECOND `if` in that function is precisely how a future
    edit lets a result be wrapped without raising (or the reverse)."""
    tree = ast.parse(ROUTER_PY.read_text(encoding="utf-8"))
    func = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "_outcome_for")

    called = {n.func.attr if isinstance(n.func, ast.Attribute)
              else getattr(n.func, "id", "")
              for n in ast.walk(func) if isinstance(n, ast.Call)}
    assert "raise_taint" in called, "the router no longer raises session taint"
    assert "wrap_untrusted" in called, "the router no longer wraps"

    conditions = [n for n in ast.walk(func) if isinstance(n, ast.If)]
    assert len(conditions) == 1, (
        f"_outcome_for has {len(conditions)} conditions — the wrap and the raise "
        "must stay under ONE, so review any new branch here")


# ─── Lifetime: the process, NOT the turn ────────────────────────────────────

class _FakeSandbox:
    """The per-turn reset hook's real consumer, so the hook provably RAN."""

    def __init__(self):
        self.turns = 0

    def new_turn(self):
        self.turns += 1


def test_the_taint_survives_the_per_turn_reset_hook():
    """DEC-15 stickiness against the pattern most likely to break it. The
    per-turn hook (`TurnPass.new_turn_voice`) is where SandboxGate is REBUILT
    each turn — deliberately, for its ≤3-runs budget. Wiring SessionTaint by
    that analogy would silently defeat DEC-15, so this drives the REAL hook and
    asserts the sandbox gate DID reset (positive control) while the taint did
    NOT."""
    from muthis.kernel.turn_pass import TurnPass

    taint = SessionTaint()
    router = ToolRouter(session_taint=taint)
    router.mount(_Plugin("fetch_page"), namespace="web",
                 provenance="web:test", taint=True)
    sandbox = _FakeSandbox()
    turn_pass = TurnPass(reasoner=object(), budget=object(), overlay=object(),
                         voice=object(), stream_tts=False, router=router,
                         sandbox=sandbox)

    turn_pass.new_turn_voice()                          # turn 1 begins
    _service(router, namespaced_name("web", "fetch_page"))
    assert taint.tainted is True

    for _ in range(3):                                  # turns 2, 3, 4
        turn_pass.new_turn_voice()
        assert taint.tainted is True, "taint was cleared at a turn boundary"

    assert sandbox.turns == 4, "the per-turn hook never ran — vacuous test"


def test_the_taint_stays_raised_across_many_later_clean_calls():
    async def fake_read(args):
        return "محتوى"

    taint = SessionTaint()
    external = ToolRouter(session_taint=taint)
    external.mount(_Plugin("fetch_page"), namespace="web",
                   provenance="web:test", taint=True)
    core = build_core_router(read_file=fake_read, session_taint=taint)

    _service(external, namespaced_name("web", "fetch_page"))
    for _ in range(5):
        _service(core, "read_local_file", {"path": "x.py"})
    assert taint.tainted is True


def test_a_fresh_object_is_clean_so_a_new_process_is_the_only_reset():
    assert SessionTaint().tainted is False


# ─── The load-bearing ABSENCES ──────────────────────────────────────────────

def test_there_is_no_clearing_path_on_the_public_surface():
    """A "clear the taint" call would be a social-engineering channel — the very
    thing an injected page would ask the user to trigger. The surface is pinned
    EXACTLY, so any new public member fails here and gets reviewed."""
    public = {name for name in dir(SessionTaint) if not name.startswith("_")}
    assert public == {"tainted", "raise_taint"}, f"surface changed: {public}"

    # `tainted` is read-only: no setter, so the only way in is raise_taint.
    taint = SessionTaint()
    try:
        taint.tainted = False            # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("tainted became writable — taint can be cleared")


def test_the_state_is_never_persisted():
    """STRUCTURAL: working memory lives in RAM and dies with the session. A
    persisted taint would also outlive its justification — the content that
    caused it is gone with the transcript."""
    tree = ast.parse(TAINT_PY.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported == {"__future__", "logging"}, (
        f"session_taint.py imports beyond logging: {sorted(imported)}")

    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for io_symbol in ("open", "write_text", "read_text", "dump", "dumps",
                      "load", "loads", "Path", "mkdir", "unlink"):
        assert io_symbol not in names, f"session_taint.py touches I/O: {io_symbol}"


def test_the_state_has_no_model_or_user_facing_surface():
    """DEC-15: enforcement is STRUCTURAL at the router — no taint status line.
    Telling the model adds a promptable surface and buys no guarantee. Proven
    two ways: the module contains no Arabic at all (so it addresses neither the
    model nor the user), and the model-visible CATALOG is byte-identical before
    and after a raise."""
    source = TAINT_PY.read_text(encoding="utf-8")
    arabic = [ch for ch in source if "؀" <= ch <= "ۿ"]
    assert not arabic, "session_taint.py carries Arabic — it must not speak"

    taint = SessionTaint()
    router = ToolRouter(session_taint=taint)
    router.mount(_Plugin("fetch_page"), namespace="web",
                 provenance="web:test", taint=True)

    before = [d.schema for d in router.descriptors()]
    _service(router, namespaced_name("web", "fetch_page"))
    assert taint.tainted is True
    assert [d.schema for d in router.descriptors()] == before, (
        "the model-visible catalog changed with the taint state")


# ─── Injection at the composition root ──────────────────────────────────────

def test_the_router_exposes_the_injected_instance_and_defaults_fail_closed():
    injected = SessionTaint()
    assert ToolRouter(session_taint=injected).session_taint is injected
    # No injection must still RECORD — an absent security seam is how a session
    # stays "clean" while untrusted content flows through it.
    assert isinstance(ToolRouter().session_taint, SessionTaint)
    assert "session_taint" in inspect.signature(build_core_router).parameters


def test_the_composition_root_builds_the_session_taint_and_injects_it():
    """Source scan, not an import: `composition.py` is reached from `muthis.main`,
    which runs `load_dotenv()` at module level and would pull real credentials —
    now including a live TAVILY_API_KEY — into the test process."""
    tree = ast.parse(COMPOSITION_PY.read_text(encoding="utf-8"))
    built = any(isinstance(n, ast.Call) and getattr(n.func, "id", "") == "SessionTaint"
                for n in ast.walk(tree))
    injected = any(
        isinstance(n, ast.Call)
        and getattr(n.func, "id", "") == "build_core_router"
        and any(kw.arg == "session_taint" for kw in n.keywords)
        for n in ast.walk(tree))
    assert built, "the composition root no longer builds a SessionTaint"
    assert injected, "the composition root no longer injects it into the router"
