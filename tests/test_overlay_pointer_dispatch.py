"""
test_overlay_pointer_dispatch.py — the overlay's command handling, proven with
FAKE view objects (no real Tk window, no real mouse). This is the logic the real
SidekickOverlay._drain delegates to from inside the Tk mainloop:

  * "show" → glide the pointer to the bbox CENTER (animator.start) and draw NOTHING
    now; only on ARRIVAL draw the rectangle + re-draw the pointer on top (the
    audio-sync: motion starts with the audio, the rectangle lands as it finishes),
  * "hide" → cancel any glide and clear BOTH pointer and rectangle (ghosting),
  * "close" → cancel the glide and signal stop.

Run:  set PYTHONPATH=src && python -m pytest tests/test_overlay_pointer_dispatch.py -q
"""

from __future__ import annotations

from muthis.overlay.sidekick_window import _bbox_center, dispatch_command


# ──────────────────────────────── Fakes ────────────────────────────────


class FakeRect:
    def __init__(self):
        self.drawn = []
        self.cleared = 0

    def draw(self, bbox, label_ar):
        self.drawn.append((bbox, label_ar))

    def clear(self):
        self.cleared += 1


class FakePointer:
    def __init__(self):
        self.moves = []
        self.cleared = 0

    def move_to(self, x, y):
        self.moves.append((x, y))

    def clear(self):
        self.cleared += 1


class FakeAnimator:
    def __init__(self):
        self.started = []      # (target, on_arrival) per start()
        self.cancels = 0

    def start(self, target, on_arrival):
        self.started.append((target, on_arrival))

    def cancel(self):
        self.cancels += 1


def _fakes():
    return FakeRect(), FakePointer(), FakeAnimator()


# ──────────────────────────────── Tests ────────────────────────────────


def test_bbox_center():
    assert _bbox_center((0, 0, 100, 200)) == (50, 100)
    assert _bbox_center((10, 20, 30, 40)) == (20, 30)


def test_show_starts_a_glide_to_center_and_defers_the_draw_to_arrival():
    rect, pointer, animator = _fakes()

    cont = dispatch_command(
        ("show", (10, 20, 110, 220), "زر الحفظ"),
        rect=rect, pointer=pointer, animator=animator,
    )

    assert cont is True
    # A glide to the bbox CENTER was started...
    assert len(animator.started) == 1
    target, on_arrival = animator.started[0]
    assert target == (60, 120)
    # ...and NOTHING is drawn yet — the rectangle is deferred to arrival (sync).
    assert rect.drawn == []
    # A stale rectangle / pointer / glide were dropped before the new glide.
    assert animator.cancels == 1
    assert rect.cleared == 1
    assert pointer.cleared == 1

    # Firing on_arrival (end of glide) draws the rectangle at the FULL bbox and
    # re-draws the pointer at the center ON TOP, so both stay until auto-hide.
    on_arrival()
    assert rect.drawn == [((10, 20, 110, 220), "زر الحفظ")]
    assert pointer.moves[-1] == (60, 120)


def test_hide_cancels_the_glide_and_clears_pointer_and_rectangle():
    rect, pointer, animator = _fakes()

    cont = dispatch_command(("hide",), rect=rect, pointer=pointer, animator=animator)

    assert cont is True
    assert animator.cancels == 1
    assert pointer.cleared == 1
    assert rect.cleared == 1
    assert rect.drawn == []          # hide never draws


def test_close_cancels_the_glide_and_signals_stop():
    rect, pointer, animator = _fakes()

    cont = dispatch_command(("close",), rect=rect, pointer=pointer, animator=animator)

    assert cont is False             # the drain loop tears the window down
    assert animator.cancels == 1
