# src/muthis/overlay/style.py
"""
OverlayStyle — the SINGLE source of overlay visual styling (Batch 1: neon look).

ONE place, tweakable by eye: per-shape neon colors, the glow layering, the core
line width, and the Arabic caption chip font/plate all live here, sourced from
`.env` with neon defaults. The widgets (rectangle / shapes / pointer) read every
style value off an injected `OverlayStyle` instead of hardcoding their own — so
the whole overlay reads as one technical/futuristic voice, retunable without
touching code.

No `tkinter` import: this module is pure config + duck-typed canvas helpers, so
`shapes_widget`/`pointer_widget` keep importing it while staying display-free for
their headless unit tests (the same discipline those widgets already follow).

Glow is EMULATED, not real alpha: Tk has no per-item translucency on Windows, so
`glow_strokes()` returns an OUTER dim "halo" stroke plus an INNER bright "core"
stroke (outer first, so the core lands on top). The halo color is the neon color
dimmed toward black by `glow_intensity` — never true transparency.

Transparent-key guard: the window's `-transparentcolor` key is magenta
(#FF00FF); any drawn pixel of that exact color would vanish. `_safe_color()` and
`dim()` nudge a color away from the key so a neon (or dimmed) value can never go
invisible.

DI: `OverlayStyle.from_env()` is the graceful fallback; `SidekickOverlay(style=)`
may inject a tuned instance (and tests inject a deterministic one). Coordinates,
ghosting, sync, click-through and DPI are NOT this module's concern — it only
decides how pixels LOOK.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Mapping

logger = logging.getLogger("muthis.overlay")

# The window's Tk -transparentcolor key (mirrors sidekick_window.TRANSPARENT_KEY):
# a drawn pixel of this exact color becomes see-through, so it must never be the
# output of a style color or a dimmed halo.
TRANSPARENT_KEY = "#FF00FF"

# Neon defaults per drawable kind (+ the highlight rectangle and the pointer).
# The circle's magenta is DELIBERATELY not #FF00FF (that is the transparent key).
DEFAULT_COLORS: dict[str, str] = {
    "line": "#00FFFF",        # neon cyan
    "arrow": "#39FF14",       # neon green
    "circle": "#FF2BD6",      # neon magenta (NOT the transparent key)
    "rectangle": "#FFEA00",   # neon yellow
    "pointer": "#00FFFF",     # neon cyan — one identity with the highlight
    "highlight": "#00FFFF",   # highlight_target rectangle stays neon cyan
}

# kind → the env var that overrides its color.
_COLOR_ENV: dict[str, str] = {
    "line": "MUTHIS_COLOR_LINE",
    "arrow": "MUTHIS_COLOR_ARROW",
    "circle": "MUTHIS_COLOR_CIRCLE",
    "rectangle": "MUTHIS_COLOR_RECT",
    "pointer": "MUTHIS_COLOR_POINTER",
    "highlight": "MUTHIS_COLOR_HIGHLIGHT",
}

# Per-STATE status-indicator neon colors (2-A); "idle" is HIDDEN, not a color.
DEFAULT_STATUS_COLORS: dict[str, str] = {
    "listening": "#00FFFF",   # neon cyan — mic is open
    "thinking": "#FFB300",    # neon amber — reasoning
    "speaking": "#39FF14",    # neon green — TTS is talking
}

# status state → the env var that overrides its color.
_STATUS_ENV: dict[str, str] = {
    "listening": "MUTHIS_STATUS_LISTENING",
    "thinking": "MUTHIS_STATUS_THINKING",
    "speaking": "MUTHIS_STATUS_SPEAKING",
}

# Which screen corner hosts the persistent state dot (MUTHIS_STATUS_CORNER).
DEFAULT_STATUS_CORNER = "bottom-right"
_VALID_CORNERS = {"top-left", "top-right", "bottom-left", "bottom-right"}

# Caption chip geometry (kept as constants — font family/size are the tunable
# knobs). Padding around the text; corner radius of the rounded plate.
CAPTION_PAD_PX = 6
CHIP_RADIUS_PX = 8

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class OverlayStyle:
    """Immutable bundle of every overlay style value. The dataclass defaults ARE
    the neon defaults, so `OverlayStyle()` is fully deterministic (no env), while
    `from_env()` overlays `.env` on top of them."""

    colors: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_COLORS))
    core_width: int = 3
    glow_enabled: bool = True
    glow_width: int = 4          # px added to EACH side of the core for the halo
    glow_intensity: float = 0.45  # halo = neon dimmed by this factor (0..1)
    label_font_family: str = "Segoe UI"   # ships with Win11, renders Arabic
    label_font_size: int = 14
    label_plate: str = "#0B0F1A"           # semi-dark chip background
    pointer_outline: str = "#003B4A"       # crisp dark edge on the pointer core
    status_colors: Mapping[str, str] = field(
        default_factory=lambda: dict(DEFAULT_STATUS_COLORS))
    status_corner: str = DEFAULT_STATUS_CORNER

    @classmethod
    def from_env(cls) -> "OverlayStyle":
        """Build a style from `.env`, falling back to the neon defaults for any
        var that is unset, blank, or malformed (a bad value logs an English
        warning and never crashes the Tk thread)."""
        colors = {
            kind: _safe_color(os.getenv(env), DEFAULT_COLORS[kind])
            for kind, env in _COLOR_ENV.items()
        }
        return cls(
            colors=colors,
            core_width=max(1, _env_int("MUTHIS_CORE_WIDTH", 3)),
            glow_enabled=_env_flag("MUTHIS_GLOW", True),
            glow_width=max(0, _env_int("MUTHIS_GLOW_WIDTH", 4)),
            glow_intensity=_clamp01(_env_float("MUTHIS_GLOW_INTENSITY", 0.45)),
            label_font_family=os.getenv("MUTHIS_LABEL_FONT") or "Segoe UI",
            label_font_size=max(1, _env_int("MUTHIS_LABEL_SIZE", 14)),
            label_plate=_safe_color(os.getenv("MUTHIS_LABEL_PLATE"), "#0B0F1A"),
            status_colors={
                state: _safe_color(os.getenv(env), DEFAULT_STATUS_COLORS[state])
                for state, env in _STATUS_ENV.items()
            },
            status_corner=_env_corner("MUTHIS_STATUS_CORNER", DEFAULT_STATUS_CORNER),
        )


# ─────────────────────────── style → draw helpers ───────────────────────────


def color_for(style: OverlayStyle, kind: str) -> str:
    """The neon color for one kind, defaulting if a widget passes an odd kind."""
    return style.colors.get(kind, DEFAULT_COLORS.get(kind, "#00FFFF"))


def glow_strokes(style: OverlayStyle, core_color: str) -> list[tuple[int, str]]:
    """The (width, color) passes for a stroked shape, OUTER → INNER so the caller
    draws the dim halo first and the bright core lands on top. Glow off → just the
    single crisp core stroke. Same list drives line/arrow/circle/rectangle and the
    highlight rectangle, so every LOOK graphic glows identically."""
    core = (style.core_width, core_color)
    if not style.glow_enabled:
        return [core]
    halo_width = style.core_width + 2 * style.glow_width
    return [(halo_width, dim(core_color, style.glow_intensity)), core]


def dim(color: str, factor: float) -> str:
    """A hex color scaled toward black by `factor` (0 → black, 1 → unchanged) —
    the halo tint. Guarded so the result is never the transparent key."""
    f = _clamp01(factor)
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    scaled = tuple(min(255, max(0, round(c * f))) for c in (r, g, b))
    return _avoid_key("#%02X%02X%02X" % scaled)


def caption_font(style: OverlayStyle) -> tuple[str, int, str]:
    """The Tk font tuple for captions — bold for legibility over any background."""
    return (style.label_font_family, style.label_font_size, "bold")


def round_rect_points(
    x1: float, y1: float, x2: float, y2: float, radius: float,
) -> list[float]:
    """Control points for a rounded rectangle drawn as a `smooth=True` polygon
    (Tk has no native rounded rect). Radius is clamped to half the shorter side."""
    r = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def draw_caption_chip(
    canvas, x: float, y: float, label_ar: str, style: OverlayStyle,
    *, text_color: str, tags: str | None = None,
) -> None:
    """Draw a crisp Arabic caption on a semi-dark rounded chip, anchored just
    ABOVE the shape's top-left so it never covers the shape. The chip is a rounded
    `smooth` polygon behind the text (neon 1px border, dark fill), pushed below
    the text. Duck-typed canvas + optional `tags` so the shapes path scopes every
    item to its tag while the highlight path stays untagged (it clears with
    delete-all)."""
    tag_kw = {"tags": tags} if tags else {}
    text_id = canvas.create_text(
        x + CAPTION_PAD_PX, y - CAPTION_PAD_PX,
        text=label_ar, anchor="sw",
        fill=text_color, font=caption_font(style), **tag_kw,
    )
    bounds = canvas.bbox(text_id)
    if bounds is None:      # some fakes / an unmeasured text — skip the plate
        return
    bx1, by1, bx2, by2 = bounds
    points = round_rect_points(
        bx1 - CAPTION_PAD_PX, by1 - CAPTION_PAD_PX // 2,
        bx2 + CAPTION_PAD_PX, by2 + CAPTION_PAD_PX // 2,
        CHIP_RADIUS_PX,
    )
    plate = canvas.create_polygon(
        *points, smooth=True, fill=style.label_plate,
        outline=text_color, width=1, **tag_kw,
    )
    canvas.tag_lower(plate, text_id)


# ─────────────────────────────── env parsing ───────────────────────────────


def _safe_color(value: str | None, default: str) -> str:
    """A validated, upper-cased #RRGGBB — falling back to `default` on a blank or
    malformed value, and nudging away from the transparent key so it stays
    visible."""
    if not value:
        return default
    if not _HEX_RE.match(value.strip()):
        logger.warning("[overlay] ignoring invalid color %r — using %s", value, default)
        return default
    return _avoid_key("#" + value.strip()[1:].upper())


def _avoid_key(color: str) -> str:
    """Keep a color off the exact transparent key (which would render invisible)
    by nudging its red channel down one step."""
    if color.upper() == TRANSPARENT_KEY:
        logger.warning("[overlay] color equals the transparent key — nudging it visible")
        return "#FE00FF"
    return color


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("[overlay] %s=%r is not an integer — using %d", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("[overlay] %s=%r is not a number — using %s", name, raw, default)
        return default


def _env_flag(name: str, default: bool) -> bool:
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


def _env_corner(name: str, default: str) -> str:
    """One of the four screen corners for the status dot; a blank/typo → default."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    token = raw.strip().lower()
    if token in _VALID_CORNERS:
        return token
    logger.warning("[overlay] %s=%r is not a valid corner — using %s", name, raw, default)
    return default


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


__all__ = [
    "OverlayStyle", "DEFAULT_COLORS", "DEFAULT_STATUS_COLORS",
    "DEFAULT_STATUS_CORNER", "TRANSPARENT_KEY",
    "color_for", "glow_strokes", "dim", "caption_font",
    "round_rect_points", "draw_caption_chip",
]
