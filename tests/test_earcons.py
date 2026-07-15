"""
test_earcons.py — the EarconPlayer (fakes only, no audio device).

The real winsound backend is replaced by an injected `play_sound` that records
calls, so we assert routing/threading/toggle behavior with zero sound. A
tmp_path stands in for assets/earcons. play() is fire-and-forget — it runs the
backend on a daemon thread — so tests synchronize via threading.Event.

Run:  set PYTHONPATH=src && python -m pytest tests/test_earcons.py -q
"""

from __future__ import annotations

import sys
import threading
import time

from muthis.earcons import EARCON_NAMES, EarconPlayer


def _wav(dir_path, name):
    """A stand-in WAV file (contents irrelevant — the fake backend never reads)."""
    path = dir_path / f"{name}.wav"
    path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")
    return path


class _RecordingBackend:
    """A fake play_sound that records the path and signals when it ran."""

    def __init__(self):
        self.played = []
        self.ran = threading.Event()

    def __call__(self, path):
        self.played.append(path)
        self.ran.set()


def test_earcon_names_are_the_two_lifecycle_cues():
    assert EARCON_NAMES == ("listening", "processing")


def test_play_invokes_backend_for_an_existing_earcon(tmp_path):
    _wav(tmp_path, "listening")
    backend = _RecordingBackend()
    player = EarconPlayer(enabled=True, sounds_dir=tmp_path, play_sound=backend)

    player.play("listening")

    assert backend.ran.wait(timeout=2.0)            # ran on the daemon thread
    assert backend.played[0].endswith("listening.wav")


def test_disabled_player_is_silent(tmp_path):
    _wav(tmp_path, "listening")
    backend = _RecordingBackend()
    player = EarconPlayer(enabled=False, sounds_dir=tmp_path, play_sound=backend)

    player.play("listening")

    assert player.enabled is False
    assert not backend.ran.wait(timeout=0.2)        # nothing played
    assert backend.played == []


def test_missing_file_is_a_silent_noop(tmp_path):
    backend = _RecordingBackend()
    player = EarconPlayer(enabled=True, sounds_dir=tmp_path, play_sound=backend)

    player.play("listening")                        # no file written

    assert not backend.ran.wait(timeout=0.2)
    assert backend.played == []


def test_play_is_fire_and_forget_and_does_not_block(tmp_path):
    _wav(tmp_path, "processing")
    started, release = threading.Event(), threading.Event()

    def slow_backend(path):
        started.set()
        release.wait(2.0)                            # would block the caller if not threaded

    player = EarconPlayer(enabled=True, sounds_dir=tmp_path, play_sound=slow_backend)

    t0 = time.monotonic()
    player.play("processing")                        # must return immediately
    elapsed = time.monotonic() - t0

    assert elapsed < 0.5                             # not blocked by the slow backend
    assert started.wait(2.0)                         # backend ran on a background thread
    release.set()


def test_backend_exception_never_propagates(tmp_path):
    _wav(tmp_path, "listening")
    ran = threading.Event()

    def boom(path):
        ran.set()
        raise OSError("audio device gone")

    player = EarconPlayer(enabled=True, sounds_dir=tmp_path, play_sound=boom)

    player.play("listening")                         # must not raise
    assert ran.wait(2.0)                             # backend ran; error swallowed in-thread


def test_env_toggle_default_on_is_platform_gated(monkeypatch):
    # enabled=None reads MUTHIS_EARCONS (default on) but earcons are Windows-only.
    monkeypatch.delenv("MUTHIS_EARCONS", raising=False)
    assert EarconPlayer(enabled=None).enabled == (sys.platform == "win32")


def test_env_toggle_off_disables(monkeypatch):
    monkeypatch.setenv("MUTHIS_EARCONS", "0")
    assert EarconPlayer(enabled=None).enabled is False
