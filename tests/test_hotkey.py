"""
test_hotkey.py — the hold/release thread→loop discipline, fakes only (no real
keyboard).

Two properties under test:
  * key-DOWN starts recording DIRECTLY on the keyboard thread (on_press is
    loop-agnostic — it only opens the mic) and is NOT scheduled on the loop;
  * key-UP is handed to the asyncio loop via call_soon_threadsafe — NEVER run
    directly on the keyboard thread (scheduling a turn off the loop is illegal).
Plus: auto-repeat is debounced (one start per physical hold), a release with no
matching press is ignored, non-target keys are ignored, the configurable char
hotkey matches case-insensitively, and using the listener pulls in no input
backend (pynput stays lazy).

Run:  pytest tests/test_hotkey.py -q
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from muthis.hotkey import DEFAULT_HOTKEY, HotkeyListener


class FakeLoop:
    """Records call_soon_threadsafe — the ONLY safe thread→loop crossing.
    Deliberately has NO run/create_task, so any attempt to drive async work
    directly from the keyboard thread would blow up instead of passing."""

    def __init__(self):
        self.scheduled = []

    def call_soon_threadsafe(self, callback, *args):
        self.scheduled.append((callback, args))


def _special_key(name):
    """Stand-in for pynput's keyboard.Key.<name> (carries .name)."""
    return SimpleNamespace(name=name)


def _char_key(char):
    """Stand-in for pynput's keyboard.KeyCode (carries .char, no .name)."""
    return SimpleNamespace(char=char)


def _listener(loop, *, hotkey="f9"):
    presses, releases = [], []
    listener = HotkeyListener(
        loop=loop,
        on_press=lambda: presses.append(True),
        on_release=lambda: releases.append(True),
        hotkey=hotkey,
    )
    return listener, presses, releases


def test_press_starts_recording_directly_not_on_loop():
    loop = FakeLoop()
    listener, presses, releases = _listener(loop)

    listener._handle_press(_special_key("f9"))

    # on_press ran on the keyboard thread (it only starts the mic)...
    assert presses == [True]
    # ...and a press scheduled NOTHING on the loop.
    assert loop.scheduled == []
    assert releases == []


def test_release_bridges_via_call_soon_threadsafe():
    loop = FakeLoop()
    listener, presses, releases = _listener(loop)

    listener._handle_press(_special_key("f9"))
    listener._handle_release(_special_key("f9"))

    # The turn is scheduled onto the loop exactly once, with the on_release
    # callback itself — NEVER invoked directly on the keyboard thread.
    assert len(loop.scheduled) == 1
    callback, args = loop.scheduled[0]
    assert callback is listener._on_release and args == ()
    assert releases == []   # not called directly on the keyboard thread


def test_autorepeat_press_starts_recording_once_per_hold():
    loop = FakeLoop()
    listener, presses, _releases = _listener(loop)

    # pynput fires on_press repeatedly while the key is held — debounce it.
    listener._handle_press(_special_key("f9"))
    listener._handle_press(_special_key("f9"))
    listener._handle_press(_special_key("f9"))

    assert presses == [True]                 # exactly one start for the hold
    listener._handle_release(_special_key("f9"))
    assert len(loop.scheduled) == 1          # one turn for the hold

    # A fresh hold works again.
    listener._handle_press(_special_key("f9"))
    assert presses == [True, True]


def test_reset_clears_held_so_a_lost_key_up_cannot_wedge_the_next_press():
    # Regression B (hotkey side): if a key-up is LOST, _held stays True and the
    # next key-down is debounced as auto-repeat (wedged). reset() — called from
    # the turn's reset_turn_state() — clears _held so the next press fires fresh.
    loop = FakeLoop()
    listener, presses, _releases = _listener(loop)

    listener._handle_press(_special_key("f9"))     # hold 1 — _held True
    assert presses == [True]
    listener._handle_press(_special_key("f9"))     # key-up LOST → debounced (wedged)
    assert presses == [True]

    listener.reset()                               # the per-turn hotkey reset

    listener._handle_press(_special_key("f9"))     # a genuine fresh press fires again
    assert presses == [True, True]


def test_release_without_press_is_ignored():
    loop = FakeLoop()
    listener, presses, _releases = _listener(loop)

    listener._handle_release(_special_key("f9"))   # spurious release

    assert loop.scheduled == []
    assert presses == []


def test_non_matching_key_does_nothing():
    loop = FakeLoop()
    listener, presses, releases = _listener(loop)

    listener._handle_press(_special_key("f8"))
    listener._handle_release(_special_key("f8"))

    assert presses == [] and releases == [] and loop.scheduled == []


def test_configurable_char_hotkey_matches_case_insensitively():
    loop = FakeLoop()
    listener, presses, _releases = _listener(loop, hotkey="K")

    # Case-insensitive: configured "K" matches a "k" KeyCode press/release.
    listener._handle_press(_char_key("k"))
    listener._handle_release(_char_key("k"))

    assert presses == [True]
    assert len(loop.scheduled) == 1


def test_default_hotkey_is_f9():
    assert DEFAULT_HOTKEY == "f9"


def test_using_listener_imports_no_input_backend():
    """CI safety: building a listener and handling press/release loads no pynput
    — the input backend is touched only inside start(), like mic/stt's lazy
    imports. We never call start() in tests, so no real hook is installed."""
    loop = FakeLoop()
    listener, _presses, _releases = _listener(loop)
    listener._handle_press(_special_key("f9"))
    listener._handle_release(_special_key("f9"))

    assert "pynput" not in sys.modules
