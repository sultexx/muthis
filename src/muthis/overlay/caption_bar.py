# src/muthis/overlay/caption_bar.py
"""
CaptionBar — the live-captions bar (v6 Phase C): a rounded semi-dark chip at
the BOTTOM-CENTER of the shared overlay canvas showing the sentence Mut'his is
currently SPEAKING.

PRIVACY: the bar renders ONLY what the VoiceOut boundary hands it —
assistant-authored Arabic speech. The user transcript, tool JSON, and internal
directives («(توجيه داخلي…») must never reach this module; they are stopped
upstream (VoiceOut.speak is the single entry, same rule as the TTS).

Pure VIEW on the Tk thread: show_text()/clear() arrive via the overlay command
queue; no timers, no state — appearing at speak-start, clearing at
audio-finished, and the hide()-ghosting clear are entirely the CALLER's timing
(Option A stays untouched). All items are scoped to CAPTION_TAG (never
delete-all) so the rectangle / pointer / shapes / status dot sharing this
canvas are never disturbed.

No tkinter import: the canvas is duck-typed (create_text / create_polygon /
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

# Every caption canvas item carries this tag (the shared-canvas rule).
CAPTION_TAG = "muthis-caption"

# Chip geometry: anchored above the very bottom edge so it never fights the
# taskbar line, horizontally centered (the status dot lives in a corner).
BOTTOM_MARGIN_PX = 48

# Soft wrap policy: voice sentences are short; anything longer is truncated with
# an ellipsis (the VOICE carries the teaching — the bar is a reading aid, never a
# document).
#
# 2 -> 3 LINES (DEC-128, shape C2), and the number is MEASURED rather than
# chosen. With rolling captions (voice_out._roll_caption) a 1,159-char answer
# becomes eleven sentence captions, of which FIVE still exceeded 2x60 and kept
# their ellipsis; the longest real sentence was 172 chars, which needs three
# lines of 60. At 3 lines the answer goes from 84.4% visible to 99.1% and NO
# sentence is cut. FOUR lines was measured too and buys exactly nothing (99.1%,
# same 0 cut) — it would only make the chip taller for no reading gain.
#
# LINES, NOT CHARS-PER-LINE, ON PURPOSE: the chip is anchored bottom-CENTER and
# grows UPWARD, while `DomainBadge` sits bottom-LEFT and documents its
# collision-freedom as horizontal separation "BY CONSTRUCTION". More lines grow
# away from the badge; a wider line would grow TOWARD it and turn a structural
# guarantee into an offset that drifts with the font.
MAX_CHARS_PER_LINE = 60
MAX_LINES = 3


def wrap_caption(
    text: str,
    max_chars_per_line: int = MAX_CHARS_PER_LINE,
    max_lines: int = MAX_LINES,
) -> str:
    """Word-wrap `text` to at most `max_lines` lines of `max_chars_per_line`;
    overflow is dropped and marked with a trailing ellipsis. Pure and
    character-count based (no font metrics), so fakes and the Tk thread agree."""
    words = text.split()
    lines: list[str] = []
    current = ""
    truncated = False
    for word in words:
        if len(word) > max_chars_per_line:  # one overlong token: hard-cut it
            word = word[: max_chars_per_line - 1] + "…"
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars_per_line:
            current = candidate
            continue
        lines.append(current)
        if len(lines) == max_lines:
            truncated = True
            current = ""
            break
        current = word
    if current:
        lines.append(current)
    if truncated and lines:
        lines[-1] = lines[-1][: max_chars_per_line - 1].rstrip() + "…"
    return "\n".join(lines)


class CaptionBar:
    """A tag-scoped bottom-center caption chip on the shared overlay canvas."""

    def __init__(
        self,
        canvas,
        screen_size: tuple[int, int],
        style: Optional[OverlayStyle] = None,
        schedule=None,
    ) -> None:
        self._canvas = canvas
        self._screen_width, self._screen_height = screen_size
        # Injected for tuning/tests; from_env() is the graceful neon fallback.
        self._style = style or OverlayStyle.from_env()
        # v7 Phase 2 caption sync: `schedule` is root.after — show_text_later
        # paces a streamed sentence's caption to its AUDIO. None → immediate.
        self._schedule = schedule
        self._generation = 0  # clear() bumps it, orphaning pending shows

    def show_text_later(self, text: str, delay_ms: int) -> None:
        """Show `text` after `delay_ms` on the Tk thread (v7 Phase 2, the
        caption↔audio sync fix): streamed sentences arrive at text-generation
        speed, far ahead of their audio — the caller computes each sentence's
        estimated audio start and the bar holds the display until then.
        Several later-shows may be pending at once (one per queued sentence);
        clear() — audio end, ghosting hide, a dead sentence — cancels them ALL
        so a wiped bar can never resurrect stale speech text."""
        if self._schedule is None or delay_ms <= 0:
            self.show_text(text)
            return
        generation = self._generation

        def fire() -> None:
            if generation == self._generation:  # not cancelled by a clear()
                self.show_text(text)

        self._schedule(max(0, int(delay_ms)), fire)

    def show_text(self, text: str) -> None:
        """Replace the bar's content with `text` (wrapped, ≤2 lines). An empty
        text just wipes — the bar never renders an empty chip. NOTE: replacing
        must NOT bump the cancel generation (a firing sentence would orphan
        its queued siblings) — only the explicit clear() cancels."""
        self._canvas.delete(CAPTION_TAG)
        wrapped = wrap_caption(text)
        if not wrapped:
            return
        color = color_for(self._style, "highlight")
        text_id = self._canvas.create_text(
            self._screen_width / 2, self._screen_height - BOTTOM_MARGIN_PX,
            text=wrapped, anchor="s", justify="center",
            fill=color, font=caption_font(self._style), tags=CAPTION_TAG,
        )
        bounds = self._canvas.bbox(text_id)
        if bounds is None:  # an unmeasured fake — text alone is still correct
            return
        bx1, by1, bx2, by2 = bounds
        plate_id = self._canvas.create_polygon(
            round_rect_points(
                bx1 - CAPTION_PAD_PX, by1 - CAPTION_PAD_PX // 2,
                bx2 + CAPTION_PAD_PX, by2 + CAPTION_PAD_PX // 2,
                radius=CAPTION_PAD_PX,
            ),
            smooth=True, fill=self._style.label_plate, outline=color,
            tags=CAPTION_TAG,
        )
        self._canvas.tag_lower(plate_id, text_id)  # plate under the text

    def clear(self) -> None:
        """Erase ONLY the caption items (audio finished / hide-ghosting path /
        a dead sentence) AND cancel every pending show_text_later — a wiped
        bar must never resurrect stale speech text. A no-op when nothing is
        shown; the other layers are never touched."""
        self._generation += 1
        self._canvas.delete(CAPTION_TAG)


__all__ = ["CaptionBar", "CAPTION_TAG", "wrap_caption",
           "BOTTOM_MARGIN_PX", "MAX_CHARS_PER_LINE", "MAX_LINES"]
