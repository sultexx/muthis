# src/muthis/turn.py
"""
Turn contracts — the orchestrator's injected-dependency shapes, its
user-facing Arabic surface strings, the TurnResult model, and the
request_screen_refresh tool_result builder.

Split out of orchestrator.py under the ≤300-line law (split, don't
compress — AGENTS.md). orchestrator.py re-exports everything here, so
existing imports keep working. Depends only on stdlib + protocol/tts types;
importable in isolation (no SDK, no Pillow).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Protocol, runtime_checkable

from .cloud.protocol import ToolCall
from .tts import TTSResult


# ─── Vision payload contract (the downscaled COPY + coordinate-map factors) ───

@dataclass(frozen=True)
class DownscaledImage:
    """The API-payload COPY of a screenshot plus the factors that map the
    model's returned pixel coordinates back to physical pixels.

    `sent_bytes` is the (possibly downscaled) PNG actually sent to the provider;
    physical pixels stay the single source of truth in screen_capture.py.
    scale_x and scale_y are computed PER-AXIS (sent_height rounds, so for aspect
    ratios that don't divide cleanly they can differ by a hair) — the overlay
    step multiplies x by scale_x and y by scale_y; nothing applies them in this
    phase. None bytes → identity scale (1.0).
    """
    sent_bytes: Optional[bytes]
    sent_width: int
    sent_height: int
    scale_x: float
    scale_y: float


# ─── Injected dependency signatures (production injection in parentheses) ────

MicFn = Callable[[], Awaitable[Optional[bytes]]]          # mic.Mic().record
SttFn = Callable[[bytes], Awaitable[str]]                 # stt.STT().transcribe
TtsFn = Callable[[str], Awaitable[Optional[TTSResult]]]   # tts.TTS().speak
ScreenCaptureFn = Callable[[], Awaitable[Optional[bytes]]]
# vision.downscale.downscale_to_max_width — physical PNG → downscaled COPY.
DownscaleFn = Callable[[Optional[bytes]], Awaitable[DownscaledImage]]


# ─── Overlay seam (the cyan LOOK pointer — DRAW ONLY, never an action tool) ───

# (x1, y1, x2, y2) in PHYSICAL pixels. The orchestrator scales the model's
# sent-image coords up to physical BEFORE handing them over; the overlay draws
# them verbatim and never rescales.
PhysicalBBox = tuple[int, int, int, int]


@runtime_checkable
class Overlay(Protocol):
    """The on-screen cyan rectangle (overlay.sidekick_window.SidekickOverlay in
    production; a fake in tests). LOOK-only: it shows/hides a rectangle plus an
    Arabic caption and does nothing else — no mouse, no clicks, no typing.

    show() receives ALREADY-PHYSICAL coordinates (the orchestrator did the
    sent→physical multiply). hide() clears the rectangle and is called before
    EVERY screen capture, so Claude never sees its own highlight baked into a
    screenshot. Implementations are resilient — they never raise."""

    async def show(self, bbox: PhysicalBBox, label_ar: str) -> None:
        ...

    async def hide(self) -> None:
        ...


def scale_bbox_to_physical(
    args: dict[str, Any], scale_x: float, scale_y: float,
) -> PhysicalBBox:
    """Map a highlight_target's SENT-image bbox to PHYSICAL pixels. Claude
    returns coordinates in the downscaled image it actually saw, so x is scaled
    by scale_x and y by scale_y (per-axis — see DownscaledImage). This is the
    ONLY place the multiply happens; the overlay receives the result physical."""
    return (
        round(args["x1"] * scale_x),
        round(args["y1"] * scale_y),
        round(args["x2"] * scale_x),
        round(args["y2"] * scale_y),
    )

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
    # Dims of the downscaled COPY actually sent, and the physical↔sent scale
    # factors. Recorded for the overlay step (next phase), which multiplies the
    # model's returned coordinates by (scale_x, scale_y) to land on physical
    # pixels. Defaults are the no-screenshot identity (no downscale).
    sent_width: int = 0
    sent_height: int = 0
    scale_x: float = 1.0
    scale_y: float = 1.0


# ─── request_screen_refresh tool_result builder ──────────────────────────────

def build_refresh_tool_result(
    refresh_call: ToolCall,
    screenshot: Optional[bytes],
) -> dict[str, Any]:
    """User message carrying the tool_result that answers a
    request_screen_refresh. Lives here (not in claude_agent.py) so the
    orchestrator stays importable without the SDK stack. `screenshot` is the
    already-downscaled payload COPY; a minimal PNG/JPEG sniff sets media_type
    (NOT imported from claude_agent, which pulls in the SDK stack)."""
    if screenshot:
        media_type = "image/png" if screenshot[:4] == b"\x89PNG" else "image/jpeg"
        inner: list[dict[str, Any]] = [{
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64.standard_b64encode(screenshot).decode("ascii"),
            },
        }]
    else:
        inner = [{"type": "text", "text": NO_SCREENSHOT_TOOL_RESULT_AR}]
    return {
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": refresh_call.tool_use_id,
            "content": inner,
        }],
    }


__all__ = [
    "DownscaledImage",
    "MicFn", "SttFn", "TtsFn", "ScreenCaptureFn", "DownscaleFn",
    "Overlay", "PhysicalBBox", "scale_bbox_to_physical",
    "BUDGET_REFUSAL_AR", "REFRESH_FOLLOWUP_TEXT_AR",
    "NO_SCREENSHOT_TOOL_RESULT_AR", "MIC_FAILED_AR", "STT_EMPTY_AR",
    "TurnResult", "build_refresh_tool_result",
]
