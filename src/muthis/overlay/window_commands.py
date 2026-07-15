# src/muthis/overlay/window_commands.py
"""
The overlay command dispatcher, extracted WHOLE from sidekick_window.py
(v6 Phase C0, Law §17.4: split, don't compress — sidekick_window sat at 299
lines, one under the ceiling, and Phase C/D need queue commands there).

Pure with respect to Tk: `dispatch_command` only calls the injected view
objects (rect / pointer / animator / shapes / status), so it is unit-tested
with fakes — no window, no mouse. The real SidekickOverlay._drain delegates
here from inside the Tk mainloop; sidekick_window re-exports both names so
every existing import path keeps working.
"""

from __future__ import annotations


def _bbox_center(bbox: tuple[int, int, int, int]) -> tuple[int, int]:
    """The CENTER of a PHYSICAL bbox — the point the gliding pointer aims at."""
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def dispatch_command(command: tuple, *, rect, pointer, animator, shapes=None,
                     status=None, caption=None, dimmer=None,
                     spotlight_on=True) -> bool:
    """Apply one overlay command to the view objects. Returns False iff the
    overlay should stop ("close"), True otherwise.

    `shapes` (ShapesWidget), `status` (StatusIndicator), `caption`
    (CaptionBar, v6 C) and `dimmer` (FocusDimmer, v6 D) are OPTIONAL so the
    pre-existing call sites/tests keep working — absent → their commands no-op.
    `spotlight_on` (v7 Phase 2) decouples the two dim features: the WHITEBOARD
    (default ON) builds the dimmer window, but a highlight dims around its
    bbox only when the SPOTLIGHT flag (MUTHIS_FOCUS_DIM, default OFF) is on —
    default True so pre-whiteboard call sites keep the v6 behavior."""
    action = command[0]
    if action == "close":
        animator.cancel()
        return False
    if action == "show":
        bbox, label_ar = command[1], command[2]
        center = _bbox_center(bbox)

        # Fresh highlight: drop any prior rectangle, pointer, and in-flight glide,
        # then glide the drawn arrow to the bbox CENTER. NOTHING is drawn now — the
        # rectangle is deferred to ARRIVAL (the audio-sync: motion starts with the
        # audio; the rectangle lands as the glide finishes).
        animator.cancel()
        rect.clear()
        pointer.clear()
        # Cinematic spotlight (v6 D, highlight ONLY — a flat draw_shapes keeps
        # its full-context screen): dim everything but the target as the glide
        # begins, so the spotlight forms WITH the audio (Option A untouched).
        # Gated by spotlight_on: a dimmer built FOR the whiteboard must not
        # re-enable the default-OFF spotlight.
        if dimmer is not None and spotlight_on:
            dimmer.show_around(bbox)

        def _on_arrival() -> None:
            # On arrival: draw the cyan rectangle, then re-draw the pointer ON TOP
            # so BOTH stay visible until auto-hide.
            rect.draw(bbox, label_ar)
            pointer.move_to(*center)

        animator.start(center, _on_arrival)
    elif action == "draw_shapes":
        # Geometric LOOK shapes (Phase A): replace the drawn shape list. The
        # highlight path above is untouched — shapes live on their own tag.
        if shapes is not None:
            shapes.draw(command[1])
    elif action == "dim_screen":
        # WHITEBOARD (v7 Phase 2): full-screen dim (no hole, smooth fade-in)
        # behind a concept drawing — the shapes glow above it (D0 z-order).
        if dimmer is not None:
            dimmer.show_full()
    elif action == "undim_screen":
        # Lights back on at SPEECH END (run_turn's finally) — smooth fade-out;
        # the ghosting "hide" below stays INSTANT and also covers the dim.
        if dimmer is not None:
            dimmer.fade_out()
    elif action == "set_state":  # 2-A: recolor the state light (halo + dot)
        if status is not None:
            status.set_state(command[1])
    elif action == "clear_status_light":  # 2-B ghosting: drop the corner dot
        if status is not None:
            status.clear_status_light()
    elif action == "show_caption":  # v6 C: the live-captions bar
        if caption is not None:
            caption.show_text(command[1])
    elif action == "show_caption_later":  # v7 Phase 2: audio-paced caption
        if caption is not None:
            caption.show_text_later(command[1], command[2])
    elif action == "clear_caption":
        if caption is not None:
            caption.clear()
    elif action == "hide":
        # Ghosting path: kill any in-flight glide and clear the pointer, the
        # rectangle, the shapes AND the caption bar, so no frame — and no
        # readable self-text — survives into the next capture.
        animator.cancel()
        pointer.clear()
        rect.clear()
        if shapes is not None:
            shapes.clear()
        if caption is not None:
            caption.clear()
        if dimmer is not None:  # ghosting: a capture never sees a dimmed screen
            dimmer.hide()
    return True


__all__ = ["dispatch_command", "_bbox_center"]
