# scripts/smoke_focus_dim.py
"""
Manual smoke test — the Cinematic Spotlight prototype (v6 Phase D0). NEVER in CI.

Pure overlay check: NO Claude / mic / TTS. Opens TWO windows for a few seconds:
  * the DIMMER — a fullscreen black Toplevel at -alpha 0.30 whose only visible
    "hole" is a -transparentcolor rectangle over the target bbox, and
  * a NEON window above it drawing the cyan highlight rectangle inside the hole
then closes both. Both windows are click-through / no-activate (the same
ex-styles as the real overlay).

D0 gate findings (measured 2026-07-15 on Win11, 1920x1080 — see plan_v6.md):
  * -alpha + -transparentcolor DO coexist on one Toplevel: outside the hole the
    screen dims to ~0.67-0.69x (expected 0.70 at alpha 0.30); inside the hole
    the pixels are UNCHANGED (ratio exactly 1.0),
  * z-order is stable: a neon window created after + lift() renders at FULL
    brightness above the dim, inside AND outside the hole,
  * the click-through ex-styles read back set on the layered dimmer.

Confirm visually: the screen dims except a bright rectangular spotlight; the
cyan rectangle glows at full intensity; everything vanishes cleanly at the end.

LOOK-ONLY: drawn windows only; the mouse is never moved, warped, or clicked.

    .venv\\Scripts\\python.exe scripts\\smoke_focus_dim.py

Privacy: draws only; never captures, logs, or persists any screen pixels.
"""

import ctypes
import time

ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # PER_MONITOR_AWARE_V2

import tkinter as tk  # noqa: E402  (after DPI awareness)

TRANSPARENT_KEY = "#FF00FF"
DIM_ALPHA = 0.30
TARGET_BBOX = (700, 350, 1220, 730)
HOLE_MARGIN = 12
HOLD_SECONDS = 6.0

GWL_EXSTYLE = -20
EX_STYLES = 0x00080000 | 0x00000020 | 0x08000000 | 0x00000080  # layered|transparent|noactivate|toolwindow


def apply_click_through(window) -> None:
    user32 = ctypes.windll.user32
    window.update_idletasks()
    hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
    get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    set_long(hwnd, GWL_EXSTYLE, get_long(hwnd, GWL_EXSTYLE) | EX_STYLES)


def main() -> None:
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{width}x{height}+0+0")
    root.configure(bg="black")
    root.attributes("-alpha", DIM_ALPHA)
    root.attributes("-transparentcolor", TRANSPARENT_KEY)
    dim_canvas = tk.Canvas(root, bg="black", highlightthickness=0)
    dim_canvas.pack(fill="both", expand=True)
    x1, y1, x2, y2 = TARGET_BBOX
    dim_canvas.create_rectangle(
        x1 - HOLE_MARGIN, y1 - HOLE_MARGIN, x2 + HOLE_MARGIN, y2 + HOLE_MARGIN,
        fill=TRANSPARENT_KEY, outline=TRANSPARENT_KEY,
    )
    apply_click_through(root)

    neon = tk.Toplevel(root)
    neon.overrideredirect(True)
    neon.attributes("-topmost", True)
    neon.geometry(f"{width}x{height}+0+0")
    neon.configure(bg=TRANSPARENT_KEY)
    neon.attributes("-transparentcolor", TRANSPARENT_KEY)
    neon_canvas = tk.Canvas(neon, bg=TRANSPARENT_KEY, highlightthickness=0)
    neon_canvas.pack(fill="both", expand=True)
    neon_canvas.create_rectangle(*TARGET_BBOX, outline="#00FFFF", width=6)
    apply_click_through(neon)
    neon.lift()

    print(f"التعتيم السينمائي ظاهر الآن — يبقى {HOLD_SECONDS:.0f} ثوانٍ...")
    deadline = time.monotonic() + HOLD_SECONDS
    while time.monotonic() < deadline:
        root.update()
        time.sleep(0.02)
    root.destroy()
    print(
        "تم. لو أظلمت الشاشة ~30% ما عدا بقعة ضوء مستطيلة حول الهدف، وظل "
        "المستطيل السياني ساطعًا بكامل قوته، ثم اختفى كل شيء نظيفًا — فالنموذج مضبوط."
    )


if __name__ == "__main__":
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
