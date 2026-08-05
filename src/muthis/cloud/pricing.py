"""
pricing.py — the USD price table and the per-turn cost arithmetic.

Extracted from claude_agent.py under the answer agreed at PLANNING time
(DEC-23 / DEC-59): when the prompt-caching slice pushes claude_agent.py past
the ≤300-line ceiling, the price table and the cost function move here
TOGETHER, because they are ONE responsibility with no dependency on the
streaming path, the HTTP client, or the tool catalog. The answer was agreed in
advance precisely so that a breach is a decision and not a debate.

budget.py remains the SOVEREIGN consumer of these numbers (Law 10). This
module computes only what TurnComplete carries; it owns no ledger, no ceiling,
and no policy.

────────────────────────────────────────────────────────────────────────────
THERE ARE TWO COST MODELS HERE, AND WHICH ONE APPLIES IS A MEASUREMENT
────────────────────────────────────────────────────────────────────────────
A provider counts cached tokens in one of two directions, and **the direction
is not inferable from documentation, from an SDK's type definitions, or from
the other provider** (DEC-88 ruling 2 — BINDING on every future integration:
a cost model is MEASURED, never inherited).

  · EXCLUSIVE — `input_tokens` is the UNCACHED REMAINDER. Cached tokens must be
    ADDED BACK or the turn is under-priced. Measured on `claude-sonnet-4-6`
    (DEC-60): under-reports 25x on a read and 301x on a write, which is Rule 10
    failing OPEN — the ledger shows headroom that does not exist.
    → `estimate_cost_usd`

  · INCLUSIVE — `input_tokens` is the WHOLE prompt and the cached count is a
    BREAKDOWN of it, not an addition to it. Cached tokens must be SUBTRACTED
    and re-priced. Measured on `gpt-5.6-luna` (DEC-88 ③): identical cold and
    warm, and `total_tokens == input + output`.
    → `estimate_inclusive_cost_usd`

**APPLYING EITHER FORMULA TO THE OTHER PROVIDER DOUBLE-COUNTS EVERY CACHED
TURN.** The two live measurements that produced these directions are the only
reason this module can be trusted, and a third provider buys its own.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("muthis.cloud.pricing")

# USD per 1M tokens (input, output). Pricing reality check.
# budget.py is the sovereign consumer of these numbers; this table only
# annotates TurnComplete. Re-pin on every model rev (the DEC-26 discipline).
PRICE_TABLE_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (5.00, 25.00),
    # FETCHED 2026-08-05 from the vendor's own published documentation and
    # recorded in DEC-90 — never quoted from memory, and never from a console,
    # so any negotiated rate or credit balance is unreflected here.
    "gpt-5.6-luna": (0.20, 1.20),
}

# The PUBLISHED cached-input price, for INCLUSIVE providers only (see the module
# docstring). It is a table rather than a multiplier on purpose: the Anthropic
# path DERIVES its cached price from CACHE_READ_MULTIPLIER because that is how
# that vendor states it, and re-using the multiplier here would be inheriting a
# cost model — the exact thing DEC-88 ruling 2 forbids. The two happen to agree
# at 0.1x today; that agreement is a coincidence of two price lists, not a rule,
# and writing the price down keeps it from becoming one.
CACHED_INPUT_PRICE_USD_PER_MTOK: dict[str, float] = {
    "gpt-5.6-luna": 0.02,  # DEC-90, same fetch as the row above
}


# Multipliers applied to the INPUT price for cached tokens.
#
# MEASURED LIVE 2026-07-31 on claude-sonnet-4-6 (scripts/diag_prompt_cache_usage.py):
# `usage.input_tokens` EXCLUDES the cached portion — 13 + 7923 = 7936, the
# cache-blind total — and it excludes the WRITE just as much as the read.
# Pricing input_tokens alone therefore UNDER-reports by 25x on a cache read and
# 301x on a cache write, which is Rule 10 failing OPEN: the ledger shows
# headroom that does not exist. A cache write also costs MORE than not caching
# at all (1.25x), so the naive formula records its largest discount at the exact
# moment it pays its largest premium.
CACHE_WRITE_5M_MULTIPLIER = 1.25
CACHE_WRITE_1H_MULTIPLIER = 2.00
CACHE_READ_MULTIPLIER = 0.10


def split_cache_creation(total: int, breakdown: Any) -> tuple[int, int]:
    """Split cache-CREATION tokens into (5-minute, 1-hour) buckets for pricing.

    The flat `cache_creation_input_tokens` scalar CANNOT distinguish the two
    TTLs, and they bill at 1.25x and 2x — so pricing off the scalar under a 1h
    TTL under-reports the write by a further 1.6x with NO signal. The nested
    `cache_creation` object is the source of truth.

    When the breakdown is absent, or does not account for every written token,
    the unexplained tokens are priced at the SAFER (HIGHER) 1h multiplier and
    the fallback is LOGGED. An unknown TTL must never resolve in the ledger's
    favour: a ledger that under-reports does not stop a session that has already
    breached the sovereign ceiling.
    """
    if total <= 0:
        return 0, 0
    five_minute = getattr(breakdown, "ephemeral_5m_input_tokens", None)
    one_hour = getattr(breakdown, "ephemeral_1h_input_tokens", None)
    if five_minute is None and one_hour is None:
        logger.warning(
            "cache_creation breakdown absent for %d write tokens — pricing ALL "
            "of them at the %.2fx (1h) multiplier", total, CACHE_WRITE_1H_MULTIPLIER)
        return 0, total
    five_minute, one_hour = five_minute or 0, one_hour or 0
    unexplained = total - (five_minute + one_hour)
    if unexplained > 0:
        logger.warning(
            "cache_creation buckets account for %d of %d write tokens — pricing "
            "the remaining %d at the %.2fx (1h) multiplier",
            five_minute + one_hour, total, unexplained, CACHE_WRITE_1H_MULTIPLIER)
        one_hour += unexplained
    return five_minute, one_hour


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    cache_read: int = 0,
    cache_write_5m: int = 0,
    cache_write_1h: int = 0,
) -> float:
    """THE EXCLUSIVE MODEL. Turn cost in USD from ALL THREE input counters plus
    output — for a provider whose `input_tokens` is the UNCACHED REMAINDER.

    `input_tokens` is the UNCACHED REMAINDER (measured, see the block above), so
    the cached tokens must be added back at their own rates or the turn is
    under-priced. With no cache activity every cache argument is 0 and the
    arithmetic reduces EXACTLY to the pre-caching formula — which is what lets a
    non-caching provider keep today's behaviour untouched (the DEC-34 shape).

    DO NOT CALL THIS FOR AN INCLUSIVE PROVIDER: its cached tokens are ALREADY
    inside `input_tokens`, so adding them back charges for them twice.
    """
    in_price, out_price = PRICE_TABLE_USD_PER_MTOK.get(model, (3.00, 15.00))
    billable_input = (
        input_tokens
        + cache_read * CACHE_READ_MULTIPLIER
        + cache_write_5m * CACHE_WRITE_5M_MULTIPLIER
        + cache_write_1h * CACHE_WRITE_1H_MULTIPLIER
    )
    return (billable_input * in_price + output_tokens * out_price) / 1_000_000


def estimate_inclusive_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    cached_tokens: int = 0,
) -> float:
    """THE INCLUSIVE MODEL — the exact inverse of the function above.

    `input_tokens` is the WHOLE prompt and `cached_tokens` is a BREAKDOWN of it
    (measured on `gpt-5.6-luna`, DEC-88 ③), so the cached portion is SUBTRACTED
    from the full-rate input and re-priced at its own published rate. With
    nothing cached the arithmetic reduces EXACTLY to input+output, so a provider
    that stops caching — or a turn that misses the cache — keeps costing what it
    always did.

    TWO UNKNOWNS, BOTH RESOLVED AGAINST THE LEDGER'S FAVOUR, which is
    `split_cache_creation`'s rule applied to the other direction: an unpriced
    MODEL falls back to the table's default (an over-estimate for this vendor,
    so Rule 10 fails CLOSED), and an unpriced CACHED rate is charged at the FULL
    input rate rather than at any discount this module cannot justify. A
    discount taken on faith makes the ledger under-report, and a ledger that
    under-reports does not stop a session that has already breached the
    sovereign ceiling.
    """
    in_price, out_price = PRICE_TABLE_USD_PER_MTOK.get(model, (3.00, 15.00))
    if model not in PRICE_TABLE_USD_PER_MTOK:
        logger.warning("no price row for model %r — pricing input at %.2f/MTok", model, in_price)
    cached_price = CACHED_INPUT_PRICE_USD_PER_MTOK.get(model)
    if cached_price is None and cached_tokens > 0:
        logger.warning(
            "no cached-input price for model %r — charging %d cached tokens at the "
            "FULL input rate", model, cached_tokens)
        cached_price = in_price
    # Clamped, never trusted: a counter larger than the total would otherwise
    # produce a NEGATIVE uncached remainder and a credit in the ledger.
    cached = max(0, min(cached_tokens, input_tokens))
    uncached = input_tokens - cached
    billable_input = uncached * in_price + cached * (cached_price or 0.0)
    return (billable_input + output_tokens * out_price) / 1_000_000
