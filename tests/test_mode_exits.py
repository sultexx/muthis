"""
test_mode_exits.py — DEC-65's THREE EXITS, the lazy expiry, and the BINDING
CONSTRAINT of 2026-07-31 (T2).

WHAT THIS FILE IS REALLY FOR. Two of the three exits are evaluated inside
`TurnPrelude.begin_turn`, so they are driven THROUGH IT with a hand-held clock
and a raw transcript — never by calling the authority directly and calling that
the exit. A test that drove the authority alone would prove the authority works
and say nothing about whether a user can actually leave a mode.

THE MARKER-CORE CONSTRAINT IS THE SHARPEST THING HERE, and it is guarded with
its POSITIVE CONTROL because its failure direction is SAFE and therefore
INVISIBLE. If the mode directive carried no family marker, the mode's step text
would sit in DEC-16's approval-detector input, and because that detector matches
on WHOLE-UTTERANCE isolation, a genuine «أوافق» would simply stop being
recognised — friction, never a bypass, and indistinguishable from the user
mis-speaking. Case A proves the strip works; case B proves case A can fail.
Without B, the assertion is satisfiable by a strip that removes everything.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from muthis.kernel.mode_surfaces import (
    MAX_STEP_TEXT_CHARS, MODE_EXIT_WORDS, detect_mode_exit, mode_directive_line,
)
from muthis.kernel.mode_transition import (
    ADVANCE, ENTER, MODE_IDLE_TIMEOUT_S, ModeAuthority, TransitionRequest,
    is_idle_expired,
)
from muthis.kernel.plan import Plan
from muthis.kernel.session_mode import SessionMode
from muthis.kernel.turn_prelude import TurnPrelude
from muthis.kernel.verbosity import _STANDALONE_WORDS, normalize_ar
from muthis.trust.confirm_gate import (
    APPROVAL_WORD_AR, APPROVE, DIRECTIVE_MARKER_AR, _APPROVALS, _REFUSALS,
    detect_confirmation, strip_directive_lines,
)

PRELUDE_PY = (pathlib.Path(__file__).resolve().parent.parent / "src" / "muthis" /
              "kernel" / "turn_prelude.py")


class _Clock:
    def __init__(self) -> None:
        self.now = 500.0

    def __call__(self) -> float:
        return self.now


def _guiding_prelude(clock=None) -> "tuple[TurnPrelude, SessionMode]":
    """A prelude with a mode already running — built through the authority, so
    no test here reaches a mutator the design forbids it to reach."""
    mode = SessionMode(clock=clock or _Clock())
    prelude = TurnPrelude(session_mode=mode)
    prelude.authority.request(TransitionRequest(
        kind=ENTER, mode_name="navigator",
        plan=Plan.build("deploy", [{"text": t, "expected_result": f"نتيجة {t}"}
                              for t in ("افتح الملف", "شغّل الاختبار", "ارفع التغيير")])))
    return prelude, mode


# ─── EXIT 1 — the DETERMINISTIC exit word, model uninvolved ─────────────────

@pytest.mark.parametrize("said", ["خلاص", "خَلاص", "خلاص.", "خلـــاص", " خلاص ",
                                  "خروج", "أنهِ الوضع", "انه الوضع"])
def test_the_exit_word_ends_the_mode_with_the_model_never_consulted(said):
    """No reasoner, no tool call, no model output anywhere in this path — the
    raw transcript alone ends the mode. A confused or INJECTED model must never
    be able to trap the user.

    The variance covered is exactly `normalize_ar`'s — tashkeel, tatweel, hamza
    forms, punctuation, spacing — because that is the ONE normalizer the three
    detectors share. LETTER ELONGATION («خلااااص») is NOT covered and is not
    made to be: every other detector in this project has the same property, and
    widening this one alone would be a second normalization behaviour."""
    prelude, mode = _guiding_prelude()
    prelude.begin_turn(said)
    assert mode.active is False, f"«{said}» did not end the mode"


@pytest.mark.parametrize("said", [
    "خلاص الملف انحفظ",              # the word inside a sentence
    "قال لي خلاص",
    "وش يعني خروج من البرنامج؟",
    "أوافق",                          # DEC-16's word must not end a mode
    "اختصر",                          # verbosity's word must not end a mode
])
def test_a_near_miss_never_ends_the_mode(said):
    """WHOLE-UTTERANCE isolation, the rule that stops «أي ضلع أطول؟» from
    flipping verbosity — applied where the cost of a false positive is losing
    the user's place rather than losing an authorization."""
    prelude, mode = _guiding_prelude()
    prelude.begin_turn(said)
    assert mode.active is True, f"«{said}» ended the mode"


def test_the_exit_set_does_not_overlap_the_approval_or_verbosity_sets():
    """Asserted against the REAL constants rather than by inspection: three
    deterministic detectors read the same transcript every turn, and a word in
    two sets means one of them is answering for the other."""
    assert not (MODE_EXIT_WORDS & _APPROVALS), "an exit word approves a call"
    assert not (MODE_EXIT_WORDS & _REFUSALS)
    assert not (MODE_EXIT_WORDS & {normalize_ar(w) for w in _STANDALONE_WORDS})
    assert MODE_EXIT_WORDS, "the exit set is empty — nothing could ever exit"


def test_the_exit_word_is_read_BEFORE_anything_is_prepended():
    """ORDER IS A CONTRACT, driven against the module directly rather than
    through the outcome — because the detector ALSO runs the DEC-31 strip, so
    the outcome alone cannot distinguish the two orders. That is exactly the
    hole the split-2 order guard fell into (DEC-73), and the fix there was the
    same: assert the order where the order lives."""
    tree = ast.parse(PRELUDE_PY.read_text(encoding="utf-8"))
    body = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "begin_turn").body
    source = [ast.dump(statement) for statement in body]
    exit_at = next(i for i, s in enumerate(source) if "detect_mode_exit" in s)
    expiry_at = next(i for i, s in enumerate(source) if "is_idle_expired" in s)
    verbosity_at = next(i for i, s in enumerate(source) if "_verbosity" in s)
    directive_at = next(i for i, s in enumerate(source) if "mode_directive_line" in s)
    assert expiry_at < exit_at < verbosity_at < directive_at, (
        "begin_turn's order broke: expiry, then the RAW-text exit word, then "
        "verbosity (which also scans raw text), then everything prepended")


# ─── EXIT 3 — the IDLE timeout, evaluated LAZILY, with no timer ─────────────

def test_idle_expiry_is_evaluated_only_at_the_START_OF_A_TURN():
    """THE POSITIVE CONTROL FOR LAZINESS. Time passing must do NOTHING on its
    own: if the mode ended without `begin_turn`, something was watching a clock,
    and a background timer is a lifecycle outside the kernel (Law 11; DEC-47
    rejected exactly that shape)."""
    clock = _Clock()
    prelude, mode = _guiding_prelude(clock)

    clock.now += MODE_IDLE_TIMEOUT_S * 10
    assert mode.active is True, "the mode ended without a turn — something ticked"
    assert is_idle_expired(mode) is True, "the predicate should already say so"

    prelude.begin_turn("وش الخطوة؟")
    assert mode.active is False, "the lazy expiry did not fire at turn start"


def test_a_mode_inside_its_idle_bound_survives_the_turn():
    clock = _Clock()
    prelude, mode = _guiding_prelude(clock)
    clock.now += MODE_IDLE_TIMEOUT_S - 1
    prelude.begin_turn("كمّل")
    assert mode.active is True


def test_the_predicate_measures_IDLE_TIME_not_turns():
    """DEC-65's ruling: a user may spend ten minutes on one step without
    producing a turn, so counting turns measures the wrong thing."""
    clock = _Clock()
    prelude, mode = _guiding_prelude(clock)
    for _ in range(20):                       # twenty turns, no time passing
        prelude.begin_turn("وش رايك؟")
    assert mode.active is True, "turn COUNT ended the mode"
    assert is_idle_expired(SessionMode()) is False, "an inactive mode never expires"


class _StaleIdleMode:
    """A mode-shaped object that is INACTIVE while still reporting idle time."""

    active = False

    def idle_seconds(self) -> float:
        return MODE_IDLE_TIMEOUT_S * 2


def test_an_inactive_mode_never_expires_even_when_it_reports_idle_time():
    """THE DISCRIMINATING CONTROL, added after a mutation survived without it.

    Dropping `mode.active` from the predicate stayed GREEN, because the real
    `SessionMode.idle_seconds()` returns 0.0 when inactive — so on that ONE path
    the conjunct is redundant. Per the standing rule, an unobservable survivor
    is EXPLAINED and its code is NOT deleted: the redundancy sits at a LAYER
    BOUNDARY, and the predicate must not rest on a collaborator's internal
    invariant. Deleting it would withdraw the guarantee from every caller that
    path does not exercise — the `doc_rag` M15 reasoning, in a new place. This
    stub is the caller that exercises it."""
    assert is_idle_expired(_StaleIdleMode()) is False  # type: ignore[arg-type]


def test_the_expired_mode_leaves_no_directive_behind_it():
    """The accepted consequence, stated in DEC-65 and checked here: expiry is
    not announced. It is DISCOVERED — the frame simply stops decorating the
    turn. (This docstring used to end "and T3's indicator is already gone",
    which was true for the WRONG reason and is now false: the chip was erased by
    the 7 s auto-hide, never by expiry, and DEC-104 ruling 1 fixed that.)"""
    clock = _Clock()
    prelude, _mode = _guiding_prelude(clock)
    clock.now += MODE_IDLE_TIMEOUT_S
    assert DIRECTIVE_MARKER_AR not in prelude.begin_turn("وش الخطوة؟")


# ─── DEC-104 ruling 2 — TWO CLOCKS, TWO QUESTIONS ───────────────────────────
#
# THE MEASURED DEFECT (DEC-102): `last_progress_at` was re-stamped ONLY by
# `enter` and a SUCCESSFUL model-issued move — not by a turn, an F9, an
# utterance, a side question, or a REFUSED move. So the clock measured time
# since the last COMMITTED STEP CHANGE, not time since the user was present, and
# the turn that killed the mode was the user's own return: expired before the
# directive was assembled, after which the model was never told a walkthrough
# had been running. `last_activity_at` is the second clock and `is_idle_expired`
# reads it. Everything below is driven THROUGH `begin_turn` and the authority,
# never by calling a mutator, because a turn is the thing under test.


def test_a_turn_that_moves_NO_step_renews_liveness_and_the_mode_SURVIVES():
    """TEST 1 — THE DEFECT ITSELF. Four turns, each after 675 s of thinking: no
    single gap reaches the 900 s bound, but the total is three times it. With
    ONE clock the mode dies on turn two, because nothing in those turns moved a
    step. The step is asserted UNMOVED at the end, so this cannot be passing by
    quietly advancing something."""
    clock = _Clock()
    prelude, mode = _guiding_prelude(clock)
    started_at = clock.now

    for turn in range(4):
        clock.now += MODE_IDLE_TIMEOUT_S * 0.75      # long, but inside the bound
        prelude.begin_turn("وش رايك في هذي؟")
        assert mode.active is True, f"the mode died on turn {turn + 1}"

    assert clock.now - started_at > MODE_IDLE_TIMEOUT_S * 2, (
        "the drive did not actually outlast the bound, so it proves nothing")
    assert mode.current_step == 1, "a liveness stamp moved the step"


def test_a_side_question_renews_liveness_AND_does_not_move_the_step():
    """TEST 2 — BOTH DIRECTIONS IN ONE DRIVE. The side-question exclusion STAYS
    and is now CONSISTENT rather than contradictory: a side question does not
    move the step, so it must not touch progress, but it IS activity, so it
    renews liveness. A one-directional assertion passes while half the ruling is
    broken — renewing liveness on a turn that also stamped progress would make
    the step counter lie, and that is the failure this pair exists to catch."""
    clock = _Clock()
    prelude, mode = _guiding_prelude(clock)
    progress_at_entry = mode.frame.last_progress_at

    clock.now += 600.0
    prelude.begin_turn("ليش هذي الخطوة أصلاً؟")      # a question, not a step

    assert mode.idle_seconds() == 0.0, "the side question did not renew liveness"
    assert mode.frame.last_progress_at == progress_at_entry, (
        "the side question stamped PROGRESS — the step counter would now lie")
    assert mode.current_step == 1, "the side question moved the step"


def test_a_REFUSED_move_renews_liveness_but_stamps_no_progress():
    """TEST 3 — THE CASE THAT WAS AGEING THE MODE, and the sharpest one: the
    user IS working the walkthrough, the model IS trying to advance, and the
    request is refused at the last step. Its turn is activity; its move is not
    progress. Driven to the end of the plan first, so the refusal is the real
    AT_END one rather than a hand-made outcome."""
    clock = _Clock()
    prelude, mode = _guiding_prelude(clock)
    for _ in range(2):
        prelude.authority.request(TransitionRequest(kind=ADVANCE))
    assert mode.current_step == 3, "the drive never reached the last step"
    progress_at_last_move = mode.frame.last_progress_at

    for turn in range(4):
        clock.now += MODE_IDLE_TIMEOUT_S * 0.75
        prelude.begin_turn("التالي")                  # the user's turn: activity
        outcome = prelude.authority.request(TransitionRequest(kind=ADVANCE))
        assert outcome.applied is False, "positive control: the move must REFUSE"
        assert mode.active is True, f"a refused move aged the mode out on {turn + 1}"

    assert mode.frame.last_progress_at == progress_at_last_move, (
        "a REFUSED move stamped progress — a bound failure would read as a step")
    assert mode.idle_seconds() == 0.0


@pytest.mark.parametrize("name", ["turn_prelude.py", "session_mode.py",
                                  "mode_transition.py"])
def test_the_second_clock_introduced_no_scheduler_on_any_module_of_its_path(name):
    """TEST 4 — STRUCTURAL, and it has to be. A BEHAVIOURAL test cannot tell
    "there is no timer" from "there is a timer that has not fired yet", so the
    absence is asserted over the source of every module the new clock touches:
    the stamp site, the field's home and the predicate. Expiry stays evaluated
    LAZILY at turn start — a background lifecycle is Law 11's bar, and DEC-47
    and DEC-65 both already refused one."""
    source = (PRELUDE_PY.parent / name)
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = ({node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} |
             {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)})
    for scheduling in ("sleep", "call_later", "call_soon", "call_at", "Timer",
                       "create_task", "ensure_future", "Thread", "to_thread",
                       "run_in_executor", "after", "schedule", "alarm"):
        assert scheduling not in names, f"{name} schedules: {scheduling}"
    imported = {node.names[0].name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom)) and node.names}
    assert not (imported & {"asyncio", "threading", "sched", "signal"}), (
        f"{name} imported a scheduling module")


def test_last_progress_at_is_stamped_on_EXACTLY_the_events_it_always_was():
    """TEST 5 — THE FIRST CLOCK, PINNED, so the second cannot quietly change it.
    Two events stamp progress and no others: entering, and a move the authority
    APPLIED. A turn does not, a side question does not, a refused move does not
    — which is the same list as before ruling 2, and that is the point."""
    clock = _Clock()
    prelude, mode = _guiding_prelude(clock)
    stamped_by_enter = mode.frame.last_progress_at
    assert stamped_by_enter == clock.now, "entering no longer stamps progress"

    clock.now += 10.0
    assert prelude.authority.request(
        TransitionRequest(kind=ADVANCE)).applied is True
    stamped_by_move = mode.frame.last_progress_at
    assert stamped_by_move == clock.now, "an applied move no longer stamps progress"

    # …and NONE of these three, each driven the way it really happens.
    clock.now += 10.0
    prelude.begin_turn("وش الخطوة؟")                                  # a turn
    prelude.begin_turn("ليش هذي الخطوة؟")                             # a side question
    assert mode.frame.last_progress_at == stamped_by_move, (
        "a turn or a side question stamped the progress clock")

    clock.now += 10.0                       # the second applied move: the control
    assert prelude.authority.request(       # that the assertion above is not
        TransitionRequest(kind=ADVANCE)).applied is True   # passing because
    assert mode.frame.last_progress_at == clock.now        # NOTHING can stamp
    stamped_at_the_end = clock.now

    clock.now += 10.0
    prelude.begin_turn("التالي")            # a real turn carrying a refused move
    assert prelude.authority.request(
        TransitionRequest(kind=ADVANCE)).applied is False, "positive control: AT_END"
    assert mode.frame.last_progress_at == stamped_at_the_end, (
        "a REFUSED move stamped the progress clock")
    assert mode.idle_seconds() == 0.0, "…while its turn still renewed liveness"


# ─── The per-turn directive line, and the BINDING CONSTRAINT ────────────────

def test_the_directive_carries_the_kernels_own_numbers_and_the_stored_text():
    prelude, _mode = _guiding_prelude()
    line = prelude.begin_turn("وش الخطوة؟").splitlines()[0]
    assert DIRECTIVE_MARKER_AR in line
    assert "1" in line and "3" in line, "the frame's numbers are missing"
    assert "افتح الملف" in line, "the kernel's stored step text is missing"


def test_the_directive_is_always_ONE_line_however_long_the_step_text():
    """`strip_directive_lines` is line-wise, so a two-line directive would leave
    its second line sitting in the transcript the approval detector reads."""
    line = mode_directive_line("navigator", 2, 5, "أولاً\nثانياً\n" + "ط" * 400)
    assert "\n" not in line
    assert len(line) < MAX_STEP_TEXT_CHARS + 400


def test_CASE_A_a_real_composed_directive_is_stripped_and_the_approval_lands():
    """CASE A of the BINDING CONSTRAINT, driven through the REAL
    `strip_directive_lines` and the REAL `detect_confirmation`."""
    prelude, _mode = _guiding_prelude()
    decorated = prelude.begin_turn(APPROVAL_WORD_AR)

    assert strip_directive_lines(decorated).strip() == APPROVAL_WORD_AR, (
        "the residue is not the bare transcript")
    assert detect_confirmation(decorated) == APPROVE, (
        "a mode directive stopped a genuine approval from being recognised")


def test_CASE_B_the_positive_control_a_markerless_line_breaks_the_detector():
    """CASE B, and it is what makes case A mean anything: the SAME line with
    every family marker removed SURVIVES the strip and the approval is lost.

    Without this the case-A assertion is satisfiable by a strip that removes
    everything — the vacuous-check family this project has met repeatedly."""
    prelude, _mode = _guiding_prelude()
    decorated = prelude.begin_turn(APPROVAL_WORD_AR)
    markerless = decorated.replace(DIRECTIVE_MARKER_AR, "سياق")

    assert DIRECTIVE_MARKER_AR not in markerless
    assert strip_directive_lines(markerless) == markerless, "it was stripped anyway"
    assert detect_confirmation(markerless) is None, (
        "the control did not fail — case A proves nothing")


def test_a_turn_with_no_mode_running_is_decorated_by_nothing():
    """The other positive control: the directive appears BECAUSE a mode is
    running, not unconditionally."""
    assert TurnPrelude().begin_turn(APPROVAL_WORD_AR) == APPROVAL_WORD_AR


def test_the_directive_survives_alongside_verbosity_and_the_barge_in_note():
    """All three sources stack, all three are marked, and the approval still
    lands — the case the DEC-16 guard calls 'both stacked, as run_turn stacks
    them', now with a third member."""
    prelude, _mode = _guiding_prelude()
    prelude.begin_turn("باختصار")                     # sticky SHORT, on
    decorated = prelude.begin_turn(APPROVAL_WORD_AR, interrupted=True)
    assert decorated.count("\n") >= 2, "the sources did not all attach"
    assert detect_confirmation(decorated) == APPROVE


def test_detect_mode_exit_is_pure_and_never_raises():
    for hostile in ("", "   ", "\n\n", "خلاص\nخلاص", "٣٢١", "x" * 5000):
        assert isinstance(detect_mode_exit(hostile), bool)


def test_an_exit_word_arriving_with_no_mode_running_changes_nothing():
    prelude = TurnPrelude()
    assert prelude.begin_turn("خلاص") == "خلاص"
    assert prelude.session_mode.active is False


def test_the_authority_and_the_frame_can_never_disagree_about_which_mode():
    """The authority is built OVER the injected mode rather than beside it, so
    'two objects, two opinions' is not a state that exists."""
    mode = SessionMode()
    prelude = TurnPrelude(session_mode=mode)
    assert prelude.session_mode is mode
    prelude.authority.request(TransitionRequest(kind=ENTER, mode_name="review"))
    assert mode.active is True and prelude.session_mode.name == "review"


def test_the_prelude_reaches_the_mode_only_through_the_authority():
    """The bypass check at the ONE place with both objects in hand. Asserted on
    the module rather than on behaviour, because a direct `enter()` here would
    pass every behavioural test in this file."""
    called = {node.func.attr
              for node in ast.walk(ast.parse(PRELUDE_PY.read_text(encoding="utf-8")))
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not (called & {"enter", "leave", "record_progress"})
    assert "request" in called, "the prelude no longer routes through the authority"
