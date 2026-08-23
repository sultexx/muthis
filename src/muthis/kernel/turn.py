# src/muthis/kernel/turn.py
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

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Protocol, runtime_checkable

from ..cloud.protocol import ToolCall
from .highlight_gate import (
    HIGHLIGHT_ACK_TEXT_AR, HIGHLIGHT_ALREADY_SHOWN_AR, HighlightGate,
    highlight_result_text,
)
# Bug-3 strip: extracted to history_hygiene.py (≤300-line split); re-exported.
from .history_hygiene import STALE_SCREENSHOT_NOTE_AR, strip_images_from_history
# Pairing + run_code surfaces extracted to tool_result_pairing.py (≤300-line
# split, DEC-21 #3); re-exported so existing importers keep working.
from .tool_result_pairing import (
    NO_SCREENSHOT_TOOL_RESULT_AR, ROUTER_SERVICED_TOOLS, RUN_CODE_TOOL,
    WEB_TOOLS, build_tool_result_message,
)
from ..tts import TTSResult


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

    # Status light (2-B): SYNC fire-and-forget — the controller calls set_state
    # from the keyboard thread, so these never await. clear_status_light ghosts
    # the corner dot before a capture; both are no-op-safe on every impl.
    def set_state(self, state: str) -> None:
        ...

    def clear_status_light(self) -> None:
        ...


def scale_bbox_to_physical(args: dict[str, Any], scale_x: float, scale_y: float) -> PhysicalBBox:
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
MIC_FAILED_AR = "ما قدرت أوصل للمايكروفون، تأكد إنه موصول."
STT_EMPTY_AR = "ما سمعت شي واضح، جرّب مرة ثانية."
# Spoken when the agentic loop hits MAX_AGENTIC_ITERATIONS — a clean stop instead
# of looping forever. User-facing Arabic (the TTS path); never the user text.
#
# IT NAMES THE LIMIT AS WHAT ENDED THE TURN, AND THAT IS THE WHOLE POINT OF THE
# WORDING (DEC-111 ①, DEC-58's class). The first text — «اكتفيت بهذا القدر» —
# was written for a model that would not stop, and Sultan's live case is the
# INVERSE: the model was mid-answer and the LOOP cut it, so the note reported
# the wrong agent. A note that lies about WHO ended the turn reports the wrong
# state achieved, which is exactly what the standing note law exists to prevent.
# The three obligations, carried here: the turn was CUT SHORT by a limit rather
# than completed · the limit is TRANSIENT and the note says what changes · the
# valid NEXT STEP is named. It attributes the ending to neither Mut'his nor the
# user — `tests/test_cap_note_attribution.py` fails if a rewording does.
AGENTIC_CAP_NOTE_AR = (
    "انقطع الجواب قبل ما يكمل، لأن الجولة وصلت للحد المسموح به عندي. "
    "هذا حد مؤقت يبدأ من جديد مع كل سؤال، فاسألني عن الباقي وأكمله لك."
)


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
    # V2 Phase 1 (M1-5): the turn-level taint flag — True once ANY serviced
    # outcome this turn carried untrusted external content (an MCP result).
    # Phase 1 RECORDS it (coarse by design, §3.2); enforcement — flipping
    # high-impact tools to confirm-first — arrives with those tools (Phase 2).
    taint: bool = False


# ─── tool_result builders — Option B "full pairing" keeps history API-valid ──

# The highlight_target tool_result surfaces and the gate-advancing selector live
# in highlight_gate.py (the circuit breaker's home); re-exported here so existing
# importers (orchestrator, tests) keep finding them on turn.
def next_highlight(
    gate: HighlightGate,
    pending: Optional[tuple[PhysicalBBox, str]],
    args: dict[str, Any],
    scale_x: float,
    scale_y: float,
) -> Optional[tuple[PhysicalBBox, str]]:
    """Circuit breaker (draw half): return the (physical bbox, label) to draw for
    the FIRST highlight_target of a turn, or `pending` unchanged for every later
    one — so the overlay is drawn at most ONCE per user turn (no redraw loop).
    `gate.drawn` is set later by build_tool_result_message at pairing time, and
    `pending is not None` guards a second highlight inside the SAME pass."""
    if gate.drawn or pending is not None:
        return pending
    return (scale_bbox_to_physical(args, scale_x, scale_y), args.get("label_ar", ""))


__all__ = [
    "DownscaledImage",
    "MicFn", "SttFn", "TtsFn", "ScreenCaptureFn", "DownscaleFn",
    "Overlay", "PhysicalBBox", "scale_bbox_to_physical",
    "BUDGET_REFUSAL_AR", "REFRESH_FOLLOWUP_TEXT_AR",
    "NO_SCREENSHOT_TOOL_RESULT_AR", "MIC_FAILED_AR", "STT_EMPTY_AR",
    "AGENTIC_CAP_NOTE_AR", "HIGHLIGHT_ACK_TEXT_AR", "HIGHLIGHT_ALREADY_SHOWN_AR",
    "next_highlight",
    "TurnResult", "build_tool_result_message", "RUN_CODE_TOOL", "WEB_TOOLS",
    "ROUTER_SERVICED_TOOLS",
    "STALE_SCREENSHOT_NOTE_AR", "strip_images_from_history",
]
