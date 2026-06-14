# src/muthis/hotkey.py
"""
hotkey.py — the global push-to-talk listener (hold to talk, release to send).

A background keyboard listener that turns a physical HOLD into two signals:
key-down starts recording, key-up schedules ONE turn on the asyncio loop — and
nothing more. It owns NO business logic (Law 11): it knows the loop, the target
key, and two thread-safe callbacks. Mic, STT, Claude, TTS, and the overlay are
all someone else's job (the composition root wires them; this listener never
sees them).

Why pynput (listen-only) and not `keyboard`: the `keyboard` library needs an
elevated (Administrator) process to install a system-wide low-level hook on
Windows 11. pynput's `keyboard.Listener` reads global key events WITHOUT
elevation, so Mut'his runs as a normal user process. Trade-off accepted: we only
LISTEN, we never inject keystrokes (which suits LOOK-only perfectly).

TWO callbacks, TWO thread disciplines — both events arrive on pynput's OWN
background thread:
  * on_press  → invoked DIRECTLY on the keyboard thread. It only starts the mic
    (no asyncio), so it needs no loop crossing and we want the LOWEST latency to
    catch the first syllable.
  * on_release → invoked via loop.call_soon_threadsafe. It schedules an asyncio
    task (the turn); asyncio loops are NOT thread-safe, so calling a coroutine
    or asyncio.create_task from the keyboard thread would mutate loop-internal
    state from the wrong thread and corrupt it (RuntimeError / dropped tasks /
    undefined behavior). call_soon_threadsafe is the SINGLE blessed crossing: it
    enqueues the callback on the loop's own thread and wakes the loop from any
    thread.

Auto-repeat: while a key is held, pynput fires on_press REPEATEDLY. `_held`
debounces it so on_press runs exactly once per physical hold, and a release with
no matching press is ignored.

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
    """Background global-key listener. Hold the configured key to record, release
    to send: key-down starts the mic directly, key-up bridges ONE turn onto the
    asyncio loop via call_soon_threadsafe — that is its entire job."""

    def __init__(
        self,
        *,
        loop: Any,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        hotkey: str = DEFAULT_HOTKEY,
    ) -> None:
        # `loop` is the running asyncio loop. `on_press`/`on_release` are PLAIN
        # (sync) callbacks — never coroutines. on_press runs on the keyboard
        # thread; on_release is handed to the loop's thread (see _handle_release).
        self._loop = loop
        self._on_press = on_press
        self._on_release = on_release
        self._target = hotkey.strip().lower()
        self._listener: Any = None   # the pynput listener, created in start()
        self._held = False           # physical key state; keyboard-thread only

    def _handle_press(self, key: Any) -> None:
        """pynput key-down handler — runs on the KEYBOARD thread.

        Debounce auto-repeat, then start the mic DIRECTLY: this touches no
        asyncio state, so no loop crossing is needed and latency stays minimal."""
        if _key_to_name(key) != self._target:
            return
        if self._held:               # auto-repeat while held — ignore
            return
        self._held = True
        logger.info("[hotkey] %r down — start recording", self._target)
        self._on_press()

    def _handle_release(self, key: Any) -> None:
        """pynput key-up handler — runs on the KEYBOARD thread.

        Bridge to the loop via the ONE safe crossing; the scheduled callback
        launches the turn on the loop's own thread, where create_task is legal."""
        if _key_to_name(key) != self._target:
            return
        if not self._held:           # release with no matching press — ignore
            return
        self._held = False
        logger.info("[hotkey] %r up — scheduling the turn on the loop", self._target)
        self._loop.call_soon_threadsafe(self._on_release)

    def start(self) -> None:
        """Spawn the pynput listener on its own background thread.

        pynput is imported HERE (lazily) so module import never pulls an input
        backend — keeps tests and headless hosts safe."""
        if self._listener is not None:
            return
        from pynput import keyboard  # lazy: input backend touched only at start

        self._listener = keyboard.Listener(
            on_press=self._handle_press,
            on_release=self._handle_release,
        )
        self._listener.daemon = True  # never block process exit
        self._listener.start()
        logger.info(
            "[hotkey] listening for %r (hold to talk, release to send)", self._target,
        )

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
