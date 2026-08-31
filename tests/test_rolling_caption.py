"""
test_rolling_caption.py — DEC-128, shape C: the caption bar follows the voice on
a TOOL-FREE turn instead of freezing on its opening.

WHAT WAS WRONG. A tool-free turn is never streamed (`tool_choice` stays "auto"
without a draw), so `TurnPass` hands the WHOLE answer to `speak_or_feed()` in one
call and the bar painted ONE truncated block for a turn that speaks for minutes.
Measured: 117 of 1,159 chars. And the cap is ABSOLUTE while the answer is not, so
coverage FALLS as Mut'his teaches longer — 10.1% at 1,159 chars, 3.4% at 3,479.

WHAT THIS GUARDS, in two halves:
  * C1 — `VoiceOut._roll_caption` splits a long buffered answer into sentence
    captions and schedules each at its estimated audio start;
  * C2 — `MAX_LINES` 2 -> 3, which is what clears the sentences that still
    exceeded the chip after C1 (five of eleven, longest 172 chars).

WHAT IT DELIBERATELY DOES NOT GUARD: ordering. Shape C touches no ordering at
all — the Option-A sync point still decides WHEN Mut'his commits to speaking, and
this only changes what the bar shows afterwards. Tests that would pass equally
well with the gate reversed are not evidence about the gate.

THE NEGATIVE CONTROL IS LOAD-BEARING (the project's standing guard shape): a
STREAMED sentence and an ack must NOT be rolled, or C1 would silently re-cut text
the splitter already cut and re-pace a path that already re-reads the audio clock
on every feed. `test_a_streamed_sentence_is_never_rolled` is that control, and
dropping `ROLLING_MIN_CHARS` to 0 must turn it RED.
"""

from __future__ import annotations

import pytest

from muthis.overlay.caption_bar import MAX_CHARS_PER_LINE, MAX_LINES, wrap_caption
from muthis.speech_stream import SentenceSplitter
from muthis.turn_voice import ARABIC_TTS_CHARS_PER_SEC
from muthis.voice_out import ROLLING_MIN_CHARS, VoiceOut

# A real Mut'his answer of the length the defect lives at: ~1,159 chars, which is
# ~101 s of speech — Sultan's "a minute or two".
ONE_PARAGRAPH = (
    "أبشر. الفكرة باختصار أن الدالة تستقبل قائمة من الأرقام ثم تمر عليها عنصراً "
    "عنصراً، وفي كل دورة تفحص شرطين: هل العنصر أكبر من الصفر، وهل هو زوجي. "
    "إذا تحقق الشرطان معاً تضيفه إلى المجموع، وإلا تتجاهله وتنتقل للعنصر التالي. "
    "لاحظ أن الشرط الثاني مكتوب داخل الشرط الأول، وهذا يعني أن الفحص الثاني لا "
    "يُنفَّذ إطلاقاً إذا كان العنصر سالباً، وهذه نقطة مهمة في الأداء. بعد انتهاء "
    "الحلقة ترجع الدالة المجموع النهائي. الخطأ الشائع هنا هو وضع جملة الإرجاع "
    "داخل الحلقة بدل خارجها، فترجع الدالة بعد أول عنصر فقط وتحصل على نتيجة خاطئة "
    "دون أي رسالة خطأ، وهذا أخطر أنواع الأخطاء لأنه صامت تماماً."
)
LONG_ANSWER = " ".join([ONE_PARAGRAPH] * 2)


class PacedOverlay:
    """An overlay WITH the paced seam — what the real SidekickOverlay offers."""

    def __init__(self) -> None:
        self.paced: list[tuple[str, int]] = []
        self.plain: list[str] = []
        self.cleared = 0

    def set_state(self, state):  # pragma: no cover - not what this file guards
        pass

    def show_caption(self, text):
        self.plain.append(text)

    def show_caption_later(self, text, delay_ms):
        self.paced.append((text, delay_ms))

    def clear_caption(self):
        self.cleared += 1


class BareOverlay:
    """No paced seam (StubOverlay / older fakes) — must degrade, never raise."""

    def __init__(self) -> None:
        self.plain: list[str] = []

    def set_state(self, state):  # pragma: no cover
        pass

    def show_caption(self, text):
        self.plain.append(text)

    def clear_caption(self):  # pragma: no cover
        pass


async def _no_tts(text):  # the VoiceOut constructor wants a TtsFn
    return None


def _voice(overlay):
    return VoiceOut(_no_tts, overlay, captions=True)


def _sentences(text):
    splitter = SentenceSplitter()
    return splitter.push(text) + splitter.flush()


# ── C1: the rolling itself ───────────────────────────────────────────────────

def test_a_long_buffered_answer_rolls_into_sentence_captions():
    overlay = PacedOverlay()
    _voice(overlay).show_caption(LONG_ANSWER)

    expected = _sentences(LONG_ANSWER)
    assert len(expected) > 1, "the fixture must actually split, or this proves nothing"
    assert [text for text, _ms in overlay.paced] == expected
    assert overlay.plain == [], "a rolled answer must not ALSO paint one block"


def test_rolling_loses_no_spoken_text():
    """The bar may re-cut the answer; it may never DROP part of it."""
    overlay = PacedOverlay()
    _voice(overlay).show_caption(LONG_ANSWER)

    rolled = " ".join(text for text, _ms in overlay.paced)
    assert rolled.split() == LONG_ANSWER.split()


def test_the_first_rolled_caption_is_immediate():
    """The bar must not go BLANK at the start of the answer: piece one is
    scheduled at 0, which CaptionBar.show_text_later shows without deferring."""
    overlay = PacedOverlay()
    _voice(overlay).show_caption(LONG_ANSWER)
    assert overlay.paced[0][1] == 0


def test_the_rolled_schedule_is_paced_by_the_shipped_rate():
    """MECHANISM CHECK, not an outcome check: each caption's delay must be the
    CUMULATIVE chars before it divided by the speech rate. A schedule that
    merely increases would pass an outcome test while pacing nothing."""
    overlay = PacedOverlay()
    _voice(overlay).show_caption(LONG_ANSWER)

    fed = 0
    for (text, delay_ms), piece in zip(overlay.paced, _sentences(LONG_ANSWER)):
        assert delay_ms == round(fed / ARABIC_TTS_CHARS_PER_SEC * 1000), (
            f"caption {text[:20]!r} is not scheduled at its audio start")
        fed += len(piece)


def test_an_existing_delay_offsets_the_whole_schedule():
    """`show_caption` is also reached with a delay from the streamed pacer; a
    rolled schedule must ride ON TOP of it, never discard it."""
    overlay = PacedOverlay()
    _voice(overlay).show_caption(LONG_ANSWER, delay_s=4.0)
    assert overlay.paced[0][1] == 4000


# ── The controls: what must NOT roll ─────────────────────────────────────────

def test_a_streamed_sentence_is_never_rolled():
    """THE NEGATIVE CONTROL. Streamed sentences arrive one at a time and are
    already paced against the real audio clock on every feed. Rolling them would
    re-cut and re-pace a path that is not broken."""
    overlay = PacedOverlay()
    sentence = _sentences(LONG_ANSWER)[0]
    assert len(sentence) <= ROLLING_MIN_CHARS, "fixture drifted: pick a shorter one"

    _voice(overlay).show_caption(sentence, delay_s=2.0)
    assert overlay.paced == [(sentence, 2000)], "a single sentence was re-cut"


def test_a_short_ack_is_never_rolled():
    overlay = PacedOverlay()
    _voice(overlay).show_caption("أبشر، شوف")
    assert overlay.plain == ["أبشر، شوف"] and overlay.paced == []


def test_an_unpunctuated_run_is_re_cut_at_words_never_mid_word():
    """A run with no sentence ender still gets split — by the splitter's SOFT
    VALVE (`MAX_BUFFER_CHARS`), which cuts at the last whitespace. So rolling one
    is safe, and the property worth holding is that no caption ever begins or
    ends inside a word.

    Recorded because it corrects an assumption this file was first written on:
    `_roll_caption`'s `len(pieces) < 2` guard is DEFENSIVE, not exercised — above
    200 chars the valve guarantees a split, and `ROLLING_MIN_CHARS` is 240. It is
    kept so the splitter's constants can move without this module silently
    changing shape."""
    overlay = PacedOverlay()
    unbroken = "كلمة " * 70                       # no sentence ender at all
    assert len(unbroken) > ROLLING_MIN_CHARS
    _voice(overlay).show_caption(unbroken)

    assert overlay.paced, "the valve should have produced captions"
    for text, _ms in overlay.paced:
        for word in text.split():
            assert word == "كلمة", f"a caption was cut mid-word: {word!r}"


def test_an_overlay_without_the_paced_seam_still_gets_one_caption():
    """Degradation, not a crash: the old single-block behaviour, unchanged."""
    overlay = BareOverlay()
    _voice(overlay).show_caption(LONG_ANSWER)
    assert overlay.plain == [LONG_ANSWER]


def test_the_captions_flag_still_switches_everything_off():
    overlay = PacedOverlay()
    VoiceOut(_no_tts, overlay, captions=False).show_caption(LONG_ANSWER)
    assert overlay.paced == [] and overlay.plain == []


# ── C2: the cap, and the outcome the whole gate exists for ───────────────────

def test_three_lines_show_the_longest_real_sentence_whole():
    longest = max(_sentences(LONG_ANSWER), key=len)
    assert len(longest) > 2 * MAX_CHARS_PER_LINE, (
        "fixture drifted — this must be a sentence TWO lines could not hold, or "
        "it proves nothing about the third")
    wrapped = wrap_caption(longest)
    assert "…" not in wrapped, "the longest real sentence is still truncated"
    assert wrapped.split() == longest.split(), "words were lost in the wrap"
    # …and it genuinely needed the third line: two would still have cut it.
    assert "…" in wrap_caption(longest, MAX_CHARS_PER_LINE, 2)


def test_the_gate_lifts_a_real_answer_from_a_tenth_to_nearly_all_of_it():
    """THE OUTCOME, stated as the viewer experiences it. Before: one block, 117
    of 1,159 chars. After C1 + C2: every sentence, essentially whole."""
    before = len(wrap_caption(LONG_ANSWER, MAX_CHARS_PER_LINE, 2))
    after = sum(len(wrap_caption(p)) for p in _sentences(LONG_ANSWER))

    assert before / len(LONG_ANSWER) < 0.15
    assert after / len(LONG_ANSWER) > 0.95, (
        f"coverage {after / len(LONG_ANSWER):.1%} — the gate's whole point")


def test_the_line_count_is_three_and_the_width_is_untouched():
    """C2's declared shape: grow UPWARD (away from the bottom-left badge), never
    wider. `tests/test_domain_badge.py` holds the same pair from the badge's
    side; this is the caption's own statement of it."""
    assert (MAX_LINES, MAX_CHARS_PER_LINE) == (3, 60)
