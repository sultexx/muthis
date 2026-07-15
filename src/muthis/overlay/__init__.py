# src/muthis/overlay/__init__.py
"""
Overlay package — the cyan-rectangle LOOK pointer.

DRAW ONLY: this package shows/hides a rectangle and a short Arabic caption. It
NEVER moves the mouse, clicks, types, or reads input — it is visual output only.

`SidekickOverlay` implements the orchestrator's `Overlay` seam (show/hide) and
is fed ALREADY-PHYSICAL coordinates (the orchestrator does the sent→physical
scale). It owns a private Tk thread; tkinter/ctypes are imported INSIDE the
thread, so the orchestrator — which type-hints only against the Overlay protocol
in turn.py — never imports Tk and stays importable on a headless box.

Production swaps the stub for SidekickOverlay at the composition root; tests
inject fakes through the same seam.
"""

from .pointer_animator import DEFAULT_POINTER_ANIM_MS
from .sidekick_window import SidekickOverlay
from .style import OverlayStyle

__all__ = ["SidekickOverlay", "DEFAULT_POINTER_ANIM_MS", "OverlayStyle"]
