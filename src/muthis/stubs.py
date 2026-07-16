# src/muthis/stubs.py
"""
Stubs — canned default dependencies for the stub-first build (Law §3.5).

Each callable here is a placeholder the Orchestrator injects by default.
They log in English, return canned data, touch NO hardware and NO network.
As each real component lands (stt/, tts/, vision/, overlay/), its stub is
deleted from this file; when the file is empty, archive it.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .file_reader import FILE_READ_UNAVAILABLE_AR
from .turn import DownscaledImage, PhysicalBBox

logger = logging.getLogger("muthis.stubs")


async def stub_mic() -> Optional[bytes]:
    # STUB default — production injects muthis.mic.Mic().record. Returning
    # None keeps CI device-free; handle_activation speaks the Arabic
    # failure line and aborts the turn early.
    logger.info("[stub:mic] no microphone in stub mode")
    return None


async def stub_stt(audio_wav: bytes) -> str:
    # Default seam only — production injects muthis.stt.STT().transcribe
    # (same SttFn shape: WAV bytes in, Arabic text out).
    logger.info(
        "[stub:stt] returning canned Arabic utterance (%d audio bytes)",
        len(audio_wav),
    )
    return "وين زر الحفظ؟"


async def stub_tts(text: str) -> None:
    # Default seam only — production injects the REAL muthis.tts.TTS().speak
    # (same TtsFn shape); returning None keeps Optional[TTSResult] honest.
    logger.info("[stub:tts] would speak %d chars", len(text))


async def stub_screen_capture() -> Optional[bytes]:
    # STUB — replaced in a later phase (vision/screen_capture.py).
    logger.info("[stub:screen_capture] no screenshot available yet")
    return None


async def stub_read_file(args: dict[str, Any]) -> str:
    # STUB default (v7 Phase 4) — production injects the REAL
    # muthis.file_reader.FileReader().read (same ReadFileFn shape). Returns
    # the Arabic unavailable note so a read_local_file call in stub mode is
    # paired honestly and the turn continues. Never logs file content.
    logger.info("[stub:read_file] file reading unavailable in stub mode (%d args)",
                len(args or {}))
    return FILE_READ_UNAVAILABLE_AR


async def stub_downscale(screenshot: Optional[bytes]) -> DownscaledImage:
    # STUB default — production injects the REAL
    # vision.downscale.downscale_to_max_width at the composition root. This
    # passthrough sends the captured bytes UNCHANGED with identity scale, so
    # tests and CI never decode a real image; sent dims are unknown (0) here.
    logger.info("[stub:downscale] passthrough (%d bytes), identity scale",
                len(screenshot) if screenshot else 0)
    return DownscaledImage(screenshot, 0, 0, 1.0, 1.0)


class StubOverlay:
    """STUB default for the overlay seam — replaced by
    overlay.sidekick_window.SidekickOverlay at the composition root. Implements
    the Overlay protocol (show/hide + the 2-B status light) with NO window and NO
    hardware; logs dimensions/timing only, never pixels. hide() and
    clear_status_light() are harmless no-ops so the orchestrator's
    hide-before-capture ordering holds even in stub mode."""

    async def show(self, bbox: PhysicalBBox, label_ar: str) -> None:
        logger.info("[stub:overlay] would draw rectangle %s (label %d chars)",
                    bbox, len(label_ar))

    async def hide(self) -> None:
        logger.info("[stub:overlay] would hide rectangle")

    def set_state(self, state: str) -> None:
        logger.info("[stub:overlay] would set status state %r", state)

    def clear_status_light(self) -> None:
        logger.info("[stub:overlay] would clear the status light (ghosting)")


# Module-level default instance: the orchestrator imports this name as the
# overlay seam default; the composition root swaps in the real SidekickOverlay.
stub_overlay = StubOverlay()


__all__ = ["stub_mic", "stub_stt", "stub_tts", "stub_screen_capture",
           "stub_downscale", "stub_overlay", "stub_read_file", "StubOverlay"]
