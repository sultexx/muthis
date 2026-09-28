"""
record.py — what one scenario run captures, and the wrappers that capture it.

THE RECORDING REASONER ASSUMES NO MODEL (revision 2 ruling ④). It implements
`CloudReasoner`, wraps whatever implementor a configuration names — `LunaAgent`
with any model id, `ClaudeAgent`, or a scripted policy — and passes EVERY event
through unchanged, so the orchestrator sees exactly what it would see without it.
Per pass it records the `tool_choice`, the tool-result texts in the newest
history message (the notes the model reads on that pass), the ordered stream —
each text segment and each tool call with its arguments, in the order they
arrived — and the usage the provider returned, with `TurnComplete.model`.

`TurnComplete.model` IS NOT A PROVIDER ECHO. Both agents fill it with their own
configured id (`luna_agent.py:209` via `build_turn_complete`, `claude_agent.py`
`model=self.model`), so comparing it with the configuration catches a wrapper
that built the agent with the WRONG id — never a provider that served another
model. Revision 2 ④ named it "the provider's echo"; that premise is false
(DEC-155 ⑤), and until a real echo exists a comparison across models is
REFUSED (`config.cross_model_refusal`).

Everything is held in memory and written by the runner to the harness home,
outside the repository. Nothing here touches `logging` configuration: the
kernel's own log lines are captured by an in-memory handler on `muthis.*`,
never a file (DEC-154).
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Optional

from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete


def _block_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def delivered_texts(history: list) -> list[str]:
    """The tool-result texts of the newest history message — what the model
    reads on this pass. Empty on a turn's first pass."""
    if not history:
        return []
    last = history[-1]
    if last.get("role") != "user" or not isinstance(last.get("content"), list):
        return []
    return [_block_text(b) for b in last["content"]
            if isinstance(b, dict) and b.get("type") == "tool_result"]


def delivered_all(history: list) -> list[str]:
    """Every tool-result text anywhere in the history — what a model can still
    read on this pass, earlier passes included."""
    return [_block_text(b) for m in history
            if m.get("role") == "user" and isinstance(m.get("content"), list)
            for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]


class RunRecorder:
    """One scenario run: turns → passes → an ordered event stream."""

    def __init__(self, *, config: str, scenario: str, rep: int, model: str) -> None:
        self.data: dict[str, Any] = {"config": config, "scenario": scenario, "rep": rep,
                                     "configured_model": model, "turns": []}
        self._pass: Optional[dict] = None

    @property
    def turn(self) -> dict:
        return self.data["turns"][-1]

    def begin_turn(self, text: str) -> None:
        self.data["turns"].append({"user_text": text, "passes": [], "spoken": [],
                                   "overlay": [], "kernel": []})

    def end_turn(self, result: Any) -> None:
        self.turn["result"] = {"timed_out": bool(getattr(result, "timed_out", False)),
                               "budget_blocked": bool(getattr(result, "budget_blocked", False)),
                               "cost_usd": float(getattr(result, "cost_usd", 0.0) or 0.0)}

    def begin_pass(self, tool_choice: str, delivered: list[str], user_text: str) -> None:
        self._pass = {"tool_choice": tool_choice, "delivered": delivered,
                      "user_text": user_text, "events": [], "usage": None}
        self.turn["passes"].append(self._pass)

    def event(self, event: Any) -> None:
        events = self._pass["events"]
        if isinstance(event, TextDelta):
            if events and events[-1][0] == "text":
                events[-1] = ("text", events[-1][1] + event.text)
            else:
                events.append(("text", event.text))
        elif isinstance(event, ToolCall):
            events.append(("call", event.name, dict(event.args)))
        elif isinstance(event, TurnComplete):
            self._pass["usage"] = {
                "input_tokens": event.input_tokens, "output_tokens": event.output_tokens,
                "cost_usd": event.cost_usd, "stop_reason": event.stop_reason,
                "model_echo": event.model,
                "cache_read": event.cache_read_input_tokens,
                "cache_write": event.cache_creation_input_tokens}


class RecordingReasoner:
    """A transparent `CloudReasoner` that records every pass of `inner`."""

    def __init__(self, inner: Any, recorder: RunRecorder) -> None:
        self._inner = inner
        self._recorder = recorder
        self.model = getattr(inner, "model", "")

    async def run(self, user_input, screenshot, history, tool_choice: str = "auto"
                  ) -> AsyncIterator[Any]:
        self._recorder.begin_pass(tool_choice, delivered_texts(history), user_input.text)
        async for event in self._inner.run(user_input, screenshot, history,
                                           tool_choice=tool_choice):
            self._recorder.event(event)
            yield event

    async def warm_up_tls(self) -> None:
        warm = getattr(self._inner, "warm_up_tls", None)
        if warm is not None:
            await warm()

    async def aclose(self) -> None:
        close = getattr(self._inner, "aclose", None)
        if close is not None:
            await close()


class RecordingVoice:
    """The TTS seam: records what the user would hear — the model's speech AND
    the kernel's own utterances (the approval request, the cap note)."""

    def __init__(self, recorder: RunRecorder) -> None:
        self._recorder = recorder

    async def speak(self, text: str) -> None:
        self._recorder.turn["spoken"].append(text)
        return None


class RecordingOverlay:
    """The overlay seam: no window; records every highlight and draw."""

    def __init__(self, recorder: RunRecorder) -> None:
        self._recorder = recorder

    def _log(self, *entry: Any) -> None:
        if self._recorder.data["turns"]:
            self._recorder.turn["overlay"].append(entry)

    async def show(self, bbox, label_ar: str) -> None:
        self._log("show", list(bbox))

    async def hide(self) -> None:
        self._log("hide")

    async def draw_shapes(self, shapes) -> None:
        self._log("draw_shapes", len(shapes))

    # These three are SYNC on the kernel's side (draw_dispatch, the orchestrator's
    # undim, turn_pass's badge call them without awaiting); an async version
    # would record nothing and leave a never-awaited coroutine behind.
    def dim_screen(self) -> None:
        self._log("dim_screen")

    def undim_screen(self) -> None:
        self._log("undim_screen")

    def show_domain_badge(self, domains) -> None:
        self._log("badge", list(domains))

    def show_mode_indicator(self, text: str) -> None:
        self._log("mode", text)

    def set_state(self, state: str) -> None:
        pass

    def clear_status_light(self) -> None:
        pass


class MemoryLogHandler(logging.Handler):
    """The kernel's own `muthis.*` lines for the current turn — names and counts
    only, as the kernel writes them. In memory; never a file."""

    def __init__(self, recorder: RunRecorder) -> None:
        super().__init__(level=logging.INFO)
        self._recorder = recorder

    def emit(self, record: logging.LogRecord) -> None:
        if self._recorder.data["turns"]:
            self._recorder.turn["kernel"].append(record.getMessage())


__all__ = ["MemoryLogHandler", "RecordingOverlay", "RecordingReasoner",
           "RecordingVoice", "RunRecorder", "delivered_all", "delivered_texts"]
