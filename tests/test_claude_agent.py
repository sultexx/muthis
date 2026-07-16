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
    # B-1: draw_shapes joined the LOOK set — it DRAWS overlay graphics only.
    # v7 Phase 4: read_local_file joined too — READ-ONLY perception, no action.
    assert offered == {"highlight_target", "draw_shapes",
                       "request_screen_refresh", "read_local_file"}
    forbidden = {"type_text", "press_hotkey", "real_click", "set_trust_mode"}
    assert offered.isdisjoint(forbidden)


class _CapturingStream:
    """Captures the messages= kwarg handed to messages.stream(), then replays
    the canned highlight events so run() still completes normally."""

    def __init__(self):
        self.captured_messages = None

    @asynccontextmanager
    async def cm(self, *_args, **kwargs):
        self.captured_messages = kwargs.get("messages")
        yield _FakeStream(_fake_events())


@pytest.mark.asyncio
async def test_run_folds_trailing_user_tool_result_into_one_user_message():
    """Strict alternation (Option B pairing / refresh tool_result both leave
    history ending on a user message): run() FOLDS this turn's content into that
    trailing user message instead of sending two consecutive user messages — so
    the assistant tool_use stays immediately followed by its tool_result and the
    roles keep alternating."""
    agent = ClaudeAgent(api_key="test-key", model="claude-sonnet-4-6")
    history = [
        {"role": "user", "content": [{"type": "text", "text": "وين زر الحفظ؟"}]},
        {"role": "assistant", "content": [
            {"type": "text", "text": "هنا"},
            {"type": "tool_use", "id": "toolu_h1", "name": "highlight_target",
             "input": {"x1": 1, "y1": 2, "x2": 3, "y2": 4, "label_ar": "زر"}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_h1", "content": "تم"}]},
    ]
    capturer = _CapturingStream()
    with patch.object(agent._client.messages, "stream", capturer.cm):
        _ = [
            ev async for ev in agent.run(
                user_input=UserInput(text="وقائمة الفتح؟"),
                screenshot=PNG_BYTES,
                history=history,
            )
        ]

    messages = capturer.captured_messages
    roles = [m["role"] for m in messages]
    assert all(a != b for a, b in zip(roles, roles[1:])), roles   # no consecutive role
    assert messages[1]["role"] == "assistant"
    folded = messages[2]                                          # the merged user msg
    assert folded["role"] == "user"
    block_types = [b["type"] for b in folded["content"]]
    assert block_types[0] == "tool_result"                       # the pairing stays first
    assert "image" in block_types and "text" in block_types      # then this turn's content
    assert folded["content"][0]["tool_use_id"] == "toolu_h1"     # answered, not orphaned


class _KwargCapturingStream:
    """Captures ALL kwargs handed to messages.stream() so a test can assert what
    the agent does (and does NOT) pass to the SDK — e.g. tool_choice."""

    def __init__(self):
        self.captured_kwargs = None

    @asynccontextmanager
    async def cm(self, *_args, **kwargs):
        self.captured_kwargs = kwargs
        yield _FakeStream(_fake_events())


@pytest.mark.asyncio
async def test_tool_choice_stays_auto_never_forced():
    """tool_choice MUST stay 'auto' (the SDK default == the kwarg is absent).
    Forcing the pointer (tool_choice={'type': 'any' | 'tool'}) would SUPPRESS the
    assistant's accompanying prose, and the dual-action 'point AND explain'
    contract depends on that prose surviving — so the tool is never forced."""
    agent = ClaudeAgent(api_key="test-key", model="claude-sonnet-4-6")
    capturer = _KwargCapturingStream()
    with patch.object(agent._client.messages, "stream", capturer.cm):
        _ = [
            ev async for ev in agent.run(
                user_input=UserInput(text="وين زر الحفظ؟"),
                screenshot=PNG_BYTES,
                history=[],
            )
        ]

    kwargs = capturer.captured_kwargs
    # Absent == the API/SDK default of "auto" (the model decides). If a future
    # change ever sets it explicitly, it must STILL be auto, never any/tool.
    tc = kwargs.get("tool_choice")
    if tc is not None:
        choice_type = tc.get("type") if isinstance(tc, dict) else tc
        assert choice_type == "auto", f"tool_choice must be auto, got {tc!r}"
        assert choice_type not in ("any", "tool"), "the pointer must NEVER be forced"
    # Tools ARE still offered — 'auto' means the model MAY point, not that it must.
    assert kwargs.get("tools"), "LOOK tools should still be offered under auto"
