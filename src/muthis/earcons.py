# src/muthis/earcons.py
"""
earcons.py — short, pleasant UI sounds (fire-and-forget, never blocking).

Two earcons signal the push-to-talk lifecycle so the user gets instant feedback:
  * "listening"  — played the instant F9 opens the mic (the hold is recording),
  * "processing" — played on release when the turn pipeline starts (masks the
    1-2 s think/answer latency).

LOOK-only is untouched — this only makes sound. The bundled WAVs live in
assets/earcons/ (synthesized by scripts/generate_earcons.py — a dev/asset step
using numpy; the RUNTIME needs only winsound + the WAVs, no numpy).

Non-blocking by construction: play() spawns a daemon thread that calls
winsound.PlaySound with SND_ASYNC, so it stalls neither the keyboard thread
(on_press) nor the asyncio loop (on_activate). It NEVER raises — a missing file,
a disabled toggle, or a non-Windows host all degrade to silence. The actual
sound backend is an injected seam (`play_sound`) so tests drive it with a fake
and touch no audio device.

Toggle: MUTHIS_EARCONS (default on). Disabled, or off-Windows, → every play() is
a silent no-op.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("muthis.earcons")

# The two lifecycle earcons (file stem in assets/earcons/<name>.wav).
EARCON_NAMES = ("listening", "processing")

# Repo-root/assets/earcons — earcons.py is src/muthis/earcons.py, so parents[2]
# is the project root (parents[0]=muthis, [1]=src, [2]=repo root).
DEFAULT_EARCONS_DIR = Path(__file__).resolve().parents[2] / "assets" / "earcons"


def _env_flag(name: str, *, default: bool) -> bool:
    """Parse a truthy/falsey env flag; absent → `default`."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _winsound_play(path: str) -> None:
    """Default backend: async, non-blocking WAV playback on Windows. Imported
    lazily so this module stays importable (and testable) on any platform."""
    import winsound

    winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)


class EarconPlayer:
    """Fire-and-forget player for the bundled lifecycle earcons. Stateless beyond
    config; safe to share. play(name) never blocks and never raises."""

    def __init__(
        self,
        *,
        enabled: Optional[bool] = None,
        sounds_dir: Optional[Path] = None,
        play_sound: Optional[Callable[[str], None]] = None,
    ) -> None:
        # Enabled by default; a falsey MUTHIS_EARCONS turns every play() to a
        # no-op, and earcons are Windows-only (winsound) — silent elsewhere.
        env_on = _env_flag("MUTHIS_EARCONS", default=True) if enabled is None else enabled
        self._enabled = bool(env_on) and sys.platform == "win32"
        self._dir = Path(sounds_dir) if sounds_dir is not None else DEFAULT_EARCONS_DIR
        self._play_sound = play_sound or _winsound_play
        if not self._enabled:
            logger.info("[earcons] disabled (MUTHIS_EARCONS off or non-Windows)")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def play(self, name: str) -> None:
        """Play earcon `name` fire-and-forget. Off / missing file → silent no-op;
        otherwise a daemon thread does the (already async) playback so the caller
        — the keyboard thread or the loop — never waits on audio."""
        if not self._enabled:
            return
        path = self._dir / f"{name}.wav"
        if not path.exists():
            logger.debug("[earcons] %r missing at %s — skipping", name, path)
            return
        threading.Thread(
            target=self._play_safely, args=(str(path),), daemon=True,
        ).start()

    def _play_safely(self, path: str) -> None:
        """Thread body: play and swallow ANY error — an earcon must never crash a
        turn or the run-forever app."""
        try:
            self._play_sound(path)
        except Exception as e:  # noqa: BLE001 — cosmetic sound must never raise
            logger.debug("[earcons] playback failed (%s: %s)", type(e).__name__, e)


__all__ = ["EarconPlayer", "EARCON_NAMES", "DEFAULT_EARCONS_DIR"]
