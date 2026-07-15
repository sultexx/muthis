"""
test_orchestrator_tts.py — the real-TTS wiring tests (buffer-then-speak).

No network, no audio, fully deterministic. FakeTTS has the EXACT call shape
of muthis.tts.TTS.speak (str → TTSResult), so the injection seam proven here
is the same one production uses: Orchestrator(..., tts=TTS().speak).

Covers:
  - one assistant message → exactly one speak() with the full TextDelta text
  - THREE separate sentences → ONE speak() with the full concatenated text
    (the anti-streaming regression guard: streaming would have spoken 3×)
  - a stream that ends WITHOUT TurnComplete returns promptly — no never-arriving
    signal to await (the no-hang guard that keeps is_processing releasable)
  - privacy boundary: the TTS never sees the user transcript or tool JSON
  - a budget-blocked turn still speaks the Arabic refusal (provider untouched)
  - a failing TTSResult(success=False, provider="none") never breaks the turn

Run:  pytest tests/test_orchestrator_tts.py -q
"""

from __future__ import annotations

import asyncio

import pytest

from muthis.budget import Budget
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.orchestrator import BUDGET_REFUSAL_AR, Orchestrator
from muthis.tts import TTSResult

# ──────────────────────────────────────────────────────────────────────────
# Fakes and helpers
# ──────────────────────────────────────────────────────────────────────────

# Deliberately PII-laden transcript — it must NEVER reach the TTS.
USER_TEXT_AR = "وين زر الحفظ؟ رقم حسابي 12345"
ASSISTANT_TEXT_AR = "زر الحفظ فوق يسار"


class FakeReasoner:
    """Scripted CloudReasoner: each run() call replays the next event list
    and records exactly what the orchestrator handed it."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls = []  # (user_input, screenshot, history) per run()

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.calls.append((user_input, screenshot, history))
        for event in self._scripts.pop(0):
            yield event


class FakeTTS:
    """Same call shape as muthis.tts.TTS.speak — records every utterance
    and answers with a canned TTSResult (never raises, like the real one)."""

    def __init__(self, result=TTSResult(success=True, provider="elevenlabs")):
        self.spoken = []
        self._result = result

    async def speak(self, text):
        self.spoken.append(text)
        return self._result


def _turn_complete(cost_usd=0.0025):
    return TurnComplete(
        input_tokens=850,
        output_tokens=64,
        cost_usd=cost_usd,
        stop_reason="end_turn",
        model="claude-sonnet-4-6",
        assistant_content=[{"type": "text", "text": ASSISTANT_TEXT_AR}],
    )


def _highlight():
    return ToolCall(
        name="highlight_target",
        args={"x1": 10, "y1": 20, "x2": 110, "y2": 60, "label_ar": "زر الحفظ"},
        tool_use_id="toolu_h1",
    )


def _orchestrator(tmp_path, scripts, *, fake_tts, daily_limit_usd=1.0):
    reasoner = FakeReasoner(scripts)
    budget = Budget(
        daily_limit_usd=daily_limit_usd,
        budget_file=tmp_path / "budget.json",
        today_fn=lambda: "2026-06-11",
    )
    orchestrator = Orchestrator(
        reasoner=reasoner,
        budget=budget,
        tts=fake_tts.speak,  # the production seam: Orchestrator(tts=TTS().speak)
    )
    return orchestrator, reasoner, budget


# ──────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assistant_message_spoken_exactly_once_with_full_text(tmp_path):
    script = [
        TextDelta("زر الحفظ "),
        TextDelta("فوق يسار"),
        _highlight(),
        _turn_complete(),
    ]
    fake_tts = FakeTTS()
    orchestrator, _reasoner, _budget = _orchestrator(
        tmp_path, [script], fake_tts=fake_tts,
    )

    result = await orchestrator.run_turn(USER_TEXT_AR)

    # Exactly ONE speak() per assistant message, with the full buffered text
    # equal to the accumulated TextDelta content.
    assert fake_tts.spoken == [ASSISTANT_TEXT_AR]
    assert fake_tts.spoken[0] == result.spoken_text
    assert not result.budget_blocked and not result.timed_out


@pytest.mark.asyncio
async def test_tts_never_sees_user_transcript_or_tool_json(tmp_path):
    script = [
        TextDelta(ASSISTANT_TEXT_AR),
        _highlight(),
        _turn_complete(),
    ]
    fake_tts = FakeTTS()
    orchestrator, _reasoner, _budget = _orchestrator(
        tmp_path, [script], fake_tts=fake_tts,
    )

    await orchestrator.run_turn(USER_TEXT_AR)

    # Privacy boundary: ONLY the assistant's synthesized Arabic crossed.
    assert fake_tts.spoken == [ASSISTANT_TEXT_AR]
    for utterance in fake_tts.spoken:
        assert USER_TEXT_AR not in utterance      # never the user transcript
        assert "12345" not in utterance           # never transcript PII
        assert "toolu_h1" not in utterance        # never tool ids
        assert "x1" not in utterance              # never tool args
        assert "{" not in utterance               # never serialized JSON


@pytest.mark.asyncio
async def test_budget_blocked_turn_speaks_refusal_without_provider_call(tmp_path):
    fake_tts = FakeTTS()
    orchestrator, reasoner, _budget = _orchestrator(
        tmp_path, scripts=[], fake_tts=fake_tts, daily_limit_usd=0.0,
    )

    result = await orchestrator.run_turn(USER_TEXT_AR)

    assert result.budget_blocked
    assert reasoner.calls == []                    # ClaudeAgent.run NOT called
    assert fake_tts.spoken == [BUDGET_REFUSAL_AR]  # refusal spoken out loud


@pytest.mark.asyncio
async def test_turn_continues_when_tts_reports_total_failure(tmp_path):
    script = [TextDelta(ASSISTANT_TEXT_AR), _turn_complete(cost_usd=0.0025)]
    fake_tts = FakeTTS(
        result=TTSResult(success=False, provider="none", error="no audio device"),
    )
    orchestrator, _reasoner, budget = _orchestrator(
        tmp_path, [script], fake_tts=fake_tts,
    )

    result = await orchestrator.run_turn(USER_TEXT_AR)

    # Voice loss ≠ turn loss: text, accounting, and history all intact.
    assert fake_tts.spoken == [ASSISTANT_TEXT_AR]
    assert result.spoken_text == ASSISTANT_TEXT_AR
    assert not result.timed_out and not result.budget_blocked
    assert budget.spent_today_usd() == 0.0025
    assert len(orchestrator.history) == 2          # user + assistant recorded


@pytest.mark.asyncio
async def test_three_sentences_reach_tts_in_a_single_call(tmp_path):
    # The anti-streaming regression guard. Under the (now reverted) sentence-level
    # streaming, these THREE terminated sentences would have produced THREE speak()
    # calls. Buffer-then-speak accumulates the whole reply and speaks it ONCE.
    script = [
        TextDelta("الجملة الأولى. "),
        TextDelta("الجملة الثانية؟ "),
        TextDelta("الجملة الثالثة!"),
        _turn_complete(),
    ]
    fake_tts = FakeTTS()
    orchestrator, _reasoner, _budget = _orchestrator(
        tmp_path, [script], fake_tts=fake_tts,
    )

    result = await orchestrator.run_turn(USER_TEXT_AR)

    full_text = "الجملة الأولى. الجملة الثانية؟ الجملة الثالثة!"
    assert len(fake_tts.spoken) == 1               # ONE call, NOT three
    assert fake_tts.spoken == [full_text]          # the full concatenated reply
    assert fake_tts.spoken[0] == result.spoken_text


@pytest.mark.asyncio
async def test_stream_without_turncomplete_returns_promptly_without_hanging(tmp_path):
    # The no-hang guard. The reverted streaming path awaited a background consumer
    # that drained a queue until a None sentinel; a stream dying WITHOUT a
    # TurnComplete was the exact "never-arriving signal" that could leave the turn
    # (and thus main's is_processing) wedged. Buffer-then-speak awaits no such task,
    # so this path returns at once. wait_for turns any regression into a fast
    # failure instead of a hung test run.
    script = [TextDelta("رد بدون اكتمال")]  # NO TurnComplete — provider died mid-stream
    fake_tts = FakeTTS()
    orchestrator, _reasoner, _budget = _orchestrator(
        tmp_path, [script], fake_tts=fake_tts,
    )

    result = await asyncio.wait_for(orchestrator.run_turn(USER_TEXT_AR), timeout=5.0)

    assert result.timed_out is False               # returned normally, NOT via the 90 s bound
    assert fake_tts.spoken == []                   # death path speaks nothing (no cost, no audio)
    assert orchestrator.history == []              # nothing recorded on an incomplete turn


# ──────────────────────────────────────────────────────────────────────────
# Sentence streaming (v5 Phase C2) — flag-gated, tool_choice="none" passes ONLY
# ──────────────────────────────────────────────────────────────────────────


class FakeSpeechSession:
    """Same lifecycle shape as tts_session.SpeechSession (open/feed/close/
    got_audio) — records the sentences it was fed, in order."""

    def __init__(self, *, fail_open=False, fail_feed_at=None):
        self.fed = []
        self.opened = False
        self.closed = False
        self._fail_open = fail_open
        self._fail_feed_at = fail_feed_at     # raise on the Nth feed (0-based)

    async def open(self):
        if self._fail_open:
            raise ConnectionError("no route to ElevenLabs")
        self.opened = True

    async def feed(self, sentence):
        if self._fail_feed_at is not None and len(self.fed) >= self._fail_feed_at:
            raise ConnectionError("socket dropped")
        self.fed.append(sentence)

    async def close(self):
        self.closed = True

    @property
    def got_audio(self):
        return bool(self.fed)


class SessionFactory:
    def __init__(self, session):
        self.session = session
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.session


def _highlight_use(tool_use_id="toolu_h1"):
    return {"type": "tool_use", "id": tool_use_id, "name": "highlight_target",
            "input": {"x1": 10, "y1": 20, "x2": 110, "y2": 60}}


def _pass_complete(stop_reason, assistant_content):
    return TurnComplete(input_tokens=10, output_tokens=5, cost_usd=0.001,
                        stop_reason=stop_reason, model="m",
                        assistant_content=assistant_content)


def _dual_action_scripts(explain_text):
    """Pass 1 points (tool_use → 'auto'), pass 2 explains ('none') — C2's shape."""
    return [
        [TextDelta("سم"), _highlight(),
         _pass_complete("tool_use",
                        [{"type": "text", "text": "سم"}, _highlight_use()])],
        [TextDelta(explain_text),
         _pass_complete("end_turn", [{"type": "text", "text": explain_text}])],
    ]


def _streaming_orchestrator(tmp_path, scripts, *, fake_tts, factory, stream_tts=True):
    reasoner = FakeReasoner(scripts)
    budget = Budget(daily_limit_usd=1.0, budget_file=tmp_path / "budget.json",
                    today_fn=lambda: "2026-06-11")
    orchestrator = Orchestrator(
        reasoner=reasoner, budget=budget, tts=fake_tts.speak,
        stream_tts=stream_tts, speech_session_factory=factory,
    )
    return orchestrator


@pytest.mark.asyncio
async def test_explain_pass_streams_while_the_draw_pass_stays_buffered(tmp_path):
    fake_tts, session = FakeTTS(), FakeSpeechSession()
    factory = SessionFactory(session)
    scripts = _dual_action_scripts("هذا زر الحفظ. يحفظ ملفك بسرعة.")
    orchestrator = _streaming_orchestrator(tmp_path, scripts, fake_tts=fake_tts, factory=factory)

    await orchestrator.run_turn("وين زر الحفظ؟")

    # Pass 1 ("auto", drew the highlight) stayed on the buffered path.
    assert fake_tts.spoken == ["سم"]
    # Pass 2 ("none") streamed its sentences in order over ONE session.
    assert session.fed == ["هذا زر الحفظ.", "يحفظ ملفك بسرعة."]
    assert factory.calls == 1 and session.opened and session.closed


@pytest.mark.asyncio
async def test_pure_text_auto_pass_never_streams(tmp_path):
    # The inverted criterion: a single-pass reply runs with tool_choice="auto"
    # (a ToolCall COULD arrive mid-stream), so it must stay buffered even with
    # the flag ON.
    fake_tts, factory = FakeTTS(), SessionFactory(FakeSpeechSession())
    script = [[TextDelta("مرحبا. كيف أساعدك؟"), _turn_complete()]]
    orchestrator = _streaming_orchestrator(tmp_path, [script[0]], fake_tts=fake_tts, factory=factory)

    await orchestrator.run_turn("هلا")

    assert factory.calls == 0                          # never even opened
    assert fake_tts.spoken == ["مرحبا. كيف أساعدك؟"]   # ONE buffered call


@pytest.mark.asyncio
async def test_refresh_followup_is_auto_and_never_streams(tmp_path):
    fake_tts, factory = FakeTTS(), SessionFactory(FakeSpeechSession())
    refresh_use = {"type": "tool_use", "id": "toolu_r1",
                   "name": "request_screen_refresh", "input": {}}
    scripts = [
        [ToolCall(name="request_screen_refresh", args={}, tool_use_id="toolu_r1"),
         _pass_complete("tool_use", [refresh_use])],
        [TextDelta("بعد التحديث."),
         _pass_complete("end_turn", [{"type": "text", "text": "بعد التحديث."}])],
    ]
    orchestrator = _streaming_orchestrator(tmp_path, scripts, fake_tts=fake_tts, factory=factory)

    await orchestrator.run_turn("وش تشوف؟")

    assert factory.calls == 0                          # the follow-up stays "auto"
    assert fake_tts.spoken == ["بعد التحديث."]


@pytest.mark.asyncio
async def test_flag_off_by_default_keeps_the_explain_pass_buffered(tmp_path):
    # conftest cleared MUTHIS_STREAM_TTS → the env default is OFF.
    fake_tts, factory = FakeTTS(), SessionFactory(FakeSpeechSession())
    scripts = _dual_action_scripts("هذا زر الحفظ.")
    orchestrator = _streaming_orchestrator(
        tmp_path, scripts, fake_tts=fake_tts, factory=factory, stream_tts=None)

    await orchestrator.run_turn("وين زر الحفظ؟")

    assert factory.calls == 0
    assert fake_tts.spoken == ["سم", "هذا زر الحفظ."]  # today's behavior, intact


@pytest.mark.asyncio
async def test_env_flag_enables_streaming(tmp_path, monkeypatch):
    monkeypatch.setenv("MUTHIS_STREAM_TTS", "1")
    fake_tts, session = FakeTTS(), FakeSpeechSession()
    factory = SessionFactory(session)
    scripts = _dual_action_scripts("هذا زر الحفظ.")
    orchestrator = _streaming_orchestrator(
        tmp_path, scripts, fake_tts=fake_tts, factory=factory, stream_tts=None)

    await orchestrator.run_turn("وين زر الحفظ؟")

    assert session.fed == ["هذا زر الحفظ."]            # env alone switched it on


@pytest.mark.asyncio
async def test_session_open_failure_falls_back_to_one_buffered_speak(tmp_path):
    fake_tts, session = FakeTTS(), FakeSpeechSession(fail_open=True)
    factory = SessionFactory(session)
    scripts = _dual_action_scripts("هذا زر الحفظ. مفيد.")
    orchestrator = _streaming_orchestrator(tmp_path, scripts, fake_tts=fake_tts, factory=factory)

    await orchestrator.run_turn("وين زر الحفظ؟")

    assert session.fed == []
    assert fake_tts.spoken == ["سم", "هذا زر الحفظ. مفيد."]  # whole pass buffered


@pytest.mark.asyncio
async def test_mid_session_failure_speaks_the_remainder_in_one_call(tmp_path):
    # Decision 15: the first sentence played via the session; the socket then
    # drops — the UNPLAYED remainder goes through ONE buffered speak().
    fake_tts, session = FakeTTS(), FakeSpeechSession(fail_feed_at=1)
    factory = SessionFactory(session)
    scripts = _dual_action_scripts("الأولى نجحت. الثانية سقطت. الثالثة أيضاً.")
    orchestrator = _streaming_orchestrator(tmp_path, scripts, fake_tts=fake_tts, factory=factory)

    await orchestrator.run_turn("وين زر الحفظ؟")

    assert session.fed == ["الأولى نجحت."]
    assert fake_tts.spoken == ["سم", "الثانية سقطت. الثالثة أيضاً."]


# ──────────────────────────────────────────────────────────────────────────
# v6 C2: live captions through the FULL pipeline (flag-gated, privacy)
# ──────────────────────────────────────────────────────────────────────────


class CaptionRecordingOverlay:
    """Overlay double with the v6 caption seam; records shows/clears."""

    def __init__(self):
        self.captions = []
        self.caption_clears = 0

    async def show(self, bbox, label_ar):
        pass

    async def hide(self):
        pass

    def set_state(self, state):
        pass

    def clear_status_light(self):
        pass

    def show_caption(self, text):
        self.captions.append(text)

    def clear_caption(self):
        self.caption_clears += 1


@pytest.mark.asyncio
async def test_caption_bar_shows_only_assistant_speech_then_clears(tmp_path, monkeypatch):
    monkeypatch.setenv("MUTHIS_CAPTIONS", "1")
    from muthis.verbosity import DIRECTIVE_OPEN_AR

    script = [TextDelta(ASSISTANT_TEXT_AR), _turn_complete()]
    fake_tts = FakeTTS()
    overlay = CaptionRecordingOverlay()
    orchestrator = Orchestrator(
        reasoner=FakeReasoner([script]),
        budget=Budget(daily_limit_usd=1.0, budget_file=tmp_path / "budget.json",
                      today_fn=lambda: "2026-06-11"),
        tts=fake_tts.speak,
        overlay=overlay,
    )

    # A verbosity command in the transcript attaches an INTERNAL directive to
    # the user message — the bar must never render any of that.
    await orchestrator.run_turn("باختصار، " + USER_TEXT_AR)

    assert overlay.captions == [ASSISTANT_TEXT_AR]  # the spoken text, verbatim
    assert overlay.caption_clears >= 1              # cleared when audio finished
    for shown in overlay.captions:
        assert USER_TEXT_AR not in shown            # never the user transcript
        assert "12345" not in shown                 # never transcript PII
        assert DIRECTIVE_OPEN_AR not in shown       # never internal directives
        assert "{" not in shown                     # never tool JSON


@pytest.mark.asyncio
async def test_captions_default_off_keeps_the_bar_untouched(tmp_path):
    script = [TextDelta(ASSISTANT_TEXT_AR), _turn_complete()]
    fake_tts = FakeTTS()
    overlay = CaptionRecordingOverlay()
    orchestrator = Orchestrator(
        reasoner=FakeReasoner([script]),
        budget=Budget(daily_limit_usd=1.0, budget_file=tmp_path / "budget.json",
                      today_fn=lambda: "2026-06-11"),
        tts=fake_tts.speak,
        overlay=overlay,
    )

    await orchestrator.run_turn(USER_TEXT_AR)

    # conftest clears MUTHIS_CAPTIONS → today's behavior, bar untouched.
    assert overlay.captions == [] and overlay.caption_clears == 0
    assert fake_tts.spoken == [ASSISTANT_TEXT_AR]   # speech itself unchanged


# ──────────────────────────────────────────────────────────────────────────
# v6 C3: captions ride the STREAMED pass sentence-by-sentence
# ──────────────────────────────────────────────────────────────────────────


class StreamCaptionOverlay(CaptionRecordingOverlay):
    """Adds the order log: caption events interleaved with session feeds are
    asserted through the session's own record; here we log clears too."""

    def __init__(self):
        super().__init__()
        self.log = []

    def show_caption(self, text):
        super().show_caption(text)
        self.log.append(("show", text))

    def clear_caption(self):
        super().clear_caption()
        self.log.append(("clear",))


def _streaming_caption_orchestrator(tmp_path, scripts, *, fake_tts, factory, overlay):
    return Orchestrator(
        reasoner=FakeReasoner(scripts),
        budget=Budget(daily_limit_usd=1.0, budget_file=tmp_path / "budget.json",
                      today_fn=lambda: "2026-06-11"),
        tts=fake_tts.speak, overlay=overlay,
        stream_tts=True, speech_session_factory=factory,
    )


@pytest.mark.asyncio
async def test_streamed_captions_follow_the_sentences_in_order(tmp_path, monkeypatch):
    monkeypatch.setenv("MUTHIS_CAPTIONS", "1")
    fake_tts, session = FakeTTS(), FakeSpeechSession()
    factory = SessionFactory(session)
    overlay = StreamCaptionOverlay()
    scripts = _dual_action_scripts("هذا زر الحفظ. يحفظ ملفك بسرعة.")
    orchestrator = _streaming_caption_orchestrator(
        tmp_path, scripts, fake_tts=fake_tts, factory=factory, overlay=overlay)

    await orchestrator.run_turn("وين زر الحفظ؟")

    # Pass 1 (buffered ack) shows its caption via speak(); pass 2 streams:
    # each sentence lands on the bar exactly when it is fed to the ONE
    # session, and the bar clears when the generation drains.
    assert session.fed == ["هذا زر الحفظ.", "يحفظ ملفك بسرعة."]
    assert overlay.log == [
        ("show", "سم"), ("clear",),                      # pass 1: buffered ack
        ("show", "هذا زر الحفظ."),
        ("show", "يحفظ ملفك بسرعة."),
        ("clear",),                                       # session drained
    ]


@pytest.mark.asyncio
async def test_streamed_captions_off_by_default_even_when_streaming(tmp_path):
    # MUTHIS_STREAM_TTS ON but MUTHIS_CAPTIONS cleared by conftest → the
    # session still gets its sentences; the bar stays untouched.
    fake_tts, session = FakeTTS(), FakeSpeechSession()
    factory = SessionFactory(session)
    overlay = StreamCaptionOverlay()
    scripts = _dual_action_scripts("هذا زر الحفظ.")
    orchestrator = _streaming_caption_orchestrator(
        tmp_path, scripts, fake_tts=fake_tts, factory=factory, overlay=overlay)

    await orchestrator.run_turn("وين زر الحفظ؟")

    assert session.fed == ["هذا زر الحفظ."]
    assert overlay.captions == [] and overlay.caption_clears == 0


@pytest.mark.asyncio
async def test_mid_session_failure_reshows_the_spoken_remainder(tmp_path, monkeypatch):
    # Decision 15 path: sentence 1 plays via the session, the socket then dies;
    # the remainder is spoken through ONE buffered speak() — and the bar must
    # show what is ACTUALLY heard: sentence 1, then the remainder, never a
    # frozen dead sentence.
    monkeypatch.setenv("MUTHIS_CAPTIONS", "1")
    fake_tts, session = FakeTTS(), FakeSpeechSession(fail_feed_at=1)
    factory = SessionFactory(session)
    overlay = StreamCaptionOverlay()
    scripts = _dual_action_scripts("الأولى تلعب. الثانية تفشل. الثالثة معها.")
    orchestrator = _streaming_caption_orchestrator(
        tmp_path, scripts, fake_tts=fake_tts, factory=factory, overlay=overlay)

    await orchestrator.run_turn("وين زر الحفظ؟")

    assert session.fed == ["الأولى تلعب."]
    assert fake_tts.spoken[-1] == "الثانية تفشل. الثالثة معها."   # one buffered call
    assert overlay.log == [
        ("show", "سم"), ("clear",),                      # pass 1: buffered ack
        ("show", "الأولى تلعب."),                        # played via the session
        ("show", "الثانية تفشل."), ("clear",),           # died → bar unfrozen
        ("clear",),                                       # session close drained
        ("show", "الثانية تفشل. الثالثة معها."), ("clear",),  # fallback speak
    ]
