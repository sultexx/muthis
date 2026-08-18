# src/muthis/overlay/mode_indicator.py
"""
ModeIndicator — the kernel-drawn mode frame, on screen (DEC-65, T3).

WHY IT EXISTS. DEC-66 makes step PROGRESS a model request the kernel approves
rather than a deterministic detector, and the argument for that is explicitly
this widget: progress's worst case is being on the WRONG STEP, which is
**VISIBLE** and corrected with a word. **A model claiming "step 3" while this
reads ٢ is visibly contradicted** — the DEC-36 domain badge's shape applied to
the turn's own frame, and the deterministic backstop that makes model-requested
progress safe.

THE ONE PLACE IT DIFFERS FROM THE BADGE IS THE PLACE THAT MATTERS, and DEC-73
recorded the cost in advance rather than letting it be discovered: **the badge's
per-turn lifetime is free BECAUSE `clear_caption` fires at end of turn, but a
mode indicator must SURVIVE ACROSS TURNS.** So it does NOT inherit the caption's
lifecycle, and the arrangement does not transfer. Concretely, the lifecycle is
split in two:

  * GHOSTING still applies — `hide()` erases it from the canvas, because a
    capture must never show Claude our own overlay (it would then reason about
    a mode indicator it had drawn for itself);
  * but the TEXT IS REMEMBERED, and `restore()` redraws it. WHO calls that, and
    WHEN, is DEC-104 ruling 1 and it changed: the duty is now UNIFIED at the
    hide itself (`window_commands.dispatch_command`), which restores the chip
    for every hide whose reason has ENDED — the 7 s auto-hide after speech and
    a barge-in both remove the OVERLAY, never the mode. Only the hide taken FOR
    A GRAB defers it, because a capture must not show Claude our own chip; that
    one restores at `FrameCapture.capture`, at the same instant as the status
    dot. Before the ruling the capture site was the ONLY caller that restored,
    so the chip died 7 s into every drawing step while the mode was still live.
    There is still no second LIFECYCLE — the memory below is the whole of it.
  * `clear_caption` does NOT touch it. That is the whole carried warning, and it
    is written as an explicit non-branch in `window_commands.dispatch_command`
    so a future reader sees a decision rather than an omission.

`forget()` is the separate verb for "there is no mode" — the kernel calls it by
sending an empty text, which both erases the chip AND drops the memory, so a
restore after the mode ends cannot resurrect it.

ANCHORED TOP-LEFT, AND COLLISION-FREE BY CONSTRUCTION rather than by an offset.
The caption chip is bottom-CENTRE, the domain badge bottom-LEFT and the status
dot defaults to bottom-RIGHT: every other persistent element is anchored to the
BOTTOM edge, so a top anchor cannot collide with any of them however the caption
wraps or the font changes (the badge's own reasoning, one edge up). It consumes
NONE of the caption's 2×60 text budget — it is a separate, tag-scoped element on
its own anchor, so a long mode name can never eat a line of speech.

**THE EXACT POSITION IS NOT FROZEN HERE.** D-3 ruled placement a UX decision for
Sultan after a prototype; these two margins are the prototype, and moving them
is a one-line change that no test pins to a pixel.

No tkinter import — the canvas is duck-typed (create_text / create_polygon /
bbox / tag_lower / delete), so this module and its tests need no display.
"""

from __future__ import annotations

from typing import Optional

from .style import (
    CAPTION_PAD_PX,
    OverlayStyle,
    caption_font,
    color_for,
    round_rect_points,
)

# Every item carries this tag — the shared-canvas rule (never delete-all), so
# the rectangle / pointer / shapes / caption / badge / status dot are untouched.
MODE_INDICATOR_TAG = "muthis-mode-indicator"

# The PROTOTYPE anchor (see the docstring): top-left, clear of every
# bottom-anchored element. Sultan's eye settles the final position.
LEFT_MARGIN_PX = 48
TOP_MARGIN_PX = 48


class ModeIndicator:
    """A tag-scoped top-left chip that survives across turns."""

    def __init__(self, canvas, style: Optional[OverlayStyle] = None) -> None:
        self._canvas = canvas
        self._style = style or OverlayStyle.from_env()
        # The remembered text is what makes this element cross-turn: `hide()`
        # wipes the canvas for ghosting, and this is what `restore()` redraws.
        self._text = ""

    # ─── The three lifecycle verbs ───────────────────────────────────────────

    def show(self, text: str) -> None:
        """Set the indicator to `text`, remembering it. An empty text FORGETS —
        an inactive mode draws nothing and must not come back on a restore."""
        self._text = text or ""
        self._draw()

    def restore(self) -> None:
        """Redraw the remembered indicator — called after every capture, which
        is what carries it across turns and across in-loop refreshes."""
        self._draw()

    def clear(self) -> None:
        """Erase the chip from the canvas but KEEP the memory (the ghosting
        hide). This is the half that differs from the badge: the badge is gone
        for good at this point, and this one is coming back."""
        self._canvas.delete(MODE_INDICATOR_TAG)

    # ─── Drawing ─────────────────────────────────────────────────────────────

    def _draw(self) -> None:
        self._canvas.delete(MODE_INDICATOR_TAG)
        if not self._text:
            return
        color = color_for(self._style, "highlight")
        text_id = self._canvas.create_text(
            LEFT_MARGIN_PX, TOP_MARGIN_PX,
            text=self._text, anchor="nw", justify="left",
            fill=color, font=caption_font(self._style), tags=MODE_INDICATOR_TAG,
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
            tags=MODE_INDICATOR_TAG,
        )
        self._canvas.tag_lower(plate_id, text_id)  # plate under the text


__all__ = ["ModeIndicator", "MODE_INDICATOR_TAG", "LEFT_MARGIN_PX", "TOP_MARGIN_PX"]
