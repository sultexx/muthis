"""
test_budget.py — the sovereign-budget gate tests (Rule 10).

No network, no provider, fully deterministic. Budget consumes real
TurnComplete objects from cloud/protocol.py; the date is frozen by
injecting today_fn (never by sleeping); ledgers live in pytest's tmp_path.

Run:  pytest tests/test_budget.py -q
"""

from __future__ import annotations

import json

from muthis.budget import Budget, DEFAULT_DAILY_LIMIT_USD, ENV_DAILY_BUDGET_USD
from muthis.cloud.protocol import TurnComplete

# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

TODAY = "2026-06-11"
YESTERDAY = "2026-06-10"


def _frozen(date_str):
    """A today_fn frozen to a fixed UTC date."""
    return lambda: date_str


def _turn(cost_usd):
    """A minimal but real TurnComplete carrying only what Budget reads."""
    return TurnComplete(
        input_tokens=850,
        output_tokens=64,
        cost_usd=cost_usd,
        stop_reason="end_turn",
        model="claude-sonnet-4-6",
    )


def _budget(tmp_path, **kwargs):
    kwargs.setdefault("daily_limit_usd", 0.10)
    kwargs.setdefault("today_fn", _frozen(TODAY))
    return Budget(budget_file=tmp_path / "budget.json", **kwargs)


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────


def test_fresh_ledger_allows_below_limit_then_blocks_at_limit(tmp_path):
    budget = _budget(tmp_path)  # limit = 0.10

    # Fresh day: nothing spent, gate is open.
    assert budget.spent_today_usd() == 0.0
    assert budget.can_afford()

    budget.record_turn(_turn(0.04))
    assert budget.can_afford()
    # Pre-flight estimate that would CROSS the limit is refused...
    assert not budget.can_afford(estimated_usd=0.06)
    # ...while one that stays under passes.
    assert budget.can_afford(estimated_usd=0.05)

    # Spend that REACHES the limit hard-blocks the next turn.
    budget.record_turn(_turn(0.06))
    assert budget.spent_today_usd() == 0.10
    assert not budget.can_afford()
    assert budget.remaining_usd() == 0.0


def test_record_turn_accumulates_and_persists(tmp_path):
    budget = _budget(tmp_path, daily_limit_usd=1.0)

    for cost in (0.002745, 0.00396, 0.001234):
        budget.record_turn(_turn(cost))

    expected = round(0.002745 + 0.00396 + 0.001234, 6)
    assert budget.spent_today_usd() == expected
    assert budget.remaining_usd() == round(1.0 - expected, 6)

    # The ledger survives a process restart: a brand-new instance reading
    # the same file sees the same total.
    reloaded = _budget(tmp_path, daily_limit_usd=1.0)
    assert reloaded.spent_today_usd() == expected

    # And the on-disk shape is keyed by UTC date.
    on_disk = json.loads((tmp_path / "budget.json").read_text(encoding="utf-8"))
    assert on_disk == {TODAY: expected}


def test_date_rollover_resets_to_zero(tmp_path):
    # Yesterday burned the whole budget...
    ledger_file = tmp_path / "budget.json"
    ledger_file.write_text(json.dumps({YESTERDAY: 0.75}), encoding="utf-8")

    # ...but today is a new key, so the gate reopens at zero. No sleeping —
    # the date is injected.
    budget = _budget(tmp_path, daily_limit_usd=0.75)
    assert budget.spent_today_usd() == 0.0
    assert budget.remaining_usd() == 0.75
    assert budget.can_afford()

    # Recording today must not erase yesterday's history.
    budget.record_turn(_turn(0.01))
    on_disk = json.loads(ledger_file.read_text(encoding="utf-8"))
    assert on_disk == {YESTERDAY: 0.75, TODAY: 0.01}


def test_corrupt_ledger_degrades_to_zero_without_crash(tmp_path):
    ledger_file = tmp_path / "budget.json"

    for corrupt_content in (
        "{{{ not json at all",
        '["a", "list", "not", "an", "object"]',
        '{"2026-06-11": "not-a-number"}',
    ):
        ledger_file.write_text(corrupt_content, encoding="utf-8")

        budget = _budget(tmp_path)  # must not raise
        assert budget.spent_today_usd() == 0.0
        assert budget.can_afford()

    # Recording over a corrupt file heals it into a valid ledger.
    budget.record_turn(_turn(0.02))
    on_disk = json.loads(ledger_file.read_text(encoding="utf-8"))
    assert on_disk == {TODAY: 0.02}


def test_daily_limit_comes_from_env_not_hardcode(tmp_path, monkeypatch):
    # Env var wins over the documented fallback...
    monkeypatch.setenv(ENV_DAILY_BUDGET_USD, "0.25")
    budget = Budget(budget_file=tmp_path / "budget.json", today_fn=_frozen(TODAY))
    assert budget.daily_limit_usd == 0.25

    # ...the fallback only applies when the var is absent...
    monkeypatch.delenv(ENV_DAILY_BUDGET_USD)
    budget = Budget(budget_file=tmp_path / "budget.json", today_fn=_frozen(TODAY))
    assert budget.daily_limit_usd == DEFAULT_DAILY_LIMIT_USD

    # ...and garbage in the var degrades to the fallback, not a crash.
    monkeypatch.setenv(ENV_DAILY_BUDGET_USD, "plenty")
    budget = Budget(budget_file=tmp_path / "budget.json", today_fn=_frozen(TODAY))
    assert budget.daily_limit_usd == DEFAULT_DAILY_LIMIT_USD
