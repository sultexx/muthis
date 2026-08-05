# src/muthis/cloud/luna_agent.py
"""
luna_agent.py — the SECOND CloudReasoner. Same three events, different vendor.

`cloud/protocol.py` is UNTOUCHED and that is the headline (DEC-88: measured
against this exact provider and found SUFFICIENT AS WRITTEN). The three events
map 1:1, `run()`'s signature needs nothing, `tool_choice="none"` is API-enforced
here too, and every `TurnComplete` field is populatable. Every difference this
vendor brings lands INSIDE this wrapper or in `pricing.py` — which is what the
CloudReasoner row in AGENTS.md always claimed the seam was for, now measured
rather than believed.

THE FOUR DIFFERENCES THIS WRAPPER ABSORBS, each MEASURED and each with its home:

  ① THE TOOL ENVELOPE (`tool_envelope.py`). `input_schema` → `parameters`, plus
    `type` and `strict`. Translated ONCE at construction, not per turn: the
    catalogue is fixed for the process, and a broken descriptor then fails LOUDLY
    at startup instead of silently mid-turn — which matters more here than
    anywhere, because a half-ported catalogue is ACCEPTED by this API with no
    error at all.

  ②③④ ALL LAND AT THE END OF THE TURN, so they live TOGETHER in
    `luna_accounting.py`: `usage` arrives only at the LAST stream event (where
    `claude_agent.py` reads it at the FIRST), there is no `stop_reason` field so
    the loop's terminator is DERIVED, and the cost model is INCLUSIVE — the
    exact inverse of DEC-60, where the Anthropic formula would double-count
    every cached turn. That file was extracted when this one reached 301/300,
    along the seam the measurements had already drawn.

    ②'s consequence is recorded rather than hidden: a stream cancelled
    mid-flight — barge-in is exactly that — delivers NO usage, so that turn's
    tokens go unrecorded. The orchestrator already handles a missing
    `TurnComplete` (it abandons the voice quietly), and the same cancellation on
    the Anthropic path records a partial figure. Neither is a silent
    over-spend: the ledger is short only by a turn the user themself cut off,
    and the session bound still applies.

CACHING IS AUTOMATIC AND ITS REACH IS WIDER THAN OURS. No breakpoint is placed
here and `cache_control.py` is deliberately NOT applied: DEC-90 measured 81% of
pass-1 input cached with the figure reproducing exactly across two runs, and
proved the cached prefix INCLUDES THE IMAGE (the uncached remainder was 1,395
tokens while the frame alone measures ~4,860 — it cannot fit). On the Anthropic
path it structurally cannot be: breakpoints go on `system` and `tools` only, and
the image rides in the messages. Both vendors price a cache read at 0.1x input,
so **they differ in cache REACH, not in cache PRICE** — and the dominant input
component of a vision turn falls on opposite sides of that line.
No `prompt_cache_key` is sent, because none was sent in the measurement that
produced those numbers and changing the request shape would strand them.

`store=False` ON EVERY CALL IS A PRIVACY CONTROL, NOT A DEFAULT (guarded by
test). Mut'his sends the user's SCREEN. Server-side retention of a Mut'his turn
is retention of the user's desktop, so it is refused at the one site that could
grant it — the same instinct as the DEC-28 logging silence.

Law 11 compliance: this wrapper owns NO locks, NO session lifecycle, NO event
queue, NO retries and NO conversation memory. One `run()` == one provider turn.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, AsyncIterator

import httpx
from openai import AsyncOpenAI

from .claude_agent import LOOK_SYSTEM_PROMPT, detect_image_media_type
from .luna_accounting import TERMINAL_EVENT_TYPES, build_turn_complete
from .luna_messages import to_vendor_input
from .protocol import ResponseEvent, TextDelta, ToolCall, UserInput
from .tool_envelope import to_vendor_catalogue
from .tool_schemas import LOOK_ONLY_TOOLS

logger = logging.getLogger("muthis.cloud.luna")

# Frozen defaults. Override via .env — never edit mid-build. NO fallback list:
# the same rule the Anthropic wrapper carries, for the same reason.
DEFAULT_MODEL = os.getenv("MUTHIS_LUNA_MODEL", "gpt-5.6-luna")
DEFAULT_MAX_TOKENS = int(os.getenv("MUTHIS_LUNA_MAX_TOKENS", "1024"))

# RULED, and deliberately NOT an environment knob (DEC-89 ruling 2). `high` made
# the unstable target stable at 3/3 and 2/2 and costs 1.52x on OUTPUT ONLY while
# input — 84.6% of a turn — is unchanged. `xhigh` was rejected on MEASURED
# ACCURACY, not price: it doubled output for ZERO additional targets. A setting
# that was measured this carefully is not a preference, and exposing it as one
# would invite a value nobody measured.
REASONING_EFFORT = "high"


class LunaAgent:
    """CloudReasoner implementation for the second provider (see protocol.py).

    The constructor mirrors `ClaudeAgent`'s so the composition root can build
    either without branching — that is what "the kernel never knows which vendor
    answered" costs in practice, and it is one parameter list.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        system_prompt: str = LOOK_SYSTEM_PROMPT,
        tools: list[dict[str, Any]] = LOOK_ONLY_TOOLS,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._max_tokens = max_tokens
        self._system_prompt = system_prompt
        # Difference ①, paid ONCE. The pinned descriptors are never mutated —
        # `to_vendor_envelope` builds new dicts and carries the schema by
        # reference (see that module's copy note).
        self._tools = to_vendor_catalogue(tools)
        # ONE shared client per agent — the Clicky lesson, unchanged: a client
        # per request wrecks connection pooling.
        self._http_client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=15.0),
        )
        self._client = AsyncOpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            http_client=self._http_client,
        )
        self._tls_warmed = False

    # ── TLS warmup ────────────────────────────────────────────────────────

    async def warm_up_tls(self) -> None:
        """Pre-establish the TLS connection so the first screenshot-bearing
        request skips the cold handshake. Failures are ignored on purpose. The
        HEAD goes through the SAME httpx client the SDK uses — warming a
        different pool is theater (Clicky's "Socket is not connected")."""
        if self._tls_warmed:
            return
        self._tls_warmed = True
        base_url = str(self._client.base_url)
        try:
            await self._http_client.head(base_url, timeout=10.0)
            logger.info("TLS warmup done for %s", base_url)
        except Exception as exc:  # noqa: BLE001 — warmup must never raise
            logger.debug("TLS warmup skipped (%s)", exc)

    # ── The single provider turn ──────────────────────────────────────────

    async def run(
        self,
        user_input: UserInput,
        screenshot: bytes | None,
        history: list[dict[str, Any]],
        tool_choice: str = "auto",
    ) -> AsyncIterator[ResponseEvent]:
        """One provider turn. Yields TextDelta / ToolCall, then one TurnComplete.

        `tool_choice` is passed through as the plain string this API takes;
        "none" is API-ENFORCED here as well (measured), so the post-highlight
        explain pass keeps its hard loop terminator rather than a prompt nudge.
        """
        media_type, image_b64 = "image/png", ""
        if screenshot:
            media_type = detect_image_media_type(screenshot)
            image_b64 = base64.standard_b64encode(screenshot).decode("ascii")
        items = to_vendor_input(history, screenshot, user_input.text, media_type, image_b64)

        spoken: list[str] = []
        tool_calls: list[ToolCall] = []
        # item_id -> (call_id, name). The arguments arrive on a LATER event that
        # carries only `item_id`, while `call_id` — the key a
        # `function_call_output` must pair on — appears only when the item is
        # ADDED. Losing that mapping orphans the call.
        pending: dict[str, tuple[str, str]] = {}
        final: Any = None

        stream = await self._client.responses.create(
            model=self.model,
            store=False,                       # PRIVACY: the payload is the user's screen
            stream=True,
            max_output_tokens=self._max_tokens,
            instructions=self._system_prompt,
            tools=self._tools,
            tool_choice=tool_choice,
            reasoning={"effort": REASONING_EFFORT},
            input=items,
        )
        async for event in stream:
            etype = getattr(event, "type", "")
            if etype == "response.output_text.delta":
                delta = getattr(event, "delta", "") or ""
                if delta:
                    spoken.append(delta)
                    yield TextDelta(delta)
            elif etype == "response.output_item.added":
                item = getattr(event, "item", None)
                if getattr(item, "type", None) == "function_call":
                    pending[item.id] = (item.call_id, item.name)
            elif etype == "response.function_call_arguments.done":
                # The `.delta` events carrying PARTIAL JSON are ignored on
                # purpose: this event carries the COMPLETE argument string, so
                # "partial JSON never leaves the wrapper" holds by construction
                # rather than by a buffer that could be flushed early.
                call = self._tool_call_from(event, pending)
                if call is not None:
                    tool_calls.append(call)
                    yield call
            elif etype in TERMINAL_EVENT_TYPES:
                final = getattr(event, "response", None)

        yield build_turn_complete(final, "".join(spoken), tool_calls, self.model)

    # ── One completed tool block ──────────────────────────────────────────

    def _tool_call_from(
        self, event: Any, pending: dict[str, tuple[str, str]]
    ) -> ToolCall | None:
        """One completed tool block → one `ToolCall`, or None with a log.

        Malformed JSON DROPS the call rather than raising — `claude_agent.py`'s
        behaviour letter for letter, so the orchestrator sees the same thing
        from either vendor: a turn with one fewer tool call, never an exception
        crossing the seam (Law 11).
        """
        item_id = getattr(event, "item_id", "")
        call_id, name = pending.get(item_id, (item_id, getattr(event, "name", "") or ""))
        try:
            args = json.loads(getattr(event, "arguments", "") or "{}")
        except json.JSONDecodeError:
            logger.error("Malformed tool JSON for %s — dropping", name)
            return None
        return ToolCall(name=name, args=args, tool_use_id=call_id)

    async def aclose(self) -> None:
        """Release the shared HTTP client. The composition root calls this once
        at SHUTDOWN — the wrapper never decides on its own to close (Law 11)."""
        await self._http_client.aclose()


__all__ = ["LunaAgent", "REASONING_EFFORT", "DEFAULT_MODEL", "DEFAULT_MAX_TOKENS"]
