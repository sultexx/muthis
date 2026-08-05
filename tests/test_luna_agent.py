"""
test_luna_agent.py — the second CloudReasoner, driven against a fake stream.

No network. The vendor's streaming events are hand-built from the SHAPE the
DEC-88 probe measured live, and the assertions are that `LunaAgent` translates
them into the exact event sequence the orchestrator already consumes:

    TextDelta* → ToolCall* → TurnComplete (exactly one, last)

FOUR OF THESE TESTS ARE NOT ABOUT TRANSLATION AT ALL, and they are the ones
worth reading:

  · `test_stop_reason_is_DERIVED...` — this provider has no `stop_reason` field
    (DEC-88 ②). A turn that called a tool still reports `status == "completed"`,
    so deriving it in the wrong ORDER ends the agentic loop after the pointer
    draws and before the explanation is ever requested. Nothing else in the
    suite would notice: the wrapper would be correct, the stream would be
    correct, and Mut'his would point in silence.
  · `test_the_tool_use_id_is_the_CALL_ID` — `call_id` and `item_id` are two
    different strings on this API, and only one of them pairs a
    `function_call_output`. Carrying the wrong one orphans every tool call.
  · `test_store_is_FALSE_on_every_call` — Mut'his sends the user's SCREEN.
    Server-side retention of a turn is retention of the user's desktop.
  · `test_the_tools_sent_are_TRANSLATED` — a raw catalogue is REJECTED by this
    API and a half-ported one is ACCEPTED in silence (`test_tool_envelope.py`).

Run:  PYTHONPATH=src pytest tests/test_luna_agent.py -q
"""

from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from muthis.cloud.luna_agent import REASONING_EFFORT, LunaAgent
from muthis.cloud.protocol import (
    CloudReasoner, TextDelta, ToolCall, TurnComplete, UserInput,
)
from muthis.kernel.tool_result_pairing import build_tool_result_message

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16

POINT_ARGS = '{"x1": 120, "y1": 80, "x2": 240, "y2": 120, "label_ar": "زر الحفظ"}'


def _final(status: str = "completed", *, input_tokens: int = 7097,
           output_tokens: int = 120, cached: int = 5895) -> NS:
    """The terminal response object. Token figures are DEC-90's measured pass-1
    numbers, so an arithmetic slip shows up as a number nobody recognises."""
    return NS(
        status=status,
        incomplete_details=None,
        usage=NS(input_tokens=input_tokens, output_tokens=output_tokens,
                 input_tokens_details=NS(cached_tokens=cached, cache_write_tokens=0)),
    )


def _events(*, arguments: str = POINT_ARGS, terminal: bool = True) -> list[NS]:
    """One tool-calling turn, in the measured order: a `reasoning` item precedes
    everything (no Anthropic analogue), text streams incrementally, tool
    arguments stream as PARTIAL JSON and complete at a `.done` boundary, and
    `usage` appears ONLY at the last event."""
    stream = [
        NS(type="response.created"),
        NS(type="response.output_item.added", item=NS(type="reasoning", id="rs_1")),
        NS(type="response.output_text.delta", delta="أبشر، "),
        NS(type="response.output_text.delta", delta="شوف هنا"),
        NS(type="response.output_item.added",
           item=NS(type="function_call", id="fc_1", call_id="call_abc",
                   name="highlight_target")),
        NS(type="response.function_call_arguments.delta", item_id="fc_1",
           delta='{"x1": 120, "y1": 8'),
        NS(type="response.function_call_arguments.delta", item_id="fc_1",
           delta='0, "x2": 240}'),
        NS(type="response.function_call_arguments.done", item_id="fc_1",
           name="highlight_target", arguments=arguments),
    ]
    if terminal:
        stream.append(NS(type="response.completed", response=_final()))
    return stream


class _FakeStream:
    def __init__(self, events):
        self._events = events

    def __aiter__(self):
        self._iter = iter(self._events)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _fake_create(events):
    """Returns a create() double that RECORDS the request it was handed — most
    of the security-relevant assertions are about what we SENT, not what we
    parsed."""
    sent: dict = {}

    async def create(**kwargs):
        sent.update(kwargs)
        return _FakeStream(events)

    return create, sent


async def _drive(agent, events, **run_kwargs):
    create, sent = _fake_create(events)
    with patch.object(agent._client.responses, "create", create):  # noqa: SLF001
        received = [
            event async for event in agent.run(
                user_input=run_kwargs.pop("user_input", UserInput(text="وين زر الحفظ؟")),
                screenshot=run_kwargs.pop("screenshot", PNG_BYTES),
                history=run_kwargs.pop("history", []),
                **run_kwargs,
            )
        ]
    return received, sent


# ═══ The contract ════════════════════════════════════════════════════════════


def test_the_agent_satisfies_the_UNCHANGED_CloudReasoner_protocol():
    """DEC-88's headline: `protocol.py` needed no change to admit a second
    vendor. This is that claim, asserted rather than recounted."""
    assert isinstance(LunaAgent(api_key="test-key"), CloudReasoner)


@pytest.mark.asyncio
async def test_the_event_sequence_is_TextDelta_ToolCall_then_ONE_TurnComplete():
    received, _ = await _drive(LunaAgent(api_key="test-key"), _events())
    assert [type(e).__name__ for e in received] == [
        "TextDelta", "TextDelta", "ToolCall", "TurnComplete"]
    assert isinstance(received[-1], TurnComplete), "TurnComplete must be LAST"
    assert sum(isinstance(e, TurnComplete) for e in received) == 1


@pytest.mark.asyncio
async def test_PARTIAL_JSON_never_leaves_the_wrapper():
    """The `.delta` events carry fragments; only the `.done` event carries the
    complete string. Nothing partial may reach the orchestrator — the same
    discipline `claude_agent.py` buys with a buffer, held here by construction."""
    received, _ = await _drive(LunaAgent(api_key="test-key"), _events())
    call = next(e for e in received if isinstance(e, ToolCall))
    assert call.args == {"x1": 120, "y1": 80, "x2": 240, "y2": 120, "label_ar": "زر الحفظ"}
    assert all(not isinstance(e, TextDelta) or "{" not in e.text for e in received)


@pytest.mark.asyncio
async def test_the_tool_use_id_is_the_CALL_ID_not_the_item_id():
    """`call_id` is what a `function_call_output` pairs on; `item_id` is what the
    arguments event carries. They are different strings, and the arguments event
    does not carry `call_id` at all — so the mapping captured at
    `output_item.added` is load-bearing. Carrying `fc_1` here would orphan every
    tool call on the next pass."""
    received, _ = await _drive(LunaAgent(api_key="test-key"), _events())
    call = next(e for e in received if isinstance(e, ToolCall))
    assert call.tool_use_id == "call_abc"
    assert call.name == "highlight_target"


@pytest.mark.asyncio
async def test_stop_reason_is_DERIVED_and_a_tool_call_beats_a_completed_status():
    """The single most load-bearing derivation in the wrapper. `status` is
    `completed` on this turn — the response DID complete — yet the loop MUST
    continue, or the explanation planned after the pointer never happens."""
    received, _ = await _drive(LunaAgent(api_key="test-key"), _events())
    complete = received[-1]
    assert complete.stop_reason == "tool_use"


@pytest.mark.asyncio
async def test_a_turn_with_no_tool_call_ends_the_loop():
    events = [NS(type="response.output_text.delta", delta="هذا هو الشرح"),
              NS(type="response.completed", response=_final())]
    received, _ = await _drive(LunaAgent(api_key="test-key"), events)
    assert received[-1].stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_usage_is_read_from_the_LAST_event():
    """Difference ②: `claude_agent.py` reads usage at `message_start`, the
    FIRST. Here nothing carries it until the stream ends."""
    received, _ = await _drive(LunaAgent(api_key="test-key"), _events())
    complete = received[-1]
    assert (complete.input_tokens, complete.output_tokens) == (7097, 120)
    assert complete.cache_read_input_tokens == 5895
    assert complete.model == "gpt-5.6-luna"


@pytest.mark.asyncio
async def test_a_stream_that_never_terminates_yields_a_ZERO_TurnComplete():
    """A cancelled stream (barge-in is exactly that) delivers no usage. The turn
    must still close cleanly and must never be charged for tokens nobody
    reported — and `stop_reason=None` is what the orchestrator already treats as
    'end the loop cleanly'."""
    received, _ = await _drive(LunaAgent(api_key="test-key"),
                               _events(terminal=False))
    complete = received[-1]
    assert (complete.input_tokens, complete.output_tokens, complete.cost_usd) == (0, 0, 0.0)
    assert complete.stop_reason == "tool_use"  # a tool DID stream before the cut


@pytest.mark.asyncio
async def test_malformed_tool_json_DROPS_the_call_and_never_raises():
    """`claude_agent.py`'s behaviour letter for letter, so the orchestrator sees
    the same thing from either vendor: one fewer tool call, never an exception
    crossing the seam (Law 11)."""
    received, _ = await _drive(LunaAgent(api_key="test-key"),
                               _events(arguments='{"x1": 120, "y1"'))
    assert not any(isinstance(e, ToolCall) for e in received)
    assert isinstance(received[-1], TurnComplete)


# ═══ What we SEND ════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_store_is_FALSE_on_every_call():
    """A PRIVACY CONTROL, not an SDK default. The payload is the user's screen;
    server-side retention of a Mut'his turn is retention of their desktop. This
    is the one site that could grant it, so it is asserted here — the same
    instinct as the DEC-28 logging silence."""
    _, sent = await _drive(LunaAgent(api_key="test-key"), _events())
    assert sent["store"] is False


@pytest.mark.asyncio
async def test_the_RULED_reasoning_effort_is_sent():
    """DEC-89 ruling 2: `high`, measured. `xhigh` was rejected on MEASURED
    ACCURACY — it doubled output for ZERO additional targets — so a drift here
    is a drift away from a number that was paid for."""
    _, sent = await _drive(LunaAgent(api_key="test-key"), _events())
    assert sent["reasoning"] == {"effort": "high"} == {"effort": REASONING_EFFORT}


@pytest.mark.asyncio
async def test_the_tools_sent_are_TRANSLATED_never_the_raw_catalogue():
    """The raw Anthropic envelope is REJECTED by this API; a half-ported one is
    ACCEPTED in silence. This asserts the translated shape actually reaches the
    wire, which `test_tool_envelope.py` cannot see from where it stands."""
    _, sent = await _drive(LunaAgent(api_key="test-key"), _events())
    assert sent["tools"], "no tools were sent at all"
    for tool in sent["tools"]:
        assert tool["type"] == "function"
        assert "parameters" in tool and "input_schema" not in tool


@pytest.mark.asyncio
async def test_tool_choice_passes_through_verbatim():
    """"none" is API-ENFORCED on this provider too (measured), so the
    post-highlight explain pass keeps a hard loop terminator rather than a
    prompt nudge."""
    _, sent = await _drive(LunaAgent(api_key="test-key"), _events(),
                           tool_choice="none")
    assert sent["tool_choice"] == "none"


@pytest.mark.asyncio
async def test_the_image_rides_as_a_data_uri_with_the_SNIFFED_media_type():
    _, sent = await _drive(LunaAgent(api_key="test-key"), _events(),
                           screenshot=JPEG_BYTES)
    parts = sent["input"][-1]["content"]
    assert parts[0]["type"] == "input_image"
    assert parts[0]["image_url"].startswith("data:image/jpeg;base64,")


# ═══ The round trip the kernel depends on ════════════════════════════════════


@pytest.mark.asyncio
async def test_assistant_content_PAIRS_through_the_REAL_kernel_builder():
    """THE INTEGRATION THAT MATTERS. `TurnComplete.assistant_content` is read by
    the KERNEL — `build_tool_result_message` pairs on `type` / `id` / `name`,
    and an unpaired `tool_use` 400s the NEXT turn. So the wrapper must emit the
    kernel's block vocabulary, and the only convincing proof is running the real
    builder over what it produced rather than eyeballing the dict."""
    received, _ = await _drive(LunaAgent(api_key="test-key"), _events())
    blocks = received[-1].assistant_content
    assert blocks[0] == {"type": "text", "text": "أبشر، شوف هنا"}
    assert blocks[1]["type"] == "tool_use"
    assert blocks[1]["id"] == "call_abc"
    assert blocks[1]["name"] == "highlight_target"

    pairing = build_tool_result_message(blocks)
    assert pairing is not None, "the kernel found nothing to pair — orphaned tool_use"
    assert pairing["role"] == "user"
    assert [b["tool_use_id"] for b in pairing["content"]] == ["call_abc"]
