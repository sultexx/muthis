# src/muthis/overlay/pointer_animator.py
"""
PointerAnimator — glides the PointerWidget from the current mouse position to a
target point with an ease-in-out curve, entirely on the Tk thread.

LOOK-ONLY BOUNDARY (load-bearing): this module READS the OS cursor position ONCE
per glide, via ctypes GetCursorPos, purely as the animation's START point. It
NEVER calls SetCursorPos / mouse_event / SendInput — it does not move, warp, or
click the real mouse. The thing that moves is a DRAWN arrow inside our own
overlay window. Moving the real cursor would be AUTOPILOT, which is gated behind
an explicit phase and must never leak into LOOK.

Threading: the glide is driven by the Tk widget's after() scheduler (injected as
`schedule`), so every frame runs on the Tk thread — the asyncio loop is never
touched and Tk is never called cross-thread. The orchestrator only sends a single
"show" command over the existing queue; this class owns the per-frame motion.

Determinism/DI: schedule (root.after), clock (time.monotonic), and cursor_reader
(read_cursor_pos) are all injected with real defaults, so tests drive the glide
frame-by-frame with fakes — no real window, no real mouse, no real sleep. A
generation counter makes a replaced/cancelled glide drop any already-queued
frame, so chains never overlap.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Callable, Optional

logger = logging.getLogger("muthis.overlay")

# Default glide duration; the composition root sources MUTHIS_POINTER_ANIM_MS and
# passes it down to SidekickOverlay (see main.py). 500 ms reads as smooth without
# making the user wait to see the highlight.
DEFAULT_POINTER_ANIM_MS = 500

# One frame every ~16 ms ≈ 60 fps — smooth without flooding the Tk event loop.
DEFAULT_FRAME_MS = 16

XY = tuple[int, int]


def read_cursor_pos() -> XY:
    """Return the OS cursor's CURRENT physical-pixel position. READ ONLY — this
    calls GetCursorPos and nothing else; it never moves, warps, or clicks the
    mouse. Physical pixels because the overlay process is per-monitor DPI-aware,
    so the start point shares the bbox's coordinate space. ctypes is stdlib (no
    new dependency) and imported lazily so importing this module stays
    headless-safe; on any failure it degrades to the origin rather than raise into
    the Tk thread."""
    try:
        import ctypes

        class _POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        point = _POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        return (int(point.x), int(point.y))
    except Exception:  # non-Windows / ctypes quirk — glide from origin, never raise
        logger.warning("[overlay] GetCursorPos unavailable — gliding from origin")
        return (0, 0)


def _ease_in_out(t: float) -> float:
    """Cosine ease-in-out on t∈[0,1]: slow start, slow finish, smooth middle."""
    return 0.5 - 0.5 * math.cos(math.pi * t)


class PointerAnimator:
    """Drives one ease-in-out glide of a PointerWidget on the Tk thread."""

    def __init__(
        self,
        *,
        schedule: Callable[[int, Callable[[], None]], object],
        pointer,
        duration_ms: int = DEFAULT_POINTER_ANIM_MS,
        frame_ms: int = DEFAULT_FRAME_MS,
        clock: Optional[Callable[[], float]] = None,
        cursor_reader: Callable[[], XY] = read_cursor_pos,
    ) -> None:
        self._schedule = schedule
        self._pointer = pointer
        self._duration_ms = max(0, int(duration_ms))
        self._frame_ms = max(1, int(frame_ms))
        self._clock = clock or time.monotonic
        self._cursor_reader = cursor_reader
        self._active = False
        self._gen = 0                      # bumped on start/cancel; stale ticks no-op
        self._start: XY = (0, 0)
        self._target: XY = (0, 0)
        self._t0 = 0.0
        self._on_arrival: Optional[Callable[[], None]] = None

    def start(self, target: XY, on_arrival: Callable[[], None]) -> None:
        """Begin gliding the pointer from the CURRENT mouse position (read once,
        read-only) to `target`. Calls on_arrival exactly once when the glide
        completes. Replaces any in-flight glide (cancel-and-replace)."""
        self.cancel()
        self._gen += 1
        self._start = self._cursor_reader()      # READ-ONLY OS cursor read
        self._target = target
        self._on_arrival = on_arrival
        self._t0 = self._clock()
        self._active = True
        self._tick(self._gen)

    def cancel(self) -> None:
        """Stop any in-flight glide WITHOUT arriving. Idempotent. Bumps the
        generation so an already-queued frame becomes a no-op — no stray frame and
        no late on_arrival ever lands (the hide-before-capture / replace paths)."""
        self._active = False
        self._gen += 1
        self._on_arrival = None

    def _tick(self, gen: int) -> None:
        # A frame from a superseded/cancelled glide (or after arrival) does nothing.
        if not self._active or gen != self._gen:
            return
        elapsed_ms = (self._clock() - self._t0) * 1000.0
        t = 1.0 if self._duration_ms == 0 else min(1.0, elapsed_ms / self._duration_ms)
        eased = _ease_in_out(t)
        x = round(self._start[0] + (self._target[0] - self._start[0]) * eased)
        y = round(self._start[1] + (self._target[1] - self._start[1]) * eased)
        self._pointer.move_to(x, y)
        if t >= 1.0:
            self._active = False
            on_arrival, self._on_arrival = self._on_arrival, None
            if on_arrival is not None:
                on_arrival()
            return
        self._schedule(self._frame_ms, lambda: self._tick(gen))


__all__ = [
    "PointerAnimator", "read_cursor_pos",
    "DEFAULT_POINTER_ANIM_MS", "DEFAULT_FRAME_MS",
]
