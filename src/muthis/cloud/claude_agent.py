"""
claude_agent.py — Anthropic wrapper for the quality path (ARCHITECTURE_v4.1).

LOOK-ONLY BUILD: the only tools exposed are highlight_target (point, never
click), draw_shapes (draw geometric overlay graphics, never act), and
request_screen_refresh — schemas live in tool_schemas.py (this file is at
the ≤300-line ceiling) and are re-exported here. type_text / press_hotkey /
real_click DO NOT EXIST yet — they arrive with Trust Modes in a later phase,
behind trust/confirm_gate.py. Do not add them here.

Clicky-inspired engineering carried into this module:
  * TLS warmup   — a throwaway HEAD request fired at init through the SAME
                   httpx client the SDK uses, so the first real call (which
                   carries a screenshot payload) reuses a warm TLS session
                   instead of paying a cold handshake.
  * Shared client — ONE long-lived httpx.AsyncClient per agent. Creating a
                   client per request wrecks connection pooling (Clicky hit
                   the same bug with per-session URLSessions).
  * Media sniffing — detect PNG vs JPEG from the first bytes; the API
                   rejects mismatched media_type declarations.

Law 11 compliance: this wrapper owns NO locks, NO session lifecycle, NO
event queue. One call to run() == one provider turn. The orchestrator owns
the 90 s session bound, budget gating, and cancellation.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, AsyncIterator

import httpx
from anthropic import AsyncAnthropic

from .protocol import ResponseEvent, TextDelta, ToolCall, TurnComplete, UserInput
# Re-export: existing callers import LOOK_ONLY_TOOLS from THIS module.
from .tool_schemas import LOOK_ONLY_TOOLS

logger = logging.getLogger("muthis.cloud.claude")

# ──────────────────────────────────────────────────────────────────────────
# Frozen defaults (v4.1 §4.2). Override via .env — never edit here mid-build.
# ──────────────────────────────────────────────────────────────────────────

DEFAULT_MODEL = os.getenv("MUTHIS_CLAUDE_MODEL", "claude-sonnet-4-6")
DEFAULT_BASE_URL = os.getenv("MUTHIS_ANTHROPIC_BASE_URL", "https://api.anthropic.com")
DEFAULT_MAX_TOKENS = int(os.getenv("MUTHIS_CLAUDE_MAX_TOKENS", "1024"))

# USD per 1M tokens (input, output). v4.1 §4.2 pricing reality check.
# budget.py is the sovereign consumer of these numbers; this table only
# annotates TurnComplete. Re-pin on every model rev (§4.3).
_PRICE_TABLE_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (5.00, 25.00),
}

# Arabic-first persona (v4.1 §17.5). User-facing Arabic; logs stay English.
LOOK_SYSTEM_PROMPT = (
    "أنت «مطحس»، مساعد مكتبي صوتي يعمل على Windows 11 لمستخدم مهندس حاسب.\n"
    "وضعك الحالي هو LOOK فقط: تستطيع أن تتكلم وأن تشير إلى عناصر الشاشة "
    "باستخدام أداة highlight_target، ولا تستطيع النقر أو الكتابة أو تنفيذ أي "
    "إجراء — لا تدّعِ أبداً أنك ضغطت زراً أو كتبت نصاً.\n"
    "قواعدك:\n"
    "1. أجب بالعربية دائماً، بجمل قصيرة مناسبة للنطق الصوتي. المصطلحات "
    "التقنية وأسماء القوائم تبقى بالإنجليزية كما تظهر على الشاشة.\n"
    "2. عندما يسأل المستخدم عن مكان عنصر، استخدم highlight_target بإحداثيات "
    "دقيقة من لقطة الشاشة المرفقة، مع label_ar مختصر.\n"
    "3. إذا كانت اللقطة قديمة أو غير كافية، استخدم request_screen_refresh "
    "بدلاً من التخمين.\n"
    "4. إذا لم تجد العنصر، قل ذلك بصراحة. لا تخترع إحداثيات."
)


def detect_image_media_type(image_bytes: bytes) -> str:
    """Sniff PNG vs JPEG from leading bytes (Clicky's trick, ported).

    mss + Pillow screenshots are PNG; pasted/encoded frames may be JPEG.
    The API rejects requests whose declared media_type mismatches the bytes.
    """
    if image_bytes[:4] == b"\x89PNG":
        return "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    logger.warning("Unknown image signature %s — defaulting to JPEG",
                   image_bytes[:4].hex() if image_bytes else "<empty>")
    return "image/jpeg"


class ClaudeAgent:
    """CloudReasoner implementation for the quality path (v4.1 §9.3).

    base_url is configurable so that pointing مطحس at a Cloudflare Worker
    proxy later (Clicky's key-handling pattern) is a one-line .env change:
    MUTHIS_ANTHROPIC_BASE_URL=https://muthis-proxy.<account>.workers.dev
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        system_prompt: str = LOOK_SYSTEM_PROMPT,
        tools: list[dict[str, Any]] = LOOK_ONLY_TOOLS,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._max_tokens = max_tokens
        self._system_prompt = system_prompt
        # V2 Phase 2 (T5): the model-visible catalog is injectable — main.py
        # passes the v2 catalog (the V1 four + sandbox.run_code). Default stays
        # the byte-pinned V1 four, so tests/other callers are unchanged.
        self._tools = tools
        # ONE shared client per agent — the SDK and the TLS warmup must use
        # the same connection pool or the warmup is theater.
        self._http_client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=15.0),
        )
        self._client = AsyncAnthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
            base_url=base_url,
            http_client=self._http_client,
        )
        self._base_url = base_url
        self._tls_warmed = False

    # ── TLS warmup ────────────────────────────────────────────────────────

    async def warm_up_tls(self) -> None:
        """Pre-establish the TLS connection so the first screenshot-bearing
        request skips the cold handshake. Failures are ignored on purpose —
        this is purely an optimization. Call once from the orchestrator at
        startup (fire-and-forget with asyncio.create_task is fine).
        """
        if self._tls_warmed:
            return
        self._tls_warmed = True
        try:
            await self._http_client.head(self._base_url, timeout=10.0)
            logger.info("TLS warmup done for %s", self._base_url)
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
        """One Claude turn. Yields TextDelta / ToolCall, then one TurnComplete.

        history is owned by the orchestrator (this wrapper stores nothing).
        tool_choice "none" forbids ALL tool use so the model must answer in text
        (the orchestrator's post-highlight pass); "auto" (default) is normal.
        """
        content_blocks: list[dict[str, Any]] = []
        if screenshot:
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": detect_image_media_type(screenshot),
                    "data": base64.standard_b64encode(screenshot).decode("ascii"),
                },
            })
        # Empty text == an agentic continuation: the orchestrator re-called run()
        # after appending a tool_result, and that tool_result IS the user turn.
        # Skip the empty block — the API rejects empty text and nothing is new.
        if user_input.text:
            content_blocks.append({"type": "text", "text": user_input.text})
        # Strict alternation: Option B pairing AND a refresh tool_result both
        # leave history ending on a user message. FOLD this turn's content into
        # that trailing user message instead of emitting a second consecutive
        # user message — so the tool_result and the new text sit in the ONE user
        # message that must follow the assistant's tool_use. The API merges
        # consecutive same-role turns anyway; doing it here keeps the payload clean.
        if not content_blocks:
            messages = list(history)  # pure continuation — resume from the tool_result
        else:
            prev = history[-1] if history else None
            if (prev is not None and prev.get("role") == "user"
                    and isinstance(prev.get("content"), list)):
                messages = [
                    *history[:-1],
                    {"role": "user", "content": [*prev["content"], *content_blocks]},
                ]
            else:
                messages = [*history, {"role": "user", "content": content_blocks}]

        input_tokens = 0
        output_tokens = 0
        stop_reason: str | None = None
        # Tool inputs stream as partial JSON (input_json_delta). Buffer per
        # block; parse ONLY at content_block_stop. Partial JSON never escapes.
        pending_tool: dict[str, str] | None = None

        async with self._client.messages.stream(
            model=self.model,
            max_tokens=self._max_tokens,
            system=self._system_prompt,
            messages=messages,
            tools=self._tools,
            tool_choice={"type": tool_choice},
        ) as stream:
            async for event in stream:
                etype = event.type
                if etype == "message_start":
                    input_tokens = event.message.usage.input_tokens
                elif etype == "content_block_start":
                    if event.content_block.type == "tool_use":
                        pending_tool = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "json": "",
                        }
                elif etype == "content_block_delta":
                    dtype = event.delta.type
                    if dtype == "text_delta":
                        yield TextDelta(event.delta.text)
                    elif dtype == "input_json_delta" and pending_tool is not None:
                        pending_tool["json"] += event.delta.partial_json
                elif etype == "content_block_stop":
                    if pending_tool is not None:
                        try:
                            args = json.loads(pending_tool["json"] or "{}")
                        except json.JSONDecodeError:
                            logger.error("Malformed tool JSON for %s — dropping",
                                         pending_tool["name"])
                            args = None
                        if args is not None:
                            yield ToolCall(
                                name=pending_tool["name"],
                                args=args,
                                tool_use_id=pending_tool["id"],
                            )
                        pending_tool = None
                elif etype == "message_delta":
                    stop_reason = event.delta.stop_reason
                    output_tokens = event.usage.output_tokens

            final_message = await stream.get_final_message()

        # Raw assistant blocks let the orchestrator answer a
        # request_screen_refresh with a tool_result on the next run() call.
        assistant_content = [block.model_dump(exclude_none=True) for block in final_message.content]
        yield TurnComplete(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=self._estimate_cost_usd(input_tokens, output_tokens),
            stop_reason=stop_reason or final_message.stop_reason,
            model=self.model,
            assistant_content=assistant_content,
        )

    # ── Accounting helper ─────────────────────────────────────────────────

    def _estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        in_price, out_price = _PRICE_TABLE_USD_PER_MTOK.get(self.model, (3.00, 15.00))
        return (input_tokens * in_price + output_tokens * out_price) / 1_000_000

    async def aclose(self) -> None:
        """Release the shared HTTP client. Orchestrator calls this once at
        SHUTDOWN — the wrapper never decides on its own to close (Law 11)."""
        await self._http_client.aclose()
