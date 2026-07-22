# tests/test_sandbox_gate.py
"""T3 — SandboxGate, the per-turn run limiter (DEC-3-B, fully decoupled).

Asserts: ≤3 runs/turn then the 4th is refused with the Arabic note; the gate
resets per user turn (fresh budget); and it is DECOUPLED from HighlightGate — a
separate class, sharing no base or instance, its module importing nothing from
the sealed kernel (built on the pattern, not the instance)."""

from __future__ import annotations

import re
from pathlib import Path

import muthis_plugins
from muthis.kernel.highlight_gate import HighlightGate
from muthis_plugins.sandbox_exec.sandbox_gate import (
    MAX_SANDBOX_RUNS,
    SANDBOX_GATE_EXHAUSTED_AR,
    SandboxGate,
)

GATE_SOURCE = Path(muthis_plugins.__file__).parent / "sandbox_exec" / "sandbox_gate.py"


def test_three_runs_then_the_fourth_is_refused():
    gate = SandboxGate()
    assert MAX_SANDBOX_RUNS == 3
    for _ in range(3):
        assert gate.consume() is None                    # runs 1, 2, 3 allowed
    assert gate.runs == 3 and gate.runs_remaining() == 0
    assert gate.consume() == SANDBOX_GATE_EXHAUSTED_AR   # the 4th refused
    assert gate.consume() == SANDBOX_GATE_EXHAUSTED_AR   # and every one beyond
    assert gate.runs == 3                                # a refusal never counts


def test_a_run_repeating_adversary_stops_at_three():
    gate = SandboxGate()
    allowed = sum(1 for _ in range(10) if gate.consume() is None)
    assert allowed == 3                                  # 10 attempts, only 3 ran


def test_resets_per_user_turn():
    gate = SandboxGate()
    for _ in range(4):
        gate.consume()
    gate.reset()                                         # fresh turn = fresh budget
    assert gate.runs == 0 and gate.consume() is None
    assert SandboxGate().consume() is None               # by-construction reset too


def test_note_is_an_internal_directive_with_sultans_framing():
    assert "توجيه داخلي" in SANDBOX_GATE_EXHAUSTED_AR        # not user-visible text
    assert "جرّبتُ ثلاث مرات" in SANDBOX_GATE_EXHAUSTED_AR   # the §2.5 framing verbatim


def test_decoupled_from_highlight_gate_pattern_not_instance():
    # different classes, no shared base — the pattern, never the instance
    assert SandboxGate is not HighlightGate
    assert not issubclass(SandboxGate, HighlightGate)
    # independent state: advancing the run gate never touches a draw gate
    sandbox, draw = SandboxGate(), HighlightGate()
    sandbox.consume()
    assert draw.drawn is False and sandbox.runs == 1
    # DEC-3-B: the gate module imports NOTHING from the app kernel
    for line in GATE_SOURCE.read_text(encoding="utf-8").splitlines():
        assert not re.match(r"\s*(from|import)\s+muthis(\.|\s|$)", line), line
