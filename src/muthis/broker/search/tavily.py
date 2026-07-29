# src/muthis/broker/search/tavily.py
"""
TavilyProvider — the DEC-18 DEFAULT search provider.

WHY IT IS THE DEFAULT (DEC-18): Tavily returns EXTRACTED CONTENT, not only links,
so it collapses the search→fetch cycle in many cases. Fewer fetches is a NARROWER
SSRF surface — every avoided fetch is an avoided attacker-chosen destination —
plus lower cost and latency. The default is revisable BY LIVE MEASUREMENT, never
by doctrine.

CONFIGURATION-ONLY DESTINATION. `TAVILY_API_KEY` and the optional
`TAVILY_BASE_URL` are read from the environment when the provider is
CONSTRUCTED. Neither is a parameter of `__init__` or of `search()`, so no caller
— and therefore no tool argument and no model input — can supply either. That is
the property that makes a key-bearing client safe, and it is enforced by the
SHAPE of this class, not by convention (`tests/test_search_provider.py` asserts
the signatures, so adding such a parameter turns the guard RED).

WIRE CONTRACT (documented from the vendor's published API; not yet exercised
live — this machine has no key until T7, per DEC-21-F):
    POST {base}/search      Authorization: Bearer <key>
    body  {"query": ..., "max_results": ...}
    reply {"results": [{"title": ..., "url": ..., "content": ...}, ...]}
Parsing is DEFENSIVE (`results_from_items`): a shape change degrades to a short
Arabic note, never an exception (Law 11). The `answer` field Tavily can return is
deliberately IGNORED — it is a model-written summary of untrusted pages, i.e. the
same untrusted material one indirection further from its source, and this seam
carries results, it does not synthesize.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

from .client import SearchHttpClient
from .protocol import (
    EMPTY_QUERY_AR,
    MAX_RESULTS,
    SearchResponse,
    clamp_results,
    clean_query,
    response_from,
    results_from_items,
)

TAVILY_DEFAULT_BASE_URL = "https://api.tavily.com"
TAVILY_SEARCH_PATH = "/search"

# The vendor's published price for ONE basic search at build time; free-tier
# credits cost nothing. Pinned the way claude_agent.py pins
# _PRICE_TABLE_USD_PER_MTOK, and re-pinned the same way when vendor pricing moves
# — confirm at T7 against a real account. It is EXPOSED, not recorded: the
# record_plugin_call wiring lands with the plugin at T6 (stub-first, DEC-10).
TAVILY_COST_PER_QUERY_USD = 0.008


class TavilyProvider:
    """A SearchProvider over Tavily. Stateless per call; owns one client."""

    name = "tavily"
    cost_per_query_usd = TAVILY_COST_PER_QUERY_USD

    def __init__(self, *, client: Optional[httpx.AsyncClient] = None) -> None:
        # The endpoint is CONFIGURATION, fixed for this object's whole life.
        base = (os.getenv("TAVILY_BASE_URL") or TAVILY_DEFAULT_BASE_URL).strip().rstrip("/")
        self._endpoint = base + TAVILY_SEARCH_PATH
        # The key is read here and handed STRAIGHT into the client's headers;
        # this object keeps no reference to it.
        self._http = SearchHttpClient(
            provider=self.name,
            auth_headers={"Authorization": f"Bearer {os.getenv('TAVILY_API_KEY', '')}"},
            client=client,
        )

    async def search(self, query: str, *, max_results: int = MAX_RESULTS) -> SearchResponse:
        """A QUERY STRING in, results or a short Arabic note out. NEVER raises."""
        cleaned = clean_query(query)
        if not cleaned:
            # Refuse before the wire: an empty query buys a paid round-trip and
            # returns nothing useful.
            return SearchResponse(ok=False, text_ar=EMPTY_QUERY_AR, provider=self.name)
        limit = clamp_results(max_results)
        data = await self._http.post_json(
            self._endpoint, json={"query": cleaned, "max_results": limit}
        )
        if isinstance(data, str):  # an Arabic-note failure from the wire layer
            return SearchResponse(ok=False, text_ar=data, provider=self.name)
        results = results_from_items(data.get("results"), snippet_key="content", limit=limit)
        return response_from(results, provider=self.name, cost_usd=self.cost_per_query_usd)

    async def aclose(self) -> None:
        await self._http.aclose()


__all__ = [
    "TavilyProvider",
    "TAVILY_DEFAULT_BASE_URL",
    "TAVILY_SEARCH_PATH",
    "TAVILY_COST_PER_QUERY_USD",
]
