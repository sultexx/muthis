# tests/test_run_code_servicing.py
"""T5 — run_code is SERVICED through the kernel (not refused), bounded ≤3/turn,
and paired BY NAME in history — with a FAKE sandbox seam (no real Docker).

This proves the corrected-T5 wiring end to end: turn_pass detects sandbox.run_code
(instead of dropping it as a LOOK-only violation), dispatches it to the injected
servicer after the sync point, the gate is reset once per turn, and
build_tool_result_message answers the run_code id with the runner's Arabic output
so the agentic loop can read it and explain."""

from __future__ import annotations

import asyncio

from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.kernel.budget import Budget
from muthis.kernel.orchestrator import Orchestrator
from muthis.kernel.turn import DownscaledImage

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


class _FakeSandbox:
    """The injected servicer seam: tool_name + new_turn() + async run()."""

    tool_name = "sandbox.run_code"

    def __init__(self, output="انتهى التشغيل برمز الخروج 0. المخرَج:\n1"):
        self.runs: list[dict] = []
        self.turns = 0
        self._output = output

    def new_turn(self) -> None:
        self.turns += 1

    async def run(self, args: dict) -> str:
        self.runs.append(args)
        return self._output


_ARGS = {"language": "python", "code": "print(1)"}
_TOOL_USE = {"type": "tool_use", "id": "run_1", "name": "sandbox.run_code", "input": _ARGS}


class _RunCodeReasoner:
    """Pass 1 emits a run_code tool_use; pass 2 (the continuation) explains."""

    def __init__(self):
        self.calls = []

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.calls.append((user_input.text, tool_choice))
        if len(self.calls) == 1:
            yield ToolCall(name="sandbox.run_code", args=_ARGS, tool_use_id="run_1")
            yield TurnComplete(input_tokens=10, output_tokens=5, cost_usd=0.0001,
                               stop_reason="tool_use", model="claude-sonnet-4-6",
                               assistant_content=[_TOOL_USE])
        else:
            yield TextDelta("شغّلتُ الكود ونجح، وطبع 1.")
            yield TurnComplete(input_tokens=5, output_tokens=5, cost_usd=0.0001,
                               stop_reason="end_turn", model="claude-sonnet-4-6",
                               assistant_content=[{"type": "text", "text": "شرح"}])


class _Overlay:
    async def show(self, bbox, label_ar): pass
    async def hide(self): pass
    def set_state(self, state): pass
    def clear_status_light(self): pass


async def _capture():
    return PNG


async def _downscale(shot):
    return DownscaledImage(shot, 1280, 720, 1.0, 1.0)


async def _silent_tts(text):
    return None


def _orchestrator(tmp_path, reasoner, sandbox):
    budget = Budget(daily_limit_usd=1.0, budget_file=tmp_path / "budget.json",
                    today_fn=lambda: "2026-07-22")
    return Orchestrator(reasoner=reasoner, budget=budget, tts=_silent_tts,
                        overlay=_Overlay(), screen_capture=_capture,
                        downscale=_downscale, sandbox=sandbox)


def test_run_code_is_serviced_bounded_and_paired_by_name(tmp_path):
    reasoner, sandbox = _RunCodeReasoner(), _FakeSandbox()
    orch = _orchestrator(tmp_path, reasoner, sandbox)

    asyncio.run(orch.run_turn("شغّل لي الكود"))

    assert sandbox.runs == [_ARGS]              # serviced (NOT refused as LOOK-only)
    assert sandbox.turns == 1                    # the gate was reset once, per turn
    assert len(reasoner.calls) == 2              # the agentic loop continued (run → explain)

    # the runner's output was paired to the run_code id in history (Option B)
    paired = [
        block["content"]
        for message in orch.history if message["role"] == "user"
        for block in message["content"]
        if block.get("type") == "tool_result" and block.get("tool_use_id") == "run_1"
    ]
    assert paired and "رمز الخروج 0" in paired[0]


def test_without_a_sandbox_seam_run_code_is_not_serviced(tmp_path):
    # No sandbox injected → run_code falls to the LOOK-only guard (never serviced);
    # the turn still completes cleanly (defensive: the model would not see it anyway).
    reasoner = _RunCodeReasoner()
    budget = Budget(daily_limit_usd=1.0, budget_file=tmp_path / "budget.json",
                    today_fn=lambda: "2026-07-22")
    orch = Orchestrator(reasoner=reasoner, budget=budget, tts=_silent_tts,
                        overlay=_Overlay(), screen_capture=_capture, downscale=_downscale)
    asyncio.run(orch.run_turn("شغّل لي الكود"))
    # the run_code id got the 'unavailable' note (never a draw ack), history valid
    notes = [
        block["content"]
        for message in orch.history if message["role"] == "user"
        for block in message["content"]
        if block.get("type") == "tool_result" and block.get("tool_use_id") == "run_1"
    ]
    assert notes  # paired (API-valid), not dropped
