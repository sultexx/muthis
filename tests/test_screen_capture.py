"""
test_screen_capture.py — ScreenCapture module tests (fakes only, no real screen).

Deterministic and device-free: mss is faked (real Pillow does the PNG encode).
Covers PNG bytes out of a canned BGRA frame, that the PRIMARY monitor is grabbed
(not the [0] union), DPI awareness pinned at construction, the blocking grab
offloaded to a worker thread, failures returning None (never raising), and that
pixels are never written to disk or logged.

Orchestrator wiring through the injected seam lives in
test_screen_capture_wiring.py; broader pipeline coverage in test_orchestrator*.py.

Run:  set PYTHONPATH=src && python -m pytest tests/test_screen_capture.py -q
"""

from __future__ import annotations

import base64
import builtins
import io
import logging
import sys
import threading

import pytest

from muthis.vision import screen_capture
from muthis.vision.screen_capture import ScreenCapture

# A minimal valid PNG signature + filler — distinctive enough to grep logs for.
CANNED_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


# ──────────────────────────────────────────────────────────────────────────
# Fakes for the mss grab (real Pillow still does the PNG encode)
# ──────────────────────────────────────────────────────────────────────────


class _FakeScreenShot:
    def __init__(self, width, height, bgra):
        self.size = (width, height)
        self.width = width
        self.height = height
        self.bgra = bgra


class _FakeSct:
    """Stands in for an mss.mss() context manager."""

    def __init__(self, monitors, shot):
        self.monitors = monitors
        self._shot = shot
        self.grabbed = []  # monitors actually grabbed

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def grab(self, monitor):
        self.grabbed.append(monitor)
        return self._shot


class _FakeMssModule:
    def __init__(self, sct):
        self._sct = sct

    def mss(self):
        return self._sct


# ──────────────────────────────────────────────────────────────────────────
# DPI awareness
# ──────────────────────────────────────────────────────────────────────────


def test_construction_pins_dpi_awareness(monkeypatch):
    called = []
    monkeypatch.setattr(
        screen_capture, "_ensure_process_dpi_awareness",
        lambda: called.append(True),
    )
    ScreenCapture()
    assert called == [True]


def test_dpi_awareness_is_noop_off_windows(monkeypatch):
    # Simulate a non-Windows host: the guard must return without touching ctypes.
    monkeypatch.setattr(screen_capture, "_IS_WINDOWS", False)
    monkeypatch.setattr(screen_capture, "_dpi_awareness_done", False)
    screen_capture._ensure_process_dpi_awareness()  # must not raise
    assert screen_capture._dpi_awareness_done is True


# ──────────────────────────────────────────────────────────────────────────
# The blocking grab → PNG core (real Pillow, faked mss)
# ──────────────────────────────────────────────────────────────────────────


def test_grab_primary_png_encodes_real_png_from_primary_monitor(monkeypatch):
    pytest.importorskip("PIL")
    monkeypatch.setattr(screen_capture, "_ensure_process_dpi_awareness", lambda: None)
    from PIL import Image

    width, height = 3, 2
    bgra = bytes([255, 0, 0, 255]) * (width * height)  # opaque blue, BGRA order
    shot = _FakeScreenShot(width, height, bgra)
    union = {"left": 0, "top": 0, "width": 99, "height": 99}
    primary = {"left": 0, "top": 0, "width": width, "height": height}
    sct = _FakeSct([union, primary], shot)
    monkeypatch.setitem(sys.modules, "mss", _FakeMssModule(sct))

    png = ScreenCapture()._grab_primary_png()

    assert png is not None and png[:4] == b"\x89PNG"      # a real, valid PNG
    assert sct.grabbed == [primary]                       # primary, NOT the union
    with Image.open(io.BytesIO(png)) as img:
        assert img.size == (width, height)                # full physical frame


def test_grab_primary_png_none_when_no_primary_monitor(monkeypatch):
    monkeypatch.setattr(screen_capture, "_ensure_process_dpi_awareness", lambda: None)
    shot = _FakeScreenShot(1, 1, b"\x00\x00\x00\xff")
    # Only the [0] union present — no physical monitor at index 1.
    sct = _FakeSct([{"left": 0, "top": 0, "width": 10, "height": 10}], shot)
    monkeypatch.setitem(sys.modules, "mss", _FakeMssModule(sct))

    assert ScreenCapture()._grab_primary_png() is None
    assert sct.grabbed == []                              # never grabbed anything


# ──────────────────────────────────────────────────────────────────────────
# capture(): async offload, failure handling, privacy
# ──────────────────────────────────────────────────────────────────────────


def _capture_with_grab(monkeypatch, grab_fn):
    monkeypatch.setattr(screen_capture, "_ensure_process_dpi_awareness", lambda: None)
    sc = ScreenCapture()
    monkeypatch.setattr(sc, "_grab_primary_png", grab_fn)
    return sc


@pytest.mark.asyncio
async def test_capture_offloads_blocking_work_to_thread(monkeypatch):
    main_thread = threading.get_ident()
    seen = {}

    def _grab():
        seen["thread"] = threading.get_ident()
        return CANNED_PNG

    sc = _capture_with_grab(monkeypatch, _grab)
    png = await sc.capture()

    assert png == CANNED_PNG
    assert seen["thread"] != main_thread  # ran off the event-loop thread


@pytest.mark.asyncio
async def test_capture_returns_none_and_never_raises_on_failure(monkeypatch):
    def _boom():
        raise RuntimeError("no display")

    sc = _capture_with_grab(monkeypatch, _boom)
    assert await sc.capture() is None  # swallowed, not raised


@pytest.mark.asyncio
async def test_capture_returns_none_on_empty_bytes(monkeypatch):
    sc = _capture_with_grab(monkeypatch, lambda: None)
    assert await sc.capture() is None


@pytest.mark.asyncio
async def test_capture_never_writes_pixels_to_disk(monkeypatch):
    sc = _capture_with_grab(monkeypatch, lambda: CANNED_PNG)

    opened_for_write = []
    real_open = builtins.open

    def _spy_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            opened_for_write.append((file, mode))
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _spy_open)
    png = await sc.capture()

    assert png == CANNED_PNG
    assert opened_for_write == []  # nothing persisted to disk


@pytest.mark.asyncio
async def test_capture_logs_dimensions_not_pixels(monkeypatch, caplog):
    distinctive = b"\x89PNG\r\n\x1a\n" + b"\xab\xcd" * 32
    sc = _capture_with_grab(monkeypatch, lambda: distinctive)

    with caplog.at_level(logging.DEBUG, logger="muthis.vision.screen_capture"):
        png = await sc.capture()

    assert png == distinctive
    encoded = base64.standard_b64encode(distinctive).decode("ascii")
    assert encoded not in caplog.text             # no base64 pixels in logs
    assert distinctive.hex() not in caplog.text   # no raw pixels in logs
    assert "captured primary monitor" in caplog.text  # size/timing IS allowed


# ──────────────────────────────────────────────────────────────────────────
# primary_monitor_size(): physical geometry probe (no pixels grabbed)
# ──────────────────────────────────────────────────────────────────────────


def test_primary_monitor_size_returns_physical_dims(monkeypatch):
    monkeypatch.setattr(screen_capture, "_ensure_process_dpi_awareness", lambda: None)
    union = {"left": 0, "top": 0, "width": 99, "height": 99}
    primary = {"left": 0, "top": 0, "width": 1920, "height": 1080}
    sct = _FakeSct([union, primary], _FakeScreenShot(1, 1, b"\x00\x00\x00\xff"))
    monkeypatch.setitem(sys.modules, "mss", _FakeMssModule(sct))

    assert screen_capture.primary_monitor_size() == (1920, 1080)
    assert sct.grabbed == []  # geometry only — NO pixels grabbed


def test_primary_monitor_size_none_when_no_primary(monkeypatch):
    monkeypatch.setattr(screen_capture, "_ensure_process_dpi_awareness", lambda: None)
    # Only the [0] union present — no physical monitor at index 1.
    sct = _FakeSct([{"left": 0, "top": 0, "width": 10, "height": 10}],
                   _FakeScreenShot(1, 1, b"\x00\x00\x00\xff"))
    monkeypatch.setitem(sys.modules, "mss", _FakeMssModule(sct))

    assert screen_capture.primary_monitor_size() is None
