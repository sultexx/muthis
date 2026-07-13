"""
test_orchestrator.py — the stubbed turn-pipeline tests.

No network, fully deterministic. A scripted FakeReasoner stands in for
ClaudeAgent (same CloudReasoner contract: TextDelta* → ToolCall* → exactly
one TurnComplete); recording stubs stand in for TTS / overlay / screen
capture; Budget is the real gate over a tmp_path ledger with a frozen date.

Run:  pytest tests/test_orchestrator.py -q
"""

from __future__ import annotations

import base64

import pytest

from muthis.budget import Budget
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.orchestrator import (
    BUDGET_REFUSAL_AR, MAX_AGENTIC_ITERATIONS, Orchestrator,
)
from muthis.turn import (
    AGENTIC_CAP_NOTE_AR, HIGHLIGHT_ACK_TEXT_AR, HIGHLIGHT_ALREADY_SHOWN_AR,
    STALE_SCREENSHOT_NOTE_AR,
)
from muthis.verbosity import DIRECTIVE_OPEN_AR

# ──────────────────────────────────────────────────────────────────────────
# Fakes and recorders
# ──────────────────────────────────────────────────────────────────────────

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class FakeReasoner:
    """Scripted CloudReasoner: each run() call replays the next event list
    and records exactly what the orchestrator handed it (incl. tool_choice)."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls = []  # (user_input, screenshot, history) per run()
        self.tool_choices = []  # the tool_choice passed per run() (plumbing proof)

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.calls.append((user_input, screenshot, history))
        self.tool_choices.append(tool_choice)
        for event in self._scripts.pop(0):
            yield event


class Recorder:
    """Async stub bundle that records everything routed through it. Doubles as
    the Overlay seam (show/hide) — the orchestrator injects the recorder itself
    as `overlay=`, plus its tts/screen_capture bound methods as the other seams."""

    def __init__(self):
        self.spoken = []        # every text chunk handed to TTS
        self.shows = []         # (bbox, label_ar) per overlay.show — ALREADY physical
        self.hides = 0          # overlay.hide() count
        self.captures = 0       # screen_capture invocations
        self.events = []        # ordered "hide"/"capture"/"show" for ghosting checks

    async def tts(self, text):
        self.spoken.append(text)

    # ── Overlay protocol (show/hide); bbox arrives ALREADY physical ──
    async def show(self, bbox, label_ar):
        self.shows.append((bbox, label_ar))
        self.events.append("show")

    async def hide(self):
        self.hides += 1
        self.events.append("hide")

    def set_state(self, state):          # 2-B status light — no-op in this fake
        pass

    def clear_status_light(self):        # (a dedicated fake records the sequence)
        pass

    async def screen_capture(self):
        self.captures += 1
        self.events.append("capture")
        return PNG_BYTES


def _turn_complete(cost_usd=0.0025, stop_reason="end_turn", assistant_content=None):
    return TurnComplete(
        input_tokens=850,
        output_tokens=64,
        cost_usd=cost_usd,
        stop_reason=stop_reason,
        model="claude-sonnet-4-6",
        assistant_content=assistant_content or [{"type": "text", "text": "هنا"}],
    )


def _highlight(tool_use_id="toolu_h1"):
    return ToolCall(
        name="highlight_target",
        args={"x1": 10, "y1": 20, "x2": 110, "y2": 60, "label_ar": "زر الحفظ"},
        tool_use_id=tool_use_id,
    )


def _orchestrator(tmp_path, scripts, daily_limit_usd=1.0):
    reasoner = FakeReasoner(scripts)
    budget = Budget(
        daily_limit_usd=daily_limit_usd,
        budget_file=tmp_path / "budget.json",
        today_fn=lambda: "2026-06-11",
    )
    recorder = Recorder()
    orchestrator = Orchestrator(
        reasoner=reasoner,
        budget=budget,
        tts=recorder.tts,
        overlay=recorder,
        screen_capture=recorder.screen_capture,
    )
    return orchestrator, reasoner, budget, recorder


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_normal_turn_flows_end_to_end(tmp_path):
    script = [
        TextDelta("زر الحفظ "),
        TextDelta("فوق يسار"),
        _highlight(),
        _turn_complete(cost_usd=0.0025),
    ]
    orchestrator, reasoner, budget, recorder = _orchestrator(tmp_path, [script])

    result = await orchestrator.run_turn("وين زر الحفظ؟")

    # Buffer-then-speak: the whole assistant message reached the TTS ONCE
    # (per-delta speaking would produce choppy half-word audio).
    assert recorder.spoken == ["زر الحفظ فوق يسار"]
    assert result.spoken_text == "زر الحفظ فوق يسار"

    # highlight_target reached the overlay as ALREADY-PHYSICAL coords. The
    # default downscale stub is identity (scale 1.0), so the bbox is unchanged.
    assert recorder.shows == [((10, 20, 110, 60), "زر الحفظ")]
    assert result.tool_calls[0].args["label_ar"] == "زر الحفظ"

    # budget.record_turn consumed the exact provider cost.
    assert budget.spent_today_usd() == 0.0025
    assert result.cost_usd == 0.0025
    assert result.input_tokens == 850 and result.output_tokens == 64
    assert not result.budget_blocked and not result.timed_out

    # The provider saw the screenshot and an empty prior history.
    user_input, screenshot, history = reasoner.calls[0]
    assert user_input.text == "وين زر الحفظ؟"
    assert screenshot == PNG_BYTES
    assert history == []


@pytest.mark.asyncio
async def test_budget_blocked_turn_never_calls_provider(tmp_path):
    orchestrator, reasoner, budget, recorder = _orchestrator(
        tmp_path, scripts=[], daily_limit_usd=0.0,  # gate closed from turn one
    )

    result = await orchestrator.run_turn("وين زر الحفظ؟")

    assert result.budget_blocked
    assert reasoner.calls == []                  # provider NEVER touched
    assert recorder.spoken == [BUDGET_REFUSAL_AR]  # Arabic refusal spoken
    assert recorder.shows == []                  # no rectangle drawn
    assert orchestrator.history == []            # a refused turn leaves no trace
    assert result.cost_usd == 0.0


@pytest.mark.asyncio
async def test_history_accumulates_across_two_turns(tmp_path):
    first_assistant = [{"type": "text", "text": "زر الحفظ فوق"}]
    second_assistant = [{"type": "text", "text": "تحت قائمة File"}]
    scripts = [
        [TextDelta("زر الحفظ فوق"), _turn_complete(assistant_content=first_assistant)],
        [TextDelta("تحت قائمة File"), _turn_complete(assistant_content=second_assistant)],
    ]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("وين زر الحفظ؟")
    assert orchestrator.history == [
        {"role": "user", "content": [{"type": "text", "text": "وين زر الحفظ؟"}]},
        {"role": "assistant", "content": first_assistant},
    ]

    await orchestrator.run_turn("وقائمة الفتح؟")

    # Turn two was given exactly turn one's history (text only, no images).
    assert reasoner.calls[1][2] == orchestrator.history[:2]
    assert orchestrator.history == [
        {"role": "user", "content": [{"type": "text", "text": "وين زر الحفظ؟"}]},
        {"role": "assistant", "content": first_assistant},
        {"role": "user", "content": [{"type": "text", "text": "وقائمة الفتح؟"}]},
        {"role": "assistant", "content": second_assistant},
    ]


@pytest.mark.asyncio
async def test_request_screen_refresh_triggers_follow_up(tmp_path):
    refresh = ToolCall(name="request_screen_refresh", args={}, tool_use_id="toolu_r1")
    refresh_assistant = [
        {"type": "tool_use", "id": "toolu_r1", "name": "request_screen_refresh", "input": {}},
    ]
    scripts = [
        # Turn 1: the model wants a fresh screenshot.
        [refresh, _turn_complete(cost_usd=0.001, stop_reason="tool_use",
                                 assistant_content=refresh_assistant)],
        # Follow-up: with the new image it answers and highlights.
        [TextDelta("زر الحفظ هنا"), _highlight(), _turn_complete(cost_usd=0.002)],
    ]
    orchestrator, reasoner, budget, recorder = _orchestrator(tmp_path, scripts)

    result = await orchestrator.run_turn("وين زر الحفظ؟")

    # Two gated provider turns happened; both costs recorded and aggregated.
    assert len(reasoner.calls) == 2
    assert budget.spent_today_usd() == round(0.001 + 0.002, 6)
    assert result.cost_usd == round(0.001 + 0.002, 6)

    # Initial capture + one FRESH capture for the tool_result.
    assert recorder.captures == 2

    # The follow-up history carries assistant_content then the tool_result
    # answering toolu_r1 with the fresh screenshot; the wrapper-level
    # screenshot argument is None (the image rides inside the tool_result).
    _user_input, followup_screenshot, followup_history = reasoner.calls[1]
    assert followup_screenshot is None
    assert followup_history[-2] == {"role": "assistant", "content": refresh_assistant}
    tool_result = followup_history[-1]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "toolu_r1"
    image_source = tool_result["content"][0]["source"]
    assert image_source["media_type"] == "image/png"
    assert base64.standard_b64decode(image_source["data"]) == PNG_BYTES

    # The refresh tool stayed internal — the overlay saw only the highlight
    # (physical coords; identity downscale stub leaves the bbox unchanged).
    assert recorder.shows == [((10, 20, 110, 60), "زر الحفظ")]
    assert result.spoken_text == "زر الحفظ هنا"


# ──────────────────────────────────────────────────────────────────────────
# Option B — tool_use/tool_result pairing keeps history API-valid
# ──────────────────────────────────────────────────────────────────────────


def _assert_no_orphan_tool_use(messages):
    """Anthropic pairing rule: every tool_use block must be answered by a
    tool_result with the SAME id in the IMMEDIATELY following message, and no
    stored message may carry empty content. This is exactly the validity the
    consecutive-turn 400 violated before Option B."""
    def blocks(msg):
        content = msg.get("content")
        return content if isinstance(content, list) else []

    for i, msg in enumerate(messages):
        assert blocks(msg), f"empty/non-list content at message {i}: {msg!r}"
        tool_use_ids = [b.get("id") for b in blocks(msg) if b.get("type") == "tool_use"]
        if not tool_use_ids:
            continue
        following = blocks(messages[i + 1]) if i + 1 < len(messages) else []
        answered = {b.get("tool_use_id") for b in following
                    if b.get("type") == "tool_result"}
        missing = [tid for tid in tool_use_ids if tid not in answered]
        assert not missing, f"orphan tool_use {missing} at message {i} (the API 400)"


_HIGHLIGHT_BLOCK = {
    "type": "tool_use", "id": "toolu_h1", "name": "highlight_target",
    "input": {"x1": 10, "y1": 20, "x2": 110, "y2": 60, "label_ar": "زر الحفظ"},
}


@pytest.mark.asyncio
async def test_highlight_tool_use_is_paired_with_tool_result(tmp_path):
    # A pointing turn now stores the highlight_target tool_use FOLLOWED by a
    # matching tool_result (Option B). Before the fix it was stored alone, and
    # the next turn's outgoing messages 400'd on the orphan.
    script = [
        TextDelta("زر الحفظ فوق"), _highlight(),
        _turn_complete(assistant_content=[
            {"type": "text", "text": "زر الحفظ فوق"}, _HIGHLIGHT_BLOCK]),
    ]
    orchestrator, _reasoner, _budget, _recorder = _orchestrator(tmp_path, [script])

    await orchestrator.run_turn("وين زر الحفظ؟")

    assert orchestrator.history[1]["content"][-1] == _HIGHLIGHT_BLOCK   # the tool_use
    assert orchestrator.history[2] == {                                 # its tool_result
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "toolu_h1",
                     "content": HIGHLIGHT_ACK_TEXT_AR}],
    }
    _assert_no_orphan_tool_use(orchestrator.history)


@pytest.mark.asyncio
async def test_two_turns_with_highlight_never_orphan_tool_use(tmp_path):
    # The exact regression: a turn that used highlight_target followed by another
    # turn must NOT raise and must NOT replay an orphan tool_use (the 400).
    scripts = [
        [TextDelta("زر الحفظ فوق"), _highlight(),
         _turn_complete(assistant_content=[
             {"type": "text", "text": "زر الحفظ فوق"}, _HIGHLIGHT_BLOCK])],
        [TextDelta("تحت قائمة File"),
         _turn_complete(assistant_content=[{"type": "text", "text": "تحت قائمة File"}])],
    ]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("وين زر الحفظ؟")
    await orchestrator.run_turn("وقائمة الفتح؟")   # would have 400'd pre-fix

    # The history the SECOND turn received already pairs turn one's tool_use.
    _user_input, _screenshot, turn2_history = reasoner.calls[1]
    assert turn2_history[1]["content"][-1]["type"] == "tool_use"
    assert turn2_history[2]["content"][0]["type"] == "tool_result"
    _assert_no_orphan_tool_use(turn2_history)
    _assert_no_orphan_tool_use(orchestrator.history)


@pytest.mark.asyncio
async def test_refresh_followup_limit_still_pairs_tool_use(tmp_path):
    # When the model asks to refresh MORE than MAX_REFRESH_FOLLOWUPS, the
    # declined refresh tool_use must STILL be paired (with a text note) so the
    # next turn is not an orphan — the limit branch no longer dangles a tool_use.
    def _refresh(tool_use_id):
        return ToolCall(name="request_screen_refresh", args={}, tool_use_id=tool_use_id)

    def _refresh_block(tool_use_id):
        return {"type": "tool_use", "id": tool_use_id,
                "name": "request_screen_refresh", "input": {}}

    scripts = [
        [_refresh("toolu_r1"), _turn_complete(
            stop_reason="tool_use", assistant_content=[_refresh_block("toolu_r1")])],
        [_refresh("toolu_r2"), _turn_complete(
            stop_reason="tool_use", assistant_content=[_refresh_block("toolu_r2")])],
    ]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("وين زر الحفظ؟")

    assert len(reasoner.calls) == 2                    # one follow-up, then stopped
    _assert_no_orphan_tool_use(orchestrator.history)   # the 2nd refresh is paired too


# ──────────────────────────────────────────────────────────────────────────
# Agentic loop — point THEN explain (the dual-action fix)
# ──────────────────────────────────────────────────────────────────────────


def _assert_strict_alternation(messages):
    """The point→explain path stores cleanly alternating roles — no two
    consecutive same-role messages, and no empty-content message."""
    roles = [m["role"] for m in messages]
    assert all(a != b for a, b in zip(roles, roles[1:])), roles
    for i, m in enumerate(messages):
        assert m.get("content"), f"empty content at message {i}: {m!r}"


@pytest.mark.asyncio
async def test_dual_action_points_then_speaks_the_continuation(tmp_path):
    # Call 1: intro text + highlight, stop_reason=tool_use — Muthis PAUSED to point.
    # Call 2: the explanation he planned AFTER pointing, stop_reason=end_turn.
    scripts = [
        [TextDelta("شوف، هذا اللي تسأل عنه"), _highlight(),
         _turn_complete(cost_usd=0.001, stop_reason="tool_use", assistant_content=[
             {"type": "text", "text": "شوف، هذا اللي تسأل عنه"}, _HIGHLIGHT_BLOCK])],
        [TextDelta("هذا زر الحفظ، اضغطه لتخزين ملفك."),
         _turn_complete(cost_usd=0.002, stop_reason="end_turn", assistant_content=[
             {"type": "text", "text": "هذا زر الحفظ، اضغطه لتخزين ملفك."}])],
    ]
    orchestrator, reasoner, budget, recorder = _orchestrator(tmp_path, scripts)

    result = await orchestrator.run_turn("وين زر الحفظ؟")

    # run() was called TWICE — the loop continued past the tool_use pause instead
    # of hanging, and BOTH turns reached the TTS in order (Option B).
    assert len(reasoner.calls) == 2
    assert recorder.spoken == ["شوف، هذا اللي تسأل عنه", "هذا زر الحفظ، اضغطه لتخزين ملفك."]
    assert result.spoken_text == "".join(recorder.spoken)
    # The pointer was drawn exactly once (one highlight executed locally).
    assert recorder.shows == [((10, 20, 110, 60), "زر الحفظ")]
    # History: highlight tool_use → matching ack tool_result → the explanation.
    assert orchestrator.history[1]["content"][-1] == _HIGHLIGHT_BLOCK
    assert orchestrator.history[2] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "toolu_h1",
                     "content": HIGHLIGHT_ACK_TEXT_AR}]}
    assert orchestrator.history[3]["content"] == [
        {"type": "text", "text": "هذا زر الحفظ، اضغطه لتخزين ملفك."}]
    # Symptom-1 fix: the continuation REUSED the same fresh frame (the explain pass
    # is no longer blind); the highlight's tool_result is still the last stored message.
    assert reasoner.calls[1][1] == PNG_BYTES
    assert reasoner.calls[1][2][-1]["content"][0]["type"] == "tool_result"
    assert result.stop_reason == "end_turn"
    _assert_no_orphan_tool_use(orchestrator.history)


@pytest.mark.asyncio
async def test_explain_pass_keeps_the_same_fresh_frame(tmp_path):
    # Symptom-1 regression guard: after pointing in iteration 0, the explain pass
    # (iteration 1) must STILL see the SAME fresh frame. Before the fix the frame
    # was dropped on the continuation (screenshot=None + text-only history), so the
    # explain pass went BLIND and re-fired request_screen_refresh despite having
    # just pointed correctly. The frame must stay attached for the whole user turn.
    scripts = [
        [TextDelta("شوف، هذا اللي تسأل عنه"), _highlight(),
         _turn_complete(cost_usd=0.001, stop_reason="tool_use", assistant_content=[
             {"type": "text", "text": "شوف، هذا اللي تسأل عنه"}, _HIGHLIGHT_BLOCK])],
        [TextDelta("هذا زر الحفظ، اضغطه لحفظ ملفك."),
         _turn_complete(cost_usd=0.002, stop_reason="end_turn", assistant_content=[
             {"type": "text", "text": "هذا زر الحفظ، اضغطه لحفظ ملفك."}])],
    ]
    orchestrator, reasoner, _budget, recorder = _orchestrator(tmp_path, scripts)

    result = await orchestrator.run_turn("وين زر الحفظ؟")

    # The point pass AND the explain pass BOTH saw the same fresh frame...
    assert len(reasoner.calls) == 2
    assert reasoner.calls[0][1] == PNG_BYTES
    assert reasoner.calls[1][1] == PNG_BYTES        # the fix — NOT None
    # ...grabbed exactly ONCE (the reuse is not a re-capture; Bug 3 ghosting intact).
    assert recorder.captures == 1
    # No needless refresh, and both planned messages were spoken in order.
    assert all(c.name != "request_screen_refresh" for c in result.tool_calls)
    assert recorder.spoken == [
        "شوف، هذا اللي تسأل عنه", "هذا زر الحفظ، اضغطه لحفظ ملفك."]
    # Bug 3 stays intact: the reused frame is ephemeral — NO image is ever stored.
    assert _image_blocks(orchestrator.history) == []
    _assert_no_orphan_tool_use(orchestrator.history)


@pytest.mark.asyncio
async def test_history_stays_api_valid_through_the_loop(tmp_path):
    # user → assistant(tool_use) → user(tool_result) → assistant(text): paired,
    # strictly alternating, no orphan, no empty message.
    scripts = [
        [TextDelta("شوف هنا"), _highlight(), _turn_complete(
            stop_reason="tool_use", assistant_content=[
                {"type": "text", "text": "شوف هنا"}, _HIGHLIGHT_BLOCK])],
        [TextDelta("هذا هو الزر المطلوب."), _turn_complete(
            stop_reason="end_turn",
            assistant_content=[{"type": "text", "text": "هذا هو الزر المطلوب."}])],
    ]
    orchestrator, _reasoner, _budget, _recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("وين زر الحفظ؟")

    assert [m["role"] for m in orchestrator.history] == [
        "user", "assistant", "user", "assistant"]
    _assert_strict_alternation(orchestrator.history)
    _assert_no_orphan_tool_use(orchestrator.history)


@pytest.mark.asyncio
async def test_agentic_loop_stops_at_the_safety_cap(tmp_path):
    # A model that NEVER says end_turn — it points again every turn. The cap must
    # bound it to MAX_AGENTIC_ITERATIONS run() calls, then stop with a spoken note.
    def _point(i):
        block = {"type": "tool_use", "id": f"toolu_{i}", "name": "highlight_target",
                 "input": {"x1": 10, "y1": 20, "x2": 110, "y2": 60, "label_ar": "زر"}}
        return [TextDelta("هنا"), _highlight(tool_use_id=f"toolu_{i}"),
                _turn_complete(cost_usd=0.0001, stop_reason="tool_use",
                               assistant_content=[{"type": "text", "text": "هنا"}, block])]

    scripts = [_point(i) for i in range(MAX_AGENTIC_ITERATIONS + 2)]  # more than the cap
    orchestrator, reasoner, _budget, recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("وين كل الأزرار؟")

    assert len(reasoner.calls) == MAX_AGENTIC_ITERATIONS      # never exceeded the cap
    assert recorder.spoken[-1] == AGENTIC_CAP_NOTE_AR         # clean spoken stop
    assert recorder.spoken.count(AGENTIC_CAP_NOTE_AR) == 1    # spoken exactly once
    _assert_no_orphan_tool_use(orchestrator.history)          # still API-valid


@pytest.mark.asyncio
async def test_budget_closes_mid_loop_and_skips_the_continuation(tmp_path):
    # The limit equals turn 1's cost: turn 1 affords, then record_turn closes the
    # gate, so the continuation is refused in Arabic and run() is NOT called again.
    scripts = [
        [TextDelta("شوف هنا"), _highlight(), _turn_complete(
            cost_usd=0.001, stop_reason="tool_use", assistant_content=[
                {"type": "text", "text": "شوف هنا"}, _HIGHLIGHT_BLOCK])],
        [TextDelta("لا يفترض يوصل"), _turn_complete(stop_reason="end_turn")],  # unreached
    ]
    orchestrator, reasoner, _budget, recorder = _orchestrator(
        tmp_path, scripts, daily_limit_usd=0.001)

    result = await orchestrator.run_turn("وين زر الحفظ؟")

    assert len(reasoner.calls) == 1                  # the continuation was NEVER called
    assert result.budget_blocked
    assert recorder.spoken == ["شوف هنا", BUDGET_REFUSAL_AR]
    _assert_no_orphan_tool_use(orchestrator.history)   # turn 1 stays paired


@pytest.mark.asyncio
async def test_abnormal_stream_none_stop_reason_ends_without_hang(tmp_path, caplog):
    # A stream that ends with stop_reason=None must NOT be treated as a tool_use
    # continuation: the loop ends cleanly with an English warning (no hang).
    scripts = [[TextDelta("جزء من الجواب"), _turn_complete(
        stop_reason=None,
        assistant_content=[{"type": "text", "text": "جزء من الجواب"}])]]
    orchestrator, reasoner, _budget, recorder = _orchestrator(tmp_path, scripts)

    with caplog.at_level("WARNING"):
        result = await orchestrator.run_turn("وش هذا؟")

    assert len(reasoner.calls) == 1              # did NOT loop / hang
    assert recorder.spoken == ["جزء من الجواب"]    # the partial text still spoken
    assert "stop_reason=None" in caplog.text       # English warning logged
    assert not result.timed_out


@pytest.mark.asyncio
async def test_refresh_inside_loop_hides_overlay_before_capture(tmp_path):
    # Ghosting rule, in-loop: the fresh capture for a request_screen_refresh that
    # happens INSIDE the agentic loop must still be preceded by an overlay hide —
    # so Claude never sees a baked-in ghost of its earlier highlight.
    refresh = ToolCall(name="request_screen_refresh", args={}, tool_use_id="toolu_r1")
    scripts = [
        [refresh, _turn_complete(stop_reason="tool_use", assistant_content=[
            {"type": "tool_use", "id": "toolu_r1",
             "name": "request_screen_refresh", "input": {}}])],
        [TextDelta("تم التحديث، هذا هو العنصر."), _turn_complete(stop_reason="end_turn")],
    ]
    orchestrator, _reasoner, _budget, recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("حدّث الشاشة")

    assert recorder.captures == 2                       # initial + the in-loop refresh
    captures_at = [i for i, e in enumerate(recorder.events) if e == "capture"]
    assert len(captures_at) == 2, recorder.events
    for i in captures_at:                               # every grab is preceded by a hide
        assert i > 0 and recorder.events[i - 1] == "hide", recorder.events


# ──────────────────────────────────────────────────────────────────────────
# Bug 3 — a request_screen_refresh frame must NEVER persist across user turns
# (the app-switch hallucination: a stale screenshot left in history). The frame
# is delivered to its own turn's iteration, then stripped before the next turn.
# ──────────────────────────────────────────────────────────────────────────


def _image_blocks(history):
    """Every image block anywhere in history — top-level OR nested inside a
    tool_result. Bug 3 is exactly a stale screenshot lingering here."""
    found = []
    for message in history:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "image":
                found.append(block)
            elif (block.get("type") == "tool_result"
                  and isinstance(block.get("content"), list)):
                found += [b for b in block["content"] if b.get("type") == "image"]
    return found


def _refresh_call(tool_use_id="toolu_r1"):
    return ToolCall(name="request_screen_refresh", args={}, tool_use_id=tool_use_id)


def _refresh_block(tool_use_id="toolu_r1"):
    return {"type": "tool_use", "id": tool_use_id,
            "name": "request_screen_refresh", "input": {}}


@pytest.mark.asyncio
async def test_fresh_frame_captured_once_per_utterance_before_the_loop(tmp_path):
    # Requirement: a NEW user turn grabs ONE fresh frame, BEFORE the agentic loop,
    # AFTER hiding the overlay (ghosting). The loop's internal iterations reuse the
    # turn context — they do NOT re-capture or inject a new image per pass.
    scripts = [
        [TextDelta("شوف هنا"), _highlight(), _turn_complete(
            stop_reason="tool_use", assistant_content=[
                {"type": "text", "text": "شوف هنا"}, _HIGHLIGHT_BLOCK])],
        [TextDelta("هذا هو الزر."), _turn_complete(
            stop_reason="end_turn",
            assistant_content=[{"type": "text", "text": "هذا هو الزر."}])],
    ]
    orchestrator, reasoner, _budget, recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("وين زر الحفظ؟")

    # TWO run() iterations (point then explain) but only ONE capture — the frame is
    # grabbed once per utterance, not once per loop pass.
    assert len(reasoner.calls) == 2
    assert recorder.captures == 1
    # That single capture happened BEFORE the first run(), preceded by a hide.
    assert recorder.events[0] == "hide"
    assert recorder.events[1] == "capture"
    assert reasoner.calls[0][1] == PNG_BYTES     # the turn's image went to the first run()
    assert reasoner.calls[1][1] == PNG_BYTES     # SAME frame reused — captured once, not re-grabbed


@pytest.mark.asyncio
async def test_refresh_frame_reaches_followup_then_strips_from_history(tmp_path):
    # The fix's core: the fresh frame IS delivered to the follow-up iteration
    # (inside the tool_result) — yet is GONE from stored history the moment the
    # turn ends, so it can never replay on a later turn.
    scripts = [
        [_refresh_call(), _turn_complete(
            stop_reason="tool_use", assistant_content=[_refresh_block()])],
        [TextDelta("هذا هو العنصر."), _turn_complete(
            stop_reason="end_turn",
            assistant_content=[{"type": "text", "text": "هذا هو العنصر."}])],
    ]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("وين زر الحفظ؟")

    # The follow-up run() SAW the fresh image inside the tool_result: the snapshot
    # is taken DURING the turn, before the post-turn strip (non-mutating proof).
    assert _image_blocks(reasoner.calls[1][2]), "the refresh frame must reach the follow-up"

    # Stored history is now image-free — the frame was stripped at turn-end.
    assert _image_blocks(orchestrator.history) == []
    # The pairing stays intact — same tool_use_id, a text note instead of pixels.
    refresh_result = orchestrator.history[2]["content"][0]
    assert refresh_result["type"] == "tool_result"
    assert refresh_result["tool_use_id"] == "toolu_r1"
    assert refresh_result["content"] == [
        {"type": "text", "text": STALE_SCREENSHOT_NOTE_AR}]
    _assert_no_orphan_tool_use(orchestrator.history)


@pytest.mark.asyncio
async def test_stale_refresh_frame_absent_on_the_next_user_turn(tmp_path):
    # The app-switch scenario: turn 1 uses request_screen_refresh (frame A); turn 2
    # is a new utterance. Turn 2's run() must receive a history with NO image — so
    # the model can't reason about a since-closed app — plus its OWN fresh frame B.
    scripts = [
        [_refresh_call(), _turn_complete(
            stop_reason="tool_use", assistant_content=[_refresh_block()])],
        [TextDelta("هذا هو العنصر."), _turn_complete(
            stop_reason="end_turn",
            assistant_content=[{"type": "text", "text": "هذا هو العنصر."}])],
        [TextDelta("تحت قائمة File."), _turn_complete(
            stop_reason="end_turn",
            assistant_content=[{"type": "text", "text": "تحت قائمة File."}])],
    ]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("وين زر الحفظ؟")   # turn 1 — refresh frame A
    await orchestrator.run_turn("وقائمة الفتح؟")    # turn 2 — a brand-new utterance

    # Turn 2's FIRST run() (calls[2]) got a history with ZERO image blocks: there is
    # no stale frame A for the model to hallucinate from.
    turn2_history = reasoner.calls[2][2]
    assert _image_blocks(turn2_history) == []
    # Turn 2 still received its OWN fresh frame via the screenshot argument.
    assert reasoner.calls[2][1] == PNG_BYTES
    _assert_no_orphan_tool_use(turn2_history)


@pytest.mark.asyncio
async def test_strip_keeps_the_agentic_loop_unbroken(tmp_path):
    # The strip must not disturb the loop: refresh → follow-up → end_turn still runs
    # run() twice, captures the fresh frame once for the refresh, speaks the answer.
    scripts = [
        [_refresh_call(), _turn_complete(
            stop_reason="tool_use", assistant_content=[_refresh_block()])],
        [TextDelta("تم التحديث، هذا هو."), _turn_complete(
            stop_reason="end_turn",
            assistant_content=[{"type": "text", "text": "تم التحديث، هذا هو."}])],
    ]
    orchestrator, reasoner, _budget, recorder = _orchestrator(tmp_path, scripts)

    result = await orchestrator.run_turn("حدّث الشاشة")

    assert len(reasoner.calls) == 2                 # the loop continued past the refresh
    assert recorder.captures == 2                   # initial + ONE fresh refresh grab
    assert result.spoken_text == "تم التحديث، هذا هو."
    assert recorder.spoken[-1] == "تم التحديث، هذا هو."
    _assert_no_orphan_tool_use(orchestrator.history)


# ──────────────────────────────────────────────────────────────────────────
# Fix 1 — highlight circuit breaker (prompt directive + hard once-per-turn backstop)
#
# Keeping the screenshot attached across the loop made Claude re-see its own
# target and call highlight_target again and again until the budget cap, never
# explaining. The breaker is two layers: a STRICT tool_result directive (prompt)
# AND a hard once-per-turn backstop (no redraw + "already shown" on the 2nd call).
# ──────────────────────────────────────────────────────────────────────────


def _highlight_use(tool_use_id, label_ar="زر الحفظ"):
    """An assistant highlight_target tool_use block (pairs with _highlight())."""
    return {"type": "tool_use", "id": tool_use_id, "name": "highlight_target",
            "input": {"x1": 10, "y1": 20, "x2": 110, "y2": 60, "label_ar": label_ar}}


def test_highlight_ack_commands_immediate_explanation():
    # Pass-2 fix: the highlight_target tool_result is a COMMAND to explain NOW,
    # not a success announcement — no "بنجاح" completion framing that invited a
    # bare ack. It orders the explanation to START with the actual information.
    assert "شرحك" in HIGHLIGHT_ACK_TEXT_AR                  # "your explanation"
    assert "ابدأ بالمعلومة" in HIGHLIGHT_ACK_TEXT_AR        # start with the info
    assert "ما هو" in HIGHLIGHT_ACK_TEXT_AR                 # WHAT/why content order
    assert "بنجاح" not in HIGHLIGHT_ACK_TEXT_AR             # no task-complete framing
    assert HIGHLIGHT_ACK_TEXT_AR != "تم عرض الـ highlight على العنصر."  # old ack is gone
    # The reword also drops the "تم وضع المؤشّر …" COMPLETION LEAD (which read as
    # task-done) and opens by naming this an INTERNAL directive the user never
    # hears — so the model treats it as an order to explain, not a result to ack.
    assert not HIGHLIGHT_ACK_TEXT_AR.startswith("تم"), "ack must not open with a completion lead"
    assert "لا يراه المستخدم" in HIGHLIGHT_ACK_TEXT_AR      # framed as an internal directive


@pytest.mark.asyncio
async def test_second_highlight_in_a_turn_is_suppressed_and_told_to_explain(tmp_path):
    # Hard backstop: the model points (iter 0), then points AGAIN while explaining
    # (iter 1). The 2nd highlight must NOT redraw the overlay, must get the
    # "already shown — explain now" tool_result, and the turn must END (no loop).
    scripts = [
        [TextDelta("شوف هنا"), _highlight(tool_use_id="toolu_a"),
         _turn_complete(stop_reason="tool_use", assistant_content=[
             {"type": "text", "text": "شوف هنا"}, _highlight_use("toolu_a")])],
        [_highlight(tool_use_id="toolu_b"), TextDelta("هذا زر الحفظ لتخزين ملفك."),
         _turn_complete(stop_reason="end_turn", assistant_content=[
             _highlight_use("toolu_b"),
             {"type": "text", "text": "هذا زر الحفظ لتخزين ملفك."}])],
    ]
    orchestrator, reasoner, _budget, recorder = _orchestrator(tmp_path, scripts)

    result = await orchestrator.run_turn("وين زر الحفظ؟")

    # The loop ran exactly twice and ENDED cleanly — no infinite highlight loop.
    assert len(reasoner.calls) == 2
    assert result.stop_reason == "end_turn"
    # The overlay was drawn exactly ONCE (the first highlight); the 2nd was suppressed.
    assert recorder.shows == [((10, 20, 110, 60), "زر الحفظ")]
    # The explanation was still spoken — Muthis pointed THEN explained.
    assert recorder.spoken == ["شوف هنا", "هذا زر الحفظ لتخزين ملفك."]
    # tool_result texts: first = "explain now" directive, second = "already shown".
    first_ack = orchestrator.history[2]["content"][0]
    assert first_ack["tool_use_id"] == "toolu_a"
    assert first_ack["content"] == HIGHLIGHT_ACK_TEXT_AR
    second_ack = orchestrator.history[4]["content"][0]
    assert second_ack["tool_use_id"] == "toolu_b"
    assert second_ack["content"] == HIGHLIGHT_ALREADY_SHOWN_AR
    _assert_no_orphan_tool_use(orchestrator.history)


@pytest.mark.asyncio
async def test_two_highlights_in_one_pass_only_the_first_is_drawn(tmp_path):
    # Same pass, two highlight_target calls: only the FIRST draws; the SECOND is
    # suppressed AND gets the "already shown" tool_result (one draw per turn).
    script = [
        TextDelta("شوف"),
        _highlight(tool_use_id="toolu_a"), _highlight(tool_use_id="toolu_b"),
        _turn_complete(stop_reason="end_turn", assistant_content=[
            {"type": "text", "text": "شوف"},
            _highlight_use("toolu_a"), _highlight_use("toolu_b")]),
    ]
    orchestrator, reasoner, _budget, recorder = _orchestrator(tmp_path, [script])

    await orchestrator.run_turn("وين الزرين؟")

    assert len(reasoner.calls) == 1
    assert recorder.shows == [((10, 20, 110, 60), "زر الحفظ")]   # exactly one draw
    results = orchestrator.history[2]["content"]                 # both tool_results, one message
    assert [b["content"] for b in results] == [
        HIGHLIGHT_ACK_TEXT_AR, HIGHLIGHT_ALREADY_SHOWN_AR]
    _assert_no_orphan_tool_use(orchestrator.history)


@pytest.mark.asyncio
async def test_highlight_gate_resets_on_a_new_user_turn(tmp_path):
    # The "already highlighted" flag is PER-TURN: turn 1 points; turn 2 is a NEW
    # utterance, so its FIRST highlight draws again (the gate is rebuilt per turn).
    scripts = [
        [_highlight(tool_use_id="toolu_a1"), TextDelta("شوف هنا"),
         _turn_complete(stop_reason="end_turn", assistant_content=[
             _highlight_use("toolu_a1"), {"type": "text", "text": "شوف هنا"}])],
        [_highlight(tool_use_id="toolu_b1"), TextDelta("وهنا الثاني"),
         _turn_complete(stop_reason="end_turn", assistant_content=[
             _highlight_use("toolu_b1"), {"type": "text", "text": "وهنا الثاني"}])],
    ]
    orchestrator, _reasoner, _budget, recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("وين زر الحفظ؟")
    assert recorder.shows == [((10, 20, 110, 60), "زر الحفظ")]          # turn 1 drew once

    await orchestrator.run_turn("وقائمة الفتح؟")
    # Turn 2's first highlight drew AGAIN — the gate reset, not stuck "drawn".
    assert recorder.shows == [
        ((10, 20, 110, 60), "زر الحفظ"), ((10, 20, 110, 60), "زر الحفظ")]
    # Each turn's first-highlight tool_result is the "explain now" directive — the
    # "already shown" note never appears, proving the flag did not leak forward.
    acks = [b["content"] for m in orchestrator.history
            if isinstance(m["content"], list)
            for b in m["content"]
            if isinstance(b, dict) and b.get("type") == "tool_result"]
    assert acks == [HIGHLIGHT_ACK_TEXT_AR, HIGHLIGHT_ACK_TEXT_AR]
    assert HIGHLIGHT_ALREADY_SHOWN_AR not in acks


# ──────────────────────────────────────────────────────────────────────────
# Fix A (root) — HARD loop termination via tool_choice="none" after a highlight
#
# The HighlightGate suppresses the DRAW but not the loop; the real terminator is
# tool_choice="none" on the post-highlight pass, so Claude CANNOT call a tool and
# MUST emit text → stop_reason end_turn → the loop ends (API-enforced, not a nudge).
# ──────────────────────────────────────────────────────────────────────────


class _AlwaysPointsReasoner:
    """Models the real API tool_choice contract: on "auto" it points
    (highlight_target + stop_reason tool_use); on "none" it CANNOT call a tool,
    so it explains in text and ends the turn. Proves termination comes from
    tool_choice="none", NOT from MAX_AGENTIC_ITERATIONS."""

    def __init__(self):
        self.calls = 0
        self.tool_choices = []

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.calls += 1
        self.tool_choices.append(tool_choice)
        if tool_choice == "none":
            yield TextDelta("هذا زر الحفظ، اضغطه لحفظ ملفك.")
            yield _turn_complete(stop_reason="end_turn", assistant_content=[
                {"type": "text", "text": "هذا زر الحفظ، اضغطه لحفظ ملفك."}])
        else:
            tid = f"toolu_{self.calls}"
            yield TextDelta("شوف هنا")
            yield _highlight(tool_use_id=tid)
            yield _turn_complete(stop_reason="tool_use", assistant_content=[
                {"type": "text", "text": "شوف هنا"}, _highlight_use(tid)])


def _orchestrator_with(reasoner, tmp_path, daily_limit_usd=1.0):
    budget = Budget(
        daily_limit_usd=daily_limit_usd, budget_file=tmp_path / "budget.json",
        today_fn=lambda: "2026-06-11")
    recorder = Recorder()
    orchestrator = Orchestrator(
        reasoner=reasoner, budget=budget, tts=recorder.tts, overlay=recorder,
        screen_capture=recorder.screen_capture)
    return orchestrator, recorder, budget


@pytest.mark.asyncio
async def test_tool_choice_none_terminates_loop_after_one_highlight(tmp_path):
    # A model that ALWAYS tries to point: pass 0 ("auto") points, pass 1 is forced
    # "none" → it MUST explain in text → end_turn → loop ends in 2 passes, NOT 4.
    reasoner = _AlwaysPointsReasoner()
    orchestrator, recorder, budget = _orchestrator_with(reasoner, tmp_path)

    result = await orchestrator.run_turn("وين زر الحفظ؟")

    assert reasoner.calls == 2                          # NOT MAX_AGENTIC_ITERATIONS (4)
    assert reasoner.tool_choices == ["auto", "none"]    # forced none after the draw
    assert result.stop_reason == "end_turn"
    assert recorder.shows == [((10, 20, 110, 60), "زر الحفظ")]   # drawn exactly once
    assert recorder.spoken[-1] == "هذا زر الحفظ، اضغطه لحفظ ملفك."
    assert budget.spent_today_usd() == round(0.0025 * 2, 6)      # only 2 calls billed
    _assert_no_orphan_tool_use(orchestrator.history)


@pytest.mark.asyncio
async def test_tool_choice_is_auto_on_first_pass_none_after_highlight(tmp_path):
    # Plumbing: pass 1 is "auto" (the model may point); the post-highlight pass is
    # "none".
    scripts = [
        [TextDelta("شوف هنا"), _highlight(tool_use_id="toolu_a"),
         _turn_complete(stop_reason="tool_use", assistant_content=[
             {"type": "text", "text": "شوف هنا"}, _highlight_use("toolu_a")])],
        [TextDelta("هذا زر الحفظ."), _turn_complete(
            stop_reason="end_turn",
            assistant_content=[{"type": "text", "text": "هذا زر الحفظ."}])],
    ]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("وين زر الحفظ؟")

    assert reasoner.tool_choices == ["auto", "none"]


@pytest.mark.asyncio
async def test_refresh_pass_is_not_forced_to_none(tmp_path):
    # A request_screen_refresh does NOT set gate.drawn, so its follow-up pass stays
    # "auto" — the model can still point at the fresh image. Only a highlight forces
    # "none".
    scripts = [
        [_refresh_call(), _turn_complete(
            stop_reason="tool_use", assistant_content=[_refresh_block()])],
        [TextDelta("زر الحفظ هنا"), _highlight(), _turn_complete(
            stop_reason="end_turn",
            assistant_content=[{"type": "text", "text": "زر الحفظ هنا"}])],
    ]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("وين زر الحفظ؟")

    assert reasoner.tool_choices == ["auto", "auto"]   # refresh follow-up NOT forced none


# ──────────────────────────────────────────────────────────────────────────
# Verbosity wiring (v5 Phase B3): the internal directive rides the USER message
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exact_n_voice_command_attaches_the_directive_to_the_user_message(tmp_path):
    # "بخمس كلمات" → the EXACT_N internal directive is prepended to the very
    # transcript handed to the reasoner (option A: the system prompt is frozen,
    # so the verbosity signal rides the user message), transcript kept intact.
    script = [TextDelta("تم"), _turn_complete()]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, [script])

    await orchestrator.run_turn("جاوب بخمس كلمات وش زر Save؟")

    user_input, _screenshot, _history = reasoner.calls[0]
    directive_line = user_input.text.split("\n")[0]
    assert directive_line.startswith(DIRECTIVE_OPEN_AR)
    assert "5" in directive_line                        # the requested word count
    assert user_input.text.endswith("جاوب بخمس كلمات وش زر Save؟")


@pytest.mark.asyncio
async def test_plain_turn_carries_no_internal_directive(tmp_path):
    # NORMAL (no voice command) → the transcript flows through verbatim.
    script = [TextDelta("زر الحفظ فوق"), _turn_complete()]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, [script])

    await orchestrator.run_turn("وين زر الحفظ؟")

    user_input, _screenshot, _history = reasoner.calls[0]
    assert user_input.text == "وين زر الحفظ؟"
    assert DIRECTIVE_OPEN_AR not in user_input.text


@pytest.mark.asyncio
async def test_directive_is_not_reattached_on_agentic_continuations(tmp_path):
    # The directive is attached ONCE per utterance: the point→explain
    # continuation (empty user text) must NOT get a second copy.
    scripts = [
        [TextDelta("سم"), _highlight("toolu_v1"),
         _turn_complete(stop_reason="tool_use", assistant_content=[
             {"type": "text", "text": "سم"},
             {"type": "tool_use", "id": "toolu_v1", "name": "highlight_target",
              "input": {"x1": 10, "y1": 20, "x2": 110, "y2": 60}}])],
        [TextDelta("هذا زر الحفظ."), _turn_complete(
            stop_reason="end_turn",
            assistant_content=[{"type": "text", "text": "هذا زر الحفظ."}])],
    ]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("باختصار وين زر الحفظ؟")

    first_input, _s, _h = reasoner.calls[0]
    continuation_input, _s2, _h2 = reasoner.calls[1]
    assert first_input.text.startswith(DIRECTIVE_OPEN_AR)   # attached once…
    assert continuation_input.text == ""                    # …never re-attached


# ──────────────────────────────────────────────────────────────────────────
# Verbosity persistence (v5 Phase B4): one-shot EXACT, sticky SHORT/DETAILED
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exact_n_is_one_shot_and_gone_on_the_next_turn(tmp_path):
    # The decay unit is the WHOLE utterance: the directive rides its own turn,
    # then the next user turn is back to NORMAL (no directive).
    scripts = [[TextDelta("تم"), _turn_complete()],
               [TextDelta("زر الحفظ فوق"), _turn_complete()]]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("جاوب بخمس كلمات وش هذا؟")
    await orchestrator.run_turn("ووين زر الحفظ؟")

    first, second = reasoner.calls[0][0], reasoner.calls[1][0]
    assert first.text.startswith(DIRECTIVE_OPEN_AR)
    assert DIRECTIVE_OPEN_AR not in second.text         # decayed after ONE utterance


@pytest.mark.asyncio
async def test_short_stays_sticky_and_a_new_command_replaces_it(tmp_path):
    # Sticky by decision: SHORT survives whole turns until another command
    # (here DETAILED) replaces it.
    scripts = [[TextDelta("سم"), _turn_complete()] for _ in range(3)]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("اختصر")                       # sticky SHORT on
    await orchestrator.run_turn("وش هذا الزر؟")                 # plain — persists
    await orchestrator.run_turn("اشرح لي بالتفصيل وش يسوي")     # switch → DETAILED

    second, third = reasoner.calls[1][0], reasoner.calls[2][0]
    assert second.text.startswith(DIRECTIVE_OPEN_AR)           # SHORT survived
    assert "الإيجاز" in second.text.split("\n")[0]
    assert "التفصيل" in third.text.split("\n")[0]              # replaced by DETAILED


@pytest.mark.asyncio
async def test_reset_phrase_returns_to_normal_across_turns(tmp_path):
    scripts = [[TextDelta("سم"), _turn_complete()] for _ in range(3)]
    orchestrator, reasoner, _budget, _recorder = _orchestrator(tmp_path, scripts)

    await orchestrator.run_turn("اختصر")                       # sticky SHORT on
    await orchestrator.run_turn("رجّع طولك الطبيعي")            # reset → NORMAL
    await orchestrator.run_turn("وش هذا؟")                     # stays NORMAL after

    reset_turn, after = reasoner.calls[1][0], reasoner.calls[2][0]
    assert DIRECTIVE_OPEN_AR not in reset_turn.text            # NORMAL emits nothing
    assert DIRECTIVE_OPEN_AR not in after.text
