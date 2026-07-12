"""
test_pointer_widget.py — the gliding arrow's drawing, proven with a FAKE canvas
(no real Tk window), now for the NEON look (Batch 1). It must draw ONLY its own
TAGGED items so clearing/redrawing the pointer never disturbs the rectangle that
shares the canvas, and it must glow: a dim HALO polygon under a bright CORE.

Env is cleared by conftest, so the from_env() fallback yields the neon defaults.

Run:  set PYTHONPATH=src && python -m pytest tests/test_pointer_widget.py -q
"""

from __future__ import annotations

from muthis.overlay.pointer_widget import POINTER_TAG, PointerWidget
from muthis.overlay.style import OverlayStyle, dim

DEFAULTS = OverlayStyle()


class FakeCanvas:
    """Records polygon creates and delete() tags — never delete('all')."""

    def __init__(self):
        self.polygons = []     # (coords, kwargs) per create_polygon
        self.deleted = []      # tag passed to each delete()

    def create_polygon(self, *coords, **kwargs):
        self.polygons.append((coords, kwargs))
        return len(self.polygons)

    def delete(self, tag):
        self.deleted.append(tag)


def test_move_to_draws_a_halo_and_a_core_both_tagged_with_tip_at_the_point():
    canvas = FakeCanvas()
    PointerWidget(canvas).move_to(300, 400)

    # Two passes: a dim halo then the bright core, both tag-scoped so they clear
    # independently of the rectangle that shares the canvas.
    assert len(canvas.polygons) == 2
    halo, core = canvas.polygons[0], canvas.polygons[1]
    assert halo[1]["tags"] == POINTER_TAG and core[1]["tags"] == POINTER_TAG
    # The arrow's tip (first offset (0,0)) sits exactly on the glide coordinate.
    assert (halo[0][0], halo[0][1]) == (300, 400)
    assert (core[0][0], core[0][1]) == (300, 400)
    # The core is the neon pointer color; the halo is that color dimmed and wider.
    assert core[1]["fill"] == DEFAULTS.colors["pointer"]
    assert halo[1]["fill"] == dim(DEFAULTS.colors["pointer"], DEFAULTS.glow_intensity)
    assert halo[1]["width"] > core[1]["width"]


def test_glow_disabled_draws_a_single_core_polygon():
    canvas = FakeCanvas()
    PointerWidget(canvas, OverlayStyle(glow_enabled=False)).move_to(5, 5)

    assert len(canvas.polygons) == 1
    assert canvas.polygons[0][1]["fill"] == DEFAULTS.colors["pointer"]


def test_move_to_replaces_previous_frame_by_tag_never_delete_all():
    canvas = FakeCanvas()
    pointer = PointerWidget(canvas)
    pointer.move_to(10, 10)
    pointer.move_to(20, 20)

    # Each redraw clears ONLY the pointer tag once — a shared rectangle is untouched.
    assert canvas.deleted == [POINTER_TAG, POINTER_TAG]
    # And the latest frame's core tip is at the newest coordinate.
    coords, _kwargs = canvas.polygons[-1]
    assert (coords[0], coords[1]) == (20, 20)


def test_clear_deletes_only_the_pointer_tag():
    canvas = FakeCanvas()
    pointer = PointerWidget(canvas)
    pointer.move_to(5, 5)
    pointer.clear()
    assert canvas.deleted[-1] == POINTER_TAG
    assert all(tag == POINTER_TAG for tag in canvas.deleted)
