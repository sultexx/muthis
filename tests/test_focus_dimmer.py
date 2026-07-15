"""
test_focus_dimmer.py — v6 Phase D: the Cinematic Spotlight (fakes only, no Tk).

D1: the FocusDimmer view (hole geometry with margin + screen clamp, show/hide
lifecycle, z-order re-raise) and the .env knobs (flag default OFF; alpha
default 0.30, clamped, typo-safe).
D2: dispatch wiring — "show" dims around the highlight bbox BEFORE the glide
starts, "hide" drops the dim (the ghosting rule: Claude never sees a dimmed
screen), draw_shapes never dims (approved decision), and the pre-dimmer
signature stays valid.

Run:  set PYTHONPATH=src && python -m pytest tests/test_focus_dimmer.py -q
"""

from __future__ import annotations

from muthis.overlay.focus_dimmer import (
    DEFAULT_FOCUS_ALPHA,
    FOCUS_MARGIN_PX,
    FocusDimmer,
    focus_dim_enabled,
    resolve_focus_alpha,
    whiteboard_enabled,
)
from muthis.overlay.style import TRANSPARENT_KEY

SCREEN = (1920, 1080)


# ──────────────────────────────── Fakes ────────────────────────────────


class FakeWindow:
    def __init__(self):
        self.calls = []

    def deiconify(self):
        self.calls.append("deiconify")

    def withdraw(self):
        self.calls.append("withdraw")

    def lift(self):
        self.calls.append("lift")


class FakeDimCanvas:
    def __init__(self):
        self.rectangles = []
        self.deletes = 0

    def create_rectangle(self, *coords, **kwargs):
        self.rectangles.append((coords, kwargs))

    def delete(self, tag):
        self.deletes += 1


def _dimmer():
    window, canvas, raised = FakeWindow(), FakeDimCanvas(), []
    dimmer = FocusDimmer(window, canvas, SCREEN, raise_neon=lambda: raised.append(1))
    return dimmer, window, canvas, raised


# ─────────────────────────────── The knobs ───────────────────────────────


def test_focus_dim_flag_defaults_off_and_env_enables(monkeypatch):
    assert focus_dim_enabled() is False          # conftest cleared the env
    monkeypatch.setenv("MUTHIS_FOCUS_DIM", "1")
    assert focus_dim_enabled() is True


def test_focus_alpha_default_override_clamp_and_typo(monkeypatch):
    assert resolve_focus_alpha() == DEFAULT_FOCUS_ALPHA
    monkeypatch.setenv("MUTHIS_FOCUS_ALPHA", "0.5")
    assert resolve_focus_alpha() == 0.5
    monkeypatch.setenv("MUTHIS_FOCUS_ALPHA", "7")      # clamped: never blackout
    assert resolve_focus_alpha() == 1.0
    monkeypatch.setenv("MUTHIS_FOCUS_ALPHA", "dark")   # typo → default, no crash
    assert resolve_focus_alpha() == DEFAULT_FOCUS_ALPHA


# ─────────────────────────────── FocusDimmer ───────────────────────────────


def test_show_around_cuts_the_keyed_hole_with_margin():
    dimmer, window, canvas, raised = _dimmer()
    dimmer.show_around((700, 350, 1220, 730))

    coords, kwargs = canvas.rectangles[0]
    assert coords == (700 - FOCUS_MARGIN_PX, 350 - FOCUS_MARGIN_PX,
                      1220 + FOCUS_MARGIN_PX, 730 + FOCUS_MARGIN_PX)
    # The hole is cut with the transparent KEY — fully see-through by
    # construction (the D0-validated colorkey mechanism).
    assert kwargs["fill"] == TRANSPARENT_KEY and kwargs["outline"] == TRANSPARENT_KEY
    # Reveal order: clear old hole → cut → deiconify → lift → re-raise neon,
    # so the rectangle/pointer/captions always stack back above the dim.
    assert canvas.deletes == 1
    assert window.calls == ["deiconify", "lift"]
    assert raised == [1]


def test_hole_is_clamped_to_the_screen():
    dimmer, _window, canvas, _raised = _dimmer()
    dimmer.show_around((2, 4, 1918, 1078))       # margin would overflow

    coords, _ = canvas.rectangles[0]
    assert coords == (0, 0, 1920, 1080)


def test_a_second_show_replaces_the_hole():
    dimmer, _window, canvas, _raised = _dimmer()
    dimmer.show_around((100, 100, 200, 200))
    dimmer.show_around((500, 500, 700, 600))

    assert canvas.deletes == 2                   # cleared before each cut
    assert len(canvas.rectangles) == 2


def test_hide_withdraws_and_clears():
    dimmer, window, canvas, _raised = _dimmer()
    dimmer.show_around((100, 100, 200, 200))
    dimmer.hide()

    assert window.calls == ["deiconify", "lift", "withdraw"]
    assert canvas.deletes == 2                   # show's clear + hide's clear


# ─────────────────────── D2: dispatch wiring (fakes) ───────────────────────


class _Recorder:
    def __init__(self, log=None, name=""):
        self._log, self._name = log, name
        self.calls = []

    def __getattr__(self, attr):
        def record(*args):
            self.calls.append((attr,) + args)
            if self._log is not None:
                self._log.append((self._name, attr))
        return record


class FakeDimmer:
    def __init__(self, log=None):
        self._log = log
        self.shown = []
        self.hides = 0

    def show_around(self, bbox):
        self.shown.append(bbox)
        if self._log is not None:
            self._log.append(("dimmer", "show_around"))

    def hide(self):
        self.hides += 1


def _dispatch(command, dimmer, log=None):
    from muthis.overlay.window_commands import dispatch_command
    return dispatch_command(
        command,
        rect=_Recorder(log, "rect"), pointer=_Recorder(log, "pointer"),
        animator=_Recorder(log, "animator"), shapes=_Recorder(log, "shapes"),
        status=None, dimmer=dimmer,
    )


def test_dispatch_show_dims_around_the_bbox_before_the_glide_starts():
    log, dimmer = [], FakeDimmer(log=None)
    dimmer._log = log
    _dispatch(("show", (10, 20, 110, 60), "زر"), dimmer, log)

    assert dimmer.shown == [(10, 20, 110, 60)]
    # The spotlight forms as the glide begins (Option A: the audio starts with
    # the draw command) — the dim call precedes animator.start.
    assert log.index(("dimmer", "show_around")) < log.index(("animator", "start"))


def test_dispatch_hide_drops_the_dim_too():
    # Ghosting: hide() runs before EVERY capture — Claude never sees a dimmed
    # screen (the plan's rule 4).
    dimmer = FakeDimmer()
    _dispatch(("hide",), dimmer)
    assert dimmer.hides == 1


def test_draw_shapes_never_dims():
    # Approved decision: illustrations need their full-context screen.
    dimmer = FakeDimmer()
    _dispatch(("draw_shapes", ()), dimmer)
    assert dimmer.shown == [] and dimmer.hides == 0


def test_dispatch_without_a_dimmer_stays_backward_compatible():
    from muthis.overlay.window_commands import dispatch_command
    assert dispatch_command(
        ("show", (10, 20, 110, 60), "زر"),
        rect=_Recorder(), pointer=_Recorder(), animator=_Recorder(),
    ) is True
    assert dispatch_command(
        ("hide",), rect=_Recorder(), pointer=_Recorder(), animator=_Recorder(),
    ) is True


# ─────────────── v7 Phase 2: the WHITEBOARD (full dim + smooth fade) ───────────────


class FadeWindow(FakeWindow):
    """FakeWindow that also records the -alpha ramp (the fade surface)."""

    def __init__(self):
        super().__init__()
        self.alphas = []
        self._alpha = DEFAULT_FOCUS_ALPHA

    def attributes(self, name, value=None):
        assert name == "-alpha"
        if value is None:
            return self._alpha
        self._alpha = value
        self.alphas.append(value)


class FakeSchedule:
    """root.after double: queued callbacks run only when driven by hand."""

    def __init__(self):
        self.queue = []

    def __call__(self, _ms, callback):
        self.queue.append(callback)

    def run_all(self, limit=500):
        steps = 0
        while self.queue and steps < limit:
            self.queue.pop(0)()
            steps += 1


def _whiteboard_dimmer():
    window, canvas, raised = FadeWindow(), FakeDimCanvas(), []
    schedule = FakeSchedule()
    dimmer = FocusDimmer(window, canvas, SCREEN,
                         raise_neon=lambda: raised.append(1),
                         schedule=schedule, alpha=DEFAULT_FOCUS_ALPHA)
    return dimmer, window, canvas, raised, schedule


def test_whiteboard_flag_defaults_on_and_falsey_rolls_back(monkeypatch):
    assert whiteboard_enabled() is True           # conftest cleared the env
    monkeypatch.setenv("MUTHIS_WHITEBOARD", "0")
    assert whiteboard_enabled() is False


def test_show_full_covers_everything_and_fades_in():
    dimmer, window, canvas, raised, schedule = _whiteboard_dimmer()
    dimmer.show_full()

    assert canvas.rectangles == [] and canvas.deletes == 1   # NO hole: full board
    # Revealed dark-less first, then the fade ramps up to the resolved alpha —
    # never overshooting it — with the neon re-raised above the dim (D0 rule).
    assert window.alphas[0] == 0.0
    assert window.calls == ["deiconify", "lift"] and raised == [1]
    schedule.run_all()
    assert window.alphas[-1] == DEFAULT_FOCUS_ALPHA
    assert all(a <= DEFAULT_FOCUS_ALPHA + 1e-9 for a in window.alphas)


def test_fade_out_ramps_to_zero_then_withdraws():
    dimmer, window, _canvas, _raised, schedule = _whiteboard_dimmer()
    dimmer.show_full()
    schedule.run_all()
    dimmer.fade_out()
    schedule.run_all()

    assert window.alphas[-1] == 0.0
    assert window.calls[-1] == "withdraw"         # lights on, board gone


def test_hide_is_instant_and_cancels_an_inflight_fade():
    # The ghosting chokepoint must never leave even a FADING dim for a capture.
    dimmer, window, canvas, _raised, schedule = _whiteboard_dimmer()
    dimmer.show_full()                            # fade-in frames queued
    dimmer.hide()                                 # instant withdraw

    assert window.calls[-1] == "withdraw" and canvas.deletes == 2
    before = list(window.alphas)
    schedule.run_all()                            # orphaned frames must drop out
    assert window.alphas == before                # no alpha moved after hide


def test_schedule_less_dimmer_degrades_to_instant():
    # Legacy/display-free construction (no scheduler): whiteboard show/undim
    # become instant — the pre-Phase-2 behavior, and what old fakes exercise.
    window, canvas = FakeWindow(), FakeDimCanvas()
    dimmer = FocusDimmer(window, canvas, SCREEN, raise_neon=lambda: None)
    dimmer.show_full()
    assert window.calls == ["deiconify", "lift"]
    dimmer.fade_out()
    assert window.calls[-1] == "withdraw"


def test_dispatch_dim_and_undim_route_to_the_dimmer():
    class WhiteboardFake(FakeDimmer):
        def __init__(self):
            super().__init__()
            self.fulls = 0
            self.fade_outs = 0

        def show_full(self):
            self.fulls += 1

        def fade_out(self):
            self.fade_outs += 1

    dimmer = WhiteboardFake()
    _dispatch(("dim_screen",), dimmer)
    _dispatch(("undim_screen",), dimmer)
    assert dimmer.fulls == 1 and dimmer.fade_outs == 1
    # And without a dimmer (rollback / init failure) both are safe no-ops.
    _dispatch(("dim_screen",), None)
    _dispatch(("undim_screen",), None)


def test_spotlight_off_whiteboard_dimmer_never_dims_a_highlight():
    # Decoupling: a dimmer window built FOR the whiteboard (spotlight flag
    # OFF) must not resurrect the default-OFF v6 spotlight on highlights.
    from muthis.overlay.window_commands import dispatch_command
    dimmer = FakeDimmer()
    dispatch_command(("show", (10, 20, 110, 60), "زر"),
                     rect=_Recorder(), pointer=_Recorder(),
                     animator=_Recorder(), dimmer=dimmer, spotlight_on=False)
    assert dimmer.shown == []
