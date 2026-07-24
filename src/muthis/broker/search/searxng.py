# src/muthis/broker/search/searxng.py
"""
SearxngProvider — the MAXIMUM-PRIVACY option behind the SAME seam (DEC-18).

NO KEY, SELF-HOSTED. SearXNG is a metasearch engine the user runs themselves, so
the query never reaches a commercial search vendor and nothing is billed:
`cost_per_query_usd` is 0.0 BY CONSTRUCTION, not by a pinned price (DEC-26 — there
is no vendor to bill and therefore nothing to verify at T7). It is the documented
exit for the §8.6 privacy disclosure that search queries otherwise leave the
machine. It carries NO credential of any kind — no key, no token, no cookie — so
this is the one provider whose request has no auth header at all.

WHY THIS PROVIDER MAY POINT AT A PRIVATE ADDRESS WHILE THE FETCHER MAY NOT
──────────────────────────────────────────────────────────────────────────
`SEARXNG_BASE_URL` legitimately points at `http://localhost:8888` or a private
LAN address — exactly the class of destination the DEC-17 hardened fetcher
BLOCKS BY DESIGN (loopback / private / link-local, validated on IP OBJECTS after
one resolve). The two are not in conflict, because the SOURCE of the address is
categorically different:

  * The FETCHER's URL arrives from the MODEL, which reads untrusted web content.
    Under DEC-15 that content is TAINTED, so its address is attacker-influenced;
    a private destination there is an SSRF attempt and is refused.
  * THIS provider's base URL arrives from `.env` — a TRUST DECISION THE MACHINE'S
    OWNER MADE, before any turn ran, about a service they themselves run. Sultan
    pointing Mut'his at his own SearXNG is not an attack on Sultan.

That distinction is only sound while the base URL is STRUCTURALLY UNREACHABLE
from any caller. If it could ever arrive from a tool argument, a TAINTED model
could aim this provider at an internal service and use it as an SSRF PROXY —
bypassing every DEC-17 guard through the one client that is deliberately NOT
hardened, and which (unlike the fetcher) may hold a credential for other vendors.
So the invariant is absolute and enforced by SHAPE, not convention: the base URL
is CONFIGURATION-ONLY — never an `__init__` parameter, never a `search()`
parameter, never a tool argument, never model input.
`tests/test_search_provider.py` asserts it for this provider by name.

WIRE CONTRACT: GET {base}/search?q=...&format=json  (the instance must have the
JSON format enabled in its own settings — a self-hosting choice we cannot make
for the user; when it is not enabled the reply is not JSON and degrades to the
ordinary malformed-response note, never an exception). The reply shape is
{"results": [{"title", "url", "content"}, ...]}. SearXNG has NO result-count
parameter, so §3.1's cap is applied when normalizing — the seam still guarantees
at most MAX_RESULTS either way.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

from .client import SearchHttpClient
from .protocol import (
    EMPTY_QUERY_AR,
    MAX_RESULTS,
    NO_PROVIDER_AR,
    SearchResponse,
    clamp_results,
    clean_query,
    response_from,
    results_from_items,
)

SEARXNG_SEARCH_PATH = "/search"

# Self-hosted: there is no vendor to bill. 0.0 by construction (DEC-26).
SEARXNG_COST_PER_QUERY_USD = 0.0


class SearxngProvider:
    """A SearchProvider over a user-run SearXNG instance. Owns one client."""

    name = "searxng"
    cost_per_query_usd = SEARXNG_COST_PER_QUERY_USD

    def __init__(self, *, client: Optional[httpx.AsyncClient] = None) -> None:
        # The endpoint is CONFIGURATION — the user's own instance — fixed for
        # this object's whole life. There is no default: an unset base URL means
        # the user has not made the trust decision, and we invent one for them
        # under no circumstances.
        base = (os.getenv("SEARXNG_BASE_URL") or "").strip().rstrip("/")
        self._endpoint = base + SEARXNG_SEARCH_PATH if base else ""
        # NO auth headers: the privacy option carries no credential at all.
        self._http = SearchHttpClient(provider=self.name, client=client)

    async def search(self, query: str, *, max_results: int = MAX_RESULTS) -> SearchResponse:
        """A QUERY STRING in, results or a short Arabic note out. NEVER raises."""
        if not self._endpoint:
            # Unlike a missing KEY (which the vendor answers with a 401), a
            # missing base URL leaves nowhere to send anything — so say the
            # honest thing rather than firing a doomed request.
            return SearchResponse(ok=False, text_ar=NO_PROVIDER_AR, provider=self.name)
        cleaned = clean_query(query)
        if not cleaned:
            return SearchResponse(ok=False, text_ar=EMPTY_QUERY_AR, provider=self.name)
        limit = clamp_results(max_results)
        # The query rides as a PARAMETER of the configured endpoint; it can never
        # become the destination.
        data = await self._http.get_json(
            self._endpoint, params={"q": cleaned, "format": "json"}
        )
        if isinstance(data, str):  # an Arabic-note failure from the wire layer
            return SearchResponse(ok=False, text_ar=data, provider=self.name)
        # No count parameter exists upstream, so the cap is enforced HERE.
        results = results_from_items(data.get("results"), snippet_key="content", limit=limit)
        return response_from(results, provider=self.name, cost_usd=self.cost_per_query_usd)

    async def aclose(self) -> None:
        await self._http.aclose()


__all__ = [
    "SearxngProvider",
    "SEARXNG_SEARCH_PATH",
    "SEARXNG_COST_PER_QUERY_USD",
]
