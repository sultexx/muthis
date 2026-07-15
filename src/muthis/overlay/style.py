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

Env parsing + the transparent-key guard live in `style_env.py` (split under the
≤300-line law — this file sat exactly at the ceiling): a malformed `.env` value
warns and falls back, and `avoid_key()` keeps any parsed color (and any `dim()`
halo tint) off the #FF00FF transparent key so it can never render invisible.
`TRANSPARENT_KEY` is re-exported here so existing importers keep working.

DI: `OverlayStyle.from_env()` is the graceful fallback; `SidekickOverlay(style=)`
may inject a tuned instance (and tests inject a deterministic one). Coordinates,
ghosting, sync, click-through and DPI are NOT this module's concern — it only
decides how pixels LOOK.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

from .style_env import (
    TRANSPARENT_KEY,
    avoid_key,
    clamp01,
    env_corner,
    env_flag,
    env_float,
    env_int,
    safe_color,
)

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

# Caption chip geometry (kept as constants — font family/size are the tunable
# knobs). Padding around the text; corner radius of the rounded plate.
CAPTION_PAD_PX = 6
CHIP_RADIUS_PX = 8


@dataclass(frozen=True)
class OverlayStyle:
    """Immutable bundle of every overlay style value. The dataclass defaults ARE
    the neon defaults, so `OverlayStyle()` is fully deterministic (no env), while
    `from_env()` overlays `.env` on top of them."""

    colors: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_COLORS))
    core_width: int = 3
    glow_enabled: bool = True
    glow_width: int = 4          # px added to EACH side of the core for the halo
    glow_intensity: float = 0.35  # halo = neon dimmed by this factor (0..1); 0.45→0.35 (v5 A3): a fainter, softer halo
    label_font_family: str = "Segoe UI"   # ships with Win11, renders Arabic
    label_font_size: int = 16  # 14→16 (v5 A3): clearer Arabic captions at a glance
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
            kind: safe_color(os.getenv(env), DEFAULT_COLORS[kind])
            for kind, env in _COLOR_ENV.items()
        }
        return cls(
            colors=colors,
            core_width=max(1, env_int("MUTHIS_CORE_WIDTH", 3)),
            glow_enabled=env_flag("MUTHIS_GLOW", True),
            glow_width=max(0, env_int("MUTHIS_GLOW_WIDTH", 4)),
            glow_intensity=clamp01(env_float("MUTHIS_GLOW_INTENSITY", 0.35)),
            label_font_family=os.getenv("MUTHIS_LABEL_FONT") or "Segoe UI",
            label_font_size=max(1, env_int("MUTHIS_LABEL_SIZE", 16)),
            label_plate=safe_color(os.getenv("MUTHIS_LABEL_PLATE"), "#0B0F1A"),
            status_colors={
                state: safe_color(os.getenv(env), DEFAULT_STATUS_COLORS[state])
                for state, env in _STATUS_ENV.items()
            },
            status_corner=env_corner("MUTHIS_STATUS_CORNER", DEFAULT_STATUS_CORNER),
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
    f = clamp01(factor)
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    scaled = tuple(min(255, max(0, round(c * f))) for c in (r, g, b))
    return avoid_key("#%02X%02X%02X" % scaled)


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


__all__ = [
    "OverlayStyle", "DEFAULT_COLORS", "DEFAULT_STATUS_COLORS",
    "DEFAULT_STATUS_CORNER", "TRANSPARENT_KEY",
    "color_for", "glow_strokes", "dim", "caption_font",
    "round_rect_points", "draw_caption_chip",
]
