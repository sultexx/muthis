# tests/test_final_pass_is_text.py
"""
DEC-147 ② — THE LAST PASS IS ALWAYS TEXT.

`loop_tool_choice` forces tool_choice="none" on pass MAX_AGENTIC_ITERATIONS, so the
model cannot start a tool it has no pass left to explain — DEC-131's brake, applied
to the final pass. The durable log held eight cap hits, and every one was a tool
started on pass 4.

THE CLAIM THIS FILE VERIFIES RATHER THAN ASSUMES. Session 6's turn ended on two
contradictory next steps: the kernel's request for a fetch refused on pass 4, then
`AGENTIC_CAP_NOTE_AR`. With the last pass forced to text, a provider that honours
tool_choice — both real ones do, measured — can start no tool on pass 4, so neither
can be spoken. It is driven here through the REAL orchestrator, router and confirm
gate, with a scripted provider that WANTS a fetch on pass 4. The mutation that moves
the brake one pass late brings both back, and this file goes RED under it.

Run:  set PYTHONPATH=src && python -m pytest tests/test_final_pass_is_text.py -q
"""

from __future__ import annotations

import asyncio
import logging

from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.kernel import orchestrator as orchestrator_module
from muthis.kernel.budget import Budget
from muthis.kernel.highlight_gate import (
    MAX_AGENTIC_ITERATIONS, HighlightGate, loop_tool_choice,
)
from muthis.kernel.orchestrator import AGENTIC_CAP_NOTE_AR, Orchestrator
from muthis.kernel.tool_router import ToolRouter, namespaced_name
from muthis.trust.confirm_gate_detector import APPROVAL_WORD_AR
from muthis.trust.high_impact import NETWORK_CAPABILITY, RouteImpact
from muthis_sdk import ToolDescriptor, ToolPlugin, ToolResult

SEARCH = namespaced_name("web", "search")
FETCH = namespaced_name("web", "fetch")
ANSWER = "هذا الجواب من نتائج البحث."
READ = "read_local_file"
ARGS = {SEARCH: {"query": "بايثون"}, FETCH: {"url": "https://a.test/page"}, READ: {"path": "a.py"}}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class _Web(ToolPlugin):
    def __init__(self):
        self.calls: list[str] = []

    def descriptors(self):
        return [ToolDescriptor(name=n, schema={"name": n, "description": "d", "input_schema": {}},
                               kernel_serviced=False) for n in ("search", "fetch")]

    async def execute(self, tool, args, ctx):
        self.calls.append(tool)
        return ToolResult(text_ar="نتائج")


class _Provider:
    """Wants the next tool on its list on every pass. HONOURS tool_choice, as both
    real providers do; `obedient=False` is the provider the cap note is kept for."""

    def __init__(self, obedient=True):
        self.obedient = obedient
        self.wants: list[str] = []
        self.tool_choices: list[str] = []
        self._n = 0

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.tool_choices.append(tool_choice)
        self._n += 1
        if (tool_choice == "none" and self.obedient) or not self.wants:
            yield TextDelta(ANSWER)
            yield TurnComplete(input_tokens=1, output_tokens=1, cost_usd=0.0,
                               stop_reason="end_turn", model="fake",
                               assistant_content=[{"type": "text", "text": ANSWER}])
            return
        name = self.wants.pop(0) if self.obedient else self.wants[0]
        call = ToolCall(name=name, args=dict(ARGS[name]), tool_use_id=f"t{self._n}")
        yield call
        yield TurnComplete(input_tokens=1, output_tokens=1, cost_usd=0.0,
                           stop_reason="tool_use", model="fake",
                           assistant_content=[{"type": "tool_use", "id": call.tool_use_id,
                                               "name": name, "input": call.args}])


def _setup(tmp_path, *, tainted=True):
    plugin = _Web()
    router = ToolRouter()
    router.mount(plugin, namespace="web", provenance="web:test", taint=True,
                 impact=RouteImpact(capabilities=frozenset({NETWORK_CAPABILITY})))
    if tainted:
        router.session_taint.raise_taint("web:test")
    provider = _Provider()
    spoken: list[str] = []

    async def _tts(text):
        spoken.append(text)

    async def _capture():
        return PNG

    orchestrator = Orchestrator(
        reasoner=provider, budget=Budget(daily_limit_usd=1.0, budget_file=tmp_path / "b.json"),
        tts=_tts, screen_capture=_capture, router=router, stream_tts=False)
    return orchestrator, provider, plugin, spoken


def test_the_last_pass_the_loop_allows_is_forced_to_text():
    """The ordinal is DEC-121's `passes_serviced` — the passes ALREADY serviced — so
    the last pass is the one where it has reached the bound less one."""
    choices = [loop_tool_choice(HighlightGate(), None, n) for n in range(MAX_AGENTIC_ITERATIONS)]
    assert choices == ["auto"] * (MAX_AGENTIC_ITERATIONS - 1) + ["none"]
    assert loop_tool_choice(HighlightGate(), None, None) == "auto", (
        "the default is fail-open by design; the production wiring is pinned structurally")
    assert orchestrator_module.MAX_AGENTIC_ITERATIONS is MAX_AGENTIC_ITERATIONS == 4, (
        "the loop and the brake no longer read ONE bound — or the cap moved, which is DEC-111's")


def test_three_granted_searches_then_an_ANSWER_and_neither_next_step(tmp_path, caplog):
    """Session 6, re-run against the build: a search approved, three granted searches,
    and a fetch WANTED on pass 4. The last pass is text, so the fetch is never started —
    no kernel request for it, no cap note, and the answer is spoken."""
    orchestrator, provider, plugin, spoken = _setup(tmp_path)
    provider.wants = [SEARCH]
    asyncio.run(orchestrator.run_turn("ابحث لي عن بايثون"))      # refused: the session is tainted
    assert plugin.calls == []
    spoken.clear()
    provider.tool_choices.clear()

    provider.wants = [SEARCH, SEARCH, SEARCH, FETCH]
    with caplog.at_level(logging.INFO):
        asyncio.run(orchestrator.run_turn(APPROVAL_WORD_AR))    # the approval: a turn grant

    # The SYMPTOM first, so a regression fails on what the user would hear: the
    # brake one pass late speaks the fetch request, then the cap note, and no answer.
    said = " ".join(spoken)
    assert AGENTIC_CAP_NOTE_AR not in said, "the cap note was spoken — the loop ran out of passes"
    assert "وقفت طلباً" not in said and "دخلت هذه الجلسة" not in said, (
        "a kernel approval request was spoken in the answering turn")
    assert ANSWER in said, "the turn produced no answer"
    assert provider.tool_choices == ["auto", "auto", "auto", "none"]
    assert plugin.calls == ["search", "search", "search"]
    assert provider.wants == [FETCH], "the fetch was not left wanted and unstarted"
    assert "agentic cap" not in caplog.text and "web__fetch refused" not in caplog.text


def test_a_provider_that_IGNORES_none_still_ends_on_the_cap_note(tmp_path):
    """The fallback stays. On `read_local_file` — contained, never tainting, never
    gated, never drawn — the final-pass reason stands alone: the brake asks for text
    on the last pass, and a provider that disobeys it gets the cap note. (A web
    search cannot show this: its first result taints the session, and the confirm
    brake then fires first.)"""
    provider = _Provider(obedient=False)
    provider.wants = [READ]
    spoken: list[str] = []

    async def _tts(text):
        spoken.append(text)

    async def _capture():
        return PNG

    orchestrator = Orchestrator(
        reasoner=provider, budget=Budget(daily_limit_usd=1.0, budget_file=tmp_path / "b.json"),
        tts=_tts, screen_capture=_capture, stream_tts=False)
    asyncio.run(orchestrator.run_turn("اقرأ الملف"))
    assert provider.tool_choices == ["auto"] * (MAX_AGENTIC_ITERATIONS - 1) + ["none"]
    assert spoken and spoken[-1] == AGENTIC_CAP_NOTE_AR
