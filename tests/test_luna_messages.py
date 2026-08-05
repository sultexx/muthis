"""
test_luna_messages.py — the message translation, and the loop it has to close.

The kernel's conversation vocabulary is the Anthropic block shape, and it
predates the second provider by a year: `Orchestrator` stores it,
`build_tool_result_message` pairs on it, `history_hygiene` rewrites it. DEC-88
found every provider difference landing in the WRAPPER, so the wrapper
translates and the kernel learns nothing.

**THE TEST THAT MATTERS IS THE LAST ONE**, and it is deliberately an integration
rather than a unit: it drives a real pass through `LunaAgent`, pairs the result
with the REAL kernel builder, feeds that history back in, and asserts the
`function_call` and its `function_call_output` still share one `call_id`. That
round trip IS the agentic loop. Every unit test above it can pass while the loop
is broken — an orphaned call is accepted by the request builder and only fails
later, at the provider, on a turn nobody is watching.

Run:  PYTHONPATH=src pytest tests/test_luna_messages.py -q
"""

from __future__ import annotations

import json

import pytest

from muthis.cloud.luna_agent import LunaAgent
from muthis.cloud.luna_messages import assistant_blocks, to_vendor_input
from muthis.cloud.protocol import ToolCall, UserInput
from muthis.kernel.history_hygiene import strip_images_from_history
from muthis.kernel.tool_result_pairing import build_tool_result_message

from tests.test_luna_agent import PNG_BYTES, _drive, _events  # noqa: E402

IMAGE_B64 = "aGVsbG8="


def _kinds(items):
    return [item.get("type", f"message:{item.get('role')}") for item in items]


# ═══ This turn's own content ═════════════════════════════════════════════════


def test_the_new_turn_is_ONE_user_message_image_then_text():
    """Image first, then text — the order `claude_agent.run()` uses and the order
    the DEC-88 pointing measurement was taken in. A 23/25 result is only
    transferable if the request shape is."""
    items = to_vendor_input([], PNG_BYTES, "وين زر الحفظ؟", "image/png", IMAGE_B64)
    assert len(items) == 1 and items[0]["role"] == "user"
    assert [part["type"] for part in items[0]["content"]] == ["input_image", "input_text"]
    assert items[0]["content"][0]["image_url"] == f"data:image/png;base64,{IMAGE_B64}"


def test_an_agentic_CONTINUATION_adds_no_message_at_all():
    """Empty text and no frame is the orchestrator re-calling run() after
    appending a tool_result: that tool_result IS the turn, and adding an empty
    message beside it would be a second user turn saying nothing."""
    history = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "call_1", "content": "تم"}]}]
    items = to_vendor_input(history, None, "", "image/png", "")
    assert _kinds(items) == ["function_call_output"]


def test_NO_FOLD_is_performed_and_the_items_are_still_correctly_ordered():
    """`claude_agent.run()` FOLDS this turn's content into a trailing user
    message because Anthropic enforces strict role alternation with the
    tool_result NESTED inside a user message. Here `function_call_output` is a
    TOP-LEVEL item, so there is no consecutive-user-message problem and the fold
    would be cargo — the pairing and the new utterance simply follow in order."""
    history = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "call_1", "content": "تم"}]}]
    items = to_vendor_input(history, PNG_BYTES, "طيب وبعدين؟", "image/png", IMAGE_B64)
    assert _kinds(items) == ["function_call_output", "message:user"]


# ═══ Kernel history → vendor items ═══════════════════════════════════════════


def test_a_tool_use_block_becomes_a_function_call_keyed_on_the_CALL_ID():
    history = [{"role": "assistant", "content": [
        {"type": "text", "text": "شوف هنا"},
        {"type": "tool_use", "id": "call_abc", "name": "highlight_target",
         "input": {"x1": 1, "label_ar": "زر"}}]}]
    items = to_vendor_input(history, None, "", "image/png", "")
    assert _kinds(items) == ["message:assistant", "function_call"]
    assert items[1]["call_id"] == "call_abc"
    assert items[1]["name"] == "highlight_target"
    # Arguments cross as a JSON STRING — the form this API both takes and streams.
    assert json.loads(items[1]["arguments"]) == {"x1": 1, "label_ar": "زر"}


def test_arabic_survives_the_argument_serialization():
    """`ensure_ascii=False`. A label the user is about to HEAR must not become
    `\\u0632\\u0631` on its way back into context."""
    history = [{"role": "assistant", "content": [
        {"type": "tool_use", "id": "c1", "name": "highlight_target",
         "input": {"label_ar": "زر الحفظ"}}]}]
    items = to_vendor_input(history, None, "", "image/png", "")
    assert "زر الحفظ" in items[0]["arguments"]


def test_assistant_text_is_output_text_and_user_text_is_input_text():
    """The one place this vendor's vocabulary splits a single kernel block type
    by ROLE."""
    history = [
        {"role": "user", "content": [{"type": "text", "text": "سؤال"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "جواب"}]},
    ]
    items = to_vendor_input(history, None, "", "image/png", "")
    assert items[0]["content"][0]["type"] == "input_text"
    assert items[1]["content"][0]["type"] == "output_text"


def test_ORDER_is_preserved_when_text_and_a_call_share_one_message():
    """Parts are FLUSHED before every top-level item, so a tool call never
    overtakes the text that preceded it — the spoken ack must stay before the
    draw it announces."""
    history = [{"role": "assistant", "content": [
        {"type": "text", "text": "أبشر"},
        {"type": "tool_use", "id": "c1", "name": "highlight_target", "input": {}},
        {"type": "text", "text": "شوف"}]}]
    items = to_vendor_input(history, None, "", "image/png", "")
    assert _kinds(items) == ["message:assistant", "function_call", "message:assistant"]


# ═══ The refresh frame, which must stay inside its own tool result ═══════════


def test_a_REFRESH_screenshot_rides_INSIDE_its_function_call_output():
    """`request_screen_refresh` is answered with the fresh frame nested in the
    tool_result. Re-attaching it as a loose user message would put the picture
    somewhere the model did not ask for it, and the pairing would stop meaning
    what it says."""
    history = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "call_r", "content": [
            {"type": "image", "source": {"type": "base64",
                                         "media_type": "image/jpeg",
                                         "data": IMAGE_B64}}]}]}]
    items = to_vendor_input(history, None, "", "image/png", "")
    output = items[0]["output"]
    assert items[0]["call_id"] == "call_r"
    assert output[0]["type"] == "input_image"
    assert output[0]["image_url"] == f"data:image/jpeg;base64,{IMAGE_B64}"


def test_a_HYGIENE_STRIPPED_refresh_result_still_translates():
    """`history_hygiene` swaps a stale frame for a short Arabic note in place
    (Bug 3, the app-switch hallucination). The translation must survive its own
    project's rewrite of the same block."""
    history = strip_images_from_history([{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "call_r", "content": [
            {"type": "image", "source": {"media_type": "image/png", "data": IMAGE_B64}}]}]}])
    items = to_vendor_input(history, None, "", "image/png", "")
    assert items[0]["output"][0]["type"] == "input_text"
    assert items[0]["output"][0]["text"]


def test_a_string_tool_result_stays_a_string():
    history = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "c1", "content": "تم التنفيذ"}]}]
    items = to_vendor_input(history, None, "", "image/png", "")
    assert items[0]["output"] == "تم التنفيذ"


@pytest.mark.parametrize("history", [
    [{"role": "user", "content": "نص خام"}],          # a string where a list is usual
    [{"role": "user", "content": None}],               # nothing usable
    [{"role": "user", "content": ["not a dict"]}],     # a non-dict block
])
def test_a_malformed_history_entry_NEVER_raises(history):
    """DEFENSIVE by contract (the `parse_shapes_args` precedent). History
    reaches this module through an injectable seam; a translation that raises
    would take the whole turn down at request-build time, before the wrapper has
    any way to answer."""
    to_vendor_input(history, None, "", "image/png", "")


# ═══ Kernel-facing blocks ════════════════════════════════════════════════════


def test_assistant_blocks_emit_the_KERNELS_vocabulary():
    blocks = assistant_blocks("شوف", [ToolCall(name="draw_shapes", args={"a": 1},
                                               tool_use_id="call_9")])
    assert blocks == [
        {"type": "text", "text": "شوف"},
        {"type": "tool_use", "id": "call_9", "name": "draw_shapes", "input": {"a": 1}},
    ]


def test_a_silent_pass_emits_no_empty_text_block():
    """An empty text block is not nothing — it is a block the pairing loop and
    the hygiene strip both walk over, and on the Anthropic path the API rejects
    it outright."""
    assert assistant_blocks("", []) == []


# ═══ THE ROUND TRIP — the agentic loop itself ════════════════════════════════


@pytest.mark.asyncio
async def test_a_TOOL_CALL_survives_a_full_pass_pair_and_replay():
    """Pass 0 calls a tool → the REAL kernel builder pairs it → that history goes
    back in → the call and its output still share ONE `call_id`.

    This is the only test in the file that would fail if `call_id` and `item_id`
    were confused, if the pairing block shape drifted, or if the flat-item
    ordering broke — and all three are silent everywhere else."""
    received, _ = await _drive(LunaAgent(api_key="test-key"), _events())
    blocks = received[-1].assistant_content
    pairing = build_tool_result_message(blocks)
    history = [{"role": "assistant", "content": blocks}, pairing]

    items = to_vendor_input(history, None, "", "image/png", "")
    calls = [i for i in items if i.get("type") == "function_call"]
    outputs = [i for i in items if i.get("type") == "function_call_output"]
    assert len(calls) == len(outputs) == 1
    assert calls[0]["call_id"] == outputs[0]["call_id"] == "call_abc", (
        "the tool call and its result no longer pair — the agentic loop is broken "
        "and nothing else in the suite can see it")
    assert _kinds(items) == ["message:assistant", "function_call", "function_call_output"]


@pytest.mark.asyncio
async def test_the_replayed_history_reaches_the_WIRE_in_that_shape():
    """The round trip above is computed; this one asserts it SURVIVES `run()` —
    the request builder is where an ordering or a fold could quietly reappear.

    Pass 1 is driven as the orchestrator drives it: EMPTY text and NO new frame,
    because the tool_result is the turn."""
    agent = LunaAgent(api_key="test-key")
    received, _ = await _drive(agent, _events())
    blocks = received[-1].assistant_content
    history = [{"role": "assistant", "content": blocks},
               build_tool_result_message(blocks)]

    _, sent = await _drive(agent, _events(), history=history,
                           user_input=UserInput(text=""), screenshot=None)
    assert _kinds(sent["input"]) == [
        "message:assistant", "function_call", "function_call_output"]
