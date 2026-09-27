"""
stats.py — exact small-sample statistics for binary per-run outcomes.

Fisher's exact test, two-sided (the tables no more probable than the one
observed), and the detection limits the design's ② table declared. Exact over
every outcome; no normal approximation, because at the run counts ruled (40 per
configuration) an approximation would move the very boundary being reported.
"""

from __future__ import annotations

from functools import lru_cache
from math import comb

ALPHA = 0.05


@lru_cache(maxsize=None)
def fisher_p(x: int, n1: int, y: int, n2: int) -> float:
    """Two-sided p for x of n1 against y of n2."""
    t, total = x + y, n1 + n2
    probs = {a: comb(n1, a) * comb(n2, t - a) / comb(total, t)
             for a in range(max(0, t - n2), min(n1, t) + 1)}
    observed = probs[x]
    return min(1.0, sum(p for p in probs.values() if p <= observed * (1 + 1e-9)))


def binom(n: int, k: int, p: float) -> float:
    return comb(n, k) * p ** k * (1 - p) ** (n - k)


def power(n: int, pa: float, pb: float) -> float:
    """Probability that Fisher's test at ALPHA separates true rates pa and pb."""
    return sum(binom(n, x, pa) * binom(n, y, pb)
               for x in range(n + 1) for y in range(n + 1) if fisher_p(x, n, y, n) < ALPHA)


def smallest_drop(n: int, base: float, target: float = 0.8) -> float | None:
    """The smallest drop from `base` detectable with `target` power at n per arm."""
    for step in range(1, 101):
        pb = base - step / 100
        if pb < 0:
            return None
        if power(n, base, pb) >= target:
            return step / 100
    return None


def compare_counts(xa: int, na: int, xb: int, nb: int) -> dict:
    p = fisher_p(xa, na, xb, nb) if na and nb else 1.0
    return {"a": f"{xa} of {na}", "b": f"{xb} of {nb}", "p": round(p, 4),
            "separated": p < ALPHA}


__all__ = ["ALPHA", "binom", "compare_counts", "fisher_p", "power", "smallest_drop"]
