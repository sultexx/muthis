# src/muthis/turn.py
"""
Turn contracts — the orchestrator's injected-dependency shapes, its
user-facing Arabic surface strings, and the TurnResult model.

Split out of orchestrator.py under the ≤300-line law (split, don't
compress — AGENTS.md). orchestrator.py re-exports everything here, so
existing imports keep working. Depends only on stdlib + protocol/tts types;
importable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from .cloud.protocol import ToolCall
from .tts import TTSResult

# ─── Injected dependency signatures (production injection in parentheses) ────

MicFn = Callable[[], Awaitable[Optional[bytes]]]          # mic.Mic().record
SttFn = Callable[[bytes], Awaitable[str]]                 # stt.STT().transcribe
TtsFn = Callable[[str], Awaitable[Optional[TTSResult]]]   # tts.TTS().speak
ScreenCaptureFn = Callable[[], Awaitable[Optional[bytes]]]
OverlayFn = Callable[[ToolCall], Awaitable[None]]

# ─── User-facing Arabic — the ONLY Arabic surfaces (logs stay English) ───────

BUDGET_REFUSAL_AR = "عذراً، استهلكنا ميزانية اليوم كاملة. نكمل بكرة إن شاء الله."
REFRESH_FOLLOWUP_TEXT_AR = "هذه لقطة الشاشة المحدثة."
NO_SCREENSHOT_TOOL_RESULT_AR = "تعذّر التقاط لقطة شاشة جديدة."
MIC_FAILED_AR = "ما قدرت أوصل للمايكروفون، تأكد إنه موصول."
STT_EMPTY_AR = "ما سمعت شي واضح، جرّب مرة ثانية."


# ─── Turn result ──────────────────────────────────────────────────────────────

@dataclass
class TurnResult:
    """Everything the caller needs to know about one completed turn."""
    spoken_text: str = ""                  # concatenated TextDelta stream
    tool_calls: list[ToolCall] = field(default_factory=list)  # executed only
    input_tokens: int = 0                  # summed across follow-ups
    output_tokens: int = 0
    cost_usd: float = 0.0
    budget_blocked: bool = False
    timed_out: bool = False
    stop_reason: Optional[str] = None      # last provider stop_reason


__all__ = [
    "MicFn", "SttFn", "TtsFn", "ScreenCaptureFn", "OverlayFn",
    "BUDGET_REFUSAL_AR", "REFRESH_FOLLOWUP_TEXT_AR",
    "NO_SCREENSHOT_TOOL_RESULT_AR", "MIC_FAILED_AR", "STT_EMPTY_AR",
    "TurnResult",
]
