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


def dispatch_command(command: tuple, *, rect, pointer, animator, shapes=None, status=None) -> bool:
    """Apply one overlay command to the view objects. Returns False iff the
    overlay should stop ("close"), True otherwise.

    `shapes` (ShapesWidget) and `status` (StatusIndicator) are OPTIONAL so the
    pre-existing call sites/tests keep working — absent → their commands no-op."""
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
    elif action == "set_state":  # 2-A: recolor the state light (halo + dot)
        if status is not None:
            status.set_state(command[1])
    elif action == "clear_status_light":  # 2-B ghosting: drop the corner dot
        if status is not None:
            status.clear_status_light()
    elif action == "hide":
        # Ghosting path: kill any in-flight glide and clear the pointer, the
        # rectangle, AND the shapes, so no frame survives into the next capture.
        animator.cancel()
        pointer.clear()
        rect.clear()
        if shapes is not None:
            shapes.clear()
    return True


__all__ = ["dispatch_command", "_bbox_center"]
