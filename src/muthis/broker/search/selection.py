# src/muthis/broker/search/selection.py
"""
Provider selection — the `.env` switch (DEC-18).

Selection is CONFIGURATION, exactly like the CloudReasoner router this seam is
modelled on: swapping vendors is an `.env` edit, never a code change, and the
consumer never learns which one answered. Nothing here is reachable from a tool
argument or from model input — a provider (and therefore an endpoint) is chosen
by the machine's owner, before any turn runs.

ORDER:
  1. `MUTHIS_SEARCH_PROVIDER` names one explicitly. If it is named but NOT
     configured, that is a configuration mistake: say so in the log and degrade
     to the no-provider note — never silently answer with a different vendor than
     the one that was asked for.
  2. Otherwise auto-detect. The order is DERIVED, not invented: Tavily first
     because DEC-18 makes it the DEFAULT, then the roadmap §3.1 enumeration
     («نشحن Tavily وBrave … وSearXNG»). When several are configured the log names
     the one that answered, and `MUTHIS_SEARCH_PROVIDER` is the explicit override.
  3. Otherwise NO provider — the ordinary short Arabic note, never an exception.

NOTHING IS ECHOED FROM THE ENVIRONMENT into the logs — not even an unrecognized
provider name. A user who pastes a key into the wrong variable must not have it
logged; the valid names are listed instead, which is the useful half anyway.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional

import httpx

from .brave import BraveProvider
from .protocol import NoSearchProvider, SearchProvider
from .searxng import SearxngProvider
from .tavily import TavilyProvider

logger = logging.getLogger("muthis.broker.search")

Builder = Callable[..., SearchProvider]
Configured = Callable[[], bool]

# name -> (is it configured?, how to build it). A provider is "configured" when
# the .env holds what it NEEDS: a key for the commercial vendors, a base URL for
# SearXNG — which needs no key at all, and for which no default is ever invented
# (an unset base URL means the user has not made that trust decision).
_PROVIDERS: dict[str, tuple[Configured, Builder]] = {
    "tavily": (lambda: bool(os.getenv("TAVILY_API_KEY", "").strip()), TavilyProvider),
    "brave": (lambda: bool(os.getenv("BRAVE_API_KEY", "").strip()), BraveProvider),
    "searxng": (lambda: bool(os.getenv("SEARXNG_BASE_URL", "").strip()), SearxngProvider),
}

# Auto-detection order. Tavily first because DEC-18 makes it the DEFAULT (it
# returns extracted content, so it collapses the search→fetch cycle — a narrower
# SSRF surface, lower cost and latency); the rest follow the roadmap §3.1
# enumeration, so the order is derived from the governing documents rather than
# chosen here. An explicit MUTHIS_SEARCH_PROVIDER always overrides it.
_AUTO_ORDER: tuple[str, ...] = ("tavily", "brave", "searxng")


def build_search_provider(*, client: Optional[httpx.AsyncClient] = None) -> SearchProvider:
    """Build the provider this machine is configured for. ALWAYS returns a
    SearchProvider — `NoSearchProvider` when nothing is configured — so the
    consumer has no missing-seam case to handle (the `stub_read_file`
    precedent). Never raises."""
    chosen = os.getenv("MUTHIS_SEARCH_PROVIDER", "").strip().lower()
    if chosen:
        return _explicit(chosen, client)
    return _auto(client)


def _explicit(name: str, client: Optional[httpx.AsyncClient]) -> SearchProvider:
    entry = _PROVIDERS.get(name)
    if entry is None:
        logger.warning(
            "[search] MUTHIS_SEARCH_PROVIDER is not a known provider (expected one of %s)"
            " -- no search provider",
            sorted(_PROVIDERS),
        )
        return NoSearchProvider()
    configured, build = entry
    if not configured():
        logger.warning("[search] provider=%s selected but not configured in .env"
                       " -- no search provider", name)
        return NoSearchProvider()
    logger.info("[search] provider=%s (explicit)", name)
    return build(client=client)


def _auto(client: Optional[httpx.AsyncClient]) -> SearchProvider:
    for name in _AUTO_ORDER:
        configured, build = _PROVIDERS[name]
        if configured():
            logger.info("[search] provider=%s (auto)", name)
            return build(client=client)
    logger.info("[search] no provider configured -- web search answers with a note")
    return NoSearchProvider()


__all__ = ["build_search_provider"]
