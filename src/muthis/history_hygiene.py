# src/muthis/history_hygiene.py
"""Compat shim (V2 Phase 0): the module moved to muthis.kernel.history_hygiene.
Kept until Phase 1 (decision Q-4); new code imports from muthis.kernel.*."""

from .kernel.history_hygiene import STALE_SCREENSHOT_NOTE_AR, strip_images_from_history

__all__ = ["STALE_SCREENSHOT_NOTE_AR", "strip_images_from_history"]
