# src/muthis/overlay/focus_dimmer.py
"""
FocusDimmer — the Cinematic Spotlight (v6 Phase D): a SECOND click-through
Toplevel that dims the whole screen to ~30% black EXCEPT a color-keyed "hole"
over the highlighted element, so the screen literally looks at one point.

Validated by the D0 gate (plan_v6.md, 2026-07-15): -alpha and -transparentcolor
coexist on one Toplevel (outside-hole luma 0.667-0.691 at alpha 0.30, inside
the hole exactly 1.0), and a lifted neon window renders full-brightness above
the dim everywhere. A SEPARATE window is load-bearing: putting -alpha on the
neon window would dim the neon itself.

NOT a return of the deleted pointer halo: the dim sits around the TARGET, not
the pointer, and mutes surroundings instead of adding an element (the v5-A
distinction documented in the plan).

Timing is entirely the CALLER's (dispatch "show"/"hide" on the Tk thread):
shows with the highlight command, inherits the auto-hide + the
hide-before-capture chokepoint through hide() — NO timer of its own, so
Option A and the ghosting rule are untouched by construction. Claude never
sees a dimmed screen. highlight_target ONLY — draw_shapes illustrations keep
their full-context screen (approved plan decision).

The class is duck-typed (window: deiconify/withdraw/lift; canvas: create_
rectangle/delete) → display-free tests; only `build_focus_dimmer` touches
tkinter, lazily, on the Tk thread (the package convention).
"""

from __future__ import annotations

import logging

from .style import TRANSPARENT_KEY
from .style_env import clamp01, env_flag, env_float

logger = logging.getLogger("muthis.overlay")

# Rollback flag: the spotlight is OFF unless .env opts in (a new, visually
# loud feature ships dark until Sultan flips the release default).
FOCUS_DIM_ENV = "MUTHIS_FOCUS_DIM"
FOCUS_ALPHA_ENV = "MUTHIS_FOCUS_ALPHA"
DEFAULT_FOCUS_ALPHA = 0.30

# Breathing margin around the highlight bbox so the spotlight never feels
# like a tight crop on the element.
FOCUS_MARGIN_PX = 12


def focus_dim_enabled() -> bool:
    return env_flag(FOCUS_DIM_ENV, False)


def resolve_focus_alpha() -> float:
    """The dim opacity (0=invisible, 1=black). Clamped so a .env typo can
    never blank the user's screen."""
    return clamp01(env_float(FOCUS_ALPHA_ENV, DEFAULT_FOCUS_ALPHA))


class FocusDimmer:
    """Show/hide the dim layer with a keyed hole over the target bbox."""

    def __init__(self, window, canvas, screen_size: tuple[int, int],
                 raise_neon, margin_px: int = FOCUS_MARGIN_PX) -> None:
        self._window = window
        self._canvas = canvas
        self._screen_width, self._screen_height = screen_size
        # Called after every show so the neon window (rectangle / pointer /
        # captions / status dot) stacks back above the dim — D0's z-order rule.
        self._raise_neon = raise_neon
        self._margin_px = margin_px

    def show_around(self, bbox: tuple[int, int, int, int]) -> None:
        """Dim everything except `bbox` (already PHYSICAL) plus a breathing
        margin, clamped to the screen. Replaces any previous hole. The canvas
        is EXCLUSIVE to the dimmer window, so delete("all") is safe here —
        the shared-canvas tag rule applies to the neon window, not this one."""
        x1, y1, x2, y2 = bbox
        hole = (
            max(0, min(x1, x2) - self._margin_px),
            max(0, min(y1, y2) - self._margin_px),
            min(self._screen_width, max(x1, x2) + self._margin_px),
            min(self._screen_height, max(y1, y2) + self._margin_px),
        )
        self._canvas.delete("all")
        self._canvas.create_rectangle(
            *hole, fill=TRANSPARENT_KEY, outline=TRANSPARENT_KEY,
        )
        self._window.deiconify()
        self._window.lift()
        self._raise_neon()

    def hide(self) -> None:
        """Drop the dim (the ghosting/auto-hide path — a capture never sees
        a dimmed screen). Safe when already hidden."""
        self._canvas.delete("all")
        self._window.withdraw()


def build_focus_dimmer(root, apply_click_through) -> FocusDimmer:
    """Build the REAL dim window on the Tk thread (lazy tkinter, the package
    convention): a borderless topmost black Toplevel at the resolved alpha
    with the transparent-key hole canvas, click-through like the neon window,
    born HIDDEN. `apply_click_through` is injected from SidekickOverlay so the
    Win32 ex-style glue lives in one place."""
    import tkinter as tk

    window = tk.Toplevel(root)
    window.overrideredirect(True)
    window.attributes("-topmost", True)
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    window.geometry(f"{width}x{height}+0+0")
    window.configure(bg="black")
    window.attributes("-alpha", resolve_focus_alpha())
    window.attributes("-transparentcolor", TRANSPARENT_KEY)
    canvas = tk.Canvas(window, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    apply_click_through(window)
    window.withdraw()  # born hidden; dispatch "show" reveals it
    return FocusDimmer(window, canvas, (width, height), raise_neon=root.lift)


__all__ = [
    "FocusDimmer", "build_focus_dimmer", "focus_dim_enabled",
    "resolve_focus_alpha", "FOCUS_DIM_ENV", "FOCUS_ALPHA_ENV",
    "DEFAULT_FOCUS_ALPHA", "FOCUS_MARGIN_PX",
]
