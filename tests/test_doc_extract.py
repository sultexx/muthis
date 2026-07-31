# tests/test_doc_extract.py
"""
Document extraction (V2 Phase 2 M3, T1) — the ASSEMBLY, driven directly.

WHAT THESE TESTS DELIBERATELY DO NOT TEST: whether `pypdf` decodes Arabic
correctly. That was settled by MEASUREMENT at the P0 gate against Sultan's real
corpus (DEC-48/DEC-49), where PyMuPDF and pdfminer.six both FAILED the binding
Arabic condition and pypdf passed on both PDFs. Re-testing a vendor here would
need the corpus, and the corpus may never enter this repository.

WHAT THEY DO TEST is the half DEC-49 recorded as REAL WORK the milestone must
carry: `pypdf` hands back loose text runs with a text matrix, and turning those
into positioned paragraphs is OUR code. The visitor is therefore driven with
SCRIPTED runs, so the RTL ordering, the y-gap paragraphing and the page
numbering are exercised deterministically with real Arabic — no corpus, no
vendor behaviour, no display.

The RTL assertion is the load-bearing one: ordering runs left-to-right would
produce a per-line word reversal that looks EXACTLY like the pdfminer defect the
whole library choice exists to avoid, and it would still return a plausible
block count.
"""

from __future__ import annotations

import pathlib

import pytest

from muthis.broker.docs.blocks import KIND_CODE, KIND_HEADING, KIND_TABLE
from muthis.broker.docs.extract import (
    NoTextLayer, PARAGRAPH_GAP_POINTS, UnsupportedDocument, extract_blocks,
)


class _FakePage:
    """One page whose visitor replays scripted (y, x, text) runs."""

    def __init__(self, runs):
        self._runs = runs

    def extract_text(self, visitor_text=None):
        for y, x, text in self._runs:
            # pypdf's signature: (text, cm, tm, font_dict, font_size); tm[4]=x, tm[5]=y.
            visitor_text(text, None, [1, 0, 0, 1, x, y], {}, 10)
        return ""


class _FakeReader:
    def __init__(self, pages):
        self.pages = [_FakePage(runs) for runs in pages]


def _patch_reader(monkeypatch, pages):
    import pypdf
    monkeypatch.setattr(pypdf, "PdfReader", lambda _path: _FakeReader(pages))


# ---------------------------------------------------------------------------
# PDF assembly
# ---------------------------------------------------------------------------

def test_runs_on_one_line_are_ordered_right_to_left(monkeypatch, tmp_path):
    """THE Arabic rule: the RIGHTMOST run comes first.

    Left-to-right assembly yields a word-order reversal that is still valid
    Arabic script — the failure mode that passes every "did we get a string
    back" check."""
    _patch_reader(monkeypatch, [[
        (700.0, 100.0, "سطام"),            # leftmost  -> LAST in reading order
        (700.0, 300.0, "جامعة الأمير "),   # rightmost -> FIRST
    ]])
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    blocks, _ = extract_blocks(pdf)

    assert blocks[0].text == "جامعة الأمير سطام"
    assert blocks[0].text != "سطامجامعة الأمير "      # the LTR mistake, named


def test_lines_are_ordered_top_down(monkeypatch, tmp_path):
    """PDF origin is bottom-left, so a LARGER y is HIGHER on the page.

    The two lines sit INSIDE the paragraph gap on purpose, so this test isolates
    ORDERING; the gap's own behaviour is the next test's job."""
    _patch_reader(monkeypatch, [[
        (695.0, 100.0, "الثاني"),
        (700.0, 100.0, "الأول"),
    ]])
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    blocks, _ = extract_blocks(pdf)

    assert blocks[0].text.splitlines() == ["الأول", "الثاني"]


def test_the_paragraph_gap_cutoff_splits_and_is_REPORTED(monkeypatch, tmp_path):
    """The cutoff is a filter INSIDE the extraction, so it is reported.

    A wrong gap silently merges or shatters paragraphs while the block count
    still looks plausible — the standing rule exists for exactly this."""
    _patch_reader(monkeypatch, [[
        (700.0, 100.0, "فقرة أولى"),
        (695.0, 100.0, "نفس الفقرة"),        # 5pt gap  -> same paragraph
        (600.0, 100.0, "فقرة ثانية"),        # 95pt gap -> new paragraph
    ]])
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    blocks, report = extract_blocks(pdf)

    assert len(blocks) == 2
    assert [b.para for b in blocks] == [0, 1]
    assert report.cutoffs["paragraph_gap_points"] == PARAGRAPH_GAP_POINTS
    assert "paragraph_gap_points=6" in report.describe()


def test_every_block_carries_page_and_paragraph(monkeypatch, tmp_path):
    """DEC-45's HARD requirement: position on every block, free now and
    unrecoverable later without a full re-index."""
    _patch_reader(monkeypatch, [
        [(700.0, 100.0, "صفحة واحد")],
        [(700.0, 100.0, "صفحة اثنين")],
    ])
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    blocks, report = extract_blocks(pdf)

    assert [b.page for b in blocks] == [1, 2]
    assert all(b.para is not None for b in blocks)
    assert report.pages_total == 2 and report.pages_with_text == 2


def test_a_pdf_with_no_text_layer_raises_NoTextLayer(monkeypatch, tmp_path):
    """A SCANNED pdf is TERMINAL and must not be reported as 'not found'.

    DEC-35: a refusal that misreports its reason turns a terminal condition into
    a retryable one, and the model rationally retried four paths."""
    _patch_reader(monkeypatch, [[], []])
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    with pytest.raises(NoTextLayer):
        extract_blocks(pdf)


def test_an_unsupported_format_raises_its_OWN_exception(tmp_path):
    """DOCX is not scanned — it is out of launch scope, and the two are
    DIFFERENT conditions with different remedies (DEC-47)."""
    docx = tmp_path / "a.docx"
    docx.write_bytes(b"PK\x03\x04")

    with pytest.raises(UnsupportedDocument):
        extract_blocks(docx)


def test_zero_admitted_is_not_ok(tmp_path):
    """The standing rule as a property of the report itself: an extraction that
    admitted nothing must NEVER look like one that ran clean."""
    from muthis.broker.docs.blocks import ExtractReport

    empty = ExtractReport(source=".md", blocks=0, pages_total=None,
                          pages_with_text=None, chars=0)
    assert empty.admitted == 0
    assert empty.ok is False
    assert ExtractReport(source=".md", blocks=3, pages_total=None,
                         pages_with_text=None, chars=9).ok is True


# ---------------------------------------------------------------------------
# Markdown / TXT structure
# ---------------------------------------------------------------------------

def _md(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    p = tmp_path / "doc.md"
    p.write_text(body, encoding="utf-8")
    return p


def test_headings_carry_their_section_number(tmp_path):
    blocks, _ = extract_blocks(_md(tmp_path, """# العنوان

## 1. المعمارية

نص عادي هنا.

### 1.1 المقارنة

نص آخر.
"""))
    sections = {b.section for b in blocks if b.kind != KIND_HEADING}
    assert "1" in sections and "1.1" in sections
    assert any(b.kind == KIND_HEADING for b in blocks)


def test_a_fenced_code_block_is_ONE_atomic_block(tmp_path):
    blocks, _ = extract_blocks(_md(tmp_path, """## 2. الكود

```python
def set_motor_speed(speed):
    RPWM.duty(speed)
```

بعد الكود.
"""))
    code = [b for b in blocks if b.kind == KIND_CODE]
    assert len(code) == 1
    assert "RPWM.duty" in code[0].text
    assert code[0].is_atomic


def test_an_unterminated_fence_is_closed_not_dropped(tmp_path):
    """A real property of the P0 corpus: dropping the run would silently lose a
    document's tail while the block count still looked reasonable."""
    blocks, _ = extract_blocks(_md(tmp_path, """## 2. الكود

```python
set_motor_speed(750)
"""))
    code = [b for b in blocks if b.kind == KIND_CODE]
    assert len(code) == 1
    assert "set_motor_speed(750)" in code[0].text


def test_a_pipe_table_is_atomic(tmp_path):
    blocks, _ = extract_blocks(_md(tmp_path, """## 1.1 المقارنة

| المشغل | التيار |
|---|---|
| L298N | 2A |
| BTS7960 | 43A |
"""))
    tables = [b for b in blocks if b.kind == KIND_TABLE]
    assert len(tables) == 1
    assert "BTS7960" in tables[0].text and "L298N" in tables[0].text
    assert tables[0].is_atomic


def test_markdown_blocks_have_no_page_but_do_have_a_position(tmp_path):
    """None is the HONEST answer for an unpaginated format — never a zero that
    would read as 'page zero'."""
    blocks, report = extract_blocks(_md(tmp_path, "أول.\n\nثاني.\n\nثالث.\n"))

    assert all(b.page is None for b in blocks)
    assert [b.para for b in blocks] == list(range(len(blocks)))
    assert report.pages_total is None
    assert report.ok and report.admitted == len(blocks)
