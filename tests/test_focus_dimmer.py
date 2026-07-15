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
