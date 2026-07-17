# src/muthis/orchestrator.py
"""Compat shim (V2 Phase 0): the module moved to muthis.kernel.orchestrator.

Explicit named re-exports keep every V1 import path working unchanged — the
474-test oracle and the scripts/diag_* live SOP run against these old paths
on purpose (zero-behavior proof). Removal is scheduled for Phase 1 (Sultan's
decision Q-4). New code imports from muthis.kernel.orchestrator."""

from .kernel.orchestrator import (
    AGENTIC_CAP_NOTE_AR,
    ALLOWED_OVERLAY_TOOL,
    BUDGET_REFUSAL_AR,
    MAX_AGENTIC_ITERATIONS,
    MAX_REFRESH_FOLLOWUPS,
    MIC_FAILED_AR,
    OVERLAY_SETTLE_S,
    REFRESH_TOOL,
    SESSION_TIMEOUT_S,
    STT_EMPTY_AR,
    Orchestrator,
    TurnResult,
)

__all__ = [
    "Orchestrator", "TurnResult", "BUDGET_REFUSAL_AR", "AGENTIC_CAP_NOTE_AR",
    "MIC_FAILED_AR", "STT_EMPTY_AR", "SESSION_TIMEOUT_S",
    "MAX_REFRESH_FOLLOWUPS", "MAX_AGENTIC_ITERATIONS", "OVERLAY_SETTLE_S",
    "REFRESH_TOOL", "ALLOWED_OVERLAY_TOOL",
]
