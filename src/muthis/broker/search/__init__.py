# src/muthis/broker/search/__init__.py
"""
The broker-owned SearchProvider seam (DEC-18) — the second half of the
`web_research` machine, beside the hardened fetcher in `broker/net/`.

The consumer is BLIND to which vendor answered: one protocol (`protocol.py`),
one key-bearing client (`client.py`), one `.env` switch (`selection.py`), and a
vendor module per provider. A provider takes a QUERY STRING and answers with
results or a short Arabic note — never an exception (Law 11), never a socket,
never the key.

Nothing here is wired into a plugin yet: HOW `web_research` reaches a provider
(the `ctx.net` analogue, DEC-24), the model-visible tool, the taint + wrapping at
the router (DEC-14/15), the citation laws (DEC-20) and budget recording all
arrive with their first consumer — stub-first (Law §3.5): this task builds the
machine, not its consumer.
"""

from __future__ import annotations

from .client import (
    SEARCH_FAILED_AR,
    SEARCH_MALFORMED_AR,
    SEARCH_TIMEOUT_AR,
    SEARCH_TIMEOUT_S,
    SearchHttpClient,
    build_search_client,
)
from .protocol import (
    EMPTY_QUERY_AR,
    MAX_RESULTS,
    MAX_SNIPPET_CHARS,
    MAX_URL_CHARS,
    NO_PROVIDER_AR,
    NO_RESULTS_AR,
    NoSearchProvider,
    SearchProvider,
    SearchResponse,
    SearchResult,
    clamp_results,
    clean_query,
    response_from,
    results_from_items,
)
from .selection import build_search_provider
from .tavily import (
    TAVILY_COST_PER_QUERY_USD,
    TAVILY_DEFAULT_BASE_URL,
    TAVILY_SEARCH_PATH,
    TavilyProvider,
)

__all__ = [
    # contract
    "SearchProvider",
    "SearchResponse",
    "SearchResult",
    "NoSearchProvider",
    "MAX_RESULTS",
    "MAX_SNIPPET_CHARS",
    "MAX_URL_CHARS",
    "clamp_results",
    "clean_query",
    "results_from_items",
    "response_from",
    # seam-level notes
    "NO_PROVIDER_AR",
    "EMPTY_QUERY_AR",
    "NO_RESULTS_AR",
    # the key-bearing client + its wire-level notes
    "SearchHttpClient",
    "build_search_client",
    "SEARCH_TIMEOUT_S",
    "SEARCH_TIMEOUT_AR",
    "SEARCH_FAILED_AR",
    "SEARCH_MALFORMED_AR",
    # selection + providers
    "build_search_provider",
    "TavilyProvider",
    "TAVILY_DEFAULT_BASE_URL",
    "TAVILY_SEARCH_PATH",
    "TAVILY_COST_PER_QUERY_USD",
]
