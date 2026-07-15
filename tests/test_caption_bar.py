"""
test_caption_bar.py — v6 Phase C: the live-captions bar (fakes only, no Tk).

C1: the pure wrap policy + the CaptionBar view on a fake canvas.
C2: dispatch routing (show_caption / clear_caption / hide-ghosting) and the
VoiceOut wiring — flag-gated behind MUTHIS_CAPTIONS (default OFF), privacy:
ONLY the text speak() receives may reach the bar, and it clears when the
audio finishes (success OR failure).

Run:  set PYTHONPATH=src && python -m pytest tests/test_caption_bar.py -q
"""

from __future__ import annotations

import pytest

from muthis.overlay.caption_bar import (
    BOTTOM_MARGIN_PX,
    CAPTION_TAG,
    CaptionBar,
    wrap_caption,
)
from muthis.overlay.style import OverlayStyle

DEFAULTS = OverlayStyle()
SCREEN = (1920, 1080)


# ──────────────────────────────── Fake canvas ────────────────────────────────


class FakeCanvas:
    """Records every draw primitive; bbox() returns a plausible text bounds."""

    def __init__(self):
        self.texts = []
        self.polygons = []
        self.deleted = []
        self.lowered = []
        self._next_id = 0

    def _new_id(self):
        self._next_id += 1
        return self._next_id

    def create_text(self, *coords, **kwargs):
        self.texts.append((coords, kwargs))
        return self._new_id()

    def create_polygon(self, *coords, **kwargs):
        self.polygons.append((coords, kwargs))
        return self._new_id()

    def bbox(self, item_id):
        return (860, 1000, 1060, 1032)

    def tag_lower(self, lower, upper):
        self.lowered.append((lower, upper))

    def delete(self, tag):
        self.deleted.append(tag)


# ─────────────────────────────── wrap_caption ───────────────────────────────


def test_wrap_short_text_stays_one_line():
    assert wrap_caption("مرحبا يا عالم") == "مرحبا يا عالم"


def test_wrap_breaks_at_word_boundaries():
    assert wrap_caption("مرحبا يا عالم", max_chars_per_line=10) == "مرحبا يا\nعالم"


def test_wrap_truncates_beyond_max_lines_with_an_ellipsis():
    wrapped = wrap_caption("aaa bbb ccc ddd eee", max_chars_per_line=7, max_lines=2)
    assert wrapped == "aaa bbb\nccc dd…"


def test_wrap_hard_cuts_a_single_overlong_token():
    wrapped = wrap_caption("a" * 100, max_chars_per_line=10, max_lines=2)
    assert wrapped == "a" * 9 + "…"
    assert all(len(line) <= 10 for line in wrapped.split("\n"))


def test_wrap_empty_text_yields_empty():
    assert wrap_caption("") == ""
    assert wrap_caption("   ") == ""


# ─────────────────────────────── CaptionBar ───────────────────────────────


def test_show_text_draws_wrapped_text_bottom_center_on_a_plate():
    canvas = FakeCanvas()
    CaptionBar(canvas, SCREEN, style=DEFAULTS).show_text("هذا هو الشرح.")

    # ONE text item: bottom-center anchor "s", the highlight neon color,
    # tag-scoped so the shared canvas's other layers are never disturbed.
    assert len(canvas.texts) == 1
    coords, kwargs = canvas.texts[0]
    assert coords == (960.0, 1080 - BOTTOM_MARGIN_PX)
    assert kwargs["anchor"] == "s"
    assert kwargs["text"] == "هذا هو الشرح."
    assert kwargs["fill"] == DEFAULTS.colors["highlight"]
    assert kwargs["tags"] == CAPTION_TAG
    # A rounded plate behind it (smooth polygon, dark chip fill), pushed
    # under the text so the Arabic stays crisp on any background.
    assert len(canvas.polygons) == 1
    _, plate_kwargs = canvas.polygons[0]
    assert plate_kwargs["smooth"] is True
    assert plate_kwargs["fill"] == DEFAULTS.label_plate
    assert plate_kwargs["tags"] == CAPTION_TAG
    assert canvas.lowered == [(2, 1)]  # plate lowered under the text


def test_show_replaces_previous_and_clear_deletes_only_the_caption_tag():
    canvas = FakeCanvas()
    bar = CaptionBar(canvas, SCREEN, style=DEFAULTS)
    bar.show_text("الجملة الأولى.")
    bar.show_text("الجملة الثانية.")
    bar.clear()

    # Every wipe is by CAPTION_TAG (never delete-all): one per show + the clear.
    assert canvas.deleted == [CAPTION_TAG, CAPTION_TAG, CAPTION_TAG]
    assert canvas.texts[-1][1]["text"] == "الجملة الثانية."


def test_empty_text_clears_without_drawing():
    canvas = FakeCanvas()
    CaptionBar(canvas, SCREEN, style=DEFAULTS).show_text("")
    assert canvas.deleted == [CAPTION_TAG]
    assert canvas.texts == [] and canvas.polygons == []


# ──────────────────── C2: dispatch routing (fakes, no Tk) ────────────────────


class _Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name,) + args)
        return record


class FakeCaption:
    def __init__(self):
        self.shown = []
        self.clears = 0

    def show_text(self, text):
        self.shown.append(text)

    def clear(self):
        self.clears += 1


def _dispatch(command, caption):
    from muthis.overlay.window_commands import dispatch_command
    return dispatch_command(
        command, rect=_Recorder(), pointer=_Recorder(), animator=_Recorder(),
        shapes=None, status=None, caption=caption,
    )


def test_dispatch_routes_show_and_clear_caption():
    caption = FakeCaption()
    assert _dispatch(("show_caption", "الجملة الحالية."), caption) is True
    assert _dispatch(("clear_caption",), caption) is True
    assert caption.shown == ["الجملة الحالية."]
    assert caption.clears == 1


def test_dispatch_hide_clears_the_caption_too():
    # Ghosting: hide() runs before EVERY capture, so a screenshot can never
    # show Mut'his its own caption text.
    caption = FakeCaption()
    _dispatch(("hide",), caption)
    assert caption.clears == 1


def test_dispatch_without_a_caption_bar_stays_backward_compatible():
    from muthis.overlay.window_commands import dispatch_command
    # The pre-captions signature (no caption kwarg) must keep working.
    assert dispatch_command(
        ("show_caption", "نص"), rect=_Recorder(), pointer=_Recorder(),
        animator=_Recorder(),
    ) is True
    assert dispatch_command(
        ("hide",), rect=_Recorder(), pointer=_Recorder(), animator=_Recorder(),
    ) is True


def test_sidekick_overlay_enqueues_caption_commands():
    from muthis.overlay.sidekick_window import SidekickOverlay
    overlay = SidekickOverlay()
    overlay._started = True          # disarm the real Tk thread
    overlay.show_caption("جملة")
    overlay.clear_caption()
    commands = []
    while not overlay._commands.empty():
        commands.append(overlay._commands.get_nowait())
    assert commands == [("show_caption", "جملة"), ("clear_caption",)]


# ─────────────── C2: the VoiceOut caption choke point (no Tk) ────────────────


class CaptionOverlay:
    """Overlay double WITH the caption seam; records call order."""

    def __init__(self):
        self.events = []

    def set_state(self, state):
        self.events.append(("state", state))

    def show_caption(self, text):
        self.events.append(("caption", text))

    def clear_caption(self):
        self.events.append(("caption_clear",))

    async def show(self, bbox, label_ar):
        pass

    async def hide(self):
        pass

    def clear_status_light(self):
        pass


class BareOverlay:
    """An overlay WITHOUT caption methods (StubOverlay shape)."""

    def set_state(self, state):
        pass


def _tts_recorder(log):
    async def tts(text):
        log.append(("tts", text))
        return None
    return tts


@pytest.mark.asyncio
async def test_captions_on_show_the_exact_spoken_text_then_clear_after_audio():
    from muthis.voice_out import VoiceOut
    overlay = CaptionOverlay()
    voice = VoiceOut(_tts_recorder(overlay.events), overlay, captions=True)

    await voice.speak("هذا هو الشرح الكامل.")

    # Caption appears WITH the speech start (right after the speaking light,
    # before the TTS awaits) and clears once the audio call finishes.
    assert overlay.events == [
        ("state", "speaking"),
        ("caption", "هذا هو الشرح الكامل."),
        ("tts", "هذا هو الشرح الكامل."),
        ("caption_clear",),
        ("state", "thinking"),
    ]


@pytest.mark.asyncio
async def test_captions_default_on_shows_the_caption():
    # Sultan's release decision (2026-07-15): env cleared/unset → captions ON.
    from muthis.voice_out import VoiceOut
    overlay = CaptionOverlay()
    voice = VoiceOut(_tts_recorder(overlay.events), overlay)

    await voice.speak("نص منطوق")

    assert ("caption", "نص منطوق") in overlay.events


@pytest.mark.asyncio
async def test_falsey_env_flag_is_the_one_env_rollback(monkeypatch):
    from muthis.voice_out import VoiceOut
    monkeypatch.setenv("MUTHIS_CAPTIONS", "0")
    overlay = CaptionOverlay()
    voice = VoiceOut(_tts_recorder(overlay.events), overlay)

    await voice.speak("نص")

    assert [e for e in overlay.events if e[0].startswith("caption")] == []


@pytest.mark.asyncio
async def test_captions_clear_even_when_the_tts_raises():
    from muthis.voice_out import VoiceOut
    overlay = CaptionOverlay()

    async def broken_tts(text):
        raise RuntimeError("device gone")

    voice = VoiceOut(broken_tts, overlay, captions=True)
    with pytest.raises(RuntimeError):
        await voice.speak("جملة")
    # The bar must never stay frozen on a dead sentence.
    assert overlay.events[-1] == ("caption_clear",)


@pytest.mark.asyncio
async def test_an_overlay_without_caption_methods_is_a_silent_noop():
    from muthis.voice_out import VoiceOut

    async def tts(text):
        return None

    # captions ON + a caption-less overlay (StubOverlay shape) → no crash.
    await VoiceOut(tts, BareOverlay(), captions=True).speak("نص")


# ─────────────── v7 Phase 2: audio-paced captions (the sync fix) ───────────────


class FakeAfter:
    """root.after double: callbacks queue and fire only when driven."""

    def __init__(self):
        self.scheduled = []  # (delay_ms, callback)

    def __call__(self, delay_ms, callback):
        self.scheduled.append((delay_ms, callback))

    def fire_all(self):
        pending, self.scheduled = self.scheduled, []
        for _delay, callback in pending:
            callback()


def _paced_bar():
    canvas, after = FakeCanvas(), FakeAfter()
    from muthis.overlay.caption_bar import CaptionBar
    return CaptionBar(canvas, SCREEN, schedule=after), canvas, after


def test_show_text_later_defers_until_the_scheduled_moment():
    bar, canvas, after = _paced_bar()
    bar.show_text_later("الجملة المؤجلة إلى صوتها", 1500)

    assert canvas.texts == []                        # nothing yet — paced
    assert after.scheduled[0][0] == 1500             # the audio-start estimate
    after.fire_all()
    assert canvas.texts and "المؤجلة" in canvas.texts[0][1]["text"]


def test_zero_delay_or_no_schedule_shows_immediately():
    bar, canvas, _after = _paced_bar()
    bar.show_text_later("فوري", 0)
    assert canvas.texts                              # no deferral for delay 0
    from muthis.overlay.caption_bar import CaptionBar
    bare_canvas = FakeCanvas()
    CaptionBar(bare_canvas, SCREEN).show_text_later("قديم", 900)
    assert bare_canvas.texts                         # schedule-less → immediate


def test_clear_cancels_every_pending_paced_show():
    # Audio end / ghosting hide / a dead sentence: a wiped bar must never
    # resurrect stale speech text from the pacing queue.
    bar, canvas, after = _paced_bar()
    bar.show_text_later("الأولى المجدولة هنا", 1000)
    bar.show_text_later("والثانية المجدولة هنا", 2000)
    bar.clear()
    after.fire_all()
    assert canvas.texts == []                        # both orphaned


def test_a_firing_sentence_never_cancels_its_queued_siblings():
    # show_text replaces the CONTENT but must not bump the cancel generation —
    # sentence 1 appearing must not orphan sentences 2..N still in the queue.
    bar, canvas, after = _paced_bar()
    bar.show_text_later("الجملة الأولى المجدولة", 500)
    bar.show_text_later("الجملة الثانية المجدولة", 1500)
    after.fire_all()
    assert len(canvas.texts) == 2                    # both fired, in order
    assert "الثانية" in canvas.texts[-1][1]["text"]


@pytest.mark.asyncio
async def test_voice_out_routes_a_delayed_caption_to_the_paced_seam():
    from muthis.voice_out import VoiceOut

    class PacedOverlay(CaptionOverlay):
        def __init__(self):
            super().__init__()
            self.paced = []

        def show_caption_later(self, text, delay_ms):
            self.paced.append((text, delay_ms))

    overlay = PacedOverlay()
    voice = VoiceOut(_tts_recorder(overlay.events), overlay, captions=True)
    voice.show_caption("مُرجأة", delay_s=2.5)
    voice.show_caption("فورية")                       # delay 0 → the plain seam

    assert overlay.paced == [("مُرجأة", 2500)]
    assert ("caption", "فورية") in overlay.events


@pytest.mark.asyncio
async def test_voice_out_delay_degrades_to_immediate_without_the_seam():
    from muthis.voice_out import VoiceOut
    overlay = CaptionOverlay()                        # no show_caption_later
    voice = VoiceOut(_tts_recorder(overlay.events), overlay, captions=True)
    voice.show_caption("تظهر فوراً", delay_s=3.0)
    assert ("caption", "تظهر فوراً") in overlay.events
