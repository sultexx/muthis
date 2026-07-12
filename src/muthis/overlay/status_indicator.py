# src/muthis/overlay/status_indicator.py
"""
StatusIndicator — the overlay's state light (batch 2-A: VISUAL ONLY, no wiring).

A single persistent neon DOT in a configurable screen corner
(`MUTHIS_STATUS_CORNER`) — the always-on state light — reusing the batch-1
`OverlayStyle` (colors + `dim()` glow) so the whole overlay reads as one voice.
(A pointer HALO once hugged the gliding tip too, but it cluttered content and was
removed; only the corner dot remains.)

FOUR states drive the color: listening (cyan) / thinking (amber) / speaking
(green) / idle (HIDDEN). `set_state(state)` just updates the visual; WHO calls it
(the real turn phases) is batch 2-B — this module only paints.

Threading (AGENTS.md §11.5): this is a pure VIEW on the Tk thread, exactly like
the other widgets. It NEVER touches asyncio. `set_state` runs from inside
`dispatch_command` (the Tk-thread queue drain), and the gentle pulse is a
self-rescheduling `schedule` (root.after) loop — NEVER a blocking `sleep`/`while`.

Ghosting (batch 2-B enforces, 2-A builds): `clear_status_light()` kills the
corner dot AND keeps it dark (past the pulse) until the next `set_state`, so 2-B
can drop it at the hide→settle→capture chokepoint.

No `tkinter` import: the canvas is duck-typed (create_oval/delete), so this
module and its unit test stay importable without a display.
"""

from __future__ import annotations

import logging
import math
from typing import Optional, Tuple

from .style import OverlayStyle, dim

logger = logging.getLogger("muthis.overlay")

# Tag so the dot clears independently and NEVER needs delete("all") — the
# shared-canvas rule the pointer/rectangle/shapes widgets all follow.
STATUS_DOT_TAG = "muthis-status-dot"

# The four states; only the first three carry a color (idle == hidden).
VALID_STATES = ("listening", "thinking", "speaking", "idle")
IDLE = "idle"

# Pulse cadence: a light tick via schedule() (root.after), and one full breath
# (dim→bright→dim) per period. 50 ms ≈ 20 fps — smooth but negligible.
DEFAULT_PULSE_MS = 50
_PULSE_PERIOD_MS = 1400.0

# Geometry (physical px). The dot sits a margin in from the chosen corner and
# "breathes" its radius by these amplitudes.
DOT_CORE_RADIUS = 7
DOT_MARGIN = 28
DOT_PULSE_AMP = 3


class StatusIndicator:
    """The neon state light — a corner DOT pulsing via schedule(). Draws/clears
    ONLY its own tagged items on the shared canvas."""

    def __init__(
        self, canvas, *, schedule, style: Optional[OverlayStyle] = None,
        screen_size: Tuple[int, int] = (0, 0),
    ) -> None:
        self._canvas = canvas
        # root.after (or a fake in tests) — the ONLY way this loops. Never sleeps.
        self._schedule = schedule
        # Injected for tuning/tests; from_env() is the graceful neon fallback.
        self._style = style or OverlayStyle.from_env()
        self._screen_w, self._screen_h = screen_size
        self._state = IDLE
        self._pulsing = False
        self._tick = 0
        # The ghosting switch: while True the corner dot stays dark despite the
        # pulse, until the next set_state re-arms it (2-B drops it at capture).
        self._light_off = False

    # ─────────────────────────────── Public API ───────────────────────────────

    def set_state(self, state: str) -> None:
        """Update the visual to `state` (listening/thinking/speaking/idle). Safe
        to call before wiring: an unknown state is a logged no-op, and a real
        state re-arms the corner light that `clear_status_light()` may have
        dropped. Repaints immediately (the pulse keeps it breathing after)."""
        if state not in VALID_STATES:
            logger.warning("[overlay] unknown status state %r — ignored", state)
            return
        self._state = state
        self._light_off = False
        self._render()

    def clear_status_light(self) -> None:
        """Kill the corner dot and KEEP it dark through the pulse until the next
        set_state — the ghosting capability 2-B wires at the capture chokepoint."""
        self._light_off = True
        self._canvas.delete(STATUS_DOT_TAG)

    def start(self) -> None:
        """Begin the gentle pulse (idempotent). Call ONCE on the Tk thread; it
        self-reschedules via schedule() and never blocks the mainloop."""
        if self._pulsing:
            return
        self._pulsing = True
        self._pulse()

    # ─────────────────────────────── Internals ───────────────────────────────

    def _pulse(self) -> None:
        """One breath frame: repaint, then re-arm via schedule() (root.after).
        This is the WHOLE loop — no sleep, no while, never blocking."""
        self._tick += 1
        self._render()
        self._schedule(DEFAULT_PULSE_MS, self._pulse)

    def _breath(self) -> float:
        """A smooth 0→1→0 breath from the tick counter (cosine, deterministic —
        0.0 at tick 0 so a pre-pulse render is stable for tests)."""
        phase = (self._tick * DEFAULT_PULSE_MS % _PULSE_PERIOD_MS) / _PULSE_PERIOD_MS
        return 0.5 * (1.0 - math.cos(2.0 * math.pi * phase))

    def _render(self) -> None:
        """Repaint the corner dot for the current state. Clears its own tag first
        (never delete-all); idle paints nothing."""
        self._canvas.delete(STATUS_DOT_TAG)
        if self._state == IDLE:
            return
        color = self._style.status_colors.get(self._state)
        if color is None:      # a state without a color == hidden, defensively
            return
        if not self._light_off:
            self._draw_dot(color, self._breath())

    def _draw_dot(self, color: str, breath: float) -> None:
        """The persistent corner state light — a dim glow disc under a bright neon
        core, its radius breathing with the pulse."""
        x, y = self._dot_center()
        r = DOT_CORE_RADIUS + breath * DOT_PULSE_AMP
        halo = dim(color, self._style.glow_intensity)
        self._disc(x, y, r + self._style.glow_width, fill=halo, outline=halo)
        self._disc(x, y, r, fill=color, outline=color)

    def _dot_center(self) -> Tuple[int, int]:
        """The dot's center from the chosen corner + a fixed margin."""
        corner = self._style.status_corner
        x = DOT_MARGIN if "left" in corner else self._screen_w - DOT_MARGIN
        y = DOT_MARGIN if "top" in corner else self._screen_h - DOT_MARGIN
        return x, y

    def _disc(self, x: float, y: float, r: float, *, fill: str, outline: str) -> None:
        self._canvas.create_oval(
            x - r, y - r, x + r, y + r, fill=fill, outline=outline,
            tags=STATUS_DOT_TAG,
        )


__all__ = ["StatusIndicator", "STATUS_DOT_TAG", "VALID_STATES"]
