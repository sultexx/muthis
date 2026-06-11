"""
test_claude_agent.py — the fake-session integration test (v4.1 §15, step 8).

No network. We fake the SDK's MessageStream with hand-built event objects
and assert that ClaudeAgent translates them into the exact CloudReasoner
event sequence the orchestrator expects:

    TextDelta* → ToolCall* → TurnComplete (exactly one, last)

Run:  pytest tests/cloud/test_claude_agent.py -q
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from muthis.cloud.claude_agent import ClaudeAgent, detect_image_media_type
from muthis.cloud.protocol import (
    CloudReasoner,
    TextDelta,
    ToolCall,
    TurnComplete,
    UserInput,
)

# ──────────────────────────────────────────────────────────────────────────
# Fake SDK stream plumbing
# ──────────────────────────────────────────────────────────────────────────


def _fake_events():
    """A realistic event sequence: text → tool_use (highlight_target)."""
    usage_start = SimpleNamespace(input_tokens=850)
    return [
        SimpleNamespace(type="message_start",
                        message=SimpleNamespace(usage=usage_start)),
        # Streamed Arabic text (becomes TTS input)
        SimpleNamespace(type="content_block_start",
                        content_block=SimpleNamespace(type="text")),
        SimpleNamespace(type="content_block_delta",
                        delta=SimpleNamespace(type="text_delta", text="هنا ")),
        SimpleNamespace(type="content_block_delta",
                        delta=SimpleNamespace(type="text_delta", text="زر Sketch")),
        SimpleNamespace(type="content_block_stop"),
        # Tool input arrives as PARTIAL JSON across multiple deltas
        SimpleNamespace(type="content_block_start",
                        content_block=SimpleNamespace(
                            type="tool_use", id="toolu_01", name="highlight_target")),
        SimpleNamespace(type="content_block_delta",
                        delta=SimpleNamespace(type="input_json_delta",
                                              partial_json='{"x1": 120, "y1": 8')),
        SimpleNamespace(type="content_block_delta",
                        delta=SimpleNamespace(type="input_json_delta",
                                              partial_json='0, "x2": 240, "y2": 120, '
                                                           '"label_ar": "زر Sketch"}')),
        SimpleNamespace(type="content_block_stop"),
        SimpleNamespace(type="message_delta",
                        delta=SimpleNamespace(stop_reason="tool_use"),
                        usage=SimpleNamespace(output_tokens=64)),
        SimpleNamespace(type="message_stop"),
    ]


class _FakeBlock(SimpleNamespace):
    def model_dump(self, exclude_none=True):  # mimic pydantic block
        return dict(self.__dict__)


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

    async def get_final_message(self):
        return SimpleNamespace(
            stop_reason="tool_use",
            content=[
                _FakeBlock(type="text", text="هنا زر Sketch"),
                _FakeBlock(type="tool_use", id="toolu_01",
                           name="highlight_target",
                           input={"x1": 120, "y1": 80, "x2": 240, "y2": 120,
                                  "label_ar": "زر Sketch"}),
            ],
        )


@asynccontextmanager
async def _fake_stream_cm(*_args, **_kwargs):
    yield _FakeStream(_fake_events())


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def test_media_type_sniffing():
    assert detect_image_media_type(PNG_BYTES) == "image/png"
    assert detect_image_media_type(JPEG_BYTES) == "image/jpeg"
    assert detect_image_media_type(b"\x00\x01") == "image/jpeg"  # safe default


def test_agent_satisfies_cloud_reasoner_protocol():
    agent = ClaudeAgent(api_key="test-key")
    assert isinstance(agent, CloudReasoner)


@pytest.mark.asyncio
async def test_fake_session_event_sequence():
    agent = ClaudeAgent(api_key="test-key", model="claude-sonnet-4-6")

    with patch.object(agent._client.messages, "stream", _fake_stream_cm):
        events = [
            ev async for ev in agent.run(
                user_input=UserInput(text="وين زر الـ Sketch في Fusion؟"),
                screenshot=PNG_BYTES,
                history=[],
            )
        ]

    # Shape: TextDelta* then ToolCall then exactly one trailing TurnComplete
    text_deltas = [e for e in events if isinstance(e, TextDelta)]
    tool_calls = [e for e in events if isinstance(e, ToolCall)]
    completes = [e for e in events if isinstance(e, TurnComplete)]

    assert "".join(d.text for d in text_deltas) == "هنا زر Sketch"
    assert len(tool_calls) == 1
    call = tool_calls[0]
    assert call.name == "highlight_target"
    assert call.tool_use_id == "toolu_01"
    # Partial JSON was buffered then parsed whole — the orchestrator never
    # sees a half-built dict.
    assert call.args == {"x1": 120, "y1": 80, "x2": 240, "y2": 120,
                         "label_ar": "زر Sketch"}

    assert len(completes) == 1 and isinstance(events[-1], TurnComplete)
    done = completes[0]
    assert done.stop_reason == "tool_use"
    assert done.input_tokens == 850 and done.output_tokens == 64
    # 850 * $3/M + 64 * $15/M
    assert done.cost_usd == pytest.approx((850 * 3 + 64 * 15) / 1_000_000)
    assert done.assistant_content[1]["name"] == "highlight_target"


@pytest.mark.asyncio
async def test_look_only_has_no_action_tools():
    """LOOK-only guarantee: no typing/clicking tool can even be OFFERED."""
    from muthis.cloud.claude_agent import LOOK_ONLY_TOOLS

    offered = {tool["name"] for tool in LOOK_ONLY_TOOLS}
    assert offered == {"highlight_target", "request_screen_refresh"}
    forbidden = {"type_text", "press_hotkey", "real_click", "set_trust_mode"}
    assert offered.isdisjoint(forbidden)
