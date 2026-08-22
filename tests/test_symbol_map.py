# tests/test_symbol_map.py
"""
THE SYMBOL MAP — attached ON TRUNCATION ONLY (DEC-113, Phase 4A).

WHAT IS BEING GUARDED IS A RULING, NOT A FEATURE. The map was MEASURED in both
regimes: on a truncated file it took the model 3/9 → 9/9 on structural questions
and 0/6 → 6/6 on grounding; on WHOLE files it TIED (four of five fixtures at
35/36 vs 35/36) and one fixture got WORSE, because a table can be misread where
raw text has no such mode. So "truncation only" is the decision, and the tests
below assert the ABSENCE of a map at least as hard as its presence.

DRIVEN THROUGH THE REAL `FileReader`, NEVER `build_symbol_map` ALONE. A suite
that only exercised the builder would stay green with the attach site deleted —
the map would be perfectly correct and never reach the model. Every attachment
test therefore goes through `FileReader().read()` with a real file on disk.

THE ABSENCE IS STRUCTURAL AND THAT IS ASSERTED TOO. The map is built inside the
branch that has already decided to truncate, so there is no whole-file code path
into it. `test_the_ruling_is_enforced_by_STRUCTURE` reads the source and asserts
the call sits in that branch — because a test proving the OUTCOME would still
pass if someone re-implemented the ruling as an `if` that a later reader could
delete as redundant.

Run:  set PYTHONDONTWRITEBYTECODE=1 && set PYTHONPATH=src && python -m pytest tests/test_symbol_map.py -q
"""

from __future__ import annotations

import asyncio
import pathlib

import pytest

from muthis.file_reader import TRUNCATION_NOTE_AR, FileReader
from muthis.symbol_map import MAP_CUT_AR, MAP_HEADER_AR, MAX_MAP_CHARS, build_symbol_map

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis"

# Small enough to be delivered whole; rich enough to have a map if one were built.
WHOLE_PY = (
    "import os\n"
    "\n"
    "CAP = 5\n"
    "\n"
    "class Widget:\n"
    "    def draw(self):\n"
    "        return 1\n"
    "\n"
    "def top_level():\n"
    "    pass\n"
)

# Long enough to blow any cap the tests use.
FILLER = "x = 1\n" * 4000


def _read(path: pathlib.Path, **kwargs) -> str:
    return asyncio.run(FileReader(**kwargs).read({"path": str(path)}))


def _write(directory: pathlib.Path, name: str, text: str) -> pathlib.Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    target.write_text(text, encoding="utf-8")
    return target


# ─── The map arrives where it was measured to win ───────────────────────────

def test_a_truncated_python_file_CARRIES_the_map(tmp_path):
    """The one regime the map was ruled for."""
    out = _read(_write(tmp_path, "big.py", WHOLE_PY + FILLER), max_chars=2_000)

    assert TRUNCATION_NOTE_AR.strip() in out, "the fixture did not truncate — test is void"
    assert MAP_HEADER_AR in out


def test_the_map_describes_the_WHOLE_file_including_what_was_NOT_delivered():
    """THE ENTIRE POINT, and it is measurable on this repo's own worst case.

    `turn_pass.py`'s `consume` runs 139-290 and the reader stops at 243, so its
    END IS NEVER DELIVERED. Before the map the model had no way to know that
    function continued at all; a map that only described the delivered head
    would be an expensive restatement of text already present."""
    out = _read(SRC / "kernel" / "turn_pass.py")

    assert TRUNCATION_NOTE_AR.strip() in out, "turn_pass.py no longer truncates — re-pick the fixture"
    assert "consume 139-290" in out
    delivered_tail = out.split(MAP_HEADER_AR)[0]
    assert "   290 |" not in delivered_tail, "line 290 WAS delivered — the fixture stopped truncating"


def test_the_map_is_APPENDED_after_the_cap_so_the_payload_GROWS(tmp_path):
    """A DECISION POINT, NOT A FREE LUNCH — asserted so nobody 'optimises' it
    into displacing code lines, which would pay for the map with exactly the
    content the map exists to compensate for."""
    # The SAME bytes read twice — once as `.py`, once as `.txt`. Only the map may
    # differ; the first line is dropped from both because it names the file.
    source = WHOLE_PY + FILLER
    with_map = _read(_write(tmp_path, "a.py", source), max_chars=2_000)
    without_map = _read(_write(tmp_path, "a.txt", source), max_chars=2_000)

    delivered_with = with_map.split("\n", 1)[1]
    delivered_without = without_map.split("\n", 1)[1]

    assert len(with_map) > len(without_map), "the map displaced code instead of growing the payload"
    assert delivered_with.startswith(delivered_without), (
        "the map changed the delivered code — it must only be APPENDED after the cap")
    assert delivered_with[len(delivered_without):] == "\n" + build_symbol_map(source), (
        "the appended tail is not exactly the map")


# ─── The absences — each of these is the ruling ─────────────────────────────

def test_a_WHOLE_python_file_gets_NO_map(tmp_path):
    """THE RULING. On whole files the map measured a TIE and one REGRESSION, so
    attaching it always would spend tokens to buy nothing and import a failure
    mode raw text does not have."""
    out = _read(_write(tmp_path, "small.py", WHOLE_PY))

    assert TRUNCATION_NOTE_AR.strip() not in out, "the fixture truncated — test is void"
    assert MAP_HEADER_AR not in out
    assert "Widget" not in out.split("محتوى الملف")[0]


def test_a_truncated_NON_python_file_gets_NO_map(tmp_path):
    """`ast` has nothing to say about SQL, config or prose."""
    for name in ("a.txt", "a.sql", "a.md", "a.cfg"):
        out = _read(_write(tmp_path, name, WHOLE_PY + FILLER), max_chars=2_000)

        assert TRUNCATION_NOTE_AR.strip() in out, f"{name} did not truncate — test is void"
        assert MAP_HEADER_AR not in out, f"{name} received a python symbol map"


def test_an_UNPARSEABLE_python_file_DEGRADES_and_never_raises(tmp_path):
    """LOAD-BEARING. A file mid-edit is routinely unparseable — an unclosed paren
    between keystrokes is the ordinary state of a file someone is working in,
    which is exactly when they ask about it. The reader must return precisely
    what it returned before the map existed."""
    for broken in ("def f(:\n", "class A(\n", "    indented = 1\n", "def f():\nreturn\n"):
        out = _read(_write(tmp_path, "broken.py", broken + FILLER), max_chars=2_000)

        assert MAP_HEADER_AR not in out
        assert TRUNCATION_NOTE_AR.strip() in out, "the read stopped working, not just the map"


def test_a_truncated_python_file_with_NO_symbols_gets_no_empty_header(tmp_path):
    """A header over an empty list is pure cost."""
    out = _read(_write(tmp_path, "flat.py", FILLER), max_chars=2_000)

    assert MAP_HEADER_AR not in out


# ─── The ruling is STRUCTURAL, not a deletable check ────────────────────────

def test_the_ruling_is_enforced_by_STRUCTURE_not_by_a_condition():
    """A check can be removed by someone who believes it redundant; a missing
    code path cannot. The map call must sit INSIDE the truncation branch."""
    reader = (SRC / "file_reader.py").read_text(encoding="utf-8")

    assert reader.count("_truncation_map(") == 2, (
        "the map is attached at more than one site — 'truncation only' stops "
        "being provable from the structure")
    branch = reader.index("if len(body) > self._max_chars:")
    call = reader.index("+ _truncation_map(text, suffix)")
    ret = reader.index("return body, start, end, total")
    assert branch < call < ret, "the map is attached outside the truncation branch"


def test_the_map_module_holds_NO_attachment_policy():
    """The builder answers 'what are this file's symbols'. WHEN to attach is the
    reader's decision and lives in one place — so a second caller cannot acquire
    a different policy by reading this module."""
    mapper = (SRC / "symbol_map.py").read_text(encoding="utf-8")

    assert "max_chars" not in mapper
    assert ".py" not in mapper.split('"""')[2], "the builder decides suffix policy — the reader must"


# ─── The builder's own contract ─────────────────────────────────────────────

@pytest.mark.parametrize("text", ["", "\n\n\n", "# only a comment\n", "x = 1\n"])
def test_build_returns_None_when_there_is_nothing_worth_saying(text):
    assert build_symbol_map(text) is None


def test_build_returns_None_rather_than_raising_on_garbage():
    for text in ("def f(:", "\x00\x01", "class", "if True\n    pass"):
        assert build_symbol_map(text) is None


def test_the_map_names_classes_methods_functions_and_CONSTANTS():
    body = build_symbol_map(WHOLE_PY)

    assert "class    Widget 5-7" in body
    assert "method draw 6-7" in body
    assert "def      top_level 9-10" in body
    assert "constants: CAP" in body
    assert "os" not in body.replace("top_level", ""), "imports are not symbols the model can ask for"


def test_async_functions_are_mapped_like_functions():
    body = build_symbol_map("async def go():\n    return 1\n")

    assert "def      go 1-2" in body


def test_the_appended_map_is_BOUNDED():
    """The reader bounds its own size twice; it must not then append something
    unbounded. A 2 MB file of one-line defs is inside `MAX_FILE_BYTES`."""
    body = build_symbol_map("".join(f"def f{i}():\n    pass\n" for i in range(20_000)))

    assert len(body) < MAX_MAP_CHARS + len(MAP_HEADER_AR) + len(MAP_CUT_AR) + 8
    assert MAP_CUT_AR in body, "the map was silently cut with nothing telling the model so"


def test_lowercase_module_globals_are_NOT_reported_as_constants():
    body = build_symbol_map("CAP = 1\nhelper = 2\ndef f():\n    pass\n")

    assert "constants: CAP" in body
    assert "helper" not in body
