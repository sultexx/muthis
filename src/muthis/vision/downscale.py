# src/muthis/vision/downscale.py
"""
downscale.py — produce the API-payload COPY of a screenshot, bounded so the
provider does NOT resize it again. This is the coordinate-mapping safeguard.

WHY (the dangerous part): claude-sonnet-4-6 (the 4.6 family) resizes any image
whose long edge exceeds ~1568 px or whose area exceeds ~1.15 MP BEFORE the model
sees it, and on that family the pixel coordinates it returns live in that
(possibly resized) image space — they are NOT guaranteed 1:1 with the bytes we
sent (the 1:1-pixel guarantee is an Opus 4.7+ high-res feature, not Sonnet 4.6).
So we downscale our sent COPY to a max width of 1280 (≤ 1568 long edge and
≤ 1.15 MP for a landscape primary monitor): the API performs ZERO further
resize, the sent-image space equals the space the model reasons in, and the
model's coordinates come back in OUR sent space. Exactly one downscale (ours),
exactly one (scale_x, scale_y), no hidden third coordinate space.

screen_capture.py stays the single source of truth (full physical pixels). This
module only builds the COPY for the payload and computes the factors that map
the model's coordinates back to physical pixels. It does NOT move the mouse or
draw anything — applying the factors is the overlay step's job (next phase).

Privacy (Law: never log/persist screenshots): pixels live only as in-memory
bytes for the turn; nothing is written to disk and only dimensions (English) are
ever logged.

Async (the threading law): Pillow decode/resize/encode is CPU-bound, so it runs
inside asyncio.to_thread — the single event loop is never frozen. Pillow is lazy-
imported (already pinned for screen_capture); this module stays importable in
isolation.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os

from ..kernel.turn import DownscaledImage

logger = logging.getLogger("muthis.vision.downscale")

# Default sent-image width cap. 1280 keeps a landscape primary monitor under
# claude-sonnet-4-6's ~1568 px / ~1.15 MP server-side resize threshold, so the
# sent-image space == the space the model reasons in. Override via .env.
DEFAULT_VISION_MAX_WIDTH = int(os.getenv("MUTHIS_VISION_MAX_WIDTH", "1280"))


def compute_scale_factors(
    physical_width: int,
    physical_height: int,
    max_width: int,
) -> tuple[int, int, float, float]:
    """Pure: map a physical frame to the sent-image dims + per-axis scale
    factors (sent_width, sent_height, scale_x, scale_y).

    No downscale when the frame is already within max_width (scale 1.0). The two
    factors are computed INDEPENDENTLY — sent_height rounds, so for aspect ratios
    that don't divide cleanly scale_x and scale_y can differ by a hair; the
    overlay must multiply x by scale_x and y by scale_y, never assume one factor.
    1920x1080 at max_width 1280 → (1280, 720, 1.5, 1.5) exactly.
    """
    if physical_width <= 0 or physical_height <= 0 or max_width <= 0:
        return physical_width, physical_height, 1.0, 1.0
    if physical_width <= max_width:
        return physical_width, physical_height, 1.0, 1.0
    sent_width = max_width
    sent_height = max(1, round(physical_height * max_width / physical_width))
    scale_x = physical_width / sent_width
    scale_y = physical_height / sent_height
    return sent_width, sent_height, scale_x, scale_y


async def downscale_to_max_width(
    png_bytes: bytes | None,
    max_width: int = DEFAULT_VISION_MAX_WIDTH,
) -> DownscaledImage:
    """Build the API-payload COPY: decode the physical PNG, downscale it to
    max_width (aspect preserved), and return a DownscaledImage carrying the sent
    PNG bytes + sent dims + (scale_x, scale_y).

    None in → None out (identity scale). A frame already within max_width passes
    through unchanged (identity scale). Blocking Pillow work runs via
    asyncio.to_thread (the threading law). NEVER raises — on any Pillow failure it
    returns the ORIGINAL bytes with identity scale, degrading exactly like
    capture() does (the turn continues; the model just gets the physical frame).
    """
    if not png_bytes:
        return DownscaledImage(None, 0, 0, 1.0, 1.0)
    try:
        return await asyncio.to_thread(_downscale_sync, png_bytes, max_width)
    except Exception as exc:  # noqa: BLE001 — payload prep must never break a turn
        logger.warning(
            "[vision] downscale failed (%s) — sending the physical frame",
            type(exc).__name__,
        )
        return DownscaledImage(png_bytes, 0, 0, 1.0, 1.0)


def _downscale_sync(png_bytes: bytes, max_width: int) -> DownscaledImage:
    """Blocking core — ALWAYS via asyncio.to_thread. Lazy-imports Pillow (kept
    importable in isolation). Encodes the COPY in memory only — never to disk."""
    from PIL import Image

    with Image.open(io.BytesIO(png_bytes)) as image:
        physical_width, physical_height = image.size
        sent_width, sent_height, scale_x, scale_y = compute_scale_factors(
            physical_width, physical_height, max_width,
        )
        if (sent_width, sent_height) == (physical_width, physical_height):
            # Already within budget — send the original bytes untouched.
            logger.info(
                "[vision] frame %dx%d within max width %d — no downscale",
                physical_width, physical_height, max_width,
            )
            return DownscaledImage(png_bytes, sent_width, sent_height, 1.0, 1.0)
        # Resampling enum on Pillow >=9.1; fall back to the legacy constant.
        resample = getattr(Image, "Resampling", Image).LANCZOS
        resized = image.convert("RGB").resize((sent_width, sent_height), resample)
        buffer = io.BytesIO()
        resized.save(buffer, format="PNG")  # in-memory only — never touches disk

    logger.info(
        "[vision] downscaled %dx%d → %dx%d (scale_x=%.4f scale_y=%.4f) for payload",
        physical_width, physical_height, sent_width, sent_height, scale_x, scale_y,
    )
    return DownscaledImage(buffer.getvalue(), sent_width, sent_height, scale_x, scale_y)


__all__ = ["compute_scale_factors", "downscale_to_max_width", "DEFAULT_VISION_MAX_WIDTH"]
