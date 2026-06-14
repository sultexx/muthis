# src/muthis/hotkey.py
"""
hotkey.py — the global push-to-talk activation listener (LOOK phase, final step).

A background keyboard listener that turns a single physical keypress into ONE
scheduled turn on the asyncio loop — and nothing more. It owns NO business logic
(Law 11): it knows the loop, the target key, and a thread-safe callback. Mic,
STT, Claude, TTS, and the overlay are all someone else's job (the composition
root wires them; this listener never sees them).

Why pynput (listen-only) and not `keyboard`: the `keyboard` library needs an
elevated (Administrator) process to install a system-wide low-level hook on
Windows 11. pynput's `keyboard.Listener` reads global key events WITHOUT
elevation, so Mut'his runs as a normal user process. Trade-off accepted: we only
LISTEN, we never inject keystrokes (which suits LOOK-only perfectly).

THE ONE SAFE THREAD→LOOP BRIDGE: pynput delivers key events on its OWN
background thread. asyncio loops are NOT thread-safe — calling a coroutine, or
`asyncio.create_task`, from the keyboard thread would mutate loop-internal state
from the wrong thread and corrupt it (RuntimeError / dropped tasks / undefined
behavior). `loop.call_soon_threadsafe(callback)` is the SINGLE blessed crossing:
it enqueues the callback on the loop's own thread and wakes the loop safely from
any thread. So `_handle_press` does exactly that — it schedules, it never runs
the turn itself.

pynput is imported LAZILY inside start() so importing this module (and building a
listener) stays headless/CI-safe and triggers no input-device backend.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("muthis.hotkey")

# Default push-to-talk key. Configurable at the composition root via .env
# (MUTHIS_HOTKEY). "f9" is a single, rarely-bound function key.
DEFAULT_HOTKEY = "f9"


def _key_to_name(key: Any) -> Optional[str]:
    """Normalize a pynput key event to a lowercase name we can compare.

    Function/special keys arrive as `keyboard.Key.<name>` (which carries a
    `.name` like "f9"); character keys arrive as `keyboard.KeyCode` (which
    carries a `.char` like "k"). We never import pynput here — we only read the
    two attributes, so a plain stand-in object works in tests too."""
    name = getattr(key, "name", None)
    if name:
        return str(name).lower()
    char = getattr(key, "char", None)
    if char:
        return str(char).lower()
    return None


class HotkeyListener:
    """Background global-key listener. On the configured key it bridges to the
    asyncio loop via call_soon_threadsafe — that is its entire job."""

    def __init__(
        self,
        *,
        loop: Any,
        on_activate: Callable[[], None],
        hotkey: str = DEFAULT_HOTKEY,
    ) -> None:
        # `loop` is the running asyncio loop; `on_activate` is a PLAIN (sync)
        # callback that the loop will run on its own thread — never a coroutine.
        self._loop = loop
        self._on_activate = on_activate
        self._target = hotkey.strip().lower()
        self._listener: Any = None  # the pynput listener, created in start()

    def _handle_press(self, key: Any) -> None:
        """pynput key-press handler — runs on the KEYBOARD thread.

        It does the bare minimum on this foreign thread: match the key, then
        hand off to the loop via the one safe bridge. No async, no work here."""
        if _key_to_name(key) != self._target:
            return
        logger.info("[hotkey] %r pressed — scheduling a turn on the loop", self._target)
        # The ONLY safe thread→loop crossing. on_activate runs on the loop's
        # own thread, where create_task is legal.
        self._loop.call_soon_threadsafe(self._on_activate)

    def start(self) -> None:
        """Spawn the pynput listener on its own background thread.

        pynput is imported HERE (lazily) so module import never pulls an input
        backend — keeps tests and headless hosts safe."""
        if self._listener is not None:
            return
        from pynput import keyboard  # lazy: input backend touched only at start

        self._listener = keyboard.Listener(on_press=self._handle_press)
        self._listener.daemon = True  # never block process exit
        self._listener.start()
        logger.info("[hotkey] listening for %r (global, no elevation)", self._target)

    def stop(self) -> None:
        """Stop the listener thread. Never raises — shutdown must stay clean."""
        if self._listener is None:
            return
        try:
            self._listener.stop()
        except Exception:  # pragma: no cover - defensive; teardown must not throw
            logger.warning("[hotkey] listener stop failed", exc_info=True)
        finally:
            self._listener = None
            logger.info("[hotkey] stopped")


__all__ = ["HotkeyListener", "DEFAULT_HOTKEY"]
