# src/muthis/kernel/interrupt_hooks.py
"""Generic interrupt hooks — the kernel's blind eradication seam (DEC-3-C).

The orchestrator gains a GENERIC list of fire-and-forget callables it runs when
a turn is interrupted (F9 barge-in). The kernel owns the MECHANISM (a list it
fires on separate daemon threads); a plugin owns the CONTENT and registers it
from the plugin/broker side. The kernel stays blind to what a hook does — as
blind as it is to MCP — so new F9-time side effects can be added without the
kernel ever importing or naming their machinery. Firing is non-blocking and
swallows every exception, so a hook can neither delay the sacred silence-first
path nor raise into interrupt_turn. Not a lifecycle (Law 11): it only holds and
fires. Pure stdlib; importable in isolation."""

from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger("muthis.kernel.interrupt_hooks")

InterruptHook = Callable[[], None]


class InterruptHooks:
    """A registry of generic F9 callables — hold and fire, nothing else."""

    def __init__(self) -> None:
        self._hooks: list[InterruptHook] = []

    def add(self, hook: InterruptHook) -> None:
        self._hooks.append(hook)

    def fire(self) -> None:
        """Run every hook fire-and-forget on its own daemon thread — parallel
        to (never blocking) the voice silence, and never raising upward."""
        for hook in self._hooks:
            threading.Thread(target=self._run, args=(hook,), daemon=True).start()

    @staticmethod
    def _run(hook: InterruptHook) -> None:
        try:
            hook()
        except Exception:  # noqa: BLE001 — an F9 hook must never surface
            logger.warning("[interrupt_hooks] a hook raised — ignored")


__all__ = ["InterruptHooks", "InterruptHook"]
