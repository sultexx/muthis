"""
test_turn_voice.py — the ONE continuous speech generation per turn (v7),
fakes only: no network, no audio device, no orchestrator.

Proves the stop-and-go fix contract: buffered pass text is FED (instant) into
the same lazy session streamed sentences join; the session opens at most ONCE
per turn and closes exactly once at finish(); degradation is decision-15 at
TURN level — never opened → live buffered speak per pass; died mid-turn → the
remainder is DEFERRED and spoken in ONE buffered call after the drain (never
overlapping the tail); nothing played → the WHOLE turn's text is re-spoken;
close-after-audio failure logs only. Captions ride the feeds and never freeze
on a dead sentence; the status light holds "speaking" across everything and
returns to "thinking" only at finish/abandon.

Run:  set PYTHONPATH=src && python -m pytest tests/test_turn_voice.py -q
"""

from __future__ import annotations

import pytest

from muthis.turn_voice import TurnVoice

# Long enough (≥ speech_stream.MIN_SENTENCE_CHARS) to stream as separate units.
S1 = "الجملة الأولى في هذا الاختبار طويلة كفاية."
S2 = "والجملة الثانية هنا طويلة كفاية أيضاً."


class FakeVoice:
    """VoiceOut double: records buffered speaks, the caption log, and the
    audio-pacing delay each caption was deferred by (v7 Phase 2)."""

    def __init__(self):
        self.spoken = []
        self.log = []
        self.caption_delays = []

    async def speak(self, text):
        self.log.append(("speak", text))
        self.spoken.append(text)

    def show_caption(self, text, delay_s=0.0):
        self.log.append(("show", text))
        self.caption_delays.append(delay_s)

    def clear_caption(self):
        self.log.append(("clear",))


class FakeOverlay:
    def __init__(self):
        self.states = []

    def set_state(self, state):
        self.states.append(state)


class FakeSession:
    def __init__(self, *, fail_open=False, fail_feed_at=None, fail_close=False,
                 silent=False):
        self.fed = []
        self.flushes = []              # the flush flag of each successful feed
        self.opened = False
        self.closed = False
        self.aborted = False           # barge-in (v7 Phase 3)
        self._fail_open = fail_open
        self._fail_feed_at = fail_feed_at
        self._fail_close = fail_close
        self._silent = silent          # got_audio stays False (no PCM arrived)

    async def open(self):
        if self._fail_open:
            raise ConnectionError("no route")
        self.opened = True

    async def feed(self, sentence, flush=False):
        if self._fail_feed_at is not None and len(self.fed) >= self._fail_feed_at:
            raise ConnectionError("socket dropped")
        self.fed.append(sentence)
        self.flushes.append(flush)

    async def close(self):
        self.closed = True
        if self._fail_close:
            raise RuntimeError("close failed")

    async def abort(self):
        self.aborted = True
        self.closed = True

    @property
    def got_audio(self):
        return bool(self.fed) and not self._silent


class Factory:
    def __init__(self, session):
        self.session = session
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.session


def _voice(session=None, *, enabled=True):
    fake_voice, overlay = FakeVoice(), FakeOverlay()
    factory = Factory(session) if session is not None else None
    turn_voice = TurnVoice(voice=fake_voice, overlay=overlay,
                           session_factory=factory, enabled=enabled)
    return turn_voice, fake_voice, overlay, factory


# ─────────────────────────────── Happy path ───────────────────────────────


@pytest.mark.asyncio
async def test_ack_and_streamed_sentences_ride_one_session():
    session = FakeSession()
    turn_voice, fake_voice, overlay, factory = _voice(session)

    await turn_voice.speak_or_feed("سم")               # pass 1 ack: instant feed
    await turn_voice.push_stream(S1 + " " + S2)        # pass 2 stream
    await turn_voice.end_stream()
    await turn_voice.finish()

    assert session.fed == ["سم", S1, S2]
    # A COMPLETE text (the ack) flushes so ElevenLabs synthesizes it NOW (a
    # 4-char ack held under the 90-char schedule floor defeated the mask);
    # streamed sentences never flush (per-feed forcing = the baked pauses).
    assert session.flushes == [True, False, False]
    assert fake_voice.spoken == []                      # nothing fell back
    assert factory.calls == 1 and session.opened and session.closed
    # The light held "speaking" for every feed; "thinking" only at finish.
    assert overlay.states == ["speaking", "speaking", "speaking", "thinking"]
    # Captions per feed; ONE clear when the generation drained.
    assert fake_voice.log == [
        ("show", "سم"), ("show", S1), ("show", S2), ("clear",)]


@pytest.mark.asyncio
async def test_empty_text_is_a_no_op():
    session = FakeSession()
    turn_voice, fake_voice, _overlay, factory = _voice(session)
    await turn_voice.speak_or_feed("")
    await turn_voice.finish()
    assert factory.calls == 0 and session.fed == [] and fake_voice.spoken == []


@pytest.mark.asyncio
async def test_finish_is_idempotent():
    session = FakeSession()
    turn_voice, fake_voice, _overlay, _factory = _voice(session)
    await turn_voice.speak_or_feed("سم")
    await turn_voice.finish()
    await turn_voice.finish()                           # run_turn's finally re-entry
    assert fake_voice.spoken == []                      # no double fallback


# ─────────────────────────── Buffered degradation ───────────────────────────


@pytest.mark.asyncio
async def test_disabled_turn_speaks_buffered_per_pass():
    turn_voice, fake_voice, overlay, _ = _voice(FakeSession(), enabled=False)
    await turn_voice.speak_or_feed("سم")
    await turn_voice.speak_or_feed(S1)
    await turn_voice.finish()                           # no session → no-op
    assert fake_voice.spoken == ["سم", S1]              # the proven blocking path
    assert overlay.states == []                          # VoiceOut owns the light here


@pytest.mark.asyncio
async def test_no_factory_means_buffered():
    turn_voice, fake_voice, _overlay, _ = _voice(None, enabled=True)
    await turn_voice.speak_or_feed(S1)
    await turn_voice.finish()
    assert fake_voice.spoken == [S1]


@pytest.mark.asyncio
async def test_open_failure_degrades_to_live_buffered_with_one_attempt():
    session = FakeSession(fail_open=True)
    turn_voice, fake_voice, _overlay, factory = _voice(session)
    await turn_voice.speak_or_feed("سم")
    await turn_voice.speak_or_feed(S1)                  # must NOT retry the open
    await turn_voice.finish()
    assert factory.calls == 1                           # sticky per-turn failure
    assert fake_voice.spoken == ["سم", S1]              # spoken LIVE (no session audio to overlap)


# ─────────────────────────────── Mid-turn death ───────────────────────────────


@pytest.mark.asyncio
async def test_death_defers_everything_to_one_fallback_after_the_drain():
    session = FakeSession(fail_feed_at=1)               # ack plays, S1 kills it
    turn_voice, fake_voice, _overlay, _ = _voice(session)
    await turn_voice.speak_or_feed("سم")
    await turn_voice.push_stream(S1 + " ")
    await turn_voice.speak_or_feed(S2)                  # after death: deferred, NOT live
    await turn_voice.end_stream()
    assert fake_voice.spoken == []                      # nothing before the drain
    await turn_voice.finish()
    assert session.closed                               # drained FIRST
    assert fake_voice.spoken == [f"{S1} {S2}"]          # remainder, one call, in order


@pytest.mark.asyncio
async def test_caption_never_freezes_on_a_dead_sentence():
    session = FakeSession(fail_feed_at=0)               # the very first feed dies
    turn_voice, fake_voice, _overlay, _ = _voice(session)
    await turn_voice.speak_or_feed(S1)
    assert fake_voice.log == [("show", S1), ("clear",)]  # shown, then unfrozen


@pytest.mark.asyncio
async def test_nothing_played_respeaks_the_whole_turn():
    session = FakeSession(silent=True)                  # feeds "work", no PCM ever
    turn_voice, fake_voice, _overlay, _ = _voice(session)
    await turn_voice.speak_or_feed("سم")
    await turn_voice.push_stream(S1)
    await turn_voice.end_stream()
    await turn_voice.finish()
    assert fake_voice.spoken == [f"سم {S1}"]            # got_audio guard: re-speak ALL


@pytest.mark.asyncio
async def test_close_failure_after_audio_logs_only_never_duplicates():
    session = FakeSession(fail_close=True)
    turn_voice, fake_voice, _overlay, _ = _voice(session)
    await turn_voice.speak_or_feed(S1)                  # played fine
    await turn_voice.finish()                           # close raises internally
    assert fake_voice.spoken == []                      # re-speaking would duplicate


# ──────────────────────── Caption pacing (v7 Phase 2) ────────────────────────


@pytest.mark.asyncio
async def test_captions_are_paced_to_estimated_audio_not_generation_speed():
    # The measured bug: sentences fed within ~4 s while their audio played
    # ~26 s — captions flashed at generation speed. Each caption now defers
    # to its sentence's ESTIMATED audio start: cumulative fed chars / rate.
    from muthis.turn_voice import ARABIC_TTS_CHARS_PER_SEC
    session = FakeSession()
    turn_voice, fake_voice, _overlay, _ = _voice(session)

    await turn_voice.speak_or_feed("سم")               # first speech: delay 0
    await turn_voice.push_stream(S1 + " " + S2)
    await turn_voice.end_stream()

    d1, d2, d3 = fake_voice.caption_delays
    assert d1 == 0.0                                   # nothing queued before it
    assert d2 == pytest.approx(len("سم") / ARABIC_TTS_CHARS_PER_SEC)
    assert d3 == pytest.approx((len("سم") + len(S1)) / ARABIC_TTS_CHARS_PER_SEC)
    assert d1 < d2 < d3                                # monotone: no flashing


@pytest.mark.asyncio
async def test_caption_pacing_subtracts_already_played_audio():
    # If audio has already PLAYED for a while (session.played_seconds), the
    # deferral shrinks by exactly that much — never below zero.
    class PlayingSession(FakeSession):
        def played_seconds(self):
            return 1000.0                              # everything long played

    session = PlayingSession()
    turn_voice, fake_voice, _overlay, _ = _voice(session)
    await turn_voice.speak_or_feed("سم")
    await turn_voice.push_stream(S1)
    await turn_voice.end_stream()

    assert fake_voice.caption_delays == [0.0, 0.0]     # clamped, shown live


# ─────────────────────────────── Eager open (Fix G) ───────────────────────────────


@pytest.mark.asyncio
async def test_begin_open_shares_the_one_attempt_with_first_speech():
    # The eager turn-start handshake and the first speech must resolve to the
    # SAME single open attempt — never a second socket.
    session = FakeSession()
    turn_voice, fake_voice, _overlay, factory = _voice(session)

    turn_voice.begin_open()                             # turn start: in flight
    turn_voice.begin_open()                             # idempotent re-entry
    await turn_voice.speak_or_feed(S1)                  # joins the same attempt
    await turn_voice.finish()

    assert factory.calls == 1                           # eager + lazy = ONE open
    assert session.fed == [S1] and fake_voice.spoken == []


@pytest.mark.asyncio
async def test_begin_open_is_a_noop_when_disabled():
    session = FakeSession()
    turn_voice, _fake_voice, _overlay, factory = _voice(session, enabled=False)
    turn_voice.begin_open()
    await turn_voice.finish()
    assert factory.calls == 0                           # buffered turn: no socket


@pytest.mark.asyncio
async def test_finish_settles_an_unused_eager_open():
    # A turn that ends before ANY speech: the in-flight handshake is awaited
    # and the opened session is closed — no orphan task, no leaked socket.
    session = FakeSession()
    turn_voice, fake_voice, _overlay, factory = _voice(session)
    turn_voice.begin_open()
    await turn_voice.finish()
    assert factory.calls == 1 and session.opened and session.closed
    assert fake_voice.spoken == []                      # nothing to fall back to


@pytest.mark.asyncio
async def test_abandon_settles_an_unused_eager_open():
    session = FakeSession()
    turn_voice, fake_voice, _overlay, _factory = _voice(session)
    turn_voice.begin_open()
    await turn_voice.abandon()
    assert session.closed and fake_voice.spoken == []


@pytest.mark.asyncio
async def test_eager_open_failure_still_degrades_to_live_buffered():
    session = FakeSession(fail_open=True)
    turn_voice, fake_voice, _overlay, factory = _voice(session)
    turn_voice.begin_open()
    await turn_voice.speak_or_feed(S1)                  # open failed → proven path
    await turn_voice.finish()
    assert factory.calls == 1                           # sticky per-turn failure
    assert fake_voice.spoken == [S1]


# ───────────────────────── Barge-in interrupt (v7 Phase 3) ─────────────────────────


@pytest.mark.asyncio
async def test_interrupt_silences_and_mutes_every_fallback():
    # The user asked us to STOP TALKING: interrupt aborts the session and the
    # later finish() must be a no-op — decision-15 would otherwise re-speak
    # the very text that was just silenced (got_audio False + fed text).
    session = FakeSession(silent=True)               # fed but nothing played
    turn_voice, fake_voice, _overlay, _ = _voice(session)
    await turn_voice.speak_or_feed(S1)

    await turn_voice.interrupt()
    await turn_voice.finish()                        # run_turn's finally

    assert session.aborted                           # aborted, not drained
    assert fake_voice.spoken == []                   # NO fallback re-speak
    assert fake_voice.log[-1] == ("clear",)          # caption wiped with the voice


@pytest.mark.asyncio
async def test_interrupt_is_idempotent_and_leaves_the_light_alone():
    session = FakeSession()
    turn_voice, fake_voice, overlay, _ = _voice(session)
    await turn_voice.speak_or_feed("سم")
    states_before = list(overlay.states)

    await turn_voice.interrupt()
    await turn_voice.interrupt()                     # double press downstream

    assert overlay.states == states_before           # the barge-in press owns
    assert fake_voice.spoken == []                   # the "listening" light


@pytest.mark.asyncio
async def test_interrupt_mid_eager_open_settles_the_handshake():
    session = FakeSession()
    turn_voice, fake_voice, _overlay, factory = _voice(session)
    turn_voice.begin_open()                          # handshake in flight

    await turn_voice.interrupt()                     # user bailed immediately

    assert factory.calls == 1 and session.aborted    # settled THEN silenced
    assert fake_voice.spoken == []


# ─────────────────────────────── Abandon path ───────────────────────────────


@pytest.mark.asyncio
async def test_abandon_releases_quietly_and_blocks_a_later_finish():
    session = FakeSession()
    turn_voice, fake_voice, overlay, _ = _voice(session)
    await turn_voice.speak_or_feed("سم")
    await turn_voice.abandon()                          # pass died without TurnComplete
    await turn_voice.finish()                           # run_turn's finally: no-op now
    assert session.closed
    assert fake_voice.spoken == []                      # that branch never speaks
    assert overlay.states[-1] == "thinking"
