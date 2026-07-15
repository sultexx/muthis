# scripts/smoke_overlay.py
"""
Manual smoke test — DPI mapping of the cyan overlay. NEVER run in CI.

Pure overlay check: NO Claude / mic / TTS. Draws ONE cyan rectangle + Arabic
caption at a KNOWN PHYSICAL coordinate on your primary monitor, holds it a few
seconds, then hides it. Use it to confirm the rectangle lands EXACTLY where you
expect on a 125%/150%-scaled Win11 display (physical pixels, not logical) —
that's the whole point: the orchestrator hands the overlay physical coords and
the overlay must draw them 1:1.

By default it frames a ~200x140 box near the center of a 1920x1080 screen. Pass
four integers to target a real UI element you can eyeball:
    .venv\\Scripts\\python.exe scripts\\smoke_overlay.py
    .venv\\Scripts\\python.exe scripts\\smoke_overlay.py 40 40 240 120   # x1 y1 x2 y2 (PHYSICAL px)

Privacy: draws only; never captures, logs, or persists any screen pixels.
"""

import asyncio
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from muthis.overlay import SidekickOverlay  # noqa: E402

DEFAULT_BBOX = (860, 470, 1060, 610)  # a ~200x140 box near a 1920x1080 center
HOLD_SECONDS = 4.0
LABEL_AR = "هنا المكان"


async def main() -> None:
    if len(sys.argv) == 5:
        bbox = tuple(int(value) for value in sys.argv[1:5])
    else:
        bbox = DEFAULT_BBOX

    overlay = SidekickOverlay()
    print(f"رسم مستطيل سماوي عند الإحداثيات الفيزيائية {bbox} لمدة {HOLD_SECONDS:.0f} ثوانٍ...")
    await overlay.show(bbox, LABEL_AR)
    await asyncio.sleep(HOLD_SECONDS)

    print("إخفاء المستطيل...")
    await overlay.hide()
    await asyncio.sleep(0.5)  # let the Tk thread process the hide before teardown
    overlay.close()
    print("تم. لو وقع المستطيل تمامًا على المكان المتوقع، فإن الـ DPI mapping مضبوط.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic on the Windows console
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
