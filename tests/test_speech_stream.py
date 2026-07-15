"""
test_speech_stream.py — the streaming Arabic sentence splitter (v5 Phase C1 +
v7 soft boundaries), pure unit tests (no TTS, no orchestrator, no network).

Proves: fragments in → complete sentences out, in order; no sentence is ever
cut mid-way; the decimal guard holds "3." at the buffer end and never splits
"3.14"; a completion shorter than MIN_SENTENCE_CHARS MERGES forward instead of
feeding TTS a scrap (v7 — kills the standalone "١." numeral); an ellipsis run
is ONE ender, never cut inside (v7); the ~200-char safety valve cuts at a soft
word boundary and keeps the remainder (v7 — the old valve cut MID-WORD);
flush() returns the tail and resets; punctuation-only scraps never come out.

Run:  set PYTHONPATH=src && python -m pytest tests/test_speech_stream.py -q
"""

from __future__ import annotations

from muthis.speech_stream import (
    EAGER_FIRST_MIN_CHARS, MAX_BUFFER_CHARS, MIN_SENTENCE_CHARS, SentenceSplitter,
)

# Long enough (≥ MIN_SENTENCE_CHARS) to emit the instant their ender arrives.
FIRST_AR = "الجملة الأولى في هذا الاختبار طويلة كفاية."
SECOND_AR = "والجملة الثانية هنا طويلة كفاية أيضاً؟"


def test_fragments_produce_sentences_in_order():
    splitter = SentenceSplitter()
    assert splitter.push(FIRST_AR + " " + SECOND_AR[:10]) == [FIRST_AR]
    assert splitter.push(SECOND_AR[10:] + " تكملة") == [SECOND_AR]
    assert splitter.flush() == ["تكملة"]


def test_a_sentence_split_across_many_tiny_deltas_arrives_once_and_whole():
    splitter = SentenceSplitter()
    sentence = "زر الحفظ موجود فوق يسار الشاشة تماماً."
    emitted = []
    for char in sentence:
        emitted += splitter.push(char)
    assert emitted == [sentence]
    assert splitter.flush() == []


def test_all_arabic_enders_and_newline_are_boundaries():
    splitter = SentenceSplitter()
    out = splitter.push(
        "هل هذا سؤال واضح وطويل كفاية؟ "
        "هذا تعجب واضح وطويل كفاية! "
        "قبل الفاصلة المنقوطة كلام طويل؛ "
        "وقبل سطر جديد كلام طويل أيضاً\n"
        "الباقي"
    )
    assert out == [
        "هل هذا سؤال واضح وطويل كفاية؟",
        "هذا تعجب واضح وطويل كفاية!",
        "قبل الفاصلة المنقوطة كلام طويل؛",
        "وقبل سطر جديد كلام طويل أيضاً",
    ]
    assert splitter.flush() == ["الباقي"]


def test_decimal_number_is_never_split():
    # The whole thing in one push: the dot between digits is not a boundary.
    splitter = SentenceSplitter()
    sentence = "قيمة الثابت المشهور هي 3.14 تقريباً في الحساب."
    assert splitter.push(sentence) == [sentence]


def test_dot_held_at_buffer_end_after_a_digit_until_context_arrives():
    splitter = SentenceSplitter()
    assert splitter.push("النسبة المئوية المسجلة هنا 3.") == []   # held — "14" may follow
    assert splitter.push("14 بالمئة كما هو واضح.") == [
        "النسبة المئوية المسجلة هنا 3.14 بالمئة كما هو واضح."]
    # And when the next char is NOT a digit, the held dot resolves to a boundary.
    assert splitter.push("انتهى العد التنازلي الطويل عند 5.") == []   # held again
    assert splitter.push(" وبدأنا") == ["انتهى العد التنازلي الطويل عند 5."]
    assert splitter.flush() == ["وبدأنا"]


def test_flush_returns_the_held_decimal_tail():
    splitter = SentenceSplitter()
    assert splitter.push("الإصدار المستقر الحالي هو رقم 2.") == []
    assert splitter.flush() == ["الإصدار المستقر الحالي هو رقم 2."]


# ─────────────────────────── v7 soft boundaries ───────────────────────────


def test_short_sentence_merges_forward_instead_of_feeding_a_scrap():
    # v7 min-length: "تمام." alone is a bad TTS/caption unit — it merges into
    # the NEXT sentence (one feed, natural prosody).
    splitter = SentenceSplitter()
    assert splitter.push("تمام.") == []                     # held for a merge
    assert splitter.push(" الزر المطلوب موجود فوق يسار الشاشة.") == [
        "تمام. الزر المطلوب موجود فوق يسار الشاشة."]


def test_list_numeral_never_feeds_alone():
    # Measured offender (diag 2026-07-15): "١." went to TTS as a standalone
    # 2-char "sentence". The min-length merge glues it to its item.
    splitter = SentenceSplitter()
    assert splitter.push("١. افتح المشروع من القائمة الرئيسية فوق.") == [
        "١. افتح المشروع من القائمة الرئيسية فوق."]


def test_ellipsis_run_is_one_ender_and_never_cut_inside():
    splitter = SentenceSplitter()
    # The run touches the buffer end — held: the stream may still grow it.
    assert splitter.push("خلني أفكر في هذا الطلب شوي...") == []
    assert splitter.push(" تمام لقيت الحل المناسب هنا!") == [
        "خلني أفكر في هذا الطلب شوي...",
        "تمام لقيت الحل المناسب هنا!",
    ]


def test_safety_valve_cuts_at_a_word_boundary_and_keeps_the_remainder():
    # Measured offender (diag 2026-07-15): the old valve dumped the whole
    # buffer at an arbitrary fragment edge — MID-WORD. Now it cuts at the last
    # soft point inside the window and keeps the tail buffered.
    splitter = SentenceSplitter()
    run = "كلمة " * 50                                # 250 chars, no punctuation
    emitted = splitter.push(run)
    assert emitted == [("كلمة " * 40).strip()]        # whole words, ≤ the window
    assert len(emitted[0]) <= MAX_BUFFER_CHARS
    assert splitter.flush() == [("كلمة " * 10).strip()]   # remainder kept, not lost


def test_valve_hard_cuts_one_unbroken_token_as_a_last_resort():
    splitter = SentenceSplitter()
    run = "ب" * (MAX_BUFFER_CHARS + 50)               # no soft point anywhere
    emitted = splitter.push(run)
    assert emitted == ["ب" * MAX_BUFFER_CHARS]        # old behavior preserved
    assert splitter.flush() == ["ب" * 50]


def test_min_length_is_tunable_per_splitter():
    splitter = SentenceSplitter(min_sentence_chars=1)
    assert splitter.push("تمام.") == ["تمام."]        # v5 behavior on demand


# ─────────────────────────── unchanged guarantees ───────────────────────────


def test_punctuation_only_scraps_never_come_out():
    splitter = SentenceSplitter()
    assert splitter.push("؟!") == []
    assert splitter.flush() == []


def test_flush_on_empty_is_empty_and_splitter_is_reusable():
    splitter = SentenceSplitter()
    assert splitter.flush() == []
    assert splitter.push("جديدة.") == []              # short: awaits a merge
    assert splitter.flush() == ["جديدة."]             # stream end releases it


def test_min_constant_is_sane():
    # The merge floor must stay well under the valve, or nothing ever emits.
    assert 0 < MIN_SENTENCE_CHARS < MAX_BUFFER_CHARS // 2


# ───────────────────────── v7.2: eager first emission ─────────────────────────


def test_first_emission_cuts_early_at_a_comma():
    # Measured starvation fix: the FIRST emission of a pass may cut at a comma
    # ≥ EAGER_FIRST_MIN_CHARS — the explanation's audio starts at the first
    # natural pause instead of after the whole opening sentence.
    splitter = SentenceSplitter()
    head = "زر Start موجود في وسط شريط المهام تقريباً،"
    tail = "وهو أيقونة شعار Windows اللي تفتح القائمة."
    out = splitter.push(head + " " + tail)
    assert out == [head, tail]                    # early first audio; rest whole


def test_eager_cut_fires_only_for_the_first_emission():
    splitter = SentenceSplitter()
    first = "الجملة الافتتاحية هنا طويلة كفاية للفاصلة، وتكمل بعد الفاصلة بكلام طويل كفاية."
    second = "الجملة الثانية فيها فاصلة أيضاً، لكنها تبقى كاملة حتى نهايتها."
    out = splitter.push(first + " " + second)
    assert out[0].endswith("،")                   # first: the eager comma cut
    assert second in out                          # later commas never cut


def test_flush_rearms_the_eager_window_for_the_next_pass():
    splitter = SentenceSplitter()
    sentence = "افتتاحية الدور فيها فاصلة بعد ثلاثين حرفاً تقريباً، ثم بقية الكلام هنا."
    assert splitter.push(sentence)[0].endswith("،")
    splitter.flush()                              # pass ended → eager re-armed
    assert splitter.push(sentence)[0].endswith("،")


def test_an_early_comma_is_not_an_eager_cut():
    # A comma BEFORE the eager floor ("نعم، ...") is conversational glue, not
    # a viable first-audio unit — the emission waits for the real ender.
    splitter = SentenceSplitter()
    sentence = "نعم، هذا هو الزر المطلوب تماماً."
    assert splitter.push(sentence) == [sentence]


def test_eager_comma_never_splits_a_number():
    splitter = SentenceSplitter()
    sentence = "القيمة النهائية للمشروع تساوي 1,250 ريالاً سعودياً."
    assert splitter.push(sentence) == [sentence]


def test_eager_floor_constant_is_sane():
    # The eager floor must sit at/above the merge floor (an eager piece must be
    # a legitimate TTS unit) and well under the valve.
    assert MIN_SENTENCE_CHARS <= EAGER_FIRST_MIN_CHARS < MAX_BUFFER_CHARS // 2
