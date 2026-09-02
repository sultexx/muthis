# tests/test_reader_truncation_honesty.py
"""
A TRUNCATED READ NOW SAYS SO — on BOTH surfaces (DEC-117).

THE DEFECT, MEASURED BEFORE IT WAS FIXED. `_numbered_slice` capped the body and
returned `start`/`end`/`total` UNADJUSTED, so `end` was the range REQUESTED and
never the range DELIVERED. Two consumers read that one value:

  · the DEC-61 log line — `read .py bytes=17467 lines 1-293 of 293` on a file
    whose payload stopped at 243;
  · the Arabic header the MODEL reads — «(الأسطر 1-293 من 293)» on that same
    payload, immediately above a truncation note saying it had been cut.

**IT WAS WRONG ON EXACTLY THE FILES THAT MATTER MOST.** Driven over the ten
pinned modules: accurate on the two that fit whole (`persona.py` 209,
`deferral_notes.py` 207) and wrong on all EIGHT that truncate — 257 of 300 for
`tool_router`, 243 of 293 for `turn_pass`, 218 of 244 for `persona_laws`. A log
that is right only when nothing interesting happened is worse than no log.

AND THE HEADER HALF IS DEC-55'S DEFECT IN A NEW PLACE. Two MODEL-FACING surfaces
disagreed inside one payload — a header claiming the whole file, a note saying it
was cut — and DEC-55 measured at T7 that a model reading two rules that conflict
resolves them unpredictably, because it reads LINEARLY. This was told to the
model on EVERY truncated read.

WHAT THIS FILE ASSERTS, AND WHY IN THIS SHAPE. The delivered end is parsed from
the PAYLOAD ITSELF — the last numbered line — never from the value under test, so
the assertion cannot agree with the code by construction. The real-tree scan
carries a POSITIVE CONTROL (at least one pinned file must actually truncate), or
it would pass while examining nothing. The DEC-61 check carries its own control
too: the canary name and directory must be present in what we PASSED IN, or
"absent from the log" proves nothing.

Run:  set PYTHONDONTWRITEBYTECODE=1 && set PYTHONPATH=src && python -m pytest tests/test_reader_truncation_honesty.py -q
"""

from __future__ import annotations

import logging
import pathlib
import re

import pytest

from muthis.file_reader import MAX_RETURN_CHARS, FileReader, TRUNCATION_NOTE_AR

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis"

# The eleven pinned modules (test_module_line_ceiling.py is the authority on
# the list; this file only reads them). IT MUST BE UPDATED IN THE SAME COMMIT
# as the authority: this copy sat at TEN for the whole of DEC-117, omitting
# `file_reader.py`, so the one file the reader defect was measured ON was the
# one this scan never read. Two homes for one fact drift; this is the drift.
PINNED = (
    "kernel/tool_router.py", "kernel/orchestrator.py", "turn_voice.py",
    "persona.py", "persona_laws.py", "overlay/sidekick_window.py",
    "composition.py", "kernel/turn_pass.py", "trust/confirm_gate.py",
    "kernel/deferral_notes.py", "file_reader.py",
)

NUMBERED = re.compile(r"^\s*(\d+) \| ", re.M)
HEADER = re.compile(r"\(الأسطر (\d+)-(\d+) من (\d+)\)")
LOGGED = re.compile(r"lines (\d+)-(\d+) of (\d+)")


def delivered_end(payload: str) -> int:
    """The last line the payload ACTUALLY carries, parsed from the payload. The
    map is appended AFTER the note, so the code half is everything before it."""
    code = payload.split(TRUNCATION_NOTE_AR)[0]
    nums = NUMBERED.findall(code)
    return int(nums[-1]) if nums else 0


def read_line(caplog) -> str:
    lines = [r.getMessage() for r in caplog.records if "] read " in r.getMessage()]
    assert len(lines) == 1, f"expected exactly one read line, got {lines}"
    return lines[0]


def long_file(tmp_path, rows: int = 400, width: int = 60) -> pathlib.Path:
    target = tmp_path / "long.py"
    target.write_text("\n".join(f"# {i:04} " + "x" * width for i in range(1, rows + 1)),
                      encoding="utf-8")
    return target


# ─── The log line ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_truncated_read_LOGS_the_delivered_end(tmp_path, caplog):
    """THE FIX. The logged end is what came back, not what was asked for."""
    target = long_file(tmp_path)

    with caplog.at_level(logging.INFO, logger="muthis.file_reader"):
        out = await FileReader().read({"path": str(target)})

    assert TRUNCATION_NOTE_AR in out, "the fixture did not truncate — widen it"
    start, end, total = (int(g) for g in LOGGED.search(read_line(caplog)).groups())
    assert (start, total) == (1, 400)
    assert end == delivered_end(out), (
        f"the log claims line {end} was delivered; the payload stops at "
        f"{delivered_end(out)} — the line is lying about truncation again")
    assert end < total, "a truncated read must log an end BELOW the total"


# ─── The model-facing header ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_truncated_read_HEADERS_the_delivered_end(tmp_path):
    """The other half, and the one the MODEL reads."""
    out = await FileReader().read({"path": str(long_file(tmp_path))})

    start, end, total = (int(g) for g in HEADER.search(out).groups())
    assert (start, total) == (1, 400)
    assert end == delivered_end(out), (
        f"the header announces lines {start}-{end}; the payload stops at "
        f"{delivered_end(out)} — the model is told it has code it never got")


@pytest.mark.asyncio
async def test_the_header_and_the_truncation_note_do_not_CONTRADICT(tmp_path):
    """DEC-55's defect, guarded where it appeared. A payload may not carry a
    note saying it was cut ABOVE a header saying nothing was."""
    out = await FileReader().read({"path": str(long_file(tmp_path))})

    assert TRUNCATION_NOTE_AR in out
    _, end, total = (int(g) for g in HEADER.search(out).groups())
    assert end < total, (
        "the note says the file was cut and the header says the whole range "
        "was delivered — two model-facing surfaces disagreeing in one payload")


# ─── The negative controls: the untruncated paths are UNCHANGED ──────────────

@pytest.mark.asyncio
async def test_a_whole_file_read_is_unchanged(tmp_path, caplog):
    target = tmp_path / "small.py"
    target.write_text("a = 1\nb = 2\nc = 3", encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="muthis.file_reader"):
        out = await FileReader().read({"path": str(target)})

    assert TRUNCATION_NOTE_AR not in out
    assert "الأسطر 1-3 من 3" in out
    assert LOGGED.search(read_line(caplog)).groups() == ("1", "3", "3")


@pytest.mark.asyncio
async def test_an_explicit_range_is_unchanged(tmp_path):
    """A range read that fits reports the RANGE — the fix touches only the
    branch that actually cut something."""
    target = tmp_path / "ranged.py"
    target.write_text("\n".join(f"line {i}" for i in range(1, 21)), encoding="utf-8")

    out = await FileReader().read({"path": str(target), "start_line": 5, "end_line": 9})

    assert HEADER.search(out).groups() == ("5", "9", "20")
    assert delivered_end(out) == 9


@pytest.mark.asyncio
async def test_a_TRUNCATED_range_read_reports_where_it_actually_stopped(tmp_path):
    """`start` is not 1 here, so this proves the arithmetic is `start + count`
    and not a disguised `1 + count`."""
    target = long_file(tmp_path, rows=800)

    out = await FileReader().read({"path": str(target), "start_line": 300})

    start, end, total = (int(g) for g in HEADER.search(out).groups())
    assert (start, total) == (300, 800)
    assert end == delivered_end(out) and 300 < end < 800


# ─── The real tree, with the control that stops the scan being vacuous ───────

@pytest.mark.asyncio
async def test_every_pinned_file_reports_honestly_and_at_least_one_TRUNCATES():
    """The population this defect was measured on. The POSITIVE CONTROL is the
    second assertion: if no pinned file truncated, the first would pass over an
    empty condition and prove nothing."""
    reader = FileReader()
    truncated = []
    for rel in PINNED:
        out = await reader.read({"path": str(SRC / rel)})
        _, end, _ = (int(g) for g in HEADER.search(out).groups())
        assert end == delivered_end(out), f"{rel}: header {end} vs payload {delivered_end(out)}"
        if TRUNCATION_NOTE_AR in out:
            truncated.append(rel)

    assert truncated, (
        "NOT ONE pinned file truncated — the reader cap or the ≤300 law moved, "
        "and this scan is now examining nothing (DEC-112's ~242-line ceiling)")


# ─── DEC-61, with its own control ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_read_line_carries_no_filename_and_no_path(tmp_path, caplog):
    """DEC-61: extension, outcome and size — never the path, never the name.
    The CONTROL is that the canary strings are genuinely in what we passed in,
    so 'absent from the log' is a finding rather than an empty search."""
    folder = tmp_path / "CANARYDIR"
    folder.mkdir()
    target = folder / "CANARYNAME.py"
    target.write_text("\n".join(f"row = {i}" for i in range(400)), encoding="utf-8")

    assert "CANARYDIR" in str(target) and "CANARYNAME" in str(target)  # control

    with caplog.at_level(logging.INFO, logger="muthis.file_reader"):
        await FileReader().read({"path": str(target)})

    line = read_line(caplog)
    assert "CANARYNAME" not in line and "CANARYDIR" not in line
    assert "\\" not in line and "/" not in line, f"a path separator reached the log: {line}"
    assert ".py" in line and "bytes=" in line, "the DEC-61 shape (extension + size) is gone"


# ─── The declared boundary ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ONE_line_longer_than_the_whole_cap(tmp_path):
    """A single line that overruns the cap by itself: `rsplit` finds no newline,
    so the delivered end is the START line — partially delivered, and reported
    as the one line it is rather than as a range the payload lacks. Declared
    here so the behaviour is a decision and not an accident."""
    target = tmp_path / "minified.py"
    target.write_text("x" * (MAX_RETURN_CHARS * 2) + "\nsecond = 1", encoding="utf-8")

    out = await FileReader().read({"path": str(target)})

    assert TRUNCATION_NOTE_AR in out
    assert HEADER.search(out).groups() == ("1", "1", "2")
