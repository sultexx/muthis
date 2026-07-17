# src/muthis/verbosity.py
"""Compat shim (V2 Phase 0): the module moved to muthis.kernel.verbosity.
Kept until Phase 1 (decision Q-4); new code imports from muthis.kernel.*."""

from .kernel.verbosity import (
    DETAILED,
    DIRECTIVE_OPEN_AR,
    EXACT,
    NORMAL,
    SHORT,
    VALID_LEVELS,
    VerbosityController,
    detect_command,
    normalize_ar,
)

__all__ = [
    "VerbosityController", "detect_command", "normalize_ar",
    "NORMAL", "SHORT", "DETAILED", "EXACT", "VALID_LEVELS",
    "DIRECTIVE_OPEN_AR",
]
