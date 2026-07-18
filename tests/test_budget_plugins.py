# tests/test_budget_plugins.py
"""
M1-3 — the per-plugin budget column (roadmap: "a column, not a contract
change"). The V1 contract tests (tests/test_budget.py) stay the untouched
oracle; this file pins the ADDITIVE surface: attribution buckets, the
sovereignty rule (a paid plugin call feeds the global daily gate), legacy
ledger compatibility, and the router→ledger seam.
"""

from __future__ import annotations

import asyncio
import json

from muthis.kernel.budget import PLUGINS_KEY, Budget
from muthis.kernel.tool_router import build_core_router

TODAY = "2026-07-17"


def _budget(tmp_path, limit=1.0):
    return Budget(daily_limit_usd=limit, budget_file=tmp_path / "budget.json",
                  today_fn=lambda: TODAY)


def test_plugin_calls_accumulate_and_persist(tmp_path):
    budget = _budget(tmp_path)
    budget.record_plugin_call("core:file_read")
    budget.record_plugin_call("core:file_read")
    budget.record_plugin_call("mcp:demo", 0.01)
    assert budget.plugin_spend_today() == {
        "core:file_read": {"calls": 2, "spent_usd": 0.0},
        "mcp:demo": {"calls": 1, "spent_usd": 0.01},
    }
    # Persisted + reloadable (a fresh instance reads the same buckets).
    reloaded = _budget(tmp_path)
    assert reloaded.plugin_spend_today()["core:file_read"]["calls"] == 2


def test_paid_plugin_call_feeds_the_sovereign_daily_total(tmp_path):
    budget = _budget(tmp_path, limit=0.05)
    assert budget.can_afford()
    budget.record_plugin_call("mcp:paid_search", 0.05)
    assert budget.spent_today_usd() == 0.05
    assert not budget.can_afford()  # the global gate saw the plugin spend


def test_free_calls_never_touch_the_daily_total(tmp_path):
    budget = _budget(tmp_path)
    budget.record_plugin_call("core:file_read", None)
    budget.record_plugin_call("core:file_read", 0.0)
    assert budget.spent_today_usd() == 0.0


def test_invalid_inputs_degrade_and_never_raise(tmp_path):
    budget = _budget(tmp_path)
    budget.record_plugin_call("", 0.5)                    # no provenance → ignored
    budget.record_plugin_call("mcp:x", float("nan"))      # NaN → count-only
    budget.record_plugin_call("mcp:x", -1.0)              # negative → count-only
    assert budget.plugin_spend_today() == {"mcp:x": {"calls": 2, "spent_usd": 0.0}}
    assert budget.spent_today_usd() == 0.0


def test_legacy_dates_only_ledger_still_loads(tmp_path):
    path = tmp_path / "budget.json"
    path.write_text(json.dumps({TODAY: 0.25}), encoding="utf-8")
    budget = Budget(daily_limit_usd=1.0, budget_file=path, today_fn=lambda: TODAY)
    assert budget.spent_today_usd() == 0.25               # V1 shape intact
    budget.record_plugin_call("core:file_read")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[TODAY] == 0.25 and PLUGINS_KEY in data    # the column joined in


def test_router_records_attribution_through_the_seam(tmp_path):
    budget = _budget(tmp_path)

    async def fake_read(args):
        return "محتوى"

    router = build_core_router(read_file=fake_read,
                               plugin_ledger=budget.record_plugin_call)
    asyncio.run(router.service("read_local_file", {"path": "x.py"}))
    asyncio.run(router.service("read_local_file", {"path": "y.py"}))
    asyncio.run(router.service("no_such_tool", {}))       # unrouted → NOT attributed
    assert budget.plugin_spend_today() == {
        "core:file_read": {"calls": 2, "spent_usd": 0.0},
    }


def test_raising_ledger_seam_never_kills_a_service_call(tmp_path):
    def broken_ledger(plugin, cost):
        raise RuntimeError("accounting exploded")

    async def fake_read(args):
        return "محتوى"

    router = build_core_router(read_file=fake_read, plugin_ledger=broken_ledger)
    outcome = asyncio.run(router.service("read_local_file", {"path": "x.py"}))
    assert outcome.result.text_ar == "محتوى"              # the turn survived
