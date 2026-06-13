# src/muthis/vision/screen_capture.py
"""
screen_capture.py — primary-monitor screenshot → PNG bytes for the LOOK pipeline.

Single responsibility: capture the primary monitor as TRUE physical pixels and
return PNG bytes ready for ClaudeAgent (which sniffs PNG/JPEG media type). This
is the real component behind the orchestrator's injected `screen_capture` seam
(ScreenCaptureFn = () -> Awaitable[Optional[bytes]]); production injects
`ScreenCapture().capture` at the composition root, exactly like Mic().record /
STT().transcribe / TTS().speak. The orchestrator's stub default stays in place
so tests and CI never touch a real display.

DPI awareness (the WHY): on Windows 11 with display scaling (125%/150%), a
DPI-unaware process is handed virtualized *logical* pixels — a blurry, downscaled
bitmap whose dimensions do NOT match the real framebuffer. We declare
PER_MONITOR_AWARE_V2 (with fallbacks) once per process before any grab so mss
reads the true physical framebuffer. This is process-global on purpose: the
later Tk overlay inherits it, so its draw space matches this capture space.

Async (the WHY): mss grabs via blocking GDI BitBlt and Pillow's PNG encode is
CPU-bound, so both run inside asyncio.to_thread — the single event loop is never
frozen (Law §11.5). mss is NOT thread-safe (its device context is bound to the
creating thread), so a fresh mss.mss() is built inside the worker on EVERY
capture; asyncio.to_thread may run us on any pool thread.

Privacy (Law: never log/persist screenshots): pixels live only as in-memory
bytes for the turn. Nothing is ever written to disk, and only dimensions /
timing / encoded size (English) are ever logged. capture() never raises — it
returns None on failure, matching the mic/stt/tts discipline; the orchestrator
already degrades gracefully (speaks an Arabic line / drops the image block) when
the screenshot is None.

Coordinate note (for the overlay phase, NOT handled here): claude-sonnet-4-6
downscales large images server-side (~1568 px long edge / ~1.15 MP), so the
pixel coordinates it returns are in that downscaled space, not physical-screen
space. We capture full physical pixels here as the single source of truth; the
overlay phase owns reconciling Claude's coordinates back to physical pixels.
"""

from __future__ import annotations

import asyncio
import io
import logging
import sys
import time
from typing import Optional

logger = logging.getLogger("muthis.vision.screen_capture")

_IS_WINDOWS = sys.platform == "win32"

# mss monitor indexing: [0] is the virtual union of all monitors; [1] is the
# first physical monitor (the primary). We capture the primary per LOOK scope.
PRIMARY_MONITOR_INDEX = 1

# Process DPI awareness is pinned at most once (the SetProcess* APIs reject or
# no-op a second change). Module-level guard keeps it idempotent.
_dpi_awareness_done = False


def _ensure_process_dpi_awareness() -> None:
    """Pin the process to PER_MONITOR_AWARE_V2 so captures read true physical
    pixels on scaled Windows 11 displays. Idempotent, best-effort, never raises:
    a process whose awareness is already fixed (manifest, prior call, or a host
    like pytest) simply keeps its value. No-op off Windows.
    """
    global _dpi_awareness_done
    if _dpi_awareness_done or not _IS_WINDOWS:
        _dpi_awareness_done = True
        return
    _dpi_awareness_done = True  # set first: exactly one attempt, even if it raises
    import ctypes

    # Newest → oldest. PER_MONITOR_AWARE_V2 = (HANDLE)-4, no shcore dependency.
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        logger.info("[vision] process DPI awareness: per-monitor-v2")
        return
    except Exception as exc:  # noqa: BLE001 — fall through to older APIs
        logger.debug("[vision] SetProcessDpiAwarenessContext unavailable (%s)", exc)
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2 (Windows 8.1+ shcore).
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        logger.info("[vision] process DPI awareness: per-monitor (shcore)")
        return
    except Exception as exc:  # noqa: BLE001
        logger.debug("[vision] SetProcessDpiAwareness unavailable (%s)", exc)
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # system-DPI-aware (Vista+)
        logger.info("[vision] process DPI awareness: system")
    except Exception as exc:  # noqa: BLE001 — capture still runs, may be scaled
        logger.warning("[vision] could not set DPI awareness (%s)", exc)


class ScreenCapture:
    """Real screen_capture dependency: primary monitor → PNG bytes.

    Injected as `ScreenCapture().capture` (matches ScreenCaptureFn). Holds no
    long-lived mss handle (mss is thread-affine and we run on the to_thread
    pool) — state is just the monitor index. One instance per process suffices.
    """

    def __init__(self, monitor_index: int = PRIMARY_MONITOR_INDEX) -> None:
        self._monitor_index = monitor_index
        # Pin DPI awareness at construction (composition-root / startup time) so
        # the very first turn's capture already reads physical pixels.
        _ensure_process_dpi_awareness()

    async def capture(self) -> Optional[bytes]:
        """Capture the primary monitor as PNG bytes. Never raises; returns None
        on failure (logged in English). Blocking grab+encode run via to_thread."""
        start = time.perf_counter()
        try:
            png_bytes = await asyncio.to_thread(self._grab_primary_png)
        except Exception as exc:  # noqa: BLE001 — capture must never break a turn
            logger.warning("[vision] screen capture failed (%s)", type(exc).__name__)
            return None
        if not png_bytes:
            logger.warning("[vision] screen capture produced no bytes")
            return None
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "[vision] captured primary monitor → %d KB PNG in %.0f ms",
            len(png_bytes) // 1024, elapsed_ms,
        )
        return png_bytes

    def _grab_primary_png(self) -> Optional[bytes]:
        """Blocking core — ALWAYS via asyncio.to_thread. Lazy-imports mss+Pillow
        (keeps this module importable in isolation) and builds a fresh mss.mss()
        on THIS worker thread (mss device contexts are not shareable across
        threads). Returns PNG bytes, or None if no primary monitor is present.
        """
        import mss  # lazy: importable in isolation; only the real path needs it
        from PIL import Image

        with mss.mss() as sct:
            monitors = sct.monitors
            if self._monitor_index >= len(monitors):
                logger.warning(
                    "[vision] no monitor at index %d (have %d physical)",
                    self._monitor_index, max(0, len(monitors) - 1),
                )
                return None
            raw = sct.grab(monitors[self._monitor_index])

        # mss yields BGRA; "BGRX" tells Pillow to read BGR and ignore the 4th
        # byte. Dimensions are TRUE physical pixels thanks to DPI awareness.
        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")  # in-memory only — never touches disk
        logger.info("[vision] frame %dx%d px", raw.width, raw.height)
        return buffer.getvalue()


__all__ = ["ScreenCapture"]
