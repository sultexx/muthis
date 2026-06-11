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
from typing import Optional

from .cloud.protocol import ToolCall

logger = logging.getLogger("muthis.stubs")


async def stub_stt() -> str:
    # STUB — replaced in a later phase (stt/elevenlabs_scribe.py).
    logger.info("[stub:stt] returning canned Arabic utterance")
    return "وين زر الحفظ؟"


async def stub_tts(text: str) -> None:
    # STUB — replaced in a later phase (tts/elevenlabs_streamer.py).
    logger.info("[stub:tts] would speak %d chars", len(text))


async def stub_screen_capture() -> Optional[bytes]:
    # STUB — replaced in a later phase (vision/screen_capture.py).
    logger.info("[stub:screen_capture] no screenshot available yet")
    return None


async def stub_overlay(tool_call: ToolCall) -> None:
    # STUB — replaced in a later phase (overlay/rectangle_widget.py).
    logger.info("[stub:overlay] would draw highlight (tool_use_id=%s)",
                tool_call.tool_use_id)


__all__ = ["stub_stt", "stub_tts", "stub_screen_capture", "stub_overlay"]
