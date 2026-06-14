# src/muthis/overlay/sidekick_window.py
"""
SidekickOverlay — the cyan-rectangle LOOK pointer as a real Win11 window.

LOOK-ONLY: this window DRAWS A RECTANGLE (plus a short Arabic caption) and
nothing else. It never moves the mouse, clicks, types, or reads input.

Threading (AGENTS.md §11.5): Tkinter is single-threaded and thread-affine, so
the window lives on its OWN daemon thread running the Tk mainloop. The async
orchestrator never touches Tk directly — show()/hide() drop a command on a
queue.Queue and return immediately, so the asyncio loop is never blocked. The
Tk thread drains the queue from inside the mainloop via root.after().

Coordinates are ALREADY PHYSICAL pixels (the orchestrator did the sent→physical
scale). For those to land exactly on a 125%/150%-scaled display the PROCESS must
be DPI-aware, so we set per-monitor-v2 awareness before creating the window
(idempotent with screen_capture, which sets the same on its side).

Click-through + transparency (Win32): the toplevel gets WS_EX_LAYERED |
WS_EX_TRANSPARENT (mouse passes straight through to the app underneath), plus
WS_EX_NOACTIVATE (never steals focus) and WS_EX_TOOLWINDOW (stays out of
Alt-Tab); a Tk -transparentcolor key makes only the drawn pixels visible.
tkinter/ctypes are imported here, never by the orchestrator (which depends only
on the Overlay protocol in turn.py).

Resilient like the other I/O seams: show()/hide()/close() never raise; a failed
window init is logged in English and turns show/hide into no-ops.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

logger = logging.getLogger("muthis.overlay")

# Tk -transparentcolor key: pixels of this exact color become fully see-through,
# so the window shows only the cyan rectangle + caption. Magenta is never drawn.
TRANSPARENT_KEY = "#FF00FF"

# How often (ms) the Tk thread drains the command queue from inside the mainloop.
_QUEUE_POLL_MS = 10

# Win32 constants for the click-through ex-styles.
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080


class SidekickOverlay:
    """Overlay protocol impl (show/hide) backed by a private Tk thread."""

    def __init__(self) -> None:
        self._commands: "queue.Queue[tuple]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._started = False
        self._dead = False  # window init failed → show/hide become no-ops
        self._lock = threading.Lock()

    # ─────────────────────────── Overlay protocol ───────────────────────────

    async def show(self, bbox: tuple[int, int, int, int], label_ar: str) -> None:
        """Draw/replace the single cyan rectangle at PHYSICAL bbox with caption.
        Non-blocking: enqueues a command for the Tk thread and returns."""
        self._enqueue(("show", bbox, label_ar))

    async def hide(self) -> None:
        """Clear the rectangle. Called before EVERY capture (ghosting fix).
        Non-blocking."""
        self._enqueue(("hide",))

    # ───────────────────────────── Lifecycle ─────────────────────────────

    def close(self) -> None:
        """Tear the window + thread down. Safe to call if never shown."""
        if not self._started or self._dead:
            return
        self._commands.put(("close",))
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    # ───────────────────────────── Internals ─────────────────────────────

    def _enqueue(self, command: tuple) -> None:
        if self._dead:
            return
        self._ensure_thread()
        self._commands.put(command)

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._thread = threading.Thread(
                target=self._run, name="muthis-overlay", daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        """Tk thread entry: DPI awareness → transparent click-through window →
        mainloop draining the command queue. tkinter/ctypes load HERE only."""
        try:
            import tkinter as tk

            from .rectangle_widget import RectangleWidget

            self._set_dpi_awareness()
            root = tk.Tk()
            self._configure_window(root)
            widget = RectangleWidget(root, TRANSPARENT_KEY)
            self._apply_click_through(root)
        except Exception:  # headless / Tk missing / Win32 quirk — degrade quietly
            logger.exception("[overlay] window init failed — overlay disabled")
            self._dead = True
            return

        def _drain() -> None:
            try:
                while True:
                    command = self._commands.get_nowait()
                    action = command[0]
                    if action == "close":
                        root.destroy()
                        return
                    if action == "show":
                        widget.draw(command[1], command[2])
                    elif action == "hide":
                        widget.clear()
            except queue.Empty:
                pass
            root.after(_QUEUE_POLL_MS, _drain)

        root.after(_QUEUE_POLL_MS, _drain)
        root.mainloop()

    # ───────────────────────────── Win32 glue ─────────────────────────────

    def _configure_window(self, root) -> None:
        """Borderless, always-on-top, primary-monitor-sized, color-keyed."""
        root.overrideredirect(True)          # no title bar / taskbar entry
        root.attributes("-topmost", True)
        root.configure(bg=TRANSPARENT_KEY)
        root.attributes("-transparentcolor", TRANSPARENT_KEY)
        width = root.winfo_screenwidth()     # physical px (process is DPI-aware)
        height = root.winfo_screenheight()
        root.geometry(f"{width}x{height}+0+0")

    def _set_dpi_awareness(self) -> None:
        """Per-monitor-v2 so PHYSICAL coords map 1:1 on a scaled display.
        Idempotent: a prior call (e.g. screen_capture) just makes this a no-op."""
        import ctypes

        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # PER_MONITOR_AWARE_V2
            return
        except Exception:
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        except Exception:
            logger.warning(
                "[overlay] could not set DPI awareness — coords may drift on "
                "scaled displays")

    def _apply_click_through(self, root) -> None:
        """OR the click-through / no-activate ex-styles onto the toplevel so the
        whole window passes the mouse straight to the app beneath."""
        import ctypes

        user32 = ctypes.windll.user32
        root.update_idletasks()  # realize the HWND first
        # GetParent reaches the real OS toplevel; fall back to the Tk id if a
        # borderless window has no wrapper parent.
        hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
        get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        style = get_long(hwnd, _GWL_EXSTYLE)
        set_long(
            hwnd, _GWL_EXSTYLE,
            style | _WS_EX_LAYERED | _WS_EX_TRANSPARENT
            | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW,
        )


__all__ = ["SidekickOverlay"]
