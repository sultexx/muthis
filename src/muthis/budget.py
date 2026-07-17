# src/muthis/budget.py
"""Compat shim (V2 Phase 0): the module moved to muthis.kernel.budget.
Kept until Phase 1 (decision Q-4); new code imports from muthis.kernel.*."""

from .kernel.budget import Budget, DEFAULT_DAILY_LIMIT_USD, ENV_DAILY_BUDGET_USD

__all__ = ["Budget", "ENV_DAILY_BUDGET_USD", "DEFAULT_DAILY_LIMIT_USD"]
