# src/muthis/broker/search/brave.py
"""
BraveProvider — the keyed alternative behind the SAME seam (DEC-18).

It differs from Tavily in exactly two places, both of them local: the request
shape (GET with query PARAMETERS and an `X-Subscription-Token` header, not a POST
with a Bearer header) and the reply shape (results nested under `web`, with the
snippet in `description`). Everything else — the never-raise wall, the untrusted
normalization, the caps, the notes — is the shared seam. That is what
"provider-blind consumer" means in practice: swapping vendors changes NOTHING
above this file, and there is no behavioral special-casing anywhere downstream.

Brave returns LINKS + snippets, not extracted page content, so a follow-up fetch
is more often needed than with Tavily (DEC-18's reason for the default). Any such
fetch goes through the DEC-17 hardened fetcher — never from here.

CONFIGURATION-ONLY DESTINATION: `BRAVE_API_KEY` and the optional `BRAVE_BASE_URL`
are read from the environment when the provider is CONSTRUCTED. Neither is a
parameter of `__init__` or of `search()`, so no caller — and therefore no tool
argument and no model input — can supply either. `tests/test_search_provider.py`
asserts the signatures, so adding such a parameter turns the guard RED.

WIRE CONTRACT (documented from the vendor's published API; DOC-DERIVED and
verified at T7 with a real key — DEC-26):
    GET {base}/res/v1/web/search?q=...&count=N     X-Subscription-Token: <key>
    reply {"web": {"results": [{"title", "url", "description"}, ...]}}
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

BRAVE_DEFAULT_BASE_URL = "https://api.search.brave.com"
BRAVE_SEARCH_PATH = "/res/v1/web/search"

# DOC-DERIVED (DEC-26): the vendor's published base per-query price. The free
# tier costs 0, and pinning the PAID figure is deliberate — for a sovereign
# ledger over-attribution stops the day early (safe), under-attribution
# overspends (unsafe). Verified at T7 against a real account; EXPOSED here, and
# recorded only at T6 (stub-first, DEC-10).
BRAVE_COST_PER_QUERY_USD = 0.005


class BraveProvider:
    """A SearchProvider over the Brave Search API. Owns one client."""

    name = "brave"
    cost_per_query_usd = BRAVE_COST_PER_QUERY_USD

    def __init__(self, *, client: Optional[httpx.AsyncClient] = None) -> None:
        # The endpoint is CONFIGURATION, fixed for this object's whole life.
        base = (os.getenv("BRAVE_BASE_URL") or BRAVE_DEFAULT_BASE_URL).strip().rstrip("/")
        self._endpoint = base + BRAVE_SEARCH_PATH
        # The key goes STRAIGHT into the client's headers; this object keeps no
        # reference to it.
        self._http = SearchHttpClient(
            provider=self.name,
            auth_headers={"X-Subscription-Token": os.getenv("BRAVE_API_KEY", "")},
            client=client,
        )

    async def search(self, query: str, *, max_results: int = MAX_RESULTS) -> SearchResponse:
        """A QUERY STRING in, results or a short Arabic note out. NEVER raises."""
        cleaned = clean_query(query)
        if not cleaned:
            return SearchResponse(ok=False, text_ar=EMPTY_QUERY_AR, provider=self.name)
        limit = clamp_results(max_results)
        # The query rides as a PARAMETER of the fixed endpoint — it can never
        # become the destination (a GET is the shape where that would matter).
        data = await self._http.get_json(self._endpoint, params={"q": cleaned, "count": limit})
        if isinstance(data, str):  # an Arabic-note failure from the wire layer
            return SearchResponse(ok=False, text_ar=data, provider=self.name)
        results = results_from_items(
            _web_results(data), snippet_key="description", limit=limit
        )
        return response_from(results, provider=self.name, cost_usd=self.cost_per_query_usd)

    async def aclose(self) -> None:
        await self._http.aclose()


def _web_results(data: dict) -> object:
    """Brave nests its hits under `web`. Reach in DEFENSIVELY — a reply without
    that object (an ad-only or error-shaped response) yields nothing to
    normalize, which becomes the ordinary no-results note, never an exception."""
    web = data.get("web")
    return web.get("results") if isinstance(web, dict) else None


__all__ = [
    "BraveProvider",
    "BRAVE_DEFAULT_BASE_URL",
    "BRAVE_SEARCH_PATH",
    "BRAVE_COST_PER_QUERY_USD",
]
