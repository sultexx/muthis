# scripts/smoke_shapes.py
"""
Manual smoke test — the NEON overlay look (Batch 1). NEVER run in CI.

Pure overlay check: NO Claude / mic / TTS. Draws, all at once on a 1920x1080
primary display:
  * the highlight_target rectangle + its gliding pointer (via show()), then
  * all draw_shapes kinds — a line, an arrow, a circle, a rectangle, and
    THREE numbered step badges (v6 B: expect ١ ٢ ٣ left-to-right) —
each with an Arabic caption, holds a few seconds, then hides everything. Use it
to judge the neon aesthetic on YOUR screen and tune the .env values by eye.

Confirm visually:
  * each shape glows in its own neon color (line=cyan, arrow=green,
    circle=magenta, rectangle=yellow, highlight=cyan) — a dim halo under a
    crisp bright core,
  * each Arabic caption sits, readable, on its rounded semi-dark chip above its
    shape (never covering it),
  * DPI mapping is correct (coords land right on a 125%/150%-scaled display too),
  * hide() clears EVERYTHING at once (the ghosting rule — nothing survives).

Tune by eye WITHOUT touching code — set any of these before running, e.g.:
    set MUTHIS_COLOR_ARROW=#FF6A00 && set MUTHIS_GLOW_WIDTH=6 && ^
    set MUTHIS_LABEL_SIZE=16 && .venv\\Scripts\\python.exe scripts\\smoke_shapes.py
  (also MUTHIS_COLOR_LINE / _CIRCLE / _RECT / _POINTER / _HIGHLIGHT, MUTHIS_GLOW,
   MUTHIS_GLOW_INTENSITY, MUTHIS_CORE_WIDTH, MUTHIS_LABEL_FONT, MUTHIS_LABEL_PLATE.)

LOOK-ONLY: drawn graphics only; the mouse is never moved, warped, or clicked.

    .venv\\Scripts\\python.exe scripts\\smoke_shapes.py

Privacy: draws only; never captures, logs, or persists any screen pixels.
"""

import asyncio
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from muthis.overlay import SidekickOverlay  # noqa: E402
from muthis.shapes import Shape, circle_shape  # noqa: E402

HOLD_SECONDS = 6.0
GLIDE_SETTLE_SECONDS = 1.2   # let the pointer glide finish + the rectangle land

# The highlight_target rectangle + pointer, drawn first (via show()) at a central
# PHYSICAL bbox that the four quadrant shapes leave clear.
HIGHLIGHT_BBOX = (760, 470, 1160, 620)
HIGHLIGHT_LABEL = "الهدف"

# PHYSICAL coordinates for a 1920x1080 primary display — one shape per
# quadrant, so all four are visible at once and none overlaps another.
# The three step badges (v6 B) march across the top strip in execution order:
# they must render ١ ٢ ٣ left-to-right (numbered by LIST order, no number field).
SHAPES = (
    Shape(kind="line", points=(200, 200, 600, 350), label_ar="خط"),
    Shape(kind="arrow", points=(1300, 250, 1700, 400), label_ar="سهم"),
    circle_shape(500, 780, 120, label_ar="دائرة"),
    Shape(kind="rectangle", points=(1250, 700, 1700, 950), label_ar="مستطيل"),
    Shape(kind="step", points=(700, 90, 745, 135), label_ar="الخطوة الأولى"),
    Shape(kind="step", points=(940, 90, 985, 135)),
    Shape(kind="step", points=(1180, 90, 1225, 135)),
)


async def main() -> None:
    overlay = SidekickOverlay()

    print("رسم مستطيل الهدف مع المؤشر المنزلق (توهّج نيون)...")
    await overlay.show(HIGHLIGHT_BBOX, HIGHLIGHT_LABEL)
    await asyncio.sleep(GLIDE_SETTLE_SECONDS)   # wait for the glide to settle

    print(f"رسم الأشكال الأربعة الآن — يبقى كل شيء على الشاشة {HOLD_SECONDS:.0f} ثوانٍ...")
    await overlay.draw_shapes(SHAPES)
    await asyncio.sleep(HOLD_SECONDS)

    print("إخفاء كل شيء (فحص قاعدة الـ ghosting)...")
    await overlay.hide()
    await asyncio.sleep(1.0)             # let the Tk thread process the hide
    overlay.close()
    print(
        "تم. لو ظهر المستطيل والمؤشر والخط والسهم والدائرة والمستطيل بألوانها "
        "النيون وتوهّجها وتسمياتها، وظهرت الشارات المرقّمة ١ ٢ ٣ من اليسار "
        "لليمين في الشريط العلوي، ثم اختفت كلها بالكامل — فكل شيء مضبوط."
    )


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Arabic on the Windows console
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
