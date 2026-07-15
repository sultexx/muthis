"""
test_orchestrator_persona.py — persona injection, proven at the wire.

This is the orchestrator-suite companion to test_orchestrator_{tts,stt}.py. It
drives the REAL ClaudeAgent through the Orchestrator exactly as production
wires it — `Orchestrator(reasoner=ClaudeAgent(system_prompt=
resolve_system_prompt(LOOK_SYSTEM_PROMPT)))` — with the SDK's network call
faked, and asserts that the `system=` ClaudeAgent actually sends is the Saudi
persona, NOT the neutral MSA LOOK_SYSTEM_PROMPT fallback.

It also pins three unbreakable constraints at the same wire:
  * screen capture stays a stub → the user turn carries NO image (screenshot
    is None all the way to ClaudeAgent),
  * the only tools offered are highlight_target + request_screen_refresh
    (LOOK-only),
  * the user transcript never reaches the TTS (privacy boundary).

No network, no audio, fully deterministic.

Run:  pytest tests/test_orchestrator_persona.py -q
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from muthis.budget import Budget
from muthis.cloud.claude_agent import ClaudeAgent, LOOK_SYSTEM_PROMPT
from muthis.orchestrator import Orchestrator
from muthis.persona import build_saudi_persona_prompt, resolve_system_prompt
from muthis.tts import TTSResult

USER_TEXT_AR = "وين زر الـ Sketch في Fusion؟"
ASSISTANT_TEXT_AR = "أبشر، زر Sketch فوق"
SENT_W, SENT_H = 1280, 720  # sent-image dims injected into the persona


# ──────────────────────── Fake SDK stream plumbing ────────────────────────


def _text_only_events():
    """A minimal text-only provider turn (no tool call needed here)."""
    return [
        SimpleNamespace(type="message_start",
                        message=SimpleNamespace(
                            usage=SimpleNamespace(input_tokens=500))),
        SimpleNamespace(type="content_block_start",
                        content_block=SimpleNamespace(type="text")),
        SimpleNamespace(type="content_block_delta",
                        delta=SimpleNamespace(type="text_delta", text="أبشر، ")),
        SimpleNamespace(type="content_block_delta",
                        delta=SimpleNamespace(type="text_delta", text="زر Sketch فوق")),
        SimpleNamespace(type="content_block_stop"),
        SimpleNamespace(type="message_delta",
                        delta=SimpleNamespace(stop_reason="end_turn"),
                        usage=SimpleNamespace(output_tokens=20)),
        SimpleNamespace(type="message_stop"),
    ]


class _FakeBlock(SimpleNamespace):
    def model_dump(self, exclude_none=True):  # mimic a pydantic content block
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
            stop_reason="end_turn",
            content=[_FakeBlock(type="text", text=ASSISTANT_TEXT_AR)],
        )


class FakeTTS:
    """Same call shape as muthis.tts.TTS.speak — records every utterance."""

    def __init__(self):
        self.spoken = []

    async def speak(self, text):
        self.spoken.append(text)
        return TTSResult(success=True, provider="elevenlabs")


# ──────────────────────────────── Test ────────────────────────────────


@pytest.mark.asyncio
async def test_saudi_persona_reaches_claude_system_param(tmp_path):
    # Production wiring: resolve the persona, hand it to ClaudeAgent through
    # the EXISTING system_prompt seam (claude_agent.py untouched).
    persona_prompt = resolve_system_prompt(LOOK_SYSTEM_PROMPT, SENT_W, SENT_H)
    agent = ClaudeAgent(api_key="test-key", system_prompt=persona_prompt)

    captured: dict = {}

    @asynccontextmanager
    async def capturing_stream(*_args, **kwargs):
        # Record exactly what ClaudeAgent asks the SDK to send.
        captured["system"] = kwargs.get("system")
        captured["messages"] = kwargs.get("messages")
        captured["tools"] = kwargs.get("tools")
        yield _FakeStream(_text_only_events())

    budget = Budget(
        daily_limit_usd=1.0,
        budget_file=tmp_path / "budget.json",
        today_fn=lambda: "2026-06-13",
    )
    fake_tts = FakeTTS()
    orchestrator = Orchestrator(
        reasoner=agent,
        budget=budget,
        tts=fake_tts.speak,
        # mic / stt / screen_capture / overlay stay stubs — screen_capture
        # returns None, so screenshot=None reaches ClaudeAgent.
    )

    with patch.object(agent._client.messages, "stream", capturing_stream):
        result = await orchestrator.run_turn(USER_TEXT_AR)

    # ── The point of the test: the Saudi persona is what Claude received ──
    assert captured["system"] == build_saudi_persona_prompt(SENT_W, SENT_H)
    assert captured["system"] != LOOK_SYSTEM_PROMPT       # not the MSA fallback
    for marker in ("أبشر", "طال عمرك", "وشلونك", "عاد"):
        assert marker in captured["system"]

    # ── screenshot=None: the user turn carries text only, no image block ──
    last_user_msg = captured["messages"][-1]
    assert last_user_msg["role"] == "user"
    block_types = {block["type"] for block in last_user_msg["content"]}
    assert block_types == {"text"}, "an image block leaked in — screen capture must stay stubbed"

    # ── LOOK-only at the wire: exactly the LOOK draw/refresh tools, nothing else ──
    offered = {tool["name"] for tool in captured["tools"]}
    assert offered == {"highlight_target", "draw_shapes", "request_screen_refresh"}

    # ── Privacy: the TTS spoke only the assistant Arabic, never the transcript ──
    assert fake_tts.spoken == [ASSISTANT_TEXT_AR]
    assert USER_TEXT_AR not in fake_tts.spoken
    assert result.spoken_text == ASSISTANT_TEXT_AR
    assert not result.budget_blocked and not result.timed_out
