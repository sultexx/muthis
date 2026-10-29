"""
test_instruction_registry.py — what holds the SHADOW registry honest while it is
a second source (DEC-157 ①; `src/muthis/instructions/__init__.py`).

  1. EQUALITY: the registry renders to production's composed prompt byte for byte
     at five screen sizes, and the sizes change the rendered length, so this is
     not one comparison run five times.
  2. THE TEN PREFIX ANCHORS, read from the persona tests where they are pinned
     (never copied here), all match the rendering.
  3. THE FRAME: every byte is an entry's text or a separator, in DEC-139's cut.
  4. THE MANIFEST: one row per entry, each hash and length its entry's, each row
     citing a DEC or marked pre-ledger. (Whether each cited DEC resolves to a
     ledger heading was checked at genesis, not here: a test that reads
     DECISIONS.md is a decision the design left to Sultan.)
  5. COVERAGE: len(laws) - len(guarded) == len(EXEMPT), and every guard passes on
     its own entry (check 1 of the meta-test, for every entry at once).
  6. NOT WIRED: nothing in `src/` outside the package imports it.

Run:  set PYTHONPATH=src && python -m pytest tests/test_instruction_registry.py -q
"""

from __future__ import annotations

import ast
import collections
import hashlib
import json
import pathlib

import pytest

from muthis.instructions import guard as G
from muthis.instructions import render as R
from muthis.persona import build_saudi_persona_prompt

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIZES = [(1280, 720), (1280, 800), (1024, 768), (1920, 1080), (7, 12345)]
REG = R.load()
MANIFEST = json.loads(R.MANIFEST.read_text(encoding="utf-8"))
ENTRIES = REG["entries"]


@pytest.mark.parametrize("width,height", SIZES)
def test_the_registry_renders_production_byte_for_byte(width, height):
    assert R.render(REG, width, height) == build_saudi_persona_prompt(width, height)


def test_the_sizes_reach_the_template():
    """C011 is the only entry that varies; if the sizes all rendered to one
    length, the five comparisons above would be one comparison."""
    assert len({len(R.render(REG, w, h)) for w, h in SIZES}) >= 2
    assert [e["id"] for e in ENTRIES if e.get("template")] == ["C011"]


def _anchors() -> dict[tuple[int, str], list[str]]:
    """Every (chars, sha256) pair pinned at module level in a persona test,
    read by AST so the values stay where they are pinned."""
    found = collections.defaultdict(list)
    for path in sorted((ROOT / "tests").glob("test_persona_*.py")):
        consts = {}
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                try:
                    consts[node.targets[0].id] = ast.literal_eval(node.value)
                except ValueError:
                    continue
        for name, value in consts.items():
            chars = consts.get(name[:-len("_SHA256")] + "_CHARS")
            if name.endswith("_SHA256") and isinstance(chars, int):
                found[(chars, value)].append(path.name)
    return found


def test_all_ten_prefix_anchors_match_the_rendered_output():
    anchors = _anchors()
    assert len(anchors) == 10, f"expected the ten prefix anchors, found {sorted(anchors)}"
    rendered = R.render(REG, 1280, 720)      # the size every anchor was pinned at
    for (chars, sha), where in anchors.items():
        assert hashlib.sha256(rendered[:chars].encode()).hexdigest() == sha, (
            f"the anchor at {chars} chars ({where}) does not match the registry")


def test_every_byte_is_an_entry_or_a_separator():
    assert [e["id"] for e in ENTRIES] == [f"C{n:03}" for n in range(1, 107)]
    assert all("\n" not in e["text"] for e in ENTRIES)
    assert collections.Counter(e["after"] for e in ENTRIES) == {"\n": 83, "\n\n": 21, "\n\n\n": 1, "": 1}
    assert collections.Counter(e["kind"] for e in ENTRIES) == {"bullet": 82, "heading": 24}
    # The one EMPTY separator is today's text, reproduced, not fixed here: the
    # last navigator bullet runs straight into the code laws' heading.
    assert [e["id"] for e in ENTRIES if e["after"] == ""] == ["C098"]


def test_the_manifest_has_one_row_per_entry():
    rows = MANIFEST["rows"]
    assert [r["id"] for r in rows] == [e["id"] for e in ENTRIES]
    assert [r["order"] for r in rows] == list(range(1, len(ENTRIES) + 1))
    for row, entry in zip(rows, ENTRIES):
        assert row["sha256"] == hashlib.sha256(entry["text"].encode()).hexdigest(), row["id"]
        assert row["chars"] == len(entry["text"]), row["id"]
        assert row["cites"] or row["pre_ledger"], f"{row['id']} cites no DEC and is not pre-ledger"
    assert MANIFEST["frame_sha256"] == hashlib.sha256(
        json.dumps([e["after"] for e in ENTRIES]).encode()).hexdigest()
    for size, sha in MANIFEST["composed_sha256"].items():
        w, h = map(int, size.split("x"))
        assert hashlib.sha256(R.render(REG, w, h).encode()).hexdigest() == sha, size
    # The execute-first law has no ruling entry (DEC-139 ⑦): recorded, never hidden.
    assert [r["id"] for r in rows if r["no_ruling"]] == [f"C{n:03}" for n in range(72, 78)]


EXEMPT = {e["id"]: e["exempt"] for e in ENTRIES if "exempt" in e}
GUARDED = [e for e in ENTRIES if "required" in e]


def test_the_coverage_guard_every_entry_is_guarded_or_exempt_with_a_reason():
    assert len(ENTRIES) - len(GUARDED) == len(EXEMPT)
    assert not {e["id"] for e in GUARDED} & set(EXEMPT)
    assert all(reason.strip() for reason in EXEMPT.values())
    empty = [e["id"] for e in GUARDED if not e["required"]]
    assert not empty, f"guarded entries that declare no required family: {empty}"


@pytest.mark.parametrize("entry", GUARDED, ids=[e["id"] for e in GUARDED])
def test_every_guard_passes_on_its_own_entry(entry):
    verdict = G.guard_for(entry)(R.entry_text(entry, 1280, 720))
    assert verdict.ok, f"{entry['id']}: missing {verdict.missing}, forbidden {verdict.forbidden}"


def test_the_delimiter_family_is_derived_from_its_home_and_equals_the_web_law_markers():
    tree = ast.parse((ROOT / "tests" / "test_persona_web_laws.py").read_text(encoding="utf-8"))
    markers = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and getattr(n.targets[0], "id", None) == "DELIMITER_MARKERS")
    assert set(G.delimiter_members()) == set(markers)


def test_nothing_in_the_app_imports_the_registry():
    """SHADOW, not MOVE: production composes from the persona modules alone."""
    package = ROOT / "src" / "muthis" / "instructions"
    importers = []
    for path in (ROOT / "src").rglob("*.py"):
        if package in path.parents:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            if any(n == "muthis.instructions" or n.startswith("muthis.instructions.") for n in names):
                importers.append(path.relative_to(ROOT).as_posix())
    assert not importers, f"the shadow registry is imported by {importers}"
