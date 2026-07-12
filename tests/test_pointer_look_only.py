"""
test_pointer_look_only.py — enforces the LOOK-only boundary for the animated
pointer at the SOURCE level: the overlay package may READ the OS cursor
(GetCursorPos) but must NEVER move, warp, or click it (SetCursorPos / mouse_event
/ SendInput / ClipCursor). Moving the real mouse would be AUTOPILOT, gated behind
an explicit phase — it must not leak into the LOOK overlay.

The scan walks each module's AST and inspects only Attribute/Name nodes, so it
catches real code usage (e.g. user32.SetCursorPos) while IGNORING the same names
where they appear inside docstrings/comments documenting the boundary. A source
scan (not a behavioural test) can't be fooled by a code path a test happens not
to hit.

Run:  set PYTHONPATH=src && python -m pytest tests/test_pointer_look_only.py -q
"""

from __future__ import annotations

import ast
import pathlib

OVERLAY_DIR = (
    pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis" / "overlay"
)

# Win32 APIs that MOVE / WARP / CLICK / CONFINE the real cursor — forbidden in LOOK.
FORBIDDEN_MOUSE_APIS = {"SetCursorPos", "mouse_event", "SendInput", "ClipCursor"}


def _overlay_sources():
    files = sorted(OVERLAY_DIR.glob("*.py"))
    assert files, f"no overlay sources found under {OVERLAY_DIR}"
    return files


def _identifiers_used(path):
    """Every attribute access (.foo) and bare name (foo) used as CODE in the file —
    string/comment occurrences are not AST Attribute/Name nodes, so they're skipped."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.Name):
            used.add(node.id)
    return used


def test_overlay_never_uses_an_os_mouse_move_api():
    offenders = []
    for path in _overlay_sources():
        used = _identifiers_used(path)
        for api in FORBIDDEN_MOUSE_APIS & used:
            offenders.append(f"{path.name}: {api}")
    assert not offenders, f"LOOK-only violation — OS mouse-move API used: {offenders}"


def test_overlay_reads_the_cursor_via_getcursorpos_only():
    # The ONE permitted cursor interaction is the read-only GetCursorPos used as
    # the glide's start point. Assert it's present as real code (an Attribute, not
    # just a docstring mention) — paired with the forbidden-setter test, the
    # boundary is provably "read, never move".
    used_anywhere = set()
    for path in _overlay_sources():
        used_anywhere |= _identifiers_used(path)
    assert "GetCursorPos" in used_anywhere
