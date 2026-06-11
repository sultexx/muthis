# src/muthis/screen_scanner.py
"""
ScreenScanner — periodic UIA text extraction → SCREEN_SCAN_TICK events.

The screen-reading producer of Mut'his v4.1: every few seconds it harvests
the foreground window's visible text and hands it to the orchestrator as an
event, giving the LOOK pipeline fresh on-screen context without OCR.

Why UIAutomation, not OCR:
  - OCR (Tesseract, PaddleOCR) would burn 200-800 ms per scan and consume
    VRAM that Mut'his must leave entirely free for the user's own
    Blender/YOLO workloads.
  - UIA reads text DIRECTLY from each window's accessibility tree — the
    same source screen readers use. Latency target: <30 ms even on busy
    screens. Zero VRAM.
  - Trade-off: UIA misses text rendered as bitmaps (some custom UIs,
    PDF viewers, video). If a target app proves opaque, a tiny CPU OCR
    fallback can be layered in a later iteration — out of scope for now.

Design rules:
  - CPU only. No torch, no CUDA, zero VRAM.
  - Fully async producer. start() returns immediately; the loop runs as a
    background task and is cancelled cleanly by stop().
  - Every blocking UIA call goes through asyncio.to_thread — the
    orchestrator event loop is NEVER frozen. COM is initialized per worker
    thread (see _scan_once_blocking for the WHY).
  - Privacy:
      • Extracted text is held only as a Python str inside the event payload.
      • NEVER written to disk, NEVER printed in logs.
      • Logs contain only counts and timing — no content.
      • Sensitive windows (password managers, credential dialogs, OS lock
        screens) are blocked via WINDOW_TITLE_DENYLIST.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional, Set

logger = logging.getLogger("screen_scanner")


# ─── Platform guard ───────────────────────────────────────────────────────────

_IS_WINDOWS = sys.platform == "win32"


# ─── Tunables ─────────────────────────────────────────────────────────────────

# Scan cadence. 4 s = roughly one sweep per natural user pause.
# Too fast → CPU pressure during voice handling; too slow → stale context.
DEFAULT_SCAN_INTERVAL_S = 4.0

# Soft budget per scan. We don't kill a slow scan mid-flight (UIA traversal
# isn't safely interruptible), but we log a warning so regressions surface.
SLOW_SCAN_WARN_MS = 200.0

# Maximum characters per scan we forward downstream. A pathological window
# (logs viewer, huge document) shouldn't drown the consumer or memory.
MAX_FORWARDED_CHARS = 20_000

# Concatenation glue between text fragments — newline keeps regex word
# boundaries clean across UI elements.
TEXT_JOIN = "\n"

# Window titles that must never be scanned. Substring match, lowercase.
# Banking session credentials, password managers, OS lock screens, etc.
WINDOW_TITLE_DENYLIST: Set[str] = {
    "password",
    "kdbx",
    "keepass",
    "1password",
    "bitwarden",
    "lastpass",
    "lockapp",
    "credential",
    "كلمة المرور",
    "كلمة السر",
}


# ─── Event payload ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ScreenScanPayload:
    """
    Carried as event.data for SCREEN_SCAN_TICK.
    `text` lives only for the duration of one consumer callback.
    """
    text:               str       # concatenated visible text from foreground
    window_title:       str       # for context only; NOT logged
    captured_at_ms:     float     # time.perf_counter() snapshot
    elapsed_ms:         float     # scan duration


# ─── ScreenScanner ────────────────────────────────────────────────────────────

class ScreenScanner:
    """
    Periodic UIA scanner. One instance per orchestrator.

    Usage (from orchestrator.startup):
        self.screen_scanner = ScreenScanner(self._on_screen_tick)
        await self.screen_scanner.start()

    Where _on_screen_tick(payload) pushes an event:
        await self.push_event(EventKind.SCREEN_SCAN_TICK, data=payload)
    """

    def __init__(
        self,
        on_tick: Callable[[ScreenScanPayload], Awaitable[None]],
        *,
        interval_s: float = DEFAULT_SCAN_INTERVAL_S,
    ) -> None:
        if not callable(on_tick):
            raise TypeError("on_tick must be an async callable.")
        self._on_tick = on_tick
        self._interval_s = max(0.5, float(interval_s))

        self._task: Optional[asyncio.Task] = None
        self._stop_evt: Optional[asyncio.Event] = None

        # Lazily-cached UIA module. Import is expensive (~200ms on first
        # call) — we pay it once when start() runs, not at module load.
        self._uia_module: Optional[object] = None

    # ───────────────────────── Lifecycle ─────────────────────────

    async def start(self) -> None:
        """Spin up the background scan loop. Idempotent."""
        if self._task is not None and not self._task.done():
            return
        self._stop_evt = asyncio.Event()
        # Warm up UIA in a thread so the first scan isn't a 200ms hiccup.
        if _IS_WINDOWS:
            await asyncio.to_thread(self._ensure_uia_loaded)
        self._task = asyncio.create_task(self._run_loop(), name="screen_scanner")
        logger.info(
            "[scanner] started — interval=%.2fs, platform=%s",
            self._interval_s, sys.platform,
        )

    async def stop(self) -> None:
        """Signal cancellation and await loop exit. Idempotent."""
        if self._task is None:
            return
        if self._stop_evt is not None:
            self._stop_evt.set()
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None
        logger.info("[scanner] stopped")

    # ───────────────────────── Main loop ─────────────────────────

    async def _run_loop(self) -> None:
        try:
            while not (self._stop_evt and self._stop_evt.is_set()):
                cycle_start = time.perf_counter()

                try:
                    payload = await asyncio.to_thread(self._scan_once_blocking)
                except Exception:
                    logger.exception("[scanner] scan failed")
                    payload = None

                if payload is not None:
                    try:
                        await self._on_tick(payload)
                    except Exception:
                        logger.exception("[scanner] on_tick callback raised")

                # Sleep the remainder of the interval — drift-free pacing.
                elapsed = time.perf_counter() - cycle_start
                remaining = max(0.0, self._interval_s - elapsed)
                try:
                    await asyncio.wait_for(self._stop_evt.wait(), timeout=remaining)
                    # If wait_for returns normally, stop_evt fired → exit.
                    break
                except asyncio.TimeoutError:
                    continue  # normal next-tick path
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[scanner] loop crashed")

    # ───────────────────── Blocking scan core ─────────────────────

    def _scan_once_blocking(self) -> Optional[ScreenScanPayload]:
        """Single UIA traversal. ALWAYS invoked via asyncio.to_thread."""
        if not _IS_WINDOWS:
            # On Linux/Mac CI: produce empty ticks so the loop is testable
            # but consumers see nothing to act on.
            return ScreenScanPayload(
                text="", window_title="", captured_at_ms=time.perf_counter() * 1000,
                elapsed_ms=0.0,
            )

        t0 = time.perf_counter()
        try:
            uia = self._ensure_uia_loaded()
        except Exception as e:
            logger.warning("[scanner] UIA load failed: %s", e)
            return None

        # COM must be initialized PER THREAD before any UIA call.
        # asyncio.to_thread runs this function on an arbitrary worker-pool
        # thread that has NOT called CoInitialize — calling UIA there raises
        # [WinError -2147221008] "CoInitialize has not been called" (the
        # documented crash in the previous project's error log). The
        # uiautomation library's own thread-init mechanism,
        # UIAutomationInitializerInThread, calls CoInitializeEx on entry and
        # CoUninitialize on exit, so every scan is self-contained no matter
        # which pool thread executes it.
        try:
            with uia.UIAutomationInitializerInThread():
                window_title, fragments = self._extract_foreground_text(uia)
        except Exception as e:
            logger.debug("[scanner] extraction error: %s", e)
            return None

        # Denylist enforcement — never forward text from sensitive windows.
        title_lc = (window_title or "").lower()
        if any(blocked in title_lc for blocked in WINDOW_TITLE_DENYLIST):
            elapsed = (time.perf_counter() - t0) * 1000
            logger.debug("[scanner] skipped denylisted window (%.1fms)", elapsed)
            return ScreenScanPayload(
                text="", window_title="", captured_at_ms=t0 * 1000,
                elapsed_ms=elapsed,
            )

        joined = TEXT_JOIN.join(fragments)
        if len(joined) > MAX_FORWARDED_CHARS:
            joined = joined[:MAX_FORWARDED_CHARS]

        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > SLOW_SCAN_WARN_MS:
            # Log only the duration, not the content (privacy rule).
            logger.warning(
                "[scanner] slow scan: %.1fms (fragments=%d)",
                elapsed_ms, len(fragments),
            )
        else:
            logger.debug(
                "[scanner] tick: %.1fms, fragments=%d, chars=%d",
                elapsed_ms, len(fragments), len(joined),
            )

        return ScreenScanPayload(
            text=joined,
            window_title=window_title,
            captured_at_ms=t0 * 1000,
            elapsed_ms=elapsed_ms,
        )

    # ─────────────────────── UIA plumbing ───────────────────────

    def _ensure_uia_loaded(self):
        """
        Import the `uiautomation` package lazily and cache it.
        Initialization on Windows pulls in COM, which is slow (~200ms)
        but only on first call — subsequent calls are cheap.
        """
        if self._uia_module is not None:
            return self._uia_module
        import uiautomation as auto  # noqa: F401
        # Silence the library's chatty default logger — it would otherwise
        # write per-call diagnostics that occasionally include element text.
        try:
            auto.SetGlobalSearchTimeout(1)  # tight bound — we want <30ms
        except Exception:
            pass
        self._uia_module = auto
        return auto

    def _extract_foreground_text(
        self,
        uia,
    ) -> tuple[str, List[str]]:
        """
        Walk the foreground window's UIA tree and harvest visible text.

        Strategy — speed-first:
          1) Get foreground window via GetForegroundControl() (single API call).
          2) BFS the control tree with a hard depth/breadth limit so a
             pathological app can't make us traverse 10k nodes.
          3) Pull text from cheap properties only (Name, Value via pattern
             when available). Skip expensive patterns (Text, Legacy).
        """
        window = uia.GetForegroundControl()
        if window is None:
            return "", []
        title = ""
        try:
            title = window.Name or ""
        except Exception:
            title = ""

        fragments: List[str] = []
        seen_text: Set[str] = set()

        # BFS with safety caps
        MAX_NODES = 800
        MAX_DEPTH = 12
        queue: List[tuple] = [(window, 0)]
        visited = 0

        while queue and visited < MAX_NODES:
            node, depth = queue.pop(0)
            visited += 1

            # Harvest text from this node
            self._harvest_node_text(node, fragments, seen_text)

            if depth >= MAX_DEPTH:
                continue

            # Enqueue children — defensive against UIA errors mid-traversal
            try:
                children = node.GetChildren() or []
            except Exception:
                children = []
            for child in children:
                queue.append((child, depth + 1))

        return title, fragments

    @staticmethod
    def _harvest_node_text(
        node,
        fragments: List[str],
        seen: Set[str],
    ) -> None:
        """Pull cheap text properties from a single UIA node."""
        # 1) Name — present on most controls, cheapest to read.
        try:
            name = node.Name
        except Exception:
            name = None
        if name:
            stripped = name.strip()
            if stripped and stripped not in seen and len(stripped) < 2000:
                seen.add(stripped)
                fragments.append(stripped)

        # 2) Value via ValuePattern — covers input fields, combos, etc.
        try:
            value_pattern = node.GetValuePattern()
        except Exception:
            value_pattern = None
        if value_pattern is not None:
            try:
                value = value_pattern.Value
            except Exception:
                value = None
            if value:
                stripped = value.strip()
                if stripped and stripped not in seen and len(stripped) < 2000:
                    seen.add(stripped)
                    fragments.append(stripped)


__all__ = [
    "ScreenScanner",
    "ScreenScanPayload",
    "DEFAULT_SCAN_INTERVAL_S",
    "WINDOW_TITLE_DENYLIST",
]
