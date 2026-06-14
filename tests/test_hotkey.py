"""
test_hotkey.py — the thread→loop bridge, with fakes only (no real keyboard).

The single property under test: a hotkey press must be handed to the asyncio
loop via call_soon_threadsafe — NEVER run directly on the keyboard thread. We
drive _handle_press with a plain stand-in key (the same two attributes pynput
keys expose) and assert the bridge, the key matching, and that importing/using
the listener pulls in no input backend (pynput stays lazy).

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


def test_matching_press_bridges_via_call_soon_threadsafe():
    activated = []
    loop = FakeLoop()
    listener = HotkeyListener(
        loop=loop, on_activate=lambda: activated.append(True), hotkey="f9",
    )

    listener._handle_press(_special_key("f9"))

    # Scheduled onto the loop exactly once, with the callback itself...
    assert len(loop.scheduled) == 1
    callback, args = loop.scheduled[0]
    assert callback is listener._on_activate and args == ()
    # ...and NOT invoked directly on the keyboard thread.
    assert activated == []


def test_non_matching_key_does_not_bridge():
    loop = FakeLoop()
    listener = HotkeyListener(loop=loop, on_activate=lambda: None, hotkey="f9")

    listener._handle_press(_special_key("f8"))

    assert loop.scheduled == []


def test_configurable_char_hotkey_matches():
    loop = FakeLoop()
    listener = HotkeyListener(loop=loop, on_activate=lambda: None, hotkey="K")

    # Case-insensitive: configured "K" matches a "k" KeyCode press.
    listener._handle_press(_char_key("k"))

    assert len(loop.scheduled) == 1


def test_default_hotkey_is_f9():
    assert DEFAULT_HOTKEY == "f9"


def test_listener_construction_imports_no_input_backend():
    """CI safety: building a listener and handling a press loads no pynput —
    the input backend is touched only inside start(), like mic/stt's lazy
    imports. We never call start() in tests, so no real hook is installed."""
    loop = FakeLoop()
    listener = HotkeyListener(loop=loop, on_activate=lambda: None, hotkey="f9")
    listener._handle_press(_special_key("f9"))

    assert "pynput" not in sys.modules
