# src/muthis/broker/net/provenance.py
"""
FetchedDomains — the turn-scoped record of what was ACTUALLY read (DEC-20).

WHY THIS OBJECT EXISTS AND WHY IT IS HERE. The domain badge is DEC-20's
DETERMINISTIC BACKSTOP: the one attribution layer the model does not author,
whose job is to expose BOTH a missing citation AND a hallucinated one. So the
fact it draws must not pass through anything the model can influence. The
rejected alternative routed the domain out through the plugin (a `ServiceOutcome`
extras field the PLUGIN populates), which would have placed the guard DOWNSTREAM
of the very output it checks — a fabricated attribution would have drawn its own
corroborating badge. DEC-20's words are "kernel-drawn from REAL provenance", and
that means NOT PLUGIN-AUTHORED. The broker's hardened fetcher is the only place
that knows the answer first-hand, so the fact is recorded there and never
travels through plugin code at all.

That is the same principle this milestone has now applied five times: `is_error`
may not gate the wrap (DEC-29), a declared `read_only` may not drive impact
classification (T5), a plugin may not wrap its own output (DEC-14), a plugin-set
number may not feed the sovereign ledger (DEC-34), and a plugin may not supply
the badge's provenance. WHO OWNS THE FACT.

SHAPE MIRRORS SessionTaint deliberately — a small standalone object built ONCE
at the composition root and INJECTED, rather than state living inside the
fetcher. The fetcher's other state (the LRU cache, the rate limiter) is
PROCESS-scoped; this is TURN-scoped, and burying a turn-scoped lifetime inside a
process-scoped component is exactly how the two get confused. Keeping it separate
makes the lifetime explicit and leaves the fetcher one responsibility.

FETCHES ONLY — search results are EXCLUDED, and that is a CORRECTNESS rule, not
a scope cut. A search returns up to five candidate links the model did NOT read.
Recording them would let a HALLUCINATED citation look verified whenever its
domain happened to appear in the result list, which inverts the badge's entire
purpose. The badge means exactly one thing: "content retrieved and read this
turn." KNOWN LIMIT, recorded rather than hidden: a turn answered from search
SNIPPETS alone therefore shows an EMPTY badge. That is the honest signal — the
model read nothing in depth — but it does mean an empty badge is not by itself
evidence of a fabricated source. T7 observes how it reads live.

INERT UNTIL THE NEXT COMMIT: nothing calls `new_turn()` yet. The single line that
will, from `TurnPass.new_turn_voice`, is kernel wiring, and it serves BOTH this
collector and `FetchGate` — ONE hook with two consumers is not a second
MECHANISM, so DEC-19 is satisfied. Until that line lands, this accumulates for
the whole PROCESS, not per turn. Do not read this guard and believe it.

LOGS NOTHING, structurally: this module imports nothing at all, so it has no
logger to leak from (DEC-20/DEC-28 — the badge is DOMAIN-only precisely because
a full URL can carry the user's private query, and the safest way to keep a
domain out of the log is to have no way to write one).
"""

from __future__ import annotations

# Bounded so a pathological turn cannot grow the record without limit; the
# per-turn fetch cap (FetchGate, 3) already bounds it in practice, so this is a
# second, independent wall rather than the primary one.
MAX_TRACKED_DOMAINS = 8


class FetchedDomains:
    """One per process, reset per turn. Insertion-ordered and de-duplicated:
    order is FETCH order, which is the order the model actually read them in,
    and a page fetched twice is still one source."""

    def __init__(self) -> None:
        self._domains: list[str] = []

    def record(self, domain: str) -> None:
        """Called by the FETCHER on a successful read — never by plugin code.

        Takes a DOMAIN, not a URL: the narrow type is the guard. A caller cannot
        accidentally hand over `?q=<the user's private question>` because there
        is no parameter that would carry it. Blank / non-string input is ignored
        rather than raising (Law 11 — provenance bookkeeping must never be able
        to kill a turn)."""
        if not isinstance(domain, str):
            return
        cleaned = domain.strip().lower()
        if not cleaned or cleaned in self._domains:
            return
        if len(self._domains) >= MAX_TRACKED_DOMAINS:
            return
        self._domains.append(cleaned)

    def domains(self) -> tuple[str, ...]:
        """What was read this turn, in fetch order. A defensive copy: the badge
        renders from it and must not be able to mutate the record."""
        return tuple(self._domains)

    def new_turn(self) -> None:
        """Start a fresh turn with an empty record. Named for the hook that will
        call it (`TurnPass.new_turn_voice`) so the wiring reads as one thing."""
        self._domains.clear()


__all__ = ["FetchedDomains", "MAX_TRACKED_DOMAINS"]
