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
    # 299 -> 298, DECLARED (DEC-147 ②): the loop bound `MAX_AGENTIC_ITERATIONS`
    # moved to `highlight_gate.py`, whose final-pass brake reads it and which
    # cannot import this module — two lines out, one pointer in. TWO of headroom.
    ("kernel/orchestrator.py", 298),
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
    # 285 -> 244, DECLARED (DEC-108 Gate 2C): the NAVIGATOR's authoring laws
    # moved to `persona_laws_navigator.py` under the law, VERBATIM, with the
    # composed prompt proven byte-identical by hash. The pin met the next
    # arrival exactly as it said it would — "the next law needs an EXTRACTION
    # before it needs a sentence" — and the arrival became one.
    ("persona_laws.py", 244),
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
    # 293 -> 294, DECLARED (DEC-138): ONE line — `turn_voice` passed into
    # `service_pass_calls` so the KERNEL can speak its approval request. The
    # seam was MEASURED against the alternative before it was chosen: putting
    # the speech HERE cost +16 and breached the LAW, so the utterance lives in
    # `pass_servicing.py` and this file only hands the voice across. A +0 form
    # existed (appending the kwarg to the call's existing tail) and was
    # REFUSED on DEC-66's precedent — a pin that reads 293 because a line was
    # stuffed is a lie in the pin. SIX lines of headroom remain.
    ("kernel/turn_pass.py", 294),
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
    # 300 -> 267, DECLARED: the pin met its next arrival exactly as it said it
    # would. The arrival was NOT a new mechanism — it was the NOTE's own growth
    # (the directive rescoped from one TOOL to the CAPABILITY, and turned into a
    # command), so the surface that had to grow left the file that could not hold
    # it. `confirm_gate_notes.py` is the home, on the `deferral_notes.py` shape:
    # the note AND the `render_args` that fills its one substitution slot, plus
    # the two bounds that exist only for it — one cluster, ONE external
    # touchpoint. Equivalence proven the DEC-108 way, by HASH of the rendered
    # note rather than by a green suite, over all three `render_args` branches
    # (a value past MAX_ARG_CHARS, a rendering past MAX_ARGS_CHARS, empty args)
    # plus newline flattening: five fixtures, five byte-identical strings. The
    # SECURITY half — the detector, the word sets, `call_fingerprint` — did not
    # move one line (DEC-42: the stronger property stays byte-identical while the
    # weaker one is worked on).
    # 267 -> 280, DECLARED (DEC-131 ruling 1): `awaiting_approval`, the ONE
    # accessor the tool_choice brake needs, and the room the extraction bought is
    # what let the distinction be WRITTEN DOWN instead of compressed away. It is
    # NOT `pending_tool is not None`: `observe()` marks a pending APPROVED and
    # leaves it in place, so the name-only predicate stays truthy ACROSS the
    # approval and would gag the very pass that must re-issue the approved call.
    # 280 -> 264, DECLARED (DEC-136): the pin met its arrival for the SECOND
    # time and again the arrival became an extraction. The three rulings measured
    # +34 against 20 lines of headroom — 314, a breach of the LAW and not merely
    # of this pin — so the DETECTOR left for `confirm_gate_detector.py`, taking
    # the word tuple with it. The seam is NOT the one DEC-131 used: that move
    # took the SURFACE out because the surface was what grew, and this time the
    # accepted set is what a ruling changed. DEC-42 is not breached by it — that
    # discipline governs a NOTES change, and here the stronger property is the
    # one under the ruling. Every name is re-exported, `_APPROVALS`/`_REFUSALS`
    # included, so `test_mode_exits.py` and six other call sites are untouched.
    # 264 -> 255, DECLARED (DEC-138): the BINDING left for `call_binding.py`,
    # and this is the first arrival at this pin that became an extraction for a
    # reason OTHER than room. `canonical_call` must return the canonical string
    # so the kernel can SPEAK the bytes it hashed, which gives the
    # canonicalisation a SECOND CONSUMER — and a mechanism with two consumers
    # belongs to neither of them. The ceiling relief is a consequence of the
    # right seam, not the argument for it: DEC-138 measured this file at 314
    # with the feature applied, and the three other reliefs were measured and
    # rejected (`_Pending` left 307, still a breach; relocating the one-shot
    # accessor fits on size but has no coherent home; shortening docstrings is
    # what the law's second clause forbids).
    # 255 -> 290, DECLARED (DEC-138 step 2): the one-shot utterance slot, the
    # accessor that hands it over and clears, the single canonicalisation at
    # the refusal, and the two sibling imports. The file fits ONLY because the
    # binding left in step 1 — measured at 314 with the feature applied and
    # the binding still here. TEN lines of headroom.
    # 290 -> 252, DECLARED (the STATE extraction, ahead of DEC-143): the pending
    # call, the turn's one look, the missed flag and the spoken hand-over left
    # for `confirm_gate_state.py` with every transition of them — MECHANISM,
    # not policy, on the binding's precedent. DEC-143's grant is wiring more
    # than logic: in place it measured 332 (302 as bare code with a docstring
    # left false); the records alone left 314 and the hand-over alone 318, both
    # together fit at exactly 300 and a subclass at 298 — neither taken. The
    # move is behaviour-identical: the suite green with ZERO test edits, 169,759
    # lockstep steps against the base gate identical, and 168 of 168 moved
    # prose units found verbatim.
    # 252 -> 286, DECLARED (DEC-143): the grant's POLICY — the one-member
    # `TURN_GRANTED_TOOLS`, the release by the turn grant, the choice between
    # speaking the SCOPE and speaking the hashed bytes, and the BINDING
    # docstring made true for both shapes. The grant itself is STATE and lives
    # in `confirm_gate_state.py`. FOURTEEN lines of headroom — more than the TEN
    # this file had before DEC-143, because the state left first.
    # 286 -> 289, DECLARED (DEC-147 ③): a look that finds nothing pending clears
    # `missed`, so a miss cannot select the retry note turns later (DEC-145 ⑨).
    # ELEVEN lines of headroom.
    ("trust/confirm_gate.py", 289),
    # 118 -> 209 in ONE gate (DEC-136's retry note, `render_words` and the
    # `confirm_note` chooser). PINNED HERE, ALONE, by Sultan's ruling — and the
    # reason is `deferral_notes.py`'s exactly, not proximity to the ceiling.
    # 209/300 is NOT near the limit; what earns the pin is that this file is the
    # DESTINATION for every surface this gate produces, so it is the module whose
    # next arrival must meet a declared number. Its own docstring records two
    # rewrites already (DEC-131 ruling 3, then DEC-136 rulings 2+3), and +91 in a
    # single gate is the fastest growth in `trust/`.
    # AND THE ROW WAS ALREADY LYING WHEN THIS PIN WAS TAKEN: AGENTS.md declared
    # **99** for a **118**-line file — stale before DEC-136 touched it, the third
    # instance of the drift that let `broker/docs/service.py` cross the law in
    # silence. A pin is what stops a row from being the only thing watching.
    # Nothing extracted and no content moved: DECLARING it IS the change.
    # ELEVEN becomes TWELVE.
    # 209 -> 234, DECLARED (DEC-143 ruling ③): the two notes shipped WITH the
    # grant, never before or after — a `{scope}` and a `{binding}` slot, the
    # retry note's per-call sentence kept byte for byte as `PER_CALL_BINDING_AR`,
    # `TURN_SCOPE_AR` for a turn-granted tool, the stop no longer claiming every
    # outward tool is stopped NOW, and the docstring's per-call claims bounded.
    # The pin met its arrival as a declared number — what it was taken for.
    ("trust/confirm_gate_notes.py", 234),
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
    ("kernel/deferral_notes.py", 207),
    # 280 -> 282 (DEC-113's `ast` import, after the map's own arrival was turned
    # into an extraction), then 282 -> 292 at DEC-117, when the truncated read's
    # `end` became the line DELIVERED rather than the line requested. PINNED
    # HERE, alone, by Sultan's ruling, and the precedent is `confirm_gate.py`:
    # that file sat UNPINNED at 300/300 for THIRTEEN DAYS because nothing was
    # reading it. This one is now the closest thing in `src/` to
    # `broker/docs/service.py`'s condition outside the declared set — and it
    # GROWS BY DESIGN, which is the half that makes the pin matter: every reader
    # surface lands here, and the last two arrivals both did. Nothing extracted
    # and no content moved: DECLARING it IS the change, exactly as at
    # `confirm_gate.py`, `persona_laws.py` and `deferral_notes.py`.
    # `file_reader_notes.py` already exists as the extraction home, so the next
    # arrival needs an EXTRACTION before it needs a sentence. TEN becomes ELEVEN.
    ("file_reader.py", 292),
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
