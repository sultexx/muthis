# scripts/smoke_vision.py
"""
Manual smoke test — capture YOUR real primary monitor ONCE and save it so you
can eyeball it. NEVER run in CI (it needs a real desktop session).

This is the ONLY place in the project that writes screenshot pixels to disk —
the app itself never does (privacy). It saves to a temp file you open yourself,
and prints the path + true pixel dimensions + PNG size, so you can confirm the
capture is FULL physical resolution (not blurry/downscaled) on your scaled
Windows 11 display BEFORE the overlay phase trusts that capture space.

Run:  .venv\\Scripts\\python.exe scripts\\smoke_vision.py
"""

import asyncio
import io
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from muthis.vision.screen_capture import ScreenCapture  # noqa: E402


async def main() -> None:
    capture = ScreenCapture()
    png_bytes = await capture.capture()
    if not png_bytes:
        print("فشل الالتقاط — تأكد إنك على جلسة سطح مكتب فعلية (مو RDP/headless).")
        return

    # Decode the PNG header to report true pixel dimensions back to you.
    width = height = 0
    try:
        from PIL import Image
        with Image.open(io.BytesIO(png_bytes)) as img:
            width, height = img.size
    except Exception:
        pass

    out_path = pathlib.Path(tempfile.gettempdir()) / "muthis_vision_smoke.png"
    out_path.write_bytes(png_bytes)

    print("✅ تم التقاط الشاشة الأساسية بنجاح.")
    print(f"الأبعاد (بكسل فيزيائي): {width} x {height}")
    print(f"حجم PNG: {len(png_bytes) // 1024} KB")
    print(f"الملف المؤقت: {out_path}")
    print("افتح الملف وتأكد إن الدقة كاملة وواضحة (مو مموّهة) على شاشتك المكبّرة.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic on the Windows console
    except Exception:
        pass
    asyncio.run(main())
