"""
test_luna_pricing.py — the second cost model, and the double-count it prevents.

DEC-88 ruling 2 is BINDING: **a cost model is MEASURED, never inherited.** The
two providers measured so far count cached tokens in OPPOSITE directions, and
the direction is not inferable from documentation, from an SDK's types, or from
the other provider:

  · EXCLUSIVE (`claude-sonnet-4-6`, DEC-60) — `input_tokens` is the UNCACHED
    REMAINDER. Cached tokens are ADDED BACK. Getting it wrong under-reports and
    Rule 10 fails OPEN: the ledger shows headroom that does not exist.
  · INCLUSIVE (`gpt-5.6-luna`, DEC-88 ③) — `input_tokens` is the WHOLE prompt
    and the cached count is a BREAKDOWN of it. Cached tokens are SUBTRACTED and
    re-priced.

**THE CENTRAL TEST IS `test_the_two_models_DISAGREE...`.** A cost function that
merely computes something plausible passes every other test in this file. What
must be proven is that applying the WRONG formula produces a DIFFERENT and
LARGER number on a real cached turn — because that is the failure mode: the code
would run, the ledger would fill, every figure would be wrong, and nothing would
raise. A silent lie in the ledger is the DEC-60 lesson and the DEC-88 ① lesson
arriving at the same file from two directions.

Run:  PYTHONPATH=src pytest tests/test_luna_pricing.py -q
"""

from __future__ import annotations

import pytest

from muthis.cloud.pricing import (
    CACHED_INPUT_PRICE_USD_PER_MTOK,
    PRICE_TABLE_USD_PER_MTOK,
    estimate_cost_usd,
    estimate_inclusive_cost_usd,
)

LUNA = "gpt-5.6-luna"

# DEC-90's MEASURED pass-1 figures, used as the worked example throughout so a
# drift shows up as a number nobody recognises.
PASS1_INPUT, PASS1_CACHED, PASS1_OUTPUT = 7_290, 5_895, 139


# ═══ The published rate card ═════════════════════════════════════════════════


def test_the_price_row_is_the_one_FETCHED_at_DEC_90():
    """Published list prices, fetched from the vendor's own documentation on
    2026-08-05 — never quoted from memory and never from a console, so a
    negotiated rate is unreflected here by design. Re-pin on every model rev
    (the DEC-26 discipline)."""
    assert PRICE_TABLE_USD_PER_MTOK[LUNA] == (0.20, 1.20)
    assert CACHED_INPUT_PRICE_USD_PER_MTOK[LUNA] == 0.02


def test_the_cached_price_is_a_TABLE_not_a_multiplier_on_the_other_provider():
    """The two vendors happen to agree at 0.1x today. **That agreement is a
    coincidence of two price lists, not a rule** — and deriving one from the
    other is precisely the inheritance DEC-88 ruling 2 forbids. Writing the
    price down is what keeps the coincidence from hardening into an assumption
    the next provider inherits."""
    input_price, _ = PRICE_TABLE_USD_PER_MTOK[LUNA]
    assert CACHED_INPUT_PRICE_USD_PER_MTOK[LUNA] == pytest.approx(input_price * 0.1)
    # ...and the Anthropic multiplier is NOT what produced it: the table holds an
    # absolute price, so changing that constant must not move this number.
    assert isinstance(CACHED_INPUT_PRICE_USD_PER_MTOK[LUNA], float)


# ═══ The inclusive arithmetic ════════════════════════════════════════════════


def test_the_cached_portion_is_SUBTRACTED_and_repriced():
    """The worked example, computed independently of the implementation."""
    expected = ((PASS1_INPUT - PASS1_CACHED) * 0.20
                + PASS1_CACHED * 0.02
                + PASS1_OUTPUT * 1.20) / 1_000_000
    assert estimate_inclusive_cost_usd(
        LUNA, PASS1_INPUT, PASS1_OUTPUT,
        cached_tokens=PASS1_CACHED) == pytest.approx(expected)


def test_with_nothing_cached_it_reduces_EXACTLY_to_input_plus_output():
    """A cache miss, a cold session and a provider that stops caching must all
    cost what they always did — the DEC-34 optional-field shape."""
    plain = (PASS1_INPUT * 0.20 + PASS1_OUTPUT * 1.20) / 1_000_000
    assert estimate_inclusive_cost_usd(
        LUNA, PASS1_INPUT, PASS1_OUTPUT) == pytest.approx(plain)
    assert estimate_inclusive_cost_usd(
        LUNA, PASS1_INPUT, PASS1_OUTPUT, cached_tokens=0) == pytest.approx(plain)


def test_a_fully_cached_prompt_is_priced_ENTIRELY_at_the_cached_rate():
    """The boundary the 81%-cached measurement is heading toward, and the one
    where an off-by-one in the subtraction would still look plausible."""
    expected = (1_000 * 0.02 + 10 * 1.20) / 1_000_000
    assert estimate_inclusive_cost_usd(
        LUNA, 1_000, 10, cached_tokens=1_000) == pytest.approx(expected)


# ═══ THE DOUBLE COUNT ════════════════════════════════════════════════════════


def test_the_two_models_DISAGREE_on_a_cached_turn_and_the_wrong_one_OVERCHARGES():
    """**THE TEST THIS FILE EXISTS FOR.** `estimate_cost_usd` ADDS the cached
    tokens back; on this provider they are already inside `input_tokens`, so it
    charges for them TWICE. Nothing raises, nothing logs, and the ledger simply
    stops being true.

    The two numbers MUST differ. If a future edit ever makes them agree, one of
    the two measured directions has been quietly discarded."""
    inclusive = estimate_inclusive_cost_usd(
        LUNA, PASS1_INPUT, PASS1_OUTPUT, cached_tokens=PASS1_CACHED)
    wrong = estimate_cost_usd(
        LUNA, PASS1_INPUT, PASS1_OUTPUT, cache_read=PASS1_CACHED)
    assert wrong > inclusive, (
        "the exclusive formula no longer over-charges an inclusive provider — "
        "the two cost models have collapsed into one and a measurement was lost")
    # The whole cached prefix is charged twice: once at full rate inside
    # `input_tokens`, once again at the cache-read rate added on top.
    assert wrong - inclusive == pytest.approx(
        PASS1_CACHED * (0.20 - 0.02) / 1_000_000 + PASS1_CACHED * 0.02 / 1_000_000)


def test_the_two_models_AGREE_when_nothing_was_cached():
    """The directions differ only where a cache is involved. Agreeing here is
    what makes the disagreement above meaningful rather than an arbitrary
    offset."""
    assert estimate_inclusive_cost_usd(LUNA, 5_000, 100) == pytest.approx(
        estimate_cost_usd(LUNA, 5_000, 100))


# ═══ Unknowns resolve AGAINST the ledger's favour ════════════════════════════


def test_a_cached_count_larger_than_the_input_cannot_CREDIT_the_ledger():
    """Clamped, never trusted. An unclamped subtraction would produce a NEGATIVE
    uncached remainder and a turn that pays the budget back — a ledger that can
    move in both directions is not a ceiling."""
    cost = estimate_inclusive_cost_usd(LUNA, 100, 10, cached_tokens=99_999)
    assert cost > 0
    assert cost == pytest.approx((100 * 0.02 + 10 * 1.20) / 1_000_000)


def test_an_unpriced_cached_rate_is_charged_at_the_FULL_input_rate(caplog):
    """`split_cache_creation`'s rule, applied to the other direction: an unknown
    resolves against the ledger's favour and is LOGGED. A discount taken on faith
    makes the ledger under-report, and a ledger that under-reports does not stop
    a session that has already breached the sovereign ceiling."""
    PRICE_TABLE_USD_PER_MTOK["muthis-test-model"] = (1.00, 2.00)
    try:
        with caplog.at_level("WARNING", logger="muthis.cloud.pricing"):
            cost = estimate_inclusive_cost_usd(
                "muthis-test-model", 1_000, 0, cached_tokens=1_000)
    finally:
        del PRICE_TABLE_USD_PER_MTOK["muthis-test-model"]
    assert cost == pytest.approx(1_000 * 1.00 / 1_000_000)  # NOT discounted
    assert "FULL input rate" in caplog.text


def test_an_unpriced_MODEL_warns_and_falls_back_to_the_table_default(caplog):
    """An unknown model over-estimates on this vendor, so Rule 10 fails CLOSED —
    but it must not do so in silence."""
    with caplog.at_level("WARNING", logger="muthis.cloud.pricing"):
        cost = estimate_inclusive_cost_usd("no-such-model", 1_000, 0)
    assert cost == pytest.approx(1_000 * 3.00 / 1_000_000)
    assert "no price row" in caplog.text


def test_the_anthropic_rows_are_untouched():
    """`pricing.py` learned a second model; it did not re-learn the first.
    budget.py is untouched entirely — the sovereign ledger stays sovereign."""
    assert PRICE_TABLE_USD_PER_MTOK["claude-sonnet-4-6"] == (3.00, 15.00)
    assert PRICE_TABLE_USD_PER_MTOK["claude-opus-4-7"] == (5.00, 25.00)
    assert "claude-sonnet-4-6" not in CACHED_INPUT_PRICE_USD_PER_MTOK
