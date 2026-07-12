"""
protocol.py — The CloudReasoner contract (ARCHITECTURE_v4.1 §3.7 / §9.3).

Law of the Routed Wrapper: every cloud provider (Claude, Gemini, ...) hides
behind this exact interface. The orchestrator consumes the same event stream
regardless of which provider answered. Swapping providers is a router-config
change, never a downstream rewrite.

This module has ZERO third-party dependencies on purpose — it must be
importable in isolation (v4.1 §17.4) and by every test stub.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol, runtime_checkable


# ──────────────────────────────────────────────────────────────────────────
# Response events — the only three things a CloudReasoner may yield
# ──────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TextDelta:
    """A chunk of streamed assistant text. The orchestrator buffers these and
    speaks the whole message once at end-of-turn (buffer-then-speak)."""
    text: str


@dataclass(frozen=True)
class ToolCall:
    """A complete, parsed tool invocation.

    The agent yields this ONLY after the provider finished streaming the
    tool's input JSON (i.e. after content_block_stop). Partial JSON never
    leaves this layer.
    """
    name: str
    args: dict[str, Any]
    tool_use_id: str


@dataclass(frozen=True)
class TurnComplete:
    """End-of-turn accounting. budget.py consumes cost_usd (Law 10:
    the budget is sovereign — but budget.py owns it, not this wrapper).

    assistant_content carries the raw assistant content blocks so the
    orchestrator can build follow-up turns (e.g. answering a
    request_screen_refresh with a tool_result + fresh screenshot)
    without this wrapper owning any conversation state.
    """
    input_tokens: int
    output_tokens: int
    cost_usd: float
    stop_reason: str | None
    model: str
    assistant_content: list[dict[str, Any]] = field(default_factory=list)


ResponseEvent = TextDelta | ToolCall | TurnComplete


# ──────────────────────────────────────────────────────────────────────────
# User input
# ──────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class UserInput:
    """One user utterance after STT. The quality path is text-only by design
    (v4.1 §5.3-4: STT only on the quality path; Claude has no native audio).
    """
    text: str


# ──────────────────────────────────────────────────────────────────────────
# The provider contract
# ──────────────────────────────────────────────────────────────────────────

@runtime_checkable
class CloudReasoner(Protocol):
    """Implemented by claude_agent.ClaudeAgent and (later) gemini_agent.

    Contract (v4.1 §9.3):
      - run() is ONE provider turn. No retries, no loops, no session state.
      - The wrapper owns no locks, no lifecycles, no event queues (Law 11).
        Session bounds (90 s), budget gating, and cancellation live in the
        orchestrator.
      - Yields TextDelta as text streams, ToolCall per completed tool block,
        and exactly one TurnComplete last.
      - tool_choice ("auto" default) lets the caller force "none" on a pass that
        must NOT call a tool (the orchestrator's post-highlight explain pass), so
        the model emits text and stop_reason becomes end_turn — an API-enforced
        loop terminator, not a prompt nudge.
    """

    def run(
        self,
        user_input: UserInput,
        screenshot: bytes | None,
        history: list[dict[str, Any]],
        tool_choice: str = "auto",
    ) -> AsyncIterator[ResponseEvent]:
        ...
