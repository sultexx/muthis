# tests/test_doc_chunking.py
"""
Structural chunking + the STRICT token guard (V2 Phase 2 M3, T1).

The token counter is INJECTED here, exactly as production injects it (T2 wires
e5's own tokenizer). A word-count stand-in makes every size in these tests
readable and every boundary exact — the point under test is the CHUNKER's
behaviour at a window, not a vendor's tokenization, which P0 already measured.

The guard test is the one that matters. A chunk over the window is truncated by
the encoder at its max sequence length: the tail is never indexed, nothing
complains, and the document LOOKS fully ingested. DEC-45 therefore requires the
operation to FAIL rather than warn, and a guard that cannot fail is not a guard
(DEC-12) — so it is driven by constructing exactly that condition.
"""

from __future__ import annotations

import pytest

from muthis.broker.docs.blocks import (
    KIND_CODE, KIND_HEADING, KIND_TABLE, KIND_TEXT, Block,
)
from muthis.broker.docs.chunking import Chunker, ChunkWindowExceeded


def words(text: str) -> int:
    """The injected counter: one token per whitespace-separated word."""
    return len(text.split())


def _text(body: str, *, page=None, para=0, section="") -> Block:
    return Block(text=body, page=page, para=para, kind=KIND_TEXT, section=section)


# ---------------------------------------------------------------------------
# Structure first, window only as a fallback
# ---------------------------------------------------------------------------

def test_a_heading_opens_a_chunk_and_stays_with_its_text():
    """Headings are the boundary the design PREFERS, and a heading belongs with
    the text it titles — separating them would strand the title."""
    blocks = [
        Block(text="المعمارية", kind=KIND_HEADING, section="1"),
        _text("النص الأول تحت العنوان.", section="1"),
        Block(text="البرمجيات", kind=KIND_HEADING, section="2"),
        _text("النص الثاني.", section="2"),
    ]
    chunks, report = Chunker(words, window=50).chunk(blocks)

    assert len(chunks) == 2
    assert chunks[0].text.startswith("المعمارية")
    assert chunks[1].text.startswith("البرمجيات")
    assert report.fallback_windowed == 0        # structure was available


def test_paragraphs_fill_to_the_cap_then_start_a_new_chunk():
    blocks = [_text(" ".join(f"كلمة{i}" for i in range(6))) for _ in range(4)]
    chunks, report = Chunker(words, window=13).chunk(blocks)

    assert all(c.n_tokens <= 13 for c in chunks)
    assert len(chunks) > 1
    assert report.admitted == len(chunks) and report.ok


def test_an_oversized_UNSTRUCTURED_block_takes_the_window_fallback():
    """The fallback is reached only when the document offered no smaller
    structure — a guess must never override a known answer."""
    body = " ".join(f"كلمة{i}" for i in range(60)) + "."
    chunks, report = Chunker(words, window=20).chunk([_text(body)])

    assert report.fallback_windowed == len(chunks) > 1
    assert all(c.n_tokens <= 20 for c in chunks)


def test_the_window_fallback_cuts_on_sentence_boundaries():
    """A cut mid-sentence reproduces, at small scale, the amputation
    small-to-big exists to prevent."""
    body = "الجملة الأولى هنا. الجملة الثانية هنا. الجملة الثالثة هنا."
    chunks, _ = Chunker(words, window=5).chunk([_text(body)])

    for chunk in chunks:
        assert "الجملة" in chunk.text
        assert not chunk.text.startswith(".")


# ---------------------------------------------------------------------------
# Atomicity (DEC-45)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", [KIND_CODE, KIND_TABLE])
def test_an_atomic_block_is_never_split(kind):
    """Splitting one destroys BOTH retrievers at once, which no other content
    type does — half a table loses the header row, half a code block loses the
    identifiers that were the exact-match signal."""
    body = " ".join(f"tok{i}" for i in range(40))
    chunks, report = Chunker(words, window=10).chunk([Block(text=body, kind=kind)])

    assert len(chunks) == 1                       # whole, not cut
    assert chunks[0].text == body
    assert chunks[0].truncated is True            # EXPLICIT, never silent
    assert report.truncated_atomic == 1


@pytest.mark.parametrize("kind", [KIND_CODE, KIND_TABLE])
def test_an_atomic_block_within_the_window_is_not_flagged(kind):
    """The positive control: the flag means 'over the window', not 'atomic'."""
    chunks, report = Chunker(words, window=50).chunk(
        [Block(text="tok1 tok2 tok3", kind=kind)])

    assert len(chunks) == 1 and chunks[0].truncated is False
    assert report.truncated_atomic == 0


def test_an_atomic_block_is_not_merged_with_its_neighbours():
    blocks = [_text("قبل الجدول."),
              Block(text="| أ | ب |", kind=KIND_TABLE),
              _text("بعد الجدول.")]
    chunks, _ = Chunker(words, window=50).chunk(blocks)

    table_chunks = [c for c in chunks if c.blocks[0].kind == KIND_TABLE]
    assert len(table_chunks) == 1
    assert table_chunks[0].text == "| أ | ب |"


# ---------------------------------------------------------------------------
# THE STRICT GUARD
# ---------------------------------------------------------------------------

def test_the_guard_FAILS_the_operation_on_an_oversized_chunk():
    """DEC-45: it FAILS, it does not warn.

    Driven by the ONE input no boundary can rescue — a SINGLE TOKEN that alone
    exceeds the window (a base64 blob, a giant URL). Sentence and word splitting
    both bottom out there by construction, so this is exactly where the guard is
    the last line rather than a redundant one."""
    def counter(text: str) -> int:
        # One pathological word tokenizes past any window; everything else is
        # ordinary. Deterministic, and independent of call ORDER.
        return 500 if "قنبلة" in text else len(text.split())

    with pytest.raises(ChunkWindowExceeded) as excinfo:
        Chunker(counter, window=10).chunk([_text("كلمة قنبلة كلمة")])

    assert excinfo.value.window == 10
    assert excinfo.value.n_tokens == 500
    assert "exceeds" in str(excinfo.value)


def test_one_sentence_longer_than_the_window_falls_to_WORD_boundaries():
    """The gap these tests found: Arabic prose runs long between full stops, and
    PDF extraction often yields a paragraph with NO sentence ender at all. A
    sentence-only splitter hands the guard an over-window chunk and REFUSES an
    ordinary document, so the fallback drops one level — still never mid-word."""
    body = " ".join(f"كلمة{i}" for i in range(45))     # no sentence ender at all
    chunks, report = Chunker(words, window=10).chunk([_text(body)])

    assert len(chunks) >= 5
    assert all(c.n_tokens <= 10 for c in chunks)
    assert report.fallback_windowed == len(chunks)
    # never mid-word: every emitted token is a whole original word
    emitted = " ".join(c.text for c in chunks).split()
    assert set(emitted) == {f"كلمة{i}" for i in range(45)}


def test_the_guard_does_NOT_fire_on_the_documented_atomic_exception():
    """The one carve-out, and it is explicit: an atomic block over the window was
    already handled with a truncation note, so failing again would make the
    documented path unreachable."""
    body = " ".join(f"tok{i}" for i in range(40))
    chunks, _ = Chunker(words, window=10).chunk([Block(text=body, kind=KIND_CODE)])

    assert chunks[0].n_tokens > 10 and chunks[0].truncated


def test_a_clean_document_passes_the_guard():
    """Positive control: the guard must not be firing for unrelated reasons."""
    chunks, report = Chunker(words, window=20).chunk(
        [_text("كلمة " * 5) for _ in range(3)])

    assert all(c.n_tokens <= 20 for c in chunks)
    assert report.ok


# ---------------------------------------------------------------------------
# Position survives chunking (DEC-45 — INERT until Phase 3)
# ---------------------------------------------------------------------------

def test_every_chunk_carries_its_position():
    blocks = [_text("أول.", page=3, para=0), _text("ثانٍ.", page=3, para=1),
              _text("ثالث.", page=9, para=0)]
    chunks, _ = Chunker(words, window=4).chunk(blocks)

    admitted = 0
    for chunk in chunks:
        assert chunk.page is not None
        assert chunk.para is not None
        assert chunk.blocks                      # the parent is derivable
        admitted += 1
    # The standing cutoff rule: a check that examined nothing must never look
    # like a check that passed.
    assert admitted == len(chunks) > 0


def test_the_parent_key_is_the_page_for_pdfs_and_the_section_otherwise():
    """small-to-big returns the PARENT, so the key must be stable and derived —
    never a second stored copy that can drift."""
    pdf_chunks, _ = Chunker(words, window=50).chunk([_text("نص.", page=7, para=2)])
    md_chunks, _ = Chunker(words, window=50).chunk([_text("نص.", section="2.1")])

    assert pdf_chunks[0].parent == "p7"
    assert md_chunks[0].parent == "s2.1"


def test_the_report_states_the_window_and_the_overlap_it_used():
    _, report = Chunker(words, window=40, overlap_ratio=0.15).chunk([_text("نص قصير.")])

    assert report.window_tokens == 40
    assert report.overlap_tokens == 6            # 15% of 40
    assert "window=40tok" in report.describe()
