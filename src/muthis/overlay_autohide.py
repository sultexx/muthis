# src/muthis/overlay_autohide.py
"""
AutoHideController — owns the SINGLE pending auto-hide task for the cyan LOOK
overlay, with cancel-and-replace semantics.

Why a separate module (not inside orchestrator.py): orchestrator.py sits at the
≤300-line law's ceiling (AGENTS.md §17.4 — split, don't compress), and "a timer
that hides the rectangle after N seconds" is a distinct, single responsibility.
This file imports only stdlib asyncio + the Overlay protocol, so it stays
importable in isolation and its test needs no SDK and no real screen.

The contract the orchestrator relies on:
  * schedule() starts a background task (asyncio.create_task — NON-blocking) that
    waits `timeout_s` then calls overlay.hide(). It FIRST cancels any still-
    pending previous task, so a NEW highlight_target replaces the old auto-hide
    instead of stacking — no premature hide of the new rectangle, no orphan task.
  * cancel() drops a pending task WITHOUT hiding. The orchestrator calls it at the
    hide-before-capture chokepoint so a stale timer never outlives the explicit
    hide, and (later) on shutdown. Idempotent; a no-op when nothing is pending.
  * If the task is cancelled mid-wait, asyncio.sleep raises CancelledError and
    overlay.hide() is simply never reached — exactly the "don't hide" intent.

DI/threading note: asyncio.create_task needs a RUNNING loop, so the task is born
in schedule() (called from inside the orchestrator's running loop), never in
__init__. The timeout is injected (the composition root will source it from
MUTHIS_OVERLAY_TIMEOUT_S in a later batch); the default lives here so the
orchestrator stays a line lighter under its own line law.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .kernel.turn import Overlay

logger = logging.getLogger("muthis.overlay_autohide")


# Default seconds a highlight stays before the overlay auto-hides. Injected into
# the Orchestrator (overlay_timeout_s); a later batch sources it from
# MUTHIS_OVERLAY_TIMEOUT_S. 7 s is long enough to find the pointed element
# without leaving a stale rectangle parked on screen.
DEFAULT_OVERLAY_TIMEOUT_S = 7.0


class AutoHideController:
    """Manages ONE auto-hide timer for the overlay with cancel-and-replace.

    Holds the single in-flight task handle (`_task`) so schedule()/cancel() can
    always reach the current timer; there is never more than one pending."""

    def __init__(
        self, overlay: Overlay, timeout_s: float = DEFAULT_OVERLAY_TIMEOUT_S,
    ) -> None:
        self._overlay = overlay
        self._timeout_s = timeout_s
        self._task: Optional[asyncio.Task] = None

    @property
    def task(self) -> Optional[asyncio.Task]:
        """The currently-scheduled auto-hide task, or None when idle. Exposed for
        the orchestrator's teardown and for deterministic test control."""
        return self._task

    def schedule(self) -> None:
        """(Re)start the auto-hide countdown. Cancels any pending task FIRST so a
        fresh highlight_target replaces the previous timer rather than stacking
        (the older rectangle is gone; only the newest one should auto-hide)."""
        self.cancel()
        self._task = asyncio.create_task(self._hide_after_timeout())

    def cancel(self) -> None:
        """Drop a pending auto-hide WITHOUT hiding. Idempotent; a no-op when idle.
        Used at the hide-before-capture chokepoint so a stale timer can't fire
        against the next turn's rectangle, and on shutdown."""
        task = self._task
        if task is not None and not task.done():
            task.cancel()
        self._task = None

    async def _hide_after_timeout(self) -> None:
        """Wait the timeout, then hide. If cancelled mid-wait, CancelledError
        propagates out of asyncio.sleep and overlay.hide() is never called — the
        replacement timer (or the explicit hide-before-capture) owns the overlay
        now. overlay.hide() is itself resilient (Overlay protocol: never raises)."""
        await asyncio.sleep(self._timeout_s)
        logger.info(
            "[overlay_autohide] %.2fs elapsed with no new highlight — hiding overlay",
            self._timeout_s,
        )
        await self._overlay.hide()


__all__ = ["AutoHideController", "DEFAULT_OVERLAY_TIMEOUT_S"]
