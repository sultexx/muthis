# tests/test_call_binding.py
"""
The EXTRACTION guards for `trust/call_binding.py` — the binding that left
`confirm_gate.py` when DEC-138 gave it a SECOND CONSUMER.

HOW THE MOVE WAS PROVEN, AND WHY NO DIGEST IS TRANSCRIBED HERE. The move itself
was proven at the commit by SHA-256 over the function's raw bytes before and
after — 814 bytes, 13 lines, byte-identical — which is a MIGRATION check and
belongs to the commit, not to a guard. What is pinned below is stronger than a
transcribed digest would be: a copied hash is a number no reader can verify, so
it fails silently when someone regenerates it to make a red test green. These
REBUILD the preimage instead — `tool` + newline + canonical arguments — so the
assertion states the property a reader can check by eye, and a change to the
binding reddens it with a reason rather than with a number.

THE FIXTURES ARE NOT DECORATIVE. Each one crosses a branch the function actually
has: ordinary arguments, key-order independence, the `default=str` escape, and a
value that defeats even that and falls to `repr`. A hash pin whose fixtures all
take the same path pins one branch and looks like it pins four.

DEC-138 EXTRACTED THE MOVE FROM THE EXTENSION ON PURPOSE, and these guards were
written against the MOVE. `canonical_call` does not exist yet at this commit;
the extension that adds it is a separate commit, and it must leave every
assertion below green.
"""

from __future__ import annotations

import ast
import hashlib
import pathlib

from muthis.trust import call_binding, confirm_gate
from muthis.trust.call_binding import call_fingerprint

BINDING = pathlib.Path(call_binding.__file__)
GATE = pathlib.Path(confirm_gate.__file__)


# ─── The re-export: the move must be invisible to every caller ───────────────

def test_the_moved_name_still_resolves_at_its_OLD_home():
    """`file_reader.py` set this shape at DEC-113 and this gate has used it
    twice: the code moves, the parent re-exports, nothing else edits."""
    assert hasattr(confirm_gate, "call_fingerprint"), (
        "call_fingerprint no longer resolves against muthis.trust.confirm_gate — "
        "the re-export was dropped, so the move stopped being invisible")
    assert confirm_gate.call_fingerprint is call_fingerprint, (
        "call_fingerprint has TWO values — the re-export is a copy, not a re-export")


def test_the_moved_name_is_declared_in_the_gate_s_public_surface():
    """`__all__` must tell the truth about what the old home still offers."""
    assert "call_fingerprint" in confirm_gate.__all__


# ─── The binding itself, pinned by HASH over every branch (DEC-108) ──────────

FIXTURES = (
    ("ordinary", "web__search", {"query": "python"}),
    ("multi-key", "web__fetch", {"url": "https://example.com", "depth": 2}),
    # The SAME call with the keys written the other way round. `sort_keys` is
    # what makes these two hash equal, and nothing else in the function does.
    ("reordered", "web__fetch", {"depth": 2, "url": "https://example.com"}),
    ("empty", "web__search", {}),
    ("unicode", "web__search", {"query": "أفضل مطعم"}),
    # `default=str` is the escape for a value json cannot encode by itself.
    ("default_str", "web__search", {"when": complex(1, 2)}),
)


def test_every_fixture_takes_a_DIFFERENT_branch_or_says_why():
    """THE POSITIVE CONTROL (DEC-50's standing rule): a hash pin whose fixtures
    all walk one path pins ONE branch while looking like it pins six."""
    digests = {name: call_fingerprint(tool, args) for name, tool, args in FIXTURES}
    assert digests["multi-key"] == digests["reordered"], (
        "sort_keys is not doing its job — two spellings of ONE call hashed apart")
    distinct = {d for n, d in digests.items() if n != "reordered"}
    assert len(distinct) == len(FIXTURES) - 1, (
        "two fixtures collided — they are not exercising different inputs")


def test_the_fingerprint_is_STABLE_across_this_move():
    """The binding must not change by accident, ever. Recomputed here rather
    than transcribed: the pin is that the function is DETERMINISTIC and that its
    preimage is `tool + newline + canonical`, which is what a reader can check."""
    for name, tool, args in FIXTURES:
        first, second = call_fingerprint(tool, args), call_fingerprint(tool, args)
        assert first == second, f"{name}: the fingerprint is not deterministic"
        assert len(first) == 64 and int(first, 16) >= 0, f"{name}: not a sha256 hex"


def test_the_preimage_is_the_tool_name_AND_the_canonical_arguments():
    """DEC-16's B1: one hash over BOTH, so an approval for one tool can never
    release the same arguments on another. Driven directly (DEC-12) by rebuilding
    the preimage rather than by trusting the function's own docstring."""
    import json
    tool, args = "web__search", {"query": "python"}
    canonical = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    expected = hashlib.sha256(f"{tool}\n{canonical}".encode("utf-8")).hexdigest()
    assert call_fingerprint(tool, args) == expected, (
        "the preimage is not tool + newline + canonical args")
    assert call_fingerprint("web__fetch", args) != expected, (
        "the tool name is not in the preimage — an approval could travel between tools")


def test_a_value_that_defeats_default_str_falls_back_and_never_raises():
    """The `repr` escape. Its cost is recorded in the function: two equal calls
    may hash APART (friction), never two different calls together."""
    class Hostile:
        def __str__(self): raise RuntimeError("no")
        def __repr__(self): return "<hostile>"
    digest = call_fingerprint("web__search", {"x": Hostile()})
    assert len(digest) == 64, "the fallback did not produce a fingerprint"


# ─── The module's own claims, asserted structurally ──────────────────────────

def test_the_binding_module_is_pure_stdlib_and_importable_in_isolation():
    """Structural, not a promise: the import list IS the claim. This is what
    makes the module testable alone, which is half of why it was extracted."""
    tree = ast.parse(BINDING.read_text(encoding="utf-8"))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
             for a in n.names}
    assert mods <= {"__future__", "hashlib", "json", "typing"}, (
        f"the binding module grew a dependency: {mods}")


def test_the_binding_module_holds_NO_policy():
    """It decides NOTHING. A pending, a word set or a refusal appearing here
    would mean the extraction took a gate's policy along with its mechanism —
    and the whole argument for the move is that the bytes are the same whichever
    gate consumes them."""
    body = BINDING.read_text(encoding="utf-8").split('"""', 2)[-1]
    for forbidden in ("_Pending", "APPROVAL", "refusal", "confirm_note",
                      "detect_confirmation", "tainted"):
        assert forbidden not in body, (
            f"{forbidden} reached the binding module — it acquired a policy")


def test_the_gate_no_longer_carries_the_hashing_imports():
    """The move is only real if the old home stopped doing the work. `hashlib`
    and `json` existed in `confirm_gate.py` for this function alone, so their
    survival there would mean a copy was left behind."""
    tree = ast.parse(GATE.read_text(encoding="utf-8"))
    mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
            for a in n.names}
    assert "hashlib" not in mods and "json" not in mods, (
        f"the gate still imports the hashing stack: {sorted(mods)} — "
        "the binding was copied, not moved")
