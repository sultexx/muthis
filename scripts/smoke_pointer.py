# scripts/smoke_pointer.py
"""
Manual smoke test — the animated LOOK pointer + DPI mapping. NEVER run in CI.

Pure overlay check: NO Claude / mic / TTS. It READS your real mouse position
(read-only — it NEVER moves, warps, or clicks your cursor) as the glide's START,
then animates a DRAWN cyan arrow gliding smoothly to the CENTER of a KNOWN
PHYSICAL bbox, draws the cyan rectangle + Arabic caption on arrival, holds a few
seconds, then hides both.

Use it on a 1920x1080 (or 125%/150%-scaled) Win11 display to confirm:
  * the drawn arrow starts at your ACTUAL cursor and glides smoothly, and
  * the rectangle lands EXACTLY on the physical coordinate (DPI mapping correct).

LOOK-ONLY: the gliding arrow is a drawn shape; your real OS mouse is never moved
— only GetCursorPos (read) is used, for the glide's start point.

    .venv\\Scripts\\python.exe scripts\\smoke_pointer.py
    .venv\\Scripts\\python.exe scripts\\smoke_pointer.py 40 40 240 120   # x1 y1 x2 y2 (PHYSICAL px)
    set MUTHIS_POINTER_ANIM_MS=900 && .venv\\Scripts\\python.exe scripts\\smoke_pointer.py

Privacy: draws only; never captures, logs, or persists any screen pixels.
"""

import asyncio
import logging
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from muthis.overlay import DEFAULT_POINTER_ANIM_MS, SidekickOverlay  # noqa: E402

DEFAULT_BBOX = (860, 470, 1060, 610)   # a ~200x140 box near a 1920x1080 center
POSITION_SECONDS = 2.0                  # time to move your mouse before the glide
HOLD_SECONDS = 4.0
LABEL_AR = "هنا المكان"


def _anim_ms() -> int:
    """Same source as production: MUTHIS_POINTER_ANIM_MS, default on bad/empty."""
    raw = os.getenv("MUTHIS_POINTER_ANIM_MS")
    if raw is None:
        return DEFAULT_POINTER_ANIM_MS
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_POINTER_ANIM_MS


async def main() -> None:
    if len(sys.argv) == 5:
        bbox = tuple(int(value) for value in sys.argv[1:5])
    else:
        bbox = DEFAULT_BBOX

    anim_ms = _anim_ms()
    overlay = SidekickOverlay(anim_duration_ms=anim_ms)

    print(
        f"حرّك ماوسك إلى أي ركن الآن — يبدأ الانزلاق بعد {POSITION_SECONDS:.0f} ثانية."
    )
    await asyncio.sleep(POSITION_SECONDS)

    print(
        f"المؤشر سينزلق من مكان ماوسك إلى مركز {bbox} خلال {anim_ms}ms، "
        f"ثم يُرسم المستطيل ويبقى {HOLD_SECONDS:.0f} ثوانٍ..."
    )
    await overlay.show(bbox, LABEL_AR)   # reads the cursor (read-only) + glides
    await asyncio.sleep(HOLD_SECONDS)

    print("إخفاء المؤشر والمستطيل...")
    await overlay.hide()
    await asyncio.sleep(0.5)             # let the Tk thread process the hide
    overlay.close()
    print("تم. لو بدأ السهم من مكان ماوسك، وانزلق بسلاسة، ووقف على المكان بالضبط — فكل شيء مضبوط.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Arabic on the Windows console
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
