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
