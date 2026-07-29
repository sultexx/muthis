# tests/test_cost_bridge.py
"""
The DEC-34 cost bridge — candidate (1), mutation-verified.

THE QUESTION THIS FILE ANSWERS is not "does the ledger handle a missing cost?"
(measured: `record_plugin_call` already coerces None to 0.0 and always counts the
call, so the ledger fails safe on its own). It is the sharper one that survived
the candidate comparison:

    can any path cause `_record` to be SKIPPED, or to FIRE TWICE?

A skipped call is invisible and looks free; a doubled one inflates the `calls`
column that per-plugin attribution is FOR. So every path through `service()` is
driven and the ledger calls are COUNTED, not merely inspected: normal (with and
without a carrier), the degraded read, a raising plugin, a raising carrier, the
confirm-gate refusal, an unrouted tool and a kernel-serviced misroute.

WHO OWNS THE NUMBER is the reason candidate (1) won, so it is asserted too: the
ROUTER obtains the cost, and the plugin-facing contracts (`ToolResult`,
`ServiceOutcome`, `can_afford`, `record_turn`) are pinned UNCHANGED. Under the
rejected candidate (2) a plugin would have declared a number that reaches the
sovereign daily total — the `is_error` hole of DEC-29 in the one place Rule 10
exists to defend.

THE KNOWN LIMIT IS A TEST, not prose: a plugin without `execute_with_cost`
records ZERO and still increments the call count, driven through the REAL Budget.

No test here imports `muthis.main` (standing rule): live credentials.
"""

from __future__ import annotations

import asyncio
import inspect
import json

import pytest

from muthis.kernel.budget import Budget
from muthis.kernel.core_router import build_core_router
from muthis.kernel.router_surfaces import namespaced_name
from muthis.kernel.tool_router import ToolRouter
from muthis.trust.high_impact import NETWORK_CAPABILITY, RouteImpact
from muthis_plugins.web_research import WebResearchPlugin
from muthis_sdk import (
    PluginContext,
    ServiceOutcome,
    ToolDescriptor,
    ToolPlugin,
    ToolResult,
)

NETWORK = frozenset({NETWORK_CAPABILITY})


class _Ledger:
    """Counts every recording. The COUNT is the point — a skip and a double are
    both invisible to a test that only checks the last recorded value."""

    def __init__(self):
        self.calls: list[tuple[str, float | None]] = []

    def __call__(self, provenance, cost_usd):
        self.calls.append((provenance, cost_usd))


class _Plain(ToolPlugin):
    """A plugin with NO carrier — the ordinary case, and the known limit."""

    def __init__(self, *, raises=False, kernel_serviced=False):
        self._raises = raises
        self._kernel_serviced = kernel_serviced

    def descriptors(self):
        return [ToolDescriptor(
            name="t", schema={"name": "t", "description": "d", "input_schema": {}},
            kernel_serviced=self._kernel_serviced)]

    async def execute(self, tool, args, ctx):
        if self._raises:
            raise RuntimeError("plugin exploded")
        return ToolResult(text_ar="نتيجة")


class _Carrier(_Plain):
    """A plugin offering the optional cost-carrying twin."""

    def __init__(self, cost=0.008, *, raises=False, carried=None):
        super().__init__()
        self._cost = cost
        self._carrier_raises = raises
        self._carried = carried

    async def execute_with_cost(self, tool, args, ctx):
        if self._carrier_raises:
            raise RuntimeError("carrier exploded")
        if self._carried is not None:
            return self._carried
        return _Carried(ToolResult(text_ar="نتيجة"), self._cost)


class _Carried:
    def __init__(self, result, cost_usd):
        self.result, self.cost_usd = result, cost_usd


class _NoCostField:
    """A malformed carrier: a result, but no cost at all."""

    def __init__(self, result):
        self.result = result


def _router(plugin, ledger, **mount):
    router = ToolRouter(plugin_ledger=ledger)
    router.mount(plugin, provenance="p:test", **mount)
    return router


def _service(router, tool="t", args=None):
    return asyncio.run(router.service(tool, args or {}))


# ─── THE SHARPENED QUESTION: never skipped, never doubled ────────────────────


def test_a_carrier_route_records_exactly_once_with_the_real_cost():
    ledger = _Ledger()
    outcome = _service(_router(_Carrier(0.008), ledger))
    assert ledger.calls == [("p:test", 0.008)]
    assert outcome.cost_usd == 0.008


def test_a_plugin_without_a_carrier_records_exactly_once_with_no_cost():
    ledger = _Ledger()
    outcome = _service(_router(_Plain(), ledger))
    assert ledger.calls == [("p:test", None)]
    assert outcome.cost_usd is None


def test_a_raising_plugin_records_exactly_once():
    ledger = _Ledger()
    _service(_router(_Plain(raises=True), ledger))
    assert ledger.calls == [("p:test", None)]


def test_a_raising_carrier_records_exactly_once_and_never_escapes():
    """The carrier is an INFORMAL contract, so it is exactly the surface most
    likely to misbehave — the never-raise wall must cover it identically."""
    ledger = _Ledger()
    outcome = _service(_router(_Carrier(raises=True), ledger))
    assert ledger.calls == [("p:test", None)]
    assert outcome.result.is_error is True


def test_the_degraded_read_records_exactly_once():
    """`read_local_file` with no files seam: the V1 Arabic note, and a call that
    happened and must still be attributed."""
    ledger = _Ledger()
    router = build_core_router(read_file=None, plugin_ledger=ledger)
    _service(router, tool="read_local_file", args={"path": "a.py"})
    assert ledger.calls == [("core:file_read", None)]


def test_a_confirm_gate_refusal_records_NOTHING():
    """The one path that must NOT record: nothing ran. The gate is checked at
    :250 and the plugin is executed at :269, so a refused call never reaches the
    plugin — and attributing a call that never happened would be a lie in the
    ledger, not a conservative estimate."""
    ledger = _Ledger()
    plugin = _Carrier(0.008)
    router = ToolRouter(plugin_ledger=ledger)
    router.mount(plugin, namespace="web", provenance="web:test", taint=True,
                 impact=RouteImpact(capabilities=NETWORK))
    router.session_taint.raise_taint("web:test")

    outcome = _service(router, tool=namespaced_name("web", "t"))

    assert outcome.provenance == "kernel:confirm"
    assert ledger.calls == [], "a refused call was charged to the ledger"


def test_an_unrouted_tool_and_a_kernel_serviced_misroute_record_NOTHING():
    ledger = _Ledger()
    _service(_router(_Plain(), ledger), tool="does_not_exist")
    assert ledger.calls == []

    ledger2 = _Ledger()
    _service(_router(_Plain(kernel_serviced=True), ledger2))
    assert ledger2.calls == []


def test_two_calls_record_twice_and_never_more():
    """The positive control for every 'exactly once' above: the counter really
    does move, so those assertions cannot pass on a dead ledger."""
    ledger = _Ledger()
    router = _router(_Carrier(0.008), ledger)
    _service(router)
    _service(router)
    assert ledger.calls == [("p:test", 0.008), ("p:test", 0.008)]


# ─── THE KNOWN LIMIT, made visible against the REAL ledger ───────────────────


def test_a_plugin_without_a_carrier_records_zero_and_still_counts_the_call(tmp_path):
    """DEC-34's KNOWN LIMIT as behaviour, not prose. Zero is the SAFE direction —
    visible in the ledger and provably wrong — while a skipped call would be
    invisible and look free. The trigger for revisiting is the first third-party
    PAID plugin; today the only paid path is first-party."""
    budget = Budget(budget_file=tmp_path / "b.json", today_fn=lambda: "2026-07-25")
    _service(_router(_Plain(), budget.record_plugin_call))

    bucket = budget.plugin_spend_today()["p:test"]
    assert bucket["calls"] == 1 and bucket["spent_usd"] == 0.0
    assert budget.spent_today_usd() == 0.0


def test_a_carrier_cost_reaches_the_ledger_and_the_sovereign_daily_total(tmp_path):
    """The other half: a real cost must land in BOTH the plugin bucket and the
    day's total, because a paid plugin call is spend like any other and
    `can_afford` must see it (M1-3)."""
    budget = Budget(budget_file=tmp_path / "b.json", today_fn=lambda: "2026-07-25")
    router = _router(_Carrier(0.008), budget.record_plugin_call)
    _service(router)
    _service(router)

    bucket = budget.plugin_spend_today()["p:test"]
    assert bucket["calls"] == 2 and bucket["spent_usd"] == 0.016
    assert budget.spent_today_usd() == 0.016
    ledger = json.loads((tmp_path / "b.json").read_text(encoding="utf-8"))
    assert ledger["2026-07-25"] == 0.016  # it persisted, not just in memory


def test_a_malformed_carrier_degrades_to_zero_rather_than_raising():
    ledger = _Ledger()
    plugin = _Carrier(carried=_NoCostField(ToolResult(text_ar="نتيجة")))
    outcome = _service(_router(plugin, ledger))
    assert ledger.calls == [("p:test", None)]
    assert outcome.result.is_error is False


# ─── The real consumer: web_research's per-query cost ────────────────────────


class _Provider:
    name = "fake"
    cost_per_query_usd = 0.008

    async def search(self, query, *, max_results=5):
        class _R:
            ok, results, text_ar, cost_usd = True, (), "", 0.008
        return _R()


def test_web_research_search_cost_flows_through_the_router_to_the_ledger(tmp_path):
    """End-to-end on the only paid path that exists: the provider's per-query
    cost reaches the sovereign ledger through the router, with the plugin never
    touching a budget symbol."""
    budget = Budget(budget_file=tmp_path / "b.json", today_fn=lambda: "2026-07-25")
    router = ToolRouter(plugin_ledger=budget.record_plugin_call)
    router.mount(WebResearchPlugin(provider=_Provider()), namespace="web",
                 provenance="web_research")

    _service(router, tool=namespaced_name("web", "search"), args={"query": "بايثون"})

    bucket = budget.plugin_spend_today()["web_research"]
    assert bucket["calls"] == 1 and bucket["spent_usd"] == 0.008
    assert budget.spent_today_usd() == 0.008


def test_a_fetch_costs_nothing_but_is_still_counted():
    """A fetch spends no vendor money, so zero is CORRECT here rather than a
    degradation — and the call is still attributed."""
    ledger = _Ledger()
    router = ToolRouter(plugin_ledger=ledger)
    router.mount(WebResearchPlugin(provider=_Provider()), namespace="web",
                 provenance="web_research")
    _service(router, tool=namespaced_name("web", "fetch"), args={"url": "https://a.example"})
    assert ledger.calls == [("web_research", 0.0)]


# ─── WHO OWNS THE NUMBER: the contracts stay untouched ───────────────────────


def test_the_plugin_facing_contracts_are_unchanged():
    """Candidate (2) was rejected because it would widen `ToolResult` — the
    plugin-facing type — and thereby ADVERTISE that a plugin-set number reaches
    `record_plugin_call`, which adds to the sovereign daily total gating
    `can_afford`. Pinning the field sets makes that regression a test failure."""
    assert set(ToolResult.__dataclass_fields__) == {"text_ar", "is_error"}
    assert set(ServiceOutcome.__dataclass_fields__) == {
        "result", "provenance", "taint", "cost_usd", "extras"}
    assert list(inspect.signature(Budget.can_afford).parameters) == ["self", "estimated_usd"]
    assert list(inspect.signature(Budget.record_turn).parameters) == ["self", "turn_complete"]


def test_the_router_obtains_the_cost_and_the_plugin_never_declares_it():
    """The deciding property of candidate (1): the figure is read by the KERNEL
    from the call it just made, so it never crosses as a plugin-set field on a
    shared contract."""
    assert hasattr(ToolRouter, "_execute_route")
    assert not hasattr(ToolResult(text_ar="x"), "cost_usd")
    params = list(inspect.signature(ToolRouter._outcome_for).parameters)
    assert params == ["self", "route", "tool", "result", "cost_usd"]


def test_the_cost_survives_the_untrusted_wrap_on_a_tainted_route():
    """A tainted result is rebuilt by `dataclasses.replace` for the DEC-14 wrap.
    The cost must survive that rebuild, or every EXTERNAL paid call — the only
    kind there is — would silently record nothing."""
    ledger = _Ledger()
    router = ToolRouter(plugin_ledger=ledger)
    router.mount(_Carrier(0.008), namespace="web", provenance="web:test", taint=True)

    outcome = _service(router, tool=namespaced_name("web", "t"))

    assert outcome.taint is True
    assert "محتوى خارجي" in outcome.result.text_ar  # it really was wrapped
    assert outcome.cost_usd == 0.008
    assert ledger.calls == [("web:test", 0.008)]


@pytest.mark.parametrize("cost", [0.0, None, 0.008])
def test_the_outcome_and_the_ledger_read_the_same_figure(cost):
    """One source, so the amount charged and the amount reported cannot
    disagree — the rule `_outcome_for` already applies to the wrap and its
    taint flag, applied to money."""
    ledger = _Ledger()
    plugin = _Carrier(carried=_Carried(ToolResult(text_ar="ن"), cost))
    outcome = _service(_router(plugin, ledger))
    assert ledger.calls[0][1] == outcome.cost_usd == cost
