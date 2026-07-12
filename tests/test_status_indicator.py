"""
test_status_indicator.py — the overlay state light (batch 2-A), proven with a
FAKE canvas + a FAKE schedule (no real Tk window, no real mouse, no sleeps).

It must:
  * recolor the corner dot per state (listening/thinking/speaking) and HIDE it on
    idle, reusing the batch-1 OverlayStyle neon colors,
  * NEVER draw the removed pointer halo (only the corner dot remains),
  * clear the dot on demand and KEEP it dark past the pulse (the 2-B ghosting
    capability), and
  * PULSE via schedule() (root.after) — a self-rescheduling loop, never a
    blocking sleep/while.

Env is cleared by conftest, so from_env() yields the documented neon defaults.

Run:  set PYTHONPATH=src && python -m pytest tests/test_status_indicator.py -q
"""

from __future__ import annotations

from muthis.overlay.sidekick_window import dispatch_command
from muthis.overlay.status_indicator import (
    DEFAULT_PULSE_MS,
    STATUS_DOT_TAG,
    StatusIndicator,
)
from muthis.overlay.style import (
    DEFAULT_STATUS_COLORS,
    DEFAULT_STATUS_CORNER,
    OverlayStyle,
)

# The removed pointer halo used this tag; assert it is never drawn again.
_OLD_HALO_TAG = "muthis-status-halo"

STYLE = OverlayStyle()
SCREEN = (1920, 1080)


# ──────────────────────────────── Fakes ────────────────────────────────


class FakeCanvas:
    """Models create_oval + delete(tag) with LIVE items, so a hidden/cleared
    element is genuinely absent (delete removes matching tags; 'all' wipes)."""

    def __init__(self):
        self.items = []        # live {id, coords, kwargs}
        self._next = 0

    def create_oval(self, *coords, **kwargs):
        self._next += 1
        self.items.append({"id": self._next, "coords": coords, "kwargs": kwargs})
        return self._next

    def delete(self, tag):
        if tag == "all":
            self.items = []
            return
        self.items = [it for it in self.items if it["kwargs"].get("tags") != tag]

    # test helpers -----------------------------------------------------------
    def tagged(self, tag):
        return [it for it in self.items if it["kwargs"].get("tags") == tag]

    def fills(self, tag):
        return [it["kwargs"].get("fill") for it in self.tagged(tag)]

    def outlines(self, tag):
        return [it["kwargs"].get("outline") for it in self.tagged(tag)]


class FakeSchedule:
    """Records (delay, callback) WITHOUT auto-running — so a self-rescheduling
    pulse never recurses forever in a test; the test drives ticks by hand."""

    def __init__(self):
        self.calls = []

    def __call__(self, delay, callback):
        self.calls.append((delay, callback))

    def run_next(self):
        _delay, callback = self.calls[-1]
        callback()


def _indicator(*, schedule=None, style=STYLE):
    return StatusIndicator(
        FakeCanvas(), schedule=schedule or FakeSchedule(), style=style,
        screen_size=SCREEN,
    )


# ─────────────────────────────── set_state ───────────────────────────────


def test_each_state_colors_the_corner_dot_with_its_neon_color():
    for state in ("listening", "thinking", "speaking"):
        ind = _indicator()
        ind.set_state(state)
        expected = DEFAULT_STATUS_COLORS[state]
        # Two dot ovals: a dim glow disc under a bright neon CORE (fill == color).
        assert expected in ind._canvas.fills(STATUS_DOT_TAG)
        assert len(ind._canvas.tagged(STATUS_DOT_TAG)) == 2


def test_idle_hides_the_corner_dot():
    ind = _indicator()
    ind.set_state("speaking")
    assert ind._canvas.tagged(STATUS_DOT_TAG)      # visible first

    ind.set_state("idle")
    assert ind._canvas.tagged(STATUS_DOT_TAG) == []


def test_unknown_state_is_a_no_op_leaving_the_prior_visual():
    ind = _indicator()
    ind.set_state("listening")
    before = list(ind._canvas.items)
    ind.set_state("bogus")            # logged + ignored, no crash
    assert ind._canvas.items == before


def test_corner_dot_sits_in_the_configured_corner():
    # bottom-right (default): center a margin in from the screen's far edge.
    ind = _indicator()
    ind.set_state("listening")
    core = ind._canvas.tagged(STATUS_DOT_TAG)[-1]["coords"]
    cx = (core[0] + core[2]) / 2
    cy = (core[1] + core[3]) / 2
    assert cx > SCREEN[0] * 0.9 and cy > SCREEN[1] * 0.9
    assert DEFAULT_STATUS_CORNER == "bottom-right"


# ───────────────────────────── halo removed ─────────────────────────────


def test_no_halo_ring_is_ever_drawn_for_any_state():
    # The pointer halo was removed (it cluttered content over code). No canvas
    # item should carry the old halo tag for ANY state — only the corner dot.
    for state in ("listening", "thinking", "speaking"):
        ind = _indicator()
        ind.set_state(state)
        assert ind._canvas.tagged(_OLD_HALO_TAG) == []
        assert ind._canvas.tagged(STATUS_DOT_TAG)          # dot still shows


# ─────────────────────── hide capability (2-B ghosting) ───────────────────────


def test_clear_status_light_removes_the_dot_and_keeps_it_dark_through_the_pulse():
    sched = FakeSchedule()
    ind = _indicator(schedule=sched)
    ind.start()
    ind.set_state("speaking")
    assert ind._canvas.tagged(STATUS_DOT_TAG)

    ind.clear_status_light()
    assert ind._canvas.tagged(STATUS_DOT_TAG) == []    # gone now
    sched.run_next()                                   # a pulse tick fires
    assert ind._canvas.tagged(STATUS_DOT_TAG) == []    # STILL dark (ghosting)

    ind.set_state("thinking")                          # a real state re-arms it
    assert ind._canvas.tagged(STATUS_DOT_TAG)


# ───────────────────────────────── pulse ─────────────────────────────────


def test_pulse_uses_schedule_not_a_blocking_loop():
    sched = FakeSchedule()
    ind = _indicator(schedule=sched)

    ind.start()                                        # returns immediately
    assert len(sched.calls) == 1
    delay, callback = sched.calls[0]
    assert delay == DEFAULT_PULSE_MS and callable(callback)

    sched.run_next()                                   # one frame re-arms the loop
    assert len(sched.calls) == 2                       # self-reschedules via after


def test_start_is_idempotent():
    sched = FakeSchedule()
    ind = _indicator(schedule=sched)
    ind.start()
    ind.start()                                        # second start does nothing
    assert len(sched.calls) == 1


# ────────────────────────── dispatch routing (queue path) ──────────────────────────


class FakeStatus:
    def __init__(self):
        self.states = []

    def set_state(self, state):
        self.states.append(state)


def test_dispatch_routes_set_state_to_the_status_indicator():
    status = FakeStatus()
    cont = dispatch_command(
        ("set_state", "thinking"), rect=None, pointer=None, animator=None,
        status=status,
    )
    assert cont is True
    assert status.states == ["thinking"]


def test_dispatch_set_state_without_a_status_is_a_safe_no_op():
    # Backward compatibility: a pre-status call site passes no status → no crash.
    cont = dispatch_command(
        ("set_state", "listening"), rect=None, pointer=None, animator=None,
    )
    assert cont is True


# ───────────────────────── OverlayStyle status config ─────────────────────────


def test_overlaystyle_status_defaults_are_the_documented_neon_values():
    style = OverlayStyle()
    assert style.status_colors == DEFAULT_STATUS_COLORS
    assert style.status_corner == "bottom-right"


def test_from_env_honors_status_overrides_and_rejects_a_bad_corner(monkeypatch):
    monkeypatch.setenv("MUTHIS_STATUS_THINKING", "#123456")
    monkeypatch.setenv("MUTHIS_STATUS_CORNER", "top-left")
    style = OverlayStyle.from_env()
    assert style.status_colors["thinking"] == "#123456"
    assert style.status_corner == "top-left"

    monkeypatch.setenv("MUTHIS_STATUS_CORNER", "middle")     # invalid → default
    assert OverlayStyle.from_env().status_corner == "bottom-right"
