"""
pricing.py — the USD price table and the per-turn cost arithmetic.

Extracted from claude_agent.py under the answer agreed at PLANNING time
(DEC-23 / DEC-59): when the prompt-caching slice pushes claude_agent.py past
the ≤300-line ceiling, the price table and the cost function move here
TOGETHER, because they are ONE responsibility with no dependency on the
streaming path, the HTTP client, or the tool catalog. The answer was agreed in
advance precisely so that a breach is a decision and not a debate.

THIS COMMIT IS MECHANICAL. The table and the arithmetic are unchanged, and no
caller's behaviour moves. The single edit is that the former method reads
`model` from an argument instead of `self.model`, because a module-level
function has no `self`.

budget.py remains the SOVEREIGN consumer of these numbers (Law 10). This
module computes only what TurnComplete carries; it owns no ledger, no ceiling,
and no policy.
"""

from __future__ import annotations

# USD per 1M tokens (input, output). Pricing reality check.
# budget.py is the sovereign consumer of these numbers; this table only
# annotates TurnComplete. Re-pin on every model rev (the DEC-26 discipline).
PRICE_TABLE_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (5.00, 25.00),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = PRICE_TABLE_USD_PER_MTOK.get(model, (3.00, 15.00))
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000
