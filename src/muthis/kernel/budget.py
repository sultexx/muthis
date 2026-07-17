# src/muthis/kernel/budget.py
"""
Budget — the sovereign daily spend ledger of Mut'his v4.1 (Rule 10).

A pure accounting gate. It consumes the `cost_usd` figure already computed
by the provider wrapper (TurnComplete in cloud/protocol.py) and answers one
question for the orchestrator: "am I allowed to spend?"

Design contract:
  - Synchronous and pure: NO locks, NO event loop, NO threads, NO session
    lifecycle (Law 11 — the orchestrator owns all of those and calls us).
  - NO network, NO provider SDKs, NO third-party deps — stdlib only, so the
    module is importable in isolation by every test stub.
  - NO pricing knowledge. Cost computation belongs to the wrapper that
    produced TurnComplete; we only add up what it reports.
  - Ledger file (budget.json) is keyed by UTC date "YYYY-MM-DD". A new day
    is simply a new key starting at zero — date rollover needs no special
    logic. Past days are kept for observability; the file stays tiny.
  - A corrupt or missing ledger NEVER crashes the app: treat as zero spent
    today, log an English warning, carry on. Losing one day's tally is
    cheaper than losing the session.
  - Money discipline: every stored value passes round(x, 6) so float drift
    cannot accumulate across hundreds of turns.

Environment variables (.env is loaded once at process entry, before imports):
  MUTHIS_DAILY_BUDGET_USD : daily ceiling in USD (default 0.75 per
                            ARCHITECTURE_v4_1 §4.2). Never hardcoded in
                            logic — the constant below is only the fallback.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    # Typing only — at runtime we duck-type (read .cost_usd), so budget.py
    # stays importable with zero package context.
    from muthis.cloud.protocol import TurnComplete

logger = logging.getLogger("budget")


# ─── Configuration constants ──────────────────────────────────────────────────

ENV_DAILY_BUDGET_USD = "MUTHIS_DAILY_BUDGET_USD"

# Fallback ONLY — the real source of truth is the env var above.
DEFAULT_DAILY_LIMIT_USD = 0.75

DEFAULT_BUDGET_FILENAME = "budget.json"

# round(x, MONEY_DECIMALS) on every store — keeps the ledger drift-free.
MONEY_DECIMALS = 6


def _utc_today() -> str:
    """Current UTC date as the ledger key 'YYYY-MM-DD'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ─── Budget ───────────────────────────────────────────────────────────────────

class Budget:
    """
    Daily spend gate. One instance per orchestrator.

    Usage (from the orchestrator, BEFORE a provider turn):
        if not self.budget.can_afford():
            ...speak "الميزانية اليومية انتهت" and refuse the turn...

    And AFTER the turn's TurnComplete arrives:
        self.budget.record_turn(turn_complete)

    Contract choice — boolean, NOT an exception:
      can_afford() returns a hard False instead of raising BudgetExceeded.
      WHY: Law 11 makes the orchestrator the sole owner of control flow; a
      gate that raises becomes a decision-maker. An exception used for flow
      control is also easy to forget to catch — and the app must never crash
      over money. An explicit False forces the caller to handle refusal.
      record_turn() likewise never raises: recording is honest bookkeeping
      even past the limit; refusal is the NEXT can_afford()'s job.
    """

    def __init__(
        self,
        *,
        daily_limit_usd: Optional[float] = None,
        budget_file: Optional[os.PathLike | str] = None,
        today_fn: Callable[[], str] = _utc_today,
    ) -> None:
        self.daily_limit_usd = self._resolve_daily_limit(daily_limit_usd)
        # Default lands in the process working directory (the project root
        # when launched normally) — already covered by .gitignore.
        self.budget_file = (
            Path(budget_file) if budget_file is not None
            else Path.cwd() / DEFAULT_BUDGET_FILENAME
        )
        # Injected clock so tests can freeze the date (no sleeping).
        self._today_fn = today_fn
        self._ledger: dict[str, float] = self._load_ledger()

    # ─────────────────────────── Public API ───────────────────────────

    def can_afford(self, estimated_usd: float = 0.0) -> bool:
        """
        Pre-flight gate: may the orchestrator spend right now?
        False the moment today's spend (plus the estimate) reaches the limit.
        """
        projected = round(self.spent_today_usd() + float(estimated_usd), MONEY_DECIMALS)
        return projected < self.daily_limit_usd

    def record_turn(self, turn_complete: "TurnComplete") -> None:
        """
        Add one turn's cost_usd to today's total and persist immediately.
        Never raises — see the contract note in the class docstring.
        """
        cost = float(getattr(turn_complete, "cost_usd", 0.0))
        if not math.isfinite(cost) or cost < 0.0:
            # A negative or NaN cost is a wrapper bug; poisoning the ledger
            # with it would corrupt every later gate decision.
            logger.warning("[budget] ignoring invalid turn cost: %r", cost)
            return

        today = self._today_fn()
        new_total = round(self._ledger.get(today, 0.0) + cost, MONEY_DECIMALS)
        self._ledger[today] = new_total
        self._save_ledger()

        logger.info(
            "[budget] recorded %.6f USD — today %.6f / %.2f USD",
            cost, new_total, self.daily_limit_usd,
        )
        if new_total >= self.daily_limit_usd:
            logger.warning(
                "[budget] daily limit reached (%.6f / %.2f USD) — "
                "further turns will be refused.",
                new_total, self.daily_limit_usd,
            )

    def spent_today_usd(self) -> float:
        """Total recorded spend for the current UTC day."""
        return round(float(self._ledger.get(self._today_fn(), 0.0)), MONEY_DECIMALS)

    def remaining_usd(self) -> float:
        """USD left under today's limit (never negative)."""
        return max(0.0, round(self.daily_limit_usd - self.spent_today_usd(), MONEY_DECIMALS))

    # ───────────────────────── Limit resolution ─────────────────────────

    @staticmethod
    def _resolve_daily_limit(override: Optional[float]) -> float:
        """Explicit constructor arg > env var > documented fallback."""
        if override is not None:
            return float(override)
        raw = os.getenv(ENV_DAILY_BUDGET_USD)
        if raw is None or not raw.strip():
            return DEFAULT_DAILY_LIMIT_USD
        try:
            return float(raw)
        except ValueError:
            logger.warning(
                "[budget] invalid %s=%r — falling back to %.2f USD",
                ENV_DAILY_BUDGET_USD, raw, DEFAULT_DAILY_LIMIT_USD,
            )
            return DEFAULT_DAILY_LIMIT_USD

    # ───────────────────────── Ledger persistence ─────────────────────────

    def _load_ledger(self) -> dict[str, float]:
        """
        Read budget.json. ANY failure (missing, unreadable, bad JSON, wrong
        shape) degrades to an empty ledger — zero spent today — with an
        English warning. Never crash the app over a bad ledger file.
        """
        try:
            raw_text = self.budget_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}  # first run — silent, this is the normal path
        except OSError as e:
            logger.warning("[budget] cannot read %s: %s — treating as empty", self.budget_file, e)
            return {}

        try:
            data = json.loads(raw_text)
            if not isinstance(data, dict):
                raise ValueError(f"ledger root must be an object, got {type(data).__name__}")
            ledger: dict[str, float] = {}
            for key, value in data.items():
                if isinstance(key, str) and isinstance(value, (int, float)):
                    ledger[key] = round(float(value), MONEY_DECIMALS)
                else:
                    raise ValueError(f"bad ledger entry: {key!r}: {value!r}")
            return ledger
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                "[budget] corrupt ledger %s (%s) — treating today as zero spent",
                self.budget_file, e,
            )
            return {}

    def _save_ledger(self) -> None:
        """
        Persist atomically: write a sibling temp file, then os.replace().
        A crash mid-write can therefore never leave a truncated ledger.
        Save failures are logged, not raised — accounting must not kill
        the session (the in-memory total stays correct regardless).
        """
        tmp_path = self.budget_file.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(
                json.dumps(self._ledger, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(tmp_path, self.budget_file)
        except OSError as e:
            logger.warning("[budget] failed to persist ledger to %s: %s", self.budget_file, e)


__all__ = [
    "Budget",
    "ENV_DAILY_BUDGET_USD",
    "DEFAULT_DAILY_LIMIT_USD",
]
