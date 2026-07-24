# tests/test_net_extract.py
"""extract.py (DEC-18) — the HTML→readable-text reduction + the ~4k-token cap,
unit-tested in isolation (no network, no fetcher). trafilatura's real behavior
was probed live in T3a; these pin the CONTRACT: markup stripped, a miss returns
None (never raw HTML), never raises, and the cap truncates at a boundary with the
Arabic note."""

from __future__ import annotations

from muthis.broker.net.extract import (
    EXTRACT_TRUNCATED_AR,
    MAX_EXTRACT_CHARS,
    cap_extract,
    extract_html,
)


# ── extract_html: markup stripped, boilerplate dropped ───────────────────────
def test_extract_html_returns_readable_prose_stripping_markup():
    html = (
        "<html><body><nav>NAV-DROP menu</nav><article><h1>Title</h1>"
        "<p>The main readable article sentence lives here for the extraction test.</p>"
        "</article><footer>FOOTER-DROP copyright</footer></body></html>"
    )
    out = extract_html(html)
    assert out and "main readable article sentence" in out
    assert "<p>" not in out and "<article>" not in out  # markup stripped
    assert "FOOTER-DROP" not in out                      # boilerplate stripped


# ── extract_html: a miss is None, NEVER raw HTML (the load-bearing guard) ─────
def test_extract_html_returns_none_when_there_is_no_readable_content():
    # A JS-only shell + bare non-markup both yield None (verified live in T3a).
    assert extract_html('<html><body><div id="root"></div><script>x=1</script></body></html>') is None
    assert extract_html("bare words with no markup structure at all") is None
    assert extract_html("") is None


def test_extract_html_never_raises_on_garbage():
    for junk in ["", "   \n\t ", "<<<>>>", "\x00\x01 not html", "<p>unclosed"]:
        out = extract_html(junk)
        assert out is None or isinstance(out, str)  # returns, never raises


# ── cap_extract: the ~4k-token cap, mirroring read_local_file ────────────────
def test_cap_extract_passes_short_text_through_untouched():
    text = "a short readable paragraph of extracted prose."
    out, truncated = cap_extract(text)
    assert out == text and truncated is False


def test_cap_extract_at_the_exact_cap_is_not_truncated():
    text = "A" * MAX_EXTRACT_CHARS
    out, truncated = cap_extract(text)
    assert out == text and truncated is False


def test_cap_extract_truncates_over_cap_with_the_note_at_a_word_boundary():
    text = "word " * 5000  # 25000 chars, no newlines
    out, truncated = cap_extract(text)
    assert truncated is True
    assert out.endswith(EXTRACT_TRUNCATED_AR)
    assert len(out) <= MAX_EXTRACT_CHARS + len(EXTRACT_TRUNCATED_AR)
    body = out[: -len(EXTRACT_TRUNCATED_AR)]
    assert body.split()[-1] == "word"  # cut at a whole word, never mid-token


def test_cap_extract_prefers_a_paragraph_boundary_when_present():
    text = "A" * 15990 + "\n" + "B" * 1000  # a newline sits inside the window
    out, truncated = cap_extract(text)
    assert truncated is True
    assert "B" not in out  # everything past the last in-window newline is dropped
