"""
test_vision_downscale.py — the coordinate-mapping safeguard math (pure + real
Pillow, no screen, deterministic).

Pins the dangerous part: physical 1920x1080 downscaled to max width 1280 yields
sent 1280x720 with scale_x == scale_y == 1.5 EXACTLY, and the real
downscale_to_max_width re-encodes a 1280x720 PNG carrying those exact factors.
Also: a frame already within max width passes through untouched (identity
scale), and None in → None out.

Run:  set PYTHONPATH=src && python -m pytest tests/test_vision_downscale.py -q
"""

from __future__ import annotations

import io

import pytest

from muthis.vision.downscale import compute_scale_factors, downscale_to_max_width


def _png_bytes(width: int, height: int) -> bytes:
    """A real, decodable PNG of the given size (deterministic, no screen)."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (123, 200, 50)).save(buffer, format="PNG")
    return buffer.getvalue()


# ──────────────────────────── Pure scale math ────────────────────────────


def test_scale_factors_1920x1080_to_1280_is_exactly_1_5():
    # THE safeguard assertion: a 1080p frame capped at 1280 width sends 1280x720,
    # and BOTH axes scale by exactly 1.5 (clean division — assert exact floats).
    assert compute_scale_factors(1920, 1080, 1280) == (1280, 720, 1.5, 1.5)


def test_scale_factors_no_downscale_when_within_max_width():
    # A frame already ≤ max width is sent untouched with identity scale.
    assert compute_scale_factors(1024, 768, 1280) == (1024, 768, 1.0, 1.0)


def test_scale_factors_axes_are_independent():
    # sent_height rounds, so scale_y need not equal scale_x — both are carried.
    sent_w, sent_h, scale_x, scale_y = compute_scale_factors(1366, 768, 1280)
    assert sent_w == 1280
    assert sent_h == round(768 * 1280 / 1366)
    assert scale_x == 1366 / 1280
    assert scale_y == 768 / sent_h


# ──────────────── Real downscale (real Pillow, in-memory PNG) ──────────────


@pytest.mark.asyncio
async def test_downscale_to_max_width_reencodes_1280x720_with_factors():
    pytest.importorskip("PIL")
    from PIL import Image

    result = await downscale_to_max_width(_png_bytes(1920, 1080), max_width=1280)

    assert result.sent_width == 1280 and result.sent_height == 720
    assert result.scale_x == 1.5 and result.scale_y == 1.5
    # The bytes really are a 1280x720 PNG (the COPY, not the 1920x1080 original).
    assert result.sent_bytes is not None and result.sent_bytes[:4] == b"\x89PNG"
    with Image.open(io.BytesIO(result.sent_bytes)) as img:
        assert img.size == (1280, 720)


@pytest.mark.asyncio
async def test_downscale_passes_through_small_frame_untouched():
    original = _png_bytes(1024, 768)
    result = await downscale_to_max_width(original, max_width=1280)
    assert result.sent_bytes == original  # byte-identical, no re-encode
    assert (result.sent_width, result.sent_height) == (1024, 768)
    assert result.scale_x == 1.0 and result.scale_y == 1.0


@pytest.mark.asyncio
async def test_downscale_none_in_none_out():
    result = await downscale_to_max_width(None, max_width=1280)
    assert result.sent_bytes is None
    assert result.scale_x == 1.0 and result.scale_y == 1.0
