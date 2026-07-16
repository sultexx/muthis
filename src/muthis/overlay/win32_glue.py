# src/muthis/overlay/win32_glue.py
"""
Win32 window glue for the overlay package, extracted WHOLE from
sidekick_window.py (v7 Phase 2 — that file sat AT the 299/300 ceiling and the
caption-pacing work needs queue methods there; Law §17.4: split, don't
compress). Two single-purpose helpers, ctypes only, no tkinter import:

  * set_dpi_awareness()      — per-monitor-v2 so PHYSICAL coords land 1:1 on
                               scaled Windows 11 displays (idempotent with
                               screen_capture, which sets the same).
  * apply_click_through(win) — OR the WS_EX_LAYERED | WS_EX_TRANSPARENT |
                               WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW ex-styles
                               onto a realized Tk toplevel so the mouse passes
                               straight through to the app beneath (LOOK-only:
                               the overlay can never swallow a click).

Called ONLY from the Tk thread (sidekick_window._run + build_focus_dimmer's
injected seam). ctypes loads lazily inside the functions, keeping this module
importable on any platform (the package's headless-safety convention).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("muthis.overlay")

# Win32 constants for the click-through ex-styles.
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080


def set_dpi_awareness() -> None:
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


def apply_click_through(root) -> None:
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
    set_long(hwnd, _GWL_EXSTYLE,
             style | _WS_EX_LAYERED | _WS_EX_TRANSPARENT | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW)


__all__ = ["set_dpi_awareness", "apply_click_through"]
