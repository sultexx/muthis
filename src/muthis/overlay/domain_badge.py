# src/muthis/overlay/domain_badge.py
"""
DomainBadge — the DEC-20 deterministic attribution backstop, drawn.

WHAT IT IS FOR. Citation is model SPEECH and therefore not structurally
enforceable; DEC-20 answers that with three layers, and this is the third — the
only one the model does not author. Because it is drawn by the kernel from what
the BROKER'S FETCHER actually retrieved (`broker/net/provenance.py`), it exposes
BOTH failure modes: a missing citation (the badge names a source the voice never
did) and a HALLUCINATED one (the user hears one source and sees another).

THREE CONSTRAINTS FROM DEC-20, each a design decision here:
  * DOMAIN ONLY, never a full URL. A URL can carry `?q=<the user's private
    question>`, and putting that on screen would defeat the privacy line the
    whole milestone defends. This widget never receives a URL — the collector
    only stores hostnames — so the rule holds by TYPE, not by care.
  * It does NOT consume the caption's text budget (2 lines x 60 chars). The
    VOICE carries the teaching; the caption carries the sentence being spoken.
    The badge is a separate, tag-scoped element with its own anchor, so a long
    source list can never eat a line of speech.
  * It INHERITS the caption's lifecycle — `clear_caption` and the
    hide-before-capture ghosting path both clear it (see window_commands), so a
    capture never shows Mut'his its own badge and no new lifecycle exists to get
    out of step.

ANCHORED BOTTOM-LEFT, deliberately. The caption chip is bottom-CENTER and its
height varies with wrapping; the status dot defaults to bottom-RIGHT. A fixed
left anchor cannot collide with either as text grows — collision-free BY
CONSTRUCTION rather than by an arithmetic offset that would drift the first time
the caption font changes.

An EMPTY badge is meaningful, not a bug: it means nothing was fetched and read
this turn (a snippet-only answer). Rendering nothing is the honest signal.

No tkinter import — the canvas is duck-typed (create_text / create_polygon /
bbox / tag_lower / delete), so this module and its tests need no display.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .style import (
    CAPTION_PAD_PX,
    OverlayStyle,
    caption_font,
    color_for,
    round_rect_points,
)

# Every badge item carries this tag — the shared-canvas rule (never delete-all),
# so the rectangle / pointer / shapes / caption / status dot are never disturbed.
DOMAIN_BADGE_TAG = "muthis-domain-badge"

# Bottom-left anchor, clear of the caption chip's bottom-center column.
LEFT_MARGIN_PX = 48
BOTTOM_MARGIN_PX = 48

# Width bound: three sources read comfortably at a glance; beyond that the badge
# would compete with the caption for attention, which DEC-20 forbids. The rest
# are COUNTED, never dropped silently — "+2" still tells the user more was read.
MAX_SHOWN = 3
SEPARATOR = " · "
SOURCE_LABEL_AR = "المصادر:"


def format_badge(domains: Sequence[str]) -> str:
    """Pure: the badge's text, or "" when nothing was read this turn.

    Separated from the drawing so the POLICY (label, bound, overflow marker) is
    testable without a canvas — the `wrap_caption` precedent."""
    cleaned = [d.strip() for d in domains if isinstance(d, str) and d.strip()]
    if not cleaned:
        return ""
    shown = cleaned[:MAX_SHOWN]
    text = SEPARATOR.join(shown)
    remaining = len(cleaned) - len(shown)
    if remaining > 0:
        text = f"{text} +{remaining}"
    return f"{SOURCE_LABEL_AR} {text}"


class DomainBadge:
    """A tag-scoped bottom-left source chip on the shared overlay canvas."""

    def __init__(
        self,
        canvas,
        screen_size: tuple[int, int],
        style: Optional[OverlayStyle] = None,
    ) -> None:
        self._canvas = canvas
        self._screen_width, self._screen_height = screen_size
        self._style = style or OverlayStyle.from_env()

    def show(self, domains: Sequence[str]) -> None:
        """Replace the badge with `domains`. An empty list just wipes — the
        badge never renders an empty chip, because "nothing read" must look
        like nothing, not like a source."""
        self._canvas.delete(DOMAIN_BADGE_TAG)
        text = format_badge(domains)
        if not text:
            return
        color = color_for(self._style, "highlight")
        text_id = self._canvas.create_text(
            LEFT_MARGIN_PX, self._screen_height - BOTTOM_MARGIN_PX,
            text=text, anchor="sw", justify="left",
            fill=color, font=caption_font(self._style), tags=DOMAIN_BADGE_TAG,
        )
        bounds = self._canvas.bbox(text_id)
        if bounds is None:  # an unmeasured fake — the text alone is still correct
            return
        bx1, by1, bx2, by2 = bounds
        plate_id = self._canvas.create_polygon(
            round_rect_points(
                bx1 - CAPTION_PAD_PX, by1 - CAPTION_PAD_PX // 2,
                bx2 + CAPTION_PAD_PX, by2 + CAPTION_PAD_PX // 2,
                radius=CAPTION_PAD_PX,
            ),
            smooth=True, fill=self._style.label_plate, outline=color,
            tags=DOMAIN_BADGE_TAG,
        )
        self._canvas.tag_lower(plate_id, text_id)  # plate under the text

    def clear(self) -> None:
        """Erase ONLY the badge items. Called on the SAME paths that clear the
        caption (audio end, ghosting hide) — the inherited lifecycle."""
        self._canvas.delete(DOMAIN_BADGE_TAG)


__all__ = ["DomainBadge", "DOMAIN_BADGE_TAG", "format_badge",
           "MAX_SHOWN", "SOURCE_LABEL_AR", "LEFT_MARGIN_PX", "BOTTOM_MARGIN_PX"]
