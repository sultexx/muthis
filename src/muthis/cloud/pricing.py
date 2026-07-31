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
    """Turn cost in USD from ALL THREE input counters plus output.

    `input_tokens` is the UNCACHED REMAINDER (measured, see the block above), so
    the cached tokens must be added back at their own rates or the turn is
    under-priced. With no cache activity every cache argument is 0 and the
    arithmetic reduces EXACTLY to the pre-caching formula — which is what lets a
    non-caching provider keep today's behaviour untouched (the DEC-34 shape).
    """
    in_price, out_price = PRICE_TABLE_USD_PER_MTOK.get(model, (3.00, 15.00))
    billable_input = (
        input_tokens
        + cache_read * CACHE_READ_MULTIPLIER
        + cache_write_5m * CACHE_WRITE_5M_MULTIPLIER
        + cache_write_1h * CACHE_WRITE_1H_MULTIPLIER
    )
    return (billable_input * in_price + output_tokens * out_price) / 1_000_000
