# tests/test_confirm_gate_notes.py
"""
The EXTRACTION guards for `trust/confirm_gate_notes.py` (the note that left
`confirm_gate.py` when that file hit 300/300).

WHAT THESE ARE FOR, AND WHAT THEY ARE NOT. The move itself was proven the DEC-108
way — by HASH of the rendered note, over every `render_args` branch, before and
after — and a hash is a MIGRATION check: it dies the moment the note is
deliberately reworded, which is the very next ruling. So it is not pinned here.
What IS pinned is the set of properties that must survive BOTH the move and the
rewording: the re-export, the three rendering branches, and the DEC-42 split that
says the security half stayed behind.

THE BRANCH TESTS CARRY THEIR OWN CONTROL. Each asserts the bound BIT, and also
that the input genuinely crossed the bound — a truncation test whose fixture is
too short passes over an empty condition and proves nothing, which is the failure
`test_reader_truncation_honesty.py` names one capability over.
"""

from __future__ import annotations

import ast
import pathlib

from muthis.trust import confirm_gate
from muthis.trust.confirm_gate_notes import (
    CONFIRM_DIRECTIVE_AR, MAX_ARGS_CHARS, MAX_ARG_CHARS, render_args,
)

NOTES = pathlib.Path(confirm_gate.__file__).parent / "confirm_gate_notes.py"
GATE = pathlib.Path(confirm_gate.__file__)

MOVED = ("CONFIRM_DIRECTIVE_AR", "MAX_ARGS_CHARS", "MAX_ARG_CHARS", "render_args")


# ─── The re-export (DEC-113's property: no import site changed) ───────────────────

def test_every_moved_name_still_resolves_at_its_OLD_home():
    """The extraction must be invisible to callers. `file_reader.py` set this
    shape at DEC-113: the notes move, the parent re-exports, nothing else edits."""
    for name in MOVED:
        assert hasattr(confirm_gate, name), (
            f"{name} no longer resolves against muthis.trust.confirm_gate — the "
            "re-export was dropped, so the move stopped being invisible")
        assert getattr(confirm_gate, name) is getattr(
            __import__("muthis.trust.confirm_gate_notes", fromlist=["x"]), name), (
            f"{name} has TWO values — the re-export is a copy, not a re-export")


def test_the_moved_names_are_declared_in_the_gate_s_public_surface():
    """`__all__` must tell the truth about what this module still offers."""
    for name in MOVED:
        assert name in confirm_gate.__all__, f"{name} re-exported but not declared"


# ─── The three rendering branches, each with its control ────────────────────────

def test_a_long_VALUE_is_truncated_and_the_cut_is_visible():
    value = "x" * (MAX_ARG_CHARS + 40)
    assert len(value) > MAX_ARG_CHARS, "fixture does not cross the bound"
    out = render_args({"query": value})
    assert "…" in out, "a value past MAX_ARG_CHARS was not marked as cut"
    assert len(out) < len(value), "nothing was actually truncated"


def test_the_WHOLE_rendering_is_bounded_even_when_each_value_is_short():
    args = {f"k{i}": "y" * 100 for i in range(8)}
    assert all(len(v) <= MAX_ARG_CHARS for v in args.values()), (
        "fixture must NOT trip the per-value bound — this is the outer bound")
    raw = sum(len(f"{k}={v}") for k, v in args.items())
    assert raw > MAX_ARGS_CHARS, "fixture does not cross the outer bound"
    assert len(render_args(args)) <= MAX_ARGS_CHARS


def test_no_arguments_renders_the_no_arguments_phrase():
    """A note must stay a sentence when the call carries nothing."""
    assert render_args({}) == "بلا معاملات"


def test_a_newline_in_a_value_never_breaks_the_note_into_lines():
    """The note is spoken; a code blob must not turn it into a transcript."""
    blob = "print(1)" + chr(10) + "print(2)"
    assert chr(10) not in render_args({"code": blob})


# ─── DEC-42: the security half stayed behind ─────────────────────────────────

def test_the_notes_module_carries_NO_security_code():
    """The message layer decides what a refusal SAYS, never whether it refuses.
    A hash, a word set or the detector appearing here would mean the extraction
    took the stronger property with the weaker one."""
    text = NOTES.read_text(encoding="utf-8")
    body = text.split('"""', 2)[-1]          # the docstring MAY discuss them
    for forbidden in ("hashlib", "sha256", "call_fingerprint", "normalize_ar",
                      "detect_confirmation", "_APPROVALS", "_REFUSALS"):
        assert forbidden not in body, (
            f"{forbidden} reached the notes module — the security boundary moved")


def test_the_notes_module_is_pure_stdlib_and_importable_in_isolation():
    """Structural, not a promise: the import list IS the claim."""
    tree = ast.parse(NOTES.read_text(encoding="utf-8"))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
             for a in n.names}
    assert mods <= {"__future__", "typing"}, f"notes module grew a dependency: {mods}"


def test_the_note_is_rendered_at_exactly_ONE_site():
    """The cluster left because it had ONE external touchpoint. If a second
    render site appears, the reason the extraction was safe has gone."""
    assert GATE.read_text(encoding="utf-8").count("CONFIRM_DIRECTIVE_AR.format(") == 1
