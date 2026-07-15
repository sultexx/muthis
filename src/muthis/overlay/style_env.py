# src/muthis/overlay/style_env.py
"""
`.env` parsing + color validation for the overlay styling config.

Extracted from `style.py` under the ≤300-line law (Law §17.4): that module sat
EXACTLY at the ceiling and Phase A (v5) needed room there, so the env→typed-value
discipline moved here whole. The rule is unchanged: a malformed value logs an
English WARNING and falls back to the documented default — the Tk thread never
crashes over a typo in `.env`.

Transparent-key guard: the window's Tk `-transparentcolor` key is magenta
(#FF00FF); any drawn pixel of that exact color would vanish. `avoid_key()`
nudges a color off the key so a neon (or dimmed-halo) value can never go
invisible — `safe_color()` routes every parsed color through it, and
`style.dim()` routes every halo tint through it.

Pure stdlib (os / re / logging), no tkinter — importable in isolation, the same
discipline as every other overlay helper.
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger("muthis.overlay")

# The window's Tk -transparentcolor key (mirrors sidekick_window.TRANSPARENT_KEY):
# a drawn pixel of this exact color becomes see-through, so it must never be the
# output of a style color or a dimmed halo. Re-exported by style.py.
TRANSPARENT_KEY = "#FF00FF"

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
_VALID_CORNERS = {"top-left", "top-right", "bottom-left", "bottom-right"}


def safe_color(value: str | None, default: str) -> str:
    """A validated, upper-cased #RRGGBB — falling back to `default` on a blank or
    malformed value, and nudging away from the transparent key so it stays
    visible."""
    if not value:
        return default
    if not _HEX_RE.match(value.strip()):
        logger.warning("[overlay] ignoring invalid color %r — using %s", value, default)
        return default
    return avoid_key("#" + value.strip()[1:].upper())


def avoid_key(color: str) -> str:
    """Keep a color off the exact transparent key (which would render invisible)
    by nudging its red channel down one step."""
    if color.upper() == TRANSPARENT_KEY:
        logger.warning("[overlay] color equals the transparent key — nudging it visible")
        return "#FE00FF"
    return color


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("[overlay] %s=%r is not an integer — using %d", name, raw, default)
        return default


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("[overlay] %s=%r is not a number — using %s", name, raw, default)
        return default


def env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    token = raw.strip().lower()
    if token in _TRUE:
        return True
    if token in _FALSE:
        return False
    logger.warning("[overlay] %s=%r is not a boolean — using %s", name, raw, default)
    return default


def env_corner(name: str, default: str) -> str:
    """One of the four screen corners for the status dot; a blank/typo → default."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    token = raw.strip().lower()
    if token in _VALID_CORNERS:
        return token
    logger.warning("[overlay] %s=%r is not a valid corner — using %s", name, raw, default)
    return default


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


__all__ = [
    "TRANSPARENT_KEY",
    "safe_color", "avoid_key",
    "env_int", "env_float", "env_flag", "env_corner",
    "clamp01",
]
