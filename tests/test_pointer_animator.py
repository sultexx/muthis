"""
test_pointer_animator.py — the gliding pointer's motion logic, proven WITHOUT a
real Tk window or a real mouse.

LOOK-ONLY: the animator READS the OS cursor once per glide (injected fake here)
and never moves it — it has no API to. These tests inject a fake cursor_reader, a
fake frame scheduler, and a fake clock, so the whole ease-in-out glide is driven
deterministically: no real window, no real mouse, no real sleep.

Run:  set PYTHONPATH=src && python -m pytest tests/test_pointer_animator.py -q
"""

from __future__ import annotations

from muthis.overlay.pointer_animator import (
    DEFAULT_POINTER_ANIM_MS, PointerAnimator, _ease_in_out,
)


# ──────────────────────────────── Fakes ────────────────────────────────


class FakePointer:
    """Records each move_to so the test can read the interpolated path."""

    def __init__(self):
        self.moves = []

    def move_to(self, x, y):
        self.moves.append((x, y))


class FakeScheduler:
    """Stands in for root.after: captures each scheduled (ms, fn). The test fires
    the next frame by advancing the fake clock then calling run_next()."""

    def __init__(self):
        self.scheduled = []

    def after(self, ms, fn):
        self.scheduled.append((ms, fn))
        return f"id{len(self.scheduled)}"

    def run_next(self):
        _ms, fn = self.scheduled.pop(0)
        fn()


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def _make(*, duration_ms=100, frame_ms=10, cursor=(0, 0)):
    pointer, sched, clock = FakePointer(), FakeScheduler(), FakeClock()
    anim = PointerAnimator(
        schedule=sched.after, pointer=pointer, duration_ms=duration_ms,
        frame_ms=frame_ms, clock=clock, cursor_reader=lambda: cursor,
    )
    return anim, pointer, sched, clock


# ──────────────────────────────── Tests ────────────────────────────────


def test_start_reads_the_os_cursor_exactly_once_read_only():
    # The cursor is READ once (the glide start) and never written — the animator
    # exposes no setter. We count reads through the injected reader.
    reads = {"n": 0}

    def fake_cursor():
        reads["n"] += 1
        return (100, 200)

    pointer, sched, clock = FakePointer(), FakeScheduler(), FakeClock()
    anim = PointerAnimator(
        schedule=sched.after, pointer=pointer, duration_ms=500,
        clock=clock, cursor_reader=fake_cursor,
    )
    anim.start((300, 400), on_arrival=lambda: None)
    assert reads["n"] == 1


def test_glide_interpolates_start_to_target_with_ease_in_out():
    anim, pointer, sched, clock = _make(duration_ms=100, frame_ms=10, cursor=(0, 0))
    arrived = {"hit": False}
    anim.start((100, 0), on_arrival=lambda: arrived.__setitem__("hit", True))

    # First frame at t=0 → eased 0 → still at the start; nothing has arrived.
    assert pointer.moves[0] == (0, 0)
    assert not arrived["hit"]

    # Midpoint t=0.5 → cosine ease = 0.5 exactly → halfway (x=50).
    clock.advance(0.05)               # 50 ms of a 100 ms glide
    sched.run_next()
    assert pointer.moves[-1] == (50, 0)
    assert not arrived["hit"]

    # End t≥1 → snaps to the target, fires on_arrival, schedules no further frame.
    clock.advance(0.05)               # now 100 ms total
    sched.run_next()
    assert pointer.moves[-1] == (100, 0)
    assert arrived["hit"]
    assert sched.scheduled == []


def test_zero_duration_arrives_on_the_first_frame():
    anim, pointer, sched, _clock = _make(duration_ms=0, cursor=(5, 5))
    arrived = {"hit": False}
    anim.start((25, 35), on_arrival=lambda: arrived.__setitem__("hit", True))

    assert pointer.moves[-1] == (25, 35)   # straight to target
    assert arrived["hit"]
    assert sched.scheduled == []


def test_cancel_stops_pending_frames_and_suppresses_arrival():
    anim, pointer, sched, clock = _make(duration_ms=100, frame_ms=10, cursor=(0, 0))
    arrived = {"hit": False}
    anim.start((100, 0), on_arrival=lambda: arrived.__setitem__("hit", True))

    anim.cancel()
    # A frame already queued before cancel must do nothing once it fires.
    clock.advance(1.0)
    sched.run_next()
    assert not arrived["hit"]


def test_a_new_glide_supersedes_the_old_one_no_overlapping_chains():
    # cancel-and-replace: starting a second glide drops any queued frame from the
    # first, so two _tick chains never run at once.
    anim, pointer, sched, clock = _make(duration_ms=100, frame_ms=10, cursor=(0, 0))
    anim.start((100, 0), on_arrival=lambda: None)   # glide A scheduled a frame
    pending_a = list(sched.scheduled)

    anim.start((0, 100), on_arrival=lambda: None)   # glide B replaces A
    # Fire glide A's stale frame: it must be a no-op (superseded generation).
    moves_before = len(pointer.moves)
    for _ms, fn in pending_a:
        fn()
    # Only glide B's own first frame (drawn synchronously in start) exists; the
    # stale A frame added nothing.
    assert len(pointer.moves) == moves_before


def test_ease_in_out_endpoints_and_midpoint():
    assert _ease_in_out(0.0) == 0.0
    assert abs(_ease_in_out(0.5) - 0.5) < 1e-9
    assert abs(_ease_in_out(1.0) - 1.0) < 1e-9


def test_default_anim_ms_is_sane():
    assert DEFAULT_POINTER_ANIM_MS == 500
