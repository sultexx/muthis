"""
test_overlay_style.py — the single overlay styling config (muthis.overlay.style),
pure and deterministic (no Tk, no display, no network).

Proves the NEON look (Batch 1) is fully .env-driven with sensible neon defaults:
  * from_env() yields the documented neon defaults when nothing is set,
  * every color / glow / font / core-width var is honored when set,
  * a malformed color falls back (with a warning) and a color equal to the
    transparent key is nudged so it can never render invisible,
  * dim() darkens a color toward black (the halo tint),
  * glow_strokes() returns the OUTER-halo + INNER-core passes (2+), collapsing to
    one crisp core when glow is disabled,
  * draw_caption_chip() emits the Arabic text on a rounded (smooth) chip pushed
    below it, scoping to a tag only when one is given.

conftest clears the MUTHIS_* overlay vars before each test, so these assertions
are independent of the developer's shell; override tests set their own via env.

Run:  set PYTHONPATH=src && python -m pytest tests/test_overlay_style.py -q
"""

from __future__ import annotations

import logging

from muthis.overlay.style import (
    DEFAULT_COLORS,
    TRANSPARENT_KEY,
    OverlayStyle,
    caption_font,
    color_for,
    dim,
    draw_caption_chip,
    glow_strokes,
)


# ─────────────────────────────── Defaults ───────────────────────────────


def test_from_env_defaults_are_the_documented_neon_values():
    style = OverlayStyle.from_env()
    assert style.colors == DEFAULT_COLORS
    assert style.colors["line"] == "#00FFFF"      # neon cyan
    assert style.colors["arrow"] == "#39FF14"     # neon green
    assert style.colors["circle"] == "#FF2BD6"    # neon magenta, NOT the key
    assert style.colors["rectangle"] == "#FFEA00"  # neon yellow
    assert style.core_width == 3
    assert style.glow_enabled is True
    assert style.glow_width == 4
    assert style.glow_intensity == 0.35   # softened 0.45 → 0.35 (v5 A3)
    assert style.label_font_family == "Segoe UI"
    assert style.label_font_size == 14
    assert style.label_plate == "#0B0F1A"


def test_no_default_color_is_the_transparent_key():
    # Every drawn neon must be visible over the magenta transparent key.
    assert TRANSPARENT_KEY not in {c.upper() for c in DEFAULT_COLORS.values()}


def test_caption_font_is_bold_family_and_size():
    style = OverlayStyle(label_font_family="Tahoma", label_font_size=18)
    assert caption_font(style) == ("Tahoma", 18, "bold")


# ─────────────────────────────── Overrides ───────────────────────────────


def test_env_overrides_each_shape_color(monkeypatch):
    monkeypatch.setenv("MUTHIS_COLOR_LINE", "#112233")
    monkeypatch.setenv("MUTHIS_COLOR_ARROW", "#abcdef")   # normalized to upper
    monkeypatch.setenv("MUTHIS_COLOR_CIRCLE", "#010101")
    monkeypatch.setenv("MUTHIS_COLOR_RECT", "#020202")
    monkeypatch.setenv("MUTHIS_COLOR_POINTER", "#030303")
    monkeypatch.setenv("MUTHIS_COLOR_HIGHLIGHT", "#040404")

    style = OverlayStyle.from_env()
    assert style.colors["line"] == "#112233"
    assert style.colors["arrow"] == "#ABCDEF"
    assert color_for(style, "circle") == "#010101"
    assert color_for(style, "rectangle") == "#020202"
    assert color_for(style, "pointer") == "#030303"
    assert color_for(style, "highlight") == "#040404"


def test_env_overrides_glow_font_and_core_width(monkeypatch):
    monkeypatch.setenv("MUTHIS_GLOW", "0")
    monkeypatch.setenv("MUTHIS_GLOW_WIDTH", "10")
    monkeypatch.setenv("MUTHIS_GLOW_INTENSITY", "0.2")
    monkeypatch.setenv("MUTHIS_CORE_WIDTH", "5")
    monkeypatch.setenv("MUTHIS_LABEL_FONT", "Tahoma")
    monkeypatch.setenv("MUTHIS_LABEL_SIZE", "20")
    monkeypatch.setenv("MUTHIS_LABEL_PLATE", "#010203")

    style = OverlayStyle.from_env()
    assert style.glow_enabled is False
    assert style.glow_width == 10
    assert style.glow_intensity == 0.2
    assert style.core_width == 5
    assert style.label_font_family == "Tahoma"
    assert style.label_font_size == 20
    assert style.label_plate == "#010203"


def test_glow_flag_accepts_words(monkeypatch):
    monkeypatch.setenv("MUTHIS_GLOW", "off")
    assert OverlayStyle.from_env().glow_enabled is False
    monkeypatch.setenv("MUTHIS_GLOW", "yes")
    assert OverlayStyle.from_env().glow_enabled is True


def test_intensity_is_clamped_to_unit_range(monkeypatch):
    monkeypatch.setenv("MUTHIS_GLOW_INTENSITY", "5")
    assert OverlayStyle.from_env().glow_intensity == 1.0
    monkeypatch.setenv("MUTHIS_GLOW_INTENSITY", "-2")
    assert OverlayStyle.from_env().glow_intensity == 0.0


def test_a_malformed_color_falls_back_to_the_neon_default(monkeypatch, caplog):
    monkeypatch.setenv("MUTHIS_COLOR_LINE", "teal")     # not #RRGGBB
    with caplog.at_level(logging.WARNING):
        style = OverlayStyle.from_env()
    assert style.colors["line"] == DEFAULT_COLORS["line"]
    assert "invalid color" in caplog.text


def test_a_bad_number_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("MUTHIS_GLOW_WIDTH", "abc")
    monkeypatch.setenv("MUTHIS_CORE_WIDTH", "xyz")
    style = OverlayStyle.from_env()
    assert style.glow_width == 4 and style.core_width == 3


def test_a_color_equal_to_the_transparent_key_is_nudged_visible(monkeypatch):
    monkeypatch.setenv("MUTHIS_COLOR_CIRCLE", "#FF00FF")  # the transparent key
    style = OverlayStyle.from_env()
    assert style.colors["circle"].upper() != TRANSPARENT_KEY


# ─────────────────────────────── dim() ───────────────────────────────


def test_dim_scales_toward_black():
    assert dim("#FFFFFF", 0.0) == "#000000"
    assert dim("#FFFFFF", 1.0) == "#FFFFFF"
    assert dim("#FFFFFF", 0.5) == "#808080"


def test_dim_never_yields_the_transparent_key():
    # A magenta kept at full brightness would land on the key — dim nudges it off.
    assert dim("#FF00FF", 1.0).upper() != TRANSPARENT_KEY


# ─────────────────────────── glow_strokes() ───────────────────────────


def test_glow_strokes_are_outer_halo_then_inner_core():
    style = OverlayStyle()  # glow on, core 3, width 4, intensity 0.35
    strokes = glow_strokes(style, "#00FFFF")
    assert len(strokes) == 2
    (halo_w, halo_c), (core_w, core_c) = strokes
    assert core_w == 3 and core_c == "#00FFFF"                 # crisp neon core
    assert halo_w == 3 + 2 * 4 and halo_c == dim("#00FFFF", 0.35)  # dim wide halo
    assert halo_w > core_w                                     # drawn under the core


def test_glow_disabled_is_a_single_core_stroke():
    strokes = glow_strokes(OverlayStyle(glow_enabled=False), "#39FF14")
    assert strokes == [(3, "#39FF14")]


# ─────────────────────────── caption chip ───────────────────────────


class _ChipCanvas:
    def __init__(self):
        self.texts = []
        self.polygons = []
        self.lowered = []
        self._id = 0

    def _next(self):
        self._id += 1
        return self._id

    def create_text(self, *coords, **kw):
        self.texts.append((coords, kw))
        return self._next()

    def bbox(self, item_id):
        return (100, 100, 160, 120)

    def create_polygon(self, *coords, **kw):
        self.polygons.append((coords, kw))
        return self._next()

    def tag_lower(self, lower, upper):
        self.lowered.append((lower, upper))


def test_draw_caption_chip_puts_text_on_a_rounded_plate_below_it():
    canvas = _ChipCanvas()
    style = OverlayStyle()
    draw_caption_chip(canvas, 50, 60, "زر", style, text_color="#00FFFF", tags="t")

    assert canvas.texts[0][1]["text"] == "زر"
    assert canvas.texts[0][1]["fill"] == "#00FFFF"
    assert canvas.texts[0][1]["font"] == caption_font(style)
    assert canvas.texts[0][1]["tags"] == "t"
    # The chip is a rounded (smooth) polygon: dark fill, neon 1px border, tagged.
    chip = canvas.polygons[0][1]
    assert chip["smooth"] is True
    assert chip["fill"] == style.label_plate
    assert chip["outline"] == "#00FFFF"
    assert chip["tags"] == "t"
    # The plate (id 2) is pushed BELOW the text (id 1) so the Arabic reads on top.
    assert canvas.lowered == [(2, 1)]


def test_caption_chip_untagged_when_no_tag_is_given():
    canvas = _ChipCanvas()
    draw_caption_chip(canvas, 0, 0, "زر", OverlayStyle(), text_color="#00FFFF")
    assert "tags" not in canvas.texts[0][1]
    assert "tags" not in canvas.polygons[0][1]
