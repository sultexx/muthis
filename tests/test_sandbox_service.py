# tests/test_sandbox_service.py
"""T5 — SandboxService: the turn-aware run_code executor (gate + runner + kill).

Fakes only (no real Docker): the ≤3/turn gate bounds runs and refuses the 4th,
new_turn() restores the budget, the runner's on_active seam tracks the live
container for eradication, and a hard failure passes its Arabic note through."""

from __future__ import annotations

import asyncio

from muthis_plugins.sandbox_exec.runner import SandboxOutcome
from muthis_plugins.sandbox_exec.sandbox_gate import SANDBOX_GATE_EXHAUSTED_AR
from muthis_plugins.sandbox_exec.service import (
    SANDBOX_TOOL_NAME,
    SandboxService,
    format_outcome_ar,
)


class _FakeRunner:
    def __init__(self, outcome=None):
        self.on_active = None
        self.calls = []
        self._outcome = outcome or SandboxOutcome(exit_code=0, stdout_tail="hi", wall_ms=5)

    async def run(self, args, *, attempt=1):
        self.calls.append((args, attempt))
        return self._outcome


def test_run_formats_the_outcome_and_counts_the_gate():
    runner = _FakeRunner()
    svc = SandboxService(runner=runner)
    out = asyncio.run(svc.run({"language": "python", "code": "print(1)"}))
    assert "رمز الخروج 0" in out and "hi" in out
    assert runner.calls[0][1] == 1                       # attempt = 1


def test_fourth_run_is_refused_and_new_turn_resets_the_budget():
    runner = _FakeRunner()
    svc = SandboxService(runner=runner)
    for _ in range(3):
        asyncio.run(svc.run({"language": "python", "code": "x"}))
    refused = asyncio.run(svc.run({"language": "python", "code": "x"}))
    assert refused == SANDBOX_GATE_EXHAUSTED_AR
    assert len(runner.calls) == 3                        # the 4th never reached the runner
    svc.new_turn()                                       # a fresh user turn
    asyncio.run(svc.run({"language": "python", "code": "x"}))
    assert len(runner.calls) == 4                        # fresh ≤3 budget


def test_tracks_the_live_container_and_kill_is_a_safe_noop():
    runner = _FakeRunner()
    svc = SandboxService(runner=runner)
    runner.on_active("muthis-run-xyz")                   # the runner announced a live container
    assert svc._active == "muthis-run-xyz"
    runner.on_active(None)                               # container gone
    assert svc._active is None
    svc.kill_active()                                    # no active container → safe no-op


def test_tool_name_is_the_namespaced_name():
    assert SANDBOX_TOOL_NAME == "sandbox.run_code"
    assert SandboxService(runner=_FakeRunner()).tool_name == "sandbox.run_code"


def test_a_hard_failure_note_passes_through():
    outcome = SandboxOutcome(exit_code=None, note_ar="تعذّر التشغيل المعزول")
    assert format_outcome_ar(outcome) == "تعذّر التشغيل المعزول"
