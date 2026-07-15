"""
test_speech_stream.py — the streaming Arabic sentence splitter (v5 Phase C1),
pure unit tests (no TTS, no orchestrator, no network).

Proves: fragments in → complete sentences out, in order; no sentence is ever
cut mid-way; the decimal guard holds "3." at the buffer end and never splits
"3.14"; the ~200-char safety valve frees an unpunctuated run; flush() returns
the tail and resets; punctuation-only scraps never come out.

Run:  set PYTHONPATH=src && python -m pytest tests/test_speech_stream.py -q
"""

from __future__ import annotations

from muthis.speech_stream import MAX_BUFFER_CHARS, SentenceSplitter


def test_fragments_produce_sentences_in_order():
    splitter = SentenceSplitter()
    assert splitter.push("الجملة الأولى. والث") == ["الجملة الأولى."]
    assert splitter.push("انية؟ تكملة") == ["والثانية؟"]
    assert splitter.flush() == ["تكملة"]


def test_a_sentence_split_across_many_tiny_deltas_arrives_once_and_whole():
    splitter = SentenceSplitter()
    sentence = "زر الحفظ فوق يسار الشاشة."
    emitted = []
    for char in sentence:
        emitted += splitter.push(char)
    assert emitted == [sentence]
    assert splitter.flush() == []


def test_all_arabic_enders_and_newline_are_boundaries():
    splitter = SentenceSplitter()
    out = splitter.push("سؤال؟ تعجب! فاصلة؛ سطر\nالباقي")
    assert out == ["سؤال؟", "تعجب!", "فاصلة؛", "سطر"]
    assert splitter.flush() == ["الباقي"]


def test_decimal_number_is_never_split():
    # The whole thing in one push: the dot between digits is not a boundary.
    splitter = SentenceSplitter()
    assert splitter.push("قيمة π هي 3.14 تقريباً.") == ["قيمة π هي 3.14 تقريباً."]


def test_dot_held_at_buffer_end_after_a_digit_until_context_arrives():
    splitter = SentenceSplitter()
    assert splitter.push("النسبة 3.") == []          # held — "14" may follow
    assert splitter.push("14 بالمئة.") == ["النسبة 3.14 بالمئة."]
    # And when the next char is NOT a digit, the held dot resolves to a boundary.
    assert splitter.push("انتهى العد عند 5.") == []   # held again
    assert splitter.push(" وبدأنا") == ["انتهى العد عند 5."]
    assert splitter.flush() == ["وبدأنا"]


def test_dot_after_a_letter_emits_immediately():
    splitter = SentenceSplitter()
    assert splitter.push("تمام.") == ["تمام."]        # no digit before → no hold


def test_flush_returns_the_held_decimal_tail():
    splitter = SentenceSplitter()
    assert splitter.push("الإصدار 2.") == []
    assert splitter.flush() == ["الإصدار 2."]         # stream ended → release it


def test_safety_valve_frees_an_unpunctuated_run():
    splitter = SentenceSplitter()
    run = "كلمة " * 50                                # 250 chars, no punctuation
    emitted = splitter.push(run)
    assert len(emitted) == 1
    assert len(emitted[0]) >= MAX_BUFFER_CHARS - 10   # the whole run, one piece
    assert splitter.flush() == []                     # buffer was reset


def test_punctuation_only_scraps_never_come_out():
    splitter = SentenceSplitter()
    assert splitter.push("؟!") == []
    assert splitter.flush() == []


def test_flush_on_empty_is_empty_and_splitter_is_reusable():
    splitter = SentenceSplitter()
    assert splitter.flush() == []
    assert splitter.push("جديدة.") == ["جديدة."]
