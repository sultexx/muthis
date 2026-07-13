"""
test_verbosity.py — the voice-controlled reply-length state (v5 Phase B),
pure unit tests (no orchestrator, no network, no audio).

B1 scope: the VerbosityController state machine + the Arabic internal
directives + the attach primitive + the one-shot EXACT decay:
  * every non-NORMAL state yields a DISTINCT directive opening with the shared
    internal-directive marker; NORMAL yields none,
  * attach() preserves the original transcript verbatim (directive prepended),
  * end_turn() decays ONLY the one-shot EXACT; sticky SHORT/DETAILED persist,
  * bad input (unknown level / EXACT without N) is a logged no-op.

Run:  set PYTHONPATH=src && python -m pytest tests/test_verbosity.py -q
"""

from __future__ import annotations

from muthis.verbosity import (
    DETAILED,
    DIRECTIVE_OPEN_AR,
    EXACT,
    NORMAL,
    SHORT,
    VerbosityController,
    detect_command,
)


def _controller(level=None, exact_n=None):
    ctrl = VerbosityController()
    if level is not None:
        ctrl.set_level(level, exact_n)
    return ctrl


# ─────────────────────────────── Defaults ───────────────────────────────


def test_controller_starts_at_normal_with_no_directive():
    ctrl = VerbosityController()
    assert ctrl.level == NORMAL
    assert ctrl.exact_n is None
    assert ctrl.directive() == ""


# ─────────────────────────────── Directives ───────────────────────────────


def test_each_state_yields_a_distinct_internal_directive():
    directives = {
        SHORT: _controller(SHORT).directive(),
        DETAILED: _controller(DETAILED).directive(),
        EXACT: _controller(EXACT, exact_n=5).directive(),
    }
    # All present, all distinct, all opening with the shared internal marker.
    assert all(d for d in directives.values())
    assert len(set(directives.values())) == 3
    assert all(d.startswith(DIRECTIVE_OPEN_AR) for d in directives.values())


def test_exact_directive_carries_the_requested_word_count():
    assert "5" in _controller(EXACT, exact_n=5).directive()
    assert "9" in _controller(EXACT, exact_n=9).directive()


# ─────────────────────────────── attach() ───────────────────────────────


def test_attach_on_normal_returns_the_transcript_unchanged():
    text = "وش هذا الزر؟"
    assert VerbosityController().attach(text) == text


def test_attach_prepends_the_directive_and_preserves_the_original_text():
    ctrl = _controller(SHORT)
    text = "اشرح لي هذا الكود"
    combined = ctrl.attach(text)
    assert combined.startswith(DIRECTIVE_OPEN_AR)
    assert combined.endswith(text)          # transcript verbatim, never mangled
    assert ctrl.directive() in combined


# ─────────────────────────────── end_turn() ───────────────────────────────


def test_exact_is_one_shot_and_decays_at_end_turn():
    ctrl = _controller(EXACT, exact_n=5)
    assert ctrl.level == EXACT
    ctrl.end_turn()
    assert ctrl.level == NORMAL and ctrl.exact_n is None
    assert ctrl.directive() == ""


def test_sticky_short_and_detailed_survive_end_turn():
    for sticky in (SHORT, DETAILED):
        ctrl = _controller(sticky)
        ctrl.end_turn()
        ctrl.end_turn()                     # two whole turns later…
        assert ctrl.level == sticky         # …still active (sticky by decision)
        assert ctrl.directive() != ""


# ─────────────────────────────── bad input ───────────────────────────────


def test_unknown_level_is_a_no_op():
    ctrl = _controller(SHORT)
    ctrl.set_level("bogus")
    assert ctrl.level == SHORT              # prior state untouched


def test_exact_without_a_valid_n_is_a_no_op():
    ctrl = _controller(SHORT)
    ctrl.set_level(EXACT)                   # no N
    ctrl.set_level(EXACT, exact_n=0)        # nonsense N
    assert ctrl.level == SHORT


# ───────────────────── B2: STT-tolerant command detection ─────────────────────


def test_short_command_matches_across_scribe_spellings():
    # Standalone imperative, hamza variant, stray tashkeel, and punctuation.
    for utterance in ("اختصر", "إختصر", "اِخْتَصِرْ", "اختصر."):
        assert detect_command(utterance) == (SHORT, None), utterance
    # Explicit phrases match anywhere — clitic prefixes included.
    assert detect_command("وباختصار وش يسوي هذا الكود؟") == (SHORT, None)
    assert detect_command("جاوبني بإيجاز") == (SHORT, None)


def test_detailed_command_matches_anywhere_including_tatweel():
    assert detect_command("اشرح لي بالتفصيل وش يسوي هذا الكود") == (DETAILED, None)
    assert detect_command("بالتفصيــل") == (DETAILED, None)      # tatweel stretch
    assert detect_command("أطول") == (DETAILED, None)            # standalone only
    assert detect_command("طوّل") == (DETAILED, None)


def test_exact_n_understands_number_words_digits_and_duals():
    assert detect_command("جاوب بخمس كلمات") == (EXACT, 5)
    assert detect_command("ب٥ كلمات") == (EXACT, 5)              # Arabic-Indic digit
    assert detect_command("ب5 كلمات") == (EXACT, 5)              # ASCII digit
    assert detect_command("بعشر كلمات وش هذا؟") == (EXACT, 10)
    assert detect_command("بكلمتين") == (EXACT, 2)               # dual, no numeral
    assert detect_command("بكلمة وحدة") == (EXACT, 1)


def test_reset_phrase_returns_to_normal():
    assert detect_command("رجّع طولك الطبيعي") == (NORMAL, None)
    assert detect_command("رجع للوضع الطبيعي") == (NORMAL, None)


def test_ambiguous_words_do_not_fire_inside_normal_questions():
    # The approved isolation rule: comparatives/imperatives inside a genuine
    # question or task must NOT flip the sticky state.
    assert detect_command("أي ضلع أطول؟") is None
    assert detect_command("اختصر لي هذا النص") is None           # a TASK, not a mode
    assert detect_command("وش هذا الزر؟") is None
    assert detect_command("") is None


def test_begin_turn_detects_updates_state_and_attaches_the_directive():
    ctrl = VerbosityController()
    combined = ctrl.begin_turn("جاوب بخمس كلمات وش هذا الزر؟")
    assert ctrl.level == EXACT and ctrl.exact_n == 5
    assert combined.startswith(DIRECTIVE_OPEN_AR)
    assert combined.endswith("جاوب بخمس كلمات وش هذا الزر؟")     # transcript intact
    # A plain follow-up utterance while NORMAL passes through untouched.
    ctrl.end_turn()
    assert ctrl.begin_turn("وش هذا؟") == "وش هذا؟"
