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

Timing is entirely the CALLER's (dispatch commands on the Tk thread): the
spotlight shows with the highlight command; the WHITEBOARD (v7 Phase 2)
shows via "dim_screen" (a FULL cover, no hole, smooth fade-in) with a
dim_screen=true draw_shapes and lifts via "undim_screen" (fade-out) at
SPEECH END from run_turn's finally. Both inherit the hide-before-capture
chokepoint through hide() (INSTANT — a capture must never see even a fading
dim) — NO timer of its own, so Option A and the ghosting rule are untouched
by construction. Claude never sees a dimmed screen. The spotlight remains
highlight_target-only; a flat (non-whiteboard) draw_shapes keeps its
full-context screen.

The class is duck-typed (window: deiconify/withdraw/lift; canvas: create_
rectangle/delete) → display-free tests; only `build_focus_dimmer` touches
tkinter, lazily, on the Tk thread (the package convention).
"""

from __future__ import annotations

import logging
import time

from .style import TRANSPARENT_KEY
from .style_env import clamp01, env_flag, env_float

logger = logging.getLogger("muthis.overlay")

# DIAG(v7 Phase 2): temporary timing probes for the whiteboard live test.
_diag = logging.getLogger("muthis.diag")

# Rollback flag: the spotlight is OFF unless .env opts in (a new, visually
# loud feature ships dark until Sultan flips the release default).
FOCUS_DIM_ENV = "MUTHIS_FOCUS_DIM"
FOCUS_ALPHA_ENV = "MUTHIS_FOCUS_ALPHA"
DEFAULT_FOCUS_ALPHA = 0.30

# v7 Phase 2 rollback flag: the WHITEBOARD (full-screen dim behind a concept
# drawing) ships ON — a falsey value is the one-env rollback (captions pattern).
WHITEBOARD_ENV = "MUTHIS_WHITEBOARD"

# Whiteboard fade pacing: ~15 frames over ~250 ms, driven by self-rescheduling
# after() on the Tk thread — NEVER a blocking sleep (the status-pulse pattern).
FADE_MS = 250
FADE_STEP_MS = 16

# Breathing margin around the highlight bbox so the spotlight never feels
# like a tight crop on the element.
FOCUS_MARGIN_PX = 12


def focus_dim_enabled() -> bool:
    return env_flag(FOCUS_DIM_ENV, False)


def whiteboard_enabled() -> bool:
    return env_flag(WHITEBOARD_ENV, True)


def resolve_focus_alpha() -> float:
    """The dim opacity (0=invisible, 1=black). Clamped so a .env typo can
    never blank the user's screen."""
    return clamp01(env_float(FOCUS_ALPHA_ENV, DEFAULT_FOCUS_ALPHA))


class FocusDimmer:
    """Show/hide the dim layer: a keyed hole over a target bbox (spotlight)
    or a FULL cover behind a concept drawing (whiteboard, v7 Phase 2)."""

    def __init__(self, window, canvas, screen_size: tuple[int, int],
                 raise_neon, margin_px: int = FOCUS_MARGIN_PX, *,
                 schedule=None, alpha: float = DEFAULT_FOCUS_ALPHA) -> None:
        self._window = window
        self._canvas = canvas
        self._screen_width, self._screen_height = screen_size
        # Called after every show so the neon window (rectangle / pointer /
        # captions / status dot) stacks back above the dim — D0's z-order rule.
        self._raise_neon = raise_neon
        self._margin_px = margin_px
        # Whiteboard fade seams: `schedule` is root.after (None → no fade,
        # instant show/hide — the pre-Phase-2 behavior, and what display-free
        # fakes without a scheduler get); `alpha` is the resolved dim opacity.
        self._schedule = schedule
        self._alpha = alpha
        self._fade_generation = 0  # a bump orphans any queued fade frame

    def show_around(self, bbox: tuple[int, int, int, int]) -> None:
        """SPOTLIGHT: dim everything except `bbox` (already PHYSICAL) plus a
        breathing margin, clamped to the screen — instantly, at full dim
        opacity. Replaces any previous hole and cancels an in-flight fade.
        The canvas is EXCLUSIVE to the dimmer window, so delete("all") is safe
        here — the shared-canvas tag rule applies to the neon window only."""
        self._fade_generation += 1           # a mid-fade alpha must not stick
        self._set_alpha(self._alpha)
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

    def show_full(self) -> None:
        """WHITEBOARD (v7 Phase 2): dim the WHOLE screen — no hole — behind a
        concept drawing, fading in smoothly like a classroom going dark. The
        neon shapes render on the neon window ABOVE this dim (the D0 z-order
        rule), so the drawing reads as chalk on a blackboard."""
        _diag.info("[DIAG] whiteboard dim-in t=%.3f", time.monotonic())
        self._canvas.delete("all")           # no hole: the full cover IS the board
        self._fade_generation += 1
        if self._schedule is None:           # no scheduler → instant (old behavior)
            self._set_alpha(self._alpha)
            self._reveal()
            return
        self._set_alpha(0.0)                 # reveal dark-less, then fade up
        self._reveal()
        self._animate(self._fade_generation, 0.0, self._alpha, on_done=None)

    def fade_out(self) -> None:
        """WHITEBOARD lights-back-on: fade the dim to zero, then withdraw.
        Called at SPEECH END (run_turn's finally) so the un-dim is
        synchronized with the voice — the drawn shapes keep their own 7 s
        grace on the neon window. Instant when no scheduler."""
        _diag.info("[DIAG] whiteboard dim-out t=%.3f", time.monotonic())
        self._fade_generation += 1
        if self._schedule is None:
            self.hide()
            return
        self._animate(self._fade_generation, self._current_alpha(), 0.0,
                      on_done=self._window.withdraw)

    def hide(self) -> None:
        """Drop the dim INSTANTLY (the ghosting/auto-hide/close path — a
        capture must never see even a FADING dim). Cancels an in-flight fade.
        Safe when already hidden."""
        self._fade_generation += 1           # orphan any queued fade frame
        self._canvas.delete("all")
        self._window.withdraw()

    # ───────────────────────────── Fade internals ─────────────────────────────

    def _reveal(self) -> None:
        self._window.deiconify()
        self._window.lift()
        self._raise_neon()

    def _animate(self, generation: int, start: float, target: float,
                 on_done) -> None:
        """Linear alpha ramp via self-rescheduling after() frames on the Tk
        thread. A superseded generation (hide / a newer fade) simply stops."""
        steps = max(1, FADE_MS // FADE_STEP_MS)

        def tick(step: int) -> None:
            if generation != self._fade_generation:
                return                       # superseded — drop this chain
            self._set_alpha(start + (target - start) * (step / steps))
            if step >= steps:
                if on_done is not None:
                    on_done()
                return
            self._schedule(FADE_STEP_MS, lambda: tick(step + 1))

        self._schedule(FADE_STEP_MS, lambda: tick(1))

    def _set_alpha(self, value: float) -> None:
        try:
            self._window.attributes("-alpha", clamp01(value))
        except Exception:  # noqa: BLE001 — a torn-down window mid-fade is harmless
            pass

    def _current_alpha(self) -> float:
        try:
            return float(self._window.attributes("-alpha"))
        except Exception:  # noqa: BLE001 — duck-typed window without a getter
            return self._alpha


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
    window.withdraw()  # born hidden; dispatch "show"/"dim_screen" reveals it
    return FocusDimmer(window, canvas, (width, height), raise_neon=root.lift,
                       schedule=root.after, alpha=resolve_focus_alpha())


__all__ = [
    "FocusDimmer", "build_focus_dimmer", "focus_dim_enabled",
    "whiteboard_enabled", "resolve_focus_alpha", "FOCUS_DIM_ENV",
    "FOCUS_ALPHA_ENV", "WHITEBOARD_ENV", "DEFAULT_FOCUS_ALPHA",
    "FOCUS_MARGIN_PX", "FADE_MS", "FADE_STEP_MS",
]
