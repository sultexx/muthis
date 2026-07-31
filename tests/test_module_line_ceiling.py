"""
test_module_line_ceiling.py — the ≤300-line LAW, which until now had NO guard.

AGENTS.md line 418 states it: "Every module ≤ 300 lines, single responsibility,
importable in isolation (LAW — the binding form is CONTRIBUTING.md acceptance
condition 1: split, never compress)."

WHY THIS FILE EXISTS, AND WHY IT IS LATE. On 2026-07-31 `broker/docs/service.py`
crossed the law inside a single commit (285 → 314) and NOTHING NOTICED. Both
halves of the enforcement were missing at once:

  · there was no automated check anywhere in the project — the suite was fully
    green with the breach in place, because a line count is not behaviour and
    nothing was reading it;
  · and `broker/docs/` had no row in the AGENTS.md key-files table, so there was
    no declared number for the real one to drift against either.

Every OTHER ceiling in this project is held by a declared row plus review, which
is why the ones under real pressure — `tool_router.py` at 300, `orchestrator.py`
at 299, `turn_voice.py` at 300 — have held for months. A file nobody had written
a row for had neither. **A law with no guard is a law that gets breached
silently**, and this one was.

THE CHECK IS DELIBERATELY DUMB. It reads line counts. It cannot know whether a
299-line module is well factored, and it is not trying to: it enforces the one
property the law states literally, and leaves single-responsibility to review.

300 IS LEGAL, 301 IS NOT. Files sit AT the ceiling on purpose (`tool_router.py`
is 300/300 and recorded as IRREDUCIBLE), so the comparison is strictly greater.
"""

from __future__ import annotations

import pathlib

import pytest

MAX_MODULE_LINES = 300

SRC_ROOT = pathlib.Path(__file__).resolve().parent.parent / "src"


def _modules() -> "list[pathlib.Path]":
    return sorted(SRC_ROOT.rglob("*.py"))


def _line_count(path: pathlib.Path) -> int:
    """Counted the way the project declares its counts (`wc -l`)."""
    return len(path.read_text(encoding="utf-8").splitlines())


def test_the_guard_is_actually_looking_at_the_source_tree():
    """THE POSITIVE CONTROL, and it is not ceremony.

    A check with a cutoff must report what it admitted (the DEC-50 standing
    rule): a glob that silently matched nothing would make every assertion below
    pass while examining NOTHING, and would look exactly like a healthy guard.
    This is the same failure mode that let the breach through in the first
    place, so the guard is not permitted to repeat it."""
    modules = _modules()
    assert SRC_ROOT.is_dir(), f"the source tree is not where this guard looks: {SRC_ROOT}"
    assert len(modules) > 50, (
        f"only {len(modules)} module(s) found under {SRC_ROOT} — the guard is "
        "examining almost nothing, which is indistinguishable from passing")
    # The file under the most ceiling pressure must be among them, so a future
    # restructure that moves the tree cannot quietly empty this check.
    assert any(m.name == "tool_router.py" for m in modules)


def test_no_module_in_src_exceeds_the_three_hundred_line_law():
    """THE LAW ITSELF. Split, never compress — see AGENTS.md line 418."""
    offenders = [(m, n) for m in _modules() if (n := _line_count(m)) > MAX_MODULE_LINES]
    assert not offenders, "the ≤300-line LAW is breached:\n" + "\n".join(
        f"  {m.relative_to(SRC_ROOT)}: {n} lines ({n - MAX_MODULE_LINES} over) — "
        "EXTRACT a seam; compressing is forbidden by the law's own second clause"
        for m, n in offenders)


@pytest.mark.parametrize("name,ceiling", [
    ("kernel/tool_router.py", 300),
    ("kernel/orchestrator.py", 299),
    ("turn_voice.py", 300),
    ("persona.py", 209),
])
def test_the_files_at_or_near_the_ceiling_have_not_moved(name, ceiling):
    """The declared numbers, pinned.

    The law above catches a BREACH; these catch DRIFT, which is the state that
    precedes one. Each of these is recorded in AGENTS.md with an explicit
    instruction to extract before adding, and two of them are additionally
    protected from compression. A change here is not necessarily wrong — it is
    a thing that must be DECLARED, and an assertion is how it gets declared."""
    path = SRC_ROOT / "muthis" / name
    assert path.is_file(), f"a pinned file has moved or been renamed: {name}"
    assert _line_count(path) == ceiling, (
        f"{name} is {_line_count(path)} lines, declared {ceiling}. If this change "
        "is intended, update the declaration in AGENTS.md and here IN THE SAME "
        "commit — an undeclared ceiling move is how the 314-line breach happened")
