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
    # 299 -> 296, DECLARED (DEC-73 split 2). The P0 D-2 measurement found that
    # the minimum cost of ANY new injected seam here is three lines against ONE
    # of headroom, so the file could not absorb the next arrival whatever it was.
    # `TurnPrelude` is the room, bought once for a real responsibility.
    # 296 -> 298, DECLARED (T1, DEC-65): the SessionMode injection — one import
    # and one constructor parameter. The third line DEC-73 projected was an EDIT
    # of the existing `TurnPrelude(...)` call, so design C cost 2 rather than 3
    # and the file keeps two lines of headroom. Measured after the write, not
    # before: the projection was checked against the file, per the ruling.
    # 298 -> 299, DECLARED (T4, DEC-66): ONE line — the prelude passed into
    # `TurnPass`, so a mode verb can reach the ONE evaluation point. A +0 form
    # existed (packing two kwargs onto one 76-char line) and was REFUSED: a pin
    # that reads 298 because a line was stuffed is a lie in the pin, and the law
    # says split, never compress. ONE line of headroom remains.
    ("kernel/orchestrator.py", 299),
    ("turn_voice.py", 300),
    ("persona.py", 209),
    # 240 -> 285 (DEC-107 Gate 1's authoring law), and pinned by Sultan's ruling
    # for a reason the two precedents below do not carry. `persona_laws.py` had
    # NO AGENTS.md row AT ALL — `broker/docs/service.py`'s condition exactly, and
    # `trust/confirm_gate.py`'s — but this file is the worse case of the three:
    # EVERY milestone law is appended to it by design, which makes it the
    # fastest-growing module in the project, and it now has FIFTEEN lines of
    # headroom. The ≤300 law above still catches a breach; what was missing is
    # the DRIFT guard, and drift is the state that precedes one. Nothing was
    # extracted and no content moved — DECLARING it IS the change, exactly as at
    # `confirm_gate.py`. The next law needs an EXTRACTION before it needs a
    # sentence, and this pin is what will say so.
    ("persona_laws.py", 285),
    # NEWLY under pressure at T3 (DEC-65's indicator), and pinned for that
    # reason: 280 -> 296 as the overlay gained its third persistent element, and
    # 274 -> 298 as the composition root gained the DEC-37-shaped seam that
    # feeds it. Neither had a declared number before, which is exactly the state
    # `broker/docs/service.py` was in when it crossed the law in silence.
    # 296 -> 300, DECLARED (DEC-104 ruling 1, Gate A): FOUR lines — the
    # `hide_for_capture` verb, which is how the ONE hide that must NOT bring the
    # mode chip back says so. THE FILE NOW HAS ZERO HEADROOM and the next
    # arrival here needs an EXTRACTION first, not a sentence. Measured after the
    # write, and it is the gate's real cost: the alternative encoding (a keyword
    # on `hide()`) was +0 lines here and was REJECTED on measurement — it breaks
    # 20 test files' overlay fakes, which is churn in twenty places to save four
    # lines in one. Flagged to Sultan in the Gate A report, not decided quietly.
    ("overlay/sidekick_window.py", 300),
    ("composition.py", 298),
    # NEWLY under pressure at T4 (DEC-78's Navigator servicing): 271 -> 293 as
    # the mode-verb detection arm landed. Pinned HERE, in T5's first commit, by
    # Sultan's ruling — and the reason is precedent, not tidiness: an UNPINNED
    # file at 293 is exactly the state `broker/docs/service.py` was in when it
    # crossed the law in silence. Declaring it is the fix; extracting is a
    # separate decision if a later task needs the room.
    ("kernel/turn_pass.py", 293),
    # 269 -> 300 at `702f9d1` (2026-08-06), UNDECLARED, landing the file exactly
    # ON the limit — where nothing read it for thirteen days. AGENTS.md said
    # `~269`, which was TRUE WHEN WRITTEN at `1520c26` and went stale at that
    # move: the failure is a row that stopped being re-read, not a typo. Neither
    # DEC-104 gate touched this file; its docs sweep is what found it. Pinned
    # HERE, alone, by Sultan's ruling and on the `turn_pass.py` precedent — an
    # UNPINNED file at the ceiling is exactly the state `broker/docs/service.py`
    # was in when it crossed the law in silence, and this one has NO headroom at
    # all, so the next line breaches. Nothing extracted, no content touched:
    # declaring it IS the change, and extracting is a separate decision.
    ("trust/confirm_gate.py", 300),
    # 208 -> 283 in ONE gate (DEC-108 Gate 2B's three verification notes and the
    # function that chooses between them), which makes it the fastest-growing
    # module of this milestone and leaves SEVENTEEN lines. Pinned by Sultan's
    # ruling, on the `turn_pass.py` precedent — an UNPINNED file at 283 is the
    # state `broker/docs/service.py` was in when it crossed the law in silence.
    # AND THE GROWTH IS BY DESIGN, WHICH IS WHY THE PIN MATTERS HERE: this
    # module's own docstring says the note set "grows every milestone (+33
    # measured per capability)" and that separating it "puts the growth in a
    # module that exists to hold it" — a file designed to grow is exactly the one
    # whose next arrival must meet a declared number. Nothing extracted and no
    # content moved: DECLARING it IS the change, as at `confirm_gate.py` and
    # `persona_laws.py`. The next note family needs an EXTRACTION before it needs
    # a sentence.
    ("kernel/deferral_notes.py", 283),
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
