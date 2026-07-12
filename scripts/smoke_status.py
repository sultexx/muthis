# scripts/smoke_status.py
"""
Manual smoke test — the status indicator (batch 2-A). NEVER run in CI.

Pure overlay check: NO Claude / mic / TTS / wiring. Cycles the four states —
listening → thinking → speaking → idle — pausing on each so you can SEE the
corner status dot and tune the neon colors / pulse by eye via .env. (The window
comes up lazily on the first set_state; the pointer halo that once accompanied
the dot was removed because it cluttered content over code.)

Confirm visually:
  * each state recolors the corner dot: listening=cyan, thinking=amber,
    speaking=green,
  * idle HIDES the dot, leaving a clean screen,
  * the dot lives in MUTHIS_STATUS_CORNER (default bottom-right) and gently
    PULSES (breathes) — never a hard blink, never a frozen disc.

Tune by eye WITHOUT touching code — set any of these before running, e.g.:
    set MUTHIS_STATUS_THINKING=#FF2BD6 && set MUTHIS_STATUS_CORNER=top-right && ^
    .venv\\Scripts\\python.exe scripts\\smoke_status.py
  (also MUTHIS_STATUS_LISTENING / _SPEAKING, plus the batch-1 MUTHIS_GLOW* /
   MUTHIS_CORE_WIDTH which the dot reuses.)

LOOK-ONLY: drawn graphics only; the mouse is never moved, warped, or clicked.

    .venv\\Scripts\\python.exe scripts\\smoke_status.py

Privacy: draws only; never captures, logs, or persists any screen pixels.
"""

import asyncio
import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from muthis.overlay import SidekickOverlay  # noqa: E402

HOLD_SECONDS = 3.0

STATES = ("listening", "thinking", "speaking", "idle")


async def main() -> None:
    overlay = SidekickOverlay()

    for state in STATES:
        print(f"الحالة: {state} — راقب النقطة الركنية ({HOLD_SECONDS:.0f} ثوانٍ)...")
        overlay.set_state(state)         # SYNC fire-and-forget; brings the window up
        await asyncio.sleep(HOLD_SECONDS)

    print("إغلاق...")
    overlay.close()
    print(
        "تم. لو تدرّجت النقطة الركنية عبر cyan → amber → green ونبضت بلطف ثم "
        "اختفت عند idle — فكل شيء مضبوط."
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
