# src/muthis/turn_timing.py
"""
turn_timing.py — the voice instrument's three timing lines (DEC-157 ⑤).

ONE CONCERN: stamping three moments of a turn, in milliseconds since the turn
started, so the voice instrument (`voice_probe.py`) can time the real pipeline:

    first_token  — the first TextDelta or ToolCall of the turn's first pass
    draw         — the buffered draw handed to the overlay (Option A's sync point)
    first_audio  — the first PCM block written to the output device

DEBUG ONLY, AND THEREFORE NEVER IN THE DURABLE LOG. A line is emitted only when
`debug_content_enabled()` is true — the SAME predicate `attach_file_log` reads
before it refuses to build the file handler (logging_policy.py). So the one state
in which a timing line exists is the one state in which the durable log cannot.
And nothing in the app starts the clock: `turn_started()` is called by the
instrument alone, at the moment it releases F9 through the built controller. In
normal operation `_turn_start` stays None and every `stage()` call returns at its
first comparison.

Module state rather than a per-turn object, on purpose: threading a clock through
`turn_pass.py` (pinned) and the player's worker thread would cost lines in three
signatures for an instrument that runs one turn per process. A lock covers the
one cross-thread caller (`first_audio`, from the PCM worker). Stdlib +
`logging_policy` only, so every importer stays importable in isolation.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from .logging_policy import debug_content_enabled

logger = logging.getLogger("muthis.timing")

STAGES = ("first_token", "draw", "first_audio")

_lock = threading.Lock()
_turn_start: Optional[float] = None
_seen: set[str] = set()


def turn_started(now: Optional[float] = None) -> None:
    """Start the clock for ONE turn (the instrument's F9 release). Outside debug
    it never starts, so no later stage can emit."""
    global _turn_start
    with _lock:
        _seen.clear()
        _turn_start = (time.monotonic() if now is None else now) if debug_content_enabled() else None


def stage(name: str, now: Optional[float] = None) -> None:
    """Emit `[timing] <name> +<ms> ms` the FIRST time `name` happens this turn."""
    if _turn_start is None or name in _seen:
        return
    with _lock:
        if _turn_start is None or name in _seen or not debug_content_enabled():
            return
        _seen.add(name)
        elapsed_ms = round(((time.monotonic() if now is None else now) - _turn_start) * 1000)
    logger.info("[timing] %s +%d ms", name, elapsed_ms)


def model_event(event: Any) -> None:
    """`first_token` for any model output — a TextDelta or a ToolCall — never the
    TurnComplete that closes a pass (an empty pass has produced nothing)."""
    if type(event).__name__ != "TurnComplete":
        stage("first_token")


def reset() -> None:
    """Stop the clock (tests, and the instrument's teardown)."""
    global _turn_start
    with _lock:
        _turn_start = None
        _seen.clear()


__all__ = ["STAGES", "model_event", "reset", "stage", "turn_started"]
