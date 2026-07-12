"""
test_overlay_shapes_dispatch.py — the draw_shapes overlay path, proven with
FAKE view objects and the REAL command queue (no Tk window, no screen):

  * "draw_shapes" → the ShapesWidget draws the list; rect/pointer untouched,
  * "hide" → shapes are cleared TOO (the ghosting rule now covers shapes),
  * "show" (the highlight_target path) never touches the shapes widget,
  * dispatch_command stays backward-compatible WITHOUT a shapes widget,
  * SidekickOverlay.draw_shapes/hide enqueue the right commands (fake thread).

Run:  set PYTHONPATH=src && python -m pytest tests/test_overlay_shapes_dispatch.py -q
"""

from __future__ import annotations

import asyncio

from muthis.overlay.sidekick_window import SidekickOverlay, dispatch_command
from muthis.shapes import Shape, circle_shape


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
        self.started = []
        self.cancels = 0

    def start(self, target, on_arrival):
        self.started.append((target, on_arrival))

    def cancel(self):
        self.cancels += 1


class FakeShapes:
    def __init__(self):
        self.drawn = []          # one entry per draw() call (the full list)
        self.cleared = 0

    def draw(self, shapes):
        self.drawn.append(tuple(shapes))

    def clear(self):
        self.cleared += 1


def _fakes():
    return FakeRect(), FakePointer(), FakeAnimator(), FakeShapes()


SHAPES = (
    Shape(kind="line", points=(150, 150, 300, 300), label_ar="خط"),
    circle_shape(500, 400, 60, label_ar="دائرة"),
)


# ─────────────────────── dispatch_command + shapes ───────────────────────


def test_draw_shapes_draws_the_list_and_touches_nothing_else():
    rect, pointer, animator, shapes = _fakes()

    cont = dispatch_command(
        ("draw_shapes", SHAPES),
        rect=rect, pointer=pointer, animator=animator, shapes=shapes,
    )

    assert cont is True
    assert shapes.drawn == [SHAPES]
    # The highlight path is untouched: no rect/pointer draw, clear, or glide.
    assert rect.drawn == [] and rect.cleared == 0
    assert pointer.moves == [] and pointer.cleared == 0
    assert animator.started == [] and animator.cancels == 0


def test_hide_clears_the_shapes_too():
    rect, pointer, animator, shapes = _fakes()

    cont = dispatch_command(
        ("hide",), rect=rect, pointer=pointer, animator=animator, shapes=shapes,
    )

    assert cont is True
    assert shapes.cleared == 1               # ghosting now covers shapes
    assert shapes.drawn == []                # hide never draws
    # The existing hide behavior is unchanged alongside.
    assert animator.cancels == 1
    assert pointer.cleared == 1
    assert rect.cleared == 1


def test_show_the_highlight_path_never_touches_the_shapes_widget():
    rect, pointer, animator, shapes = _fakes()

    dispatch_command(
        ("show", (10, 20, 110, 220), "زر الحفظ"),
        rect=rect, pointer=pointer, animator=animator, shapes=shapes,
    )

    assert shapes.drawn == [] and shapes.cleared == 0


def test_dispatch_still_works_without_a_shapes_widget():
    # Backward compatibility: the pre-shapes signature (no shapes kwarg) must
    # keep working so highlight_target call sites/tests stay unchanged.
    rect, pointer, animator, _ = _fakes()

    assert dispatch_command(
        ("hide",), rect=rect, pointer=pointer, animator=animator,
    ) is True
    assert dispatch_command(
        ("draw_shapes", SHAPES),
        rect=rect, pointer=pointer, animator=animator,
    ) is True                                # a no-op, never a crash


# ──────────────── SidekickOverlay enqueues (no Tk thread) ────────────────


def _overlay_with_a_disarmed_thread() -> SidekickOverlay:
    """A real SidekickOverlay whose Tk thread never starts, so the REAL queue
    can be inspected directly (the commands are what the Tk thread would see)."""
    overlay = SidekickOverlay()
    overlay._ensure_thread = lambda: None    # the fake "thread"
    return overlay


def test_draw_shapes_enqueues_one_command_with_the_shape_tuple():
    overlay = _overlay_with_a_disarmed_thread()

    asyncio.run(overlay.draw_shapes(list(SHAPES)))

    command = overlay._commands.get_nowait()
    assert command == ("draw_shapes", SHAPES)  # normalized to a tuple
    assert overlay._commands.empty()           # exactly ONE command


def test_hide_enqueues_the_same_hide_command_as_before():
    overlay = _overlay_with_a_disarmed_thread()

    asyncio.run(overlay.hide())

    assert overlay._commands.get_nowait() == ("hide",)
