# src/muthis/broker/search/protocol.py
"""
The SearchProvider seam (DEC-18, V2 Roadmap §3.1) — ONE contract, several
vendors, a BLIND consumer.

Built on the proven CloudReasoner pattern (`cloud/protocol.py`): every provider
hides behind this exact interface, selection is a `.env` change, and the consumer
never learns which vendor answered. No third-party deps here, so the contract
imports in isolation (the ≤300-line law) and any test double can implement it.

WHY THE BROKER OWNS THIS — not the plugin, and not `cloud/`:
DEC-17 put the hardened fetcher in the broker because "external plugin code holds
NO OS handle": a plugin receives content, never a socket. The identical argument
holds for search, one step STRONGER — a provider call carries an API KEY, so the
plugin must receive RESULTS and never the key, the client, or the endpoint.
`cloud/` is the REASONER path (the providers the orchestrator streams TextDelta /
ToolCall / TurnComplete from); a search vendor is not a reasoner, so it lives
beside the fetcher in `broker/`, not there. web_research is first-party and eats
the same dogfood, with no privileged path.

THE THIRD CLIENT (the central safety property — mechanics in `client.py`):
the provider client is a THIRD long-lived HTTP client, distinct from BOTH the
DEC-17 hardened fetcher (ZERO-CREDENTIAL BY LAW — a key-bearing call structurally
cannot and must not go through it) and the Anthropic client (the Clicky lesson:
never mix a key-bearing pool with another purpose). Its safety rests on a
DIFFERENT property, enforced structurally: a provider takes a QUERY STRING, never
a URL, and its endpoint is a FIXED host resolved from CONFIGURATION — so no tool
argument and no model input can ever aim it.

RESULTS ARE UNTRUSTED DATA. A title, a snippet and a URL are authored by the page
owner. A provider CARRIES them and does nothing clever with them: it never
follows a result URL, never fetches one, never interprets one. Any URL a result
carries is fetched LATER and ONLY through the DEC-17 hardened fetcher. Injection
defense is the DEC-14 wrapper at the router boundary and taint is raised there
too (DEC-15) — neither is this seam's job, and neither may be weakened here
(DEC-4: security a plugin author can weaken is not security).

NOT HERE, deliberately (stub-first — the DEC-10 precedent):
  * BUDGET RECORDING — `record_plugin_call` lands with the plugin at T6; wiring
    it now would be dead code with no consumer. The per-query cost is EXPOSED
    (`cost_per_query_usd`, `SearchResponse.cost_usd`) so T6 has something to
    record.
  * `recency` (§3.1's optional search argument) — it lands with the tool schema
    at T6, where each vendor's mapping can be tested against a real response.
  * HOW the plugin reaches a provider (the `ctx.net` analogue, DEC-24) — T6.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("muthis.broker.search")

# §3.1 caps a search at 5 results. The seam clamps to it, so a malformed or
# over-wide model argument can never widen the request (defense at the seam, not
# only in the schema the model sees).
MAX_RESULTS = 5

# §3.4 «المقتطفات مسقوفة توكنيًا»: per-result bounds so a verbose — or hostile —
# provider cannot blow the context window. 5 × 1000 chars ≈ 1.2k tokens.
MAX_SNIPPET_CHARS = 1_000
# A result URL longer than this is DROPPED, never truncated: cutting a URL would
# silently produce a DIFFERENT destination, and quietly rewriting untrusted data
# is exactly the "clever" this seam refuses to be.
MAX_URL_CHARS = 2_048

# ─── Seam-level Arabic notes (wire-level notes live in client.py) ─────────────
NO_PROVIDER_AR = "ما فيه مزوّد بحث مضبوط. أضف مفتاح المزوّد في ملف .env وبعدها أقدر أبحث لك."
EMPTY_QUERY_AR = "ما وصلني نص أبحث عنه."
NO_RESULTS_AR = "ما طلعت نتائج لهذا البحث. جرّب صياغة ثانية."


@dataclass(frozen=True)
class SearchResult:
    """ONE hit. UNTRUSTED DATA: title / url / snippet are written by the page
    owner. Carried verbatim (bounded) — never followed, never fetched, never
    interpreted."""

    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True)
class SearchResponse:
    """What the seam hands back — deliberately shaped like `FetchResult` so both
    halves of the web surface degrade identically.

    `ok` means "there is usable material for the model"; on anything else
    `text_ar` is the short Arabic note (Law 11 — no exception ever crosses this
    seam). `cost_usd` is what THIS query cost, exposed for the T6
    `record_plugin_call` (0.0 for free tiers and SearXNG). `provider` names the
    answering vendor for LOGS / attribution the way `TurnComplete` carries
    `model` — the consumer must never branch on it; that is what blind means."""

    ok: bool
    text_ar: str
    results: tuple[SearchResult, ...] = ()
    provider: str = ""
    cost_usd: float = 0.0


@runtime_checkable
class SearchProvider(Protocol):
    """Implemented by every vendor wrapper AND by `NoSearchProvider`.

    Contract:
      * `search()` takes a QUERY STRING — never a URL, never a base URL, never a
        host. The destination is configuration, never an argument.
      * it NEVER raises: every failure is a `SearchResponse` carrying a short
        Arabic note (Law 11 — the wrapper owns no lifecycle beyond its client).
      * `name` and `cost_per_query_usd` are declarations, not behavior.
    """

    name: str
    cost_per_query_usd: float

    async def search(
        self, query: str, *, max_results: int = MAX_RESULTS
    ) -> SearchResponse:
        ...

    async def aclose(self) -> None:
        ...


class NoSearchProvider:
    """The configured-nothing provider — the `stub_read_file` precedent: the seam
    always EXISTS, so a missing key is an ordinary short Arabic note, never an
    exception and never a crash. DEC-18 requires the tool to be present in the
    byte-pinned catalog on EVERY machine, so a missing provider must be a RESULT,
    not a structural difference."""

    name = "none"
    cost_per_query_usd = 0.0

    async def search(
        self, query: str, *, max_results: int = MAX_RESULTS
    ) -> SearchResponse:
        return SearchResponse(ok=False, text_ar=NO_PROVIDER_AR, provider=self.name)

    async def aclose(self) -> None:
        return None


# ─── Shared helpers every provider uses (so the rules live in ONE place) ──────


def clamp_results(max_results: Any) -> int:
    """Bound a requested result count to §3.1's cap. Garbage in → the cap, never
    an exception: the argument reaches here from the model."""
    try:
        wanted = int(max_results)
    except (TypeError, ValueError):
        return MAX_RESULTS
    return max(1, min(wanted, MAX_RESULTS))


def clean_query(query: Any) -> str:
    """The ONLY thing a caller may supply: a query STRING. Non-strings collapse
    to "" (the caller then answers EMPTY_QUERY_AR) — a query is never a URL, a
    dict or anything the provider would have to interpret."""
    return query.strip() if isinstance(query, str) else ""


def results_from_items(items: Any, *, snippet_key: str, limit: int) -> tuple[SearchResult, ...]:
    """Normalize ONE vendor's raw result list into the shared type.

    DEFENSIVE by contract (the `parse_shapes_args` precedent): a non-list, a
    non-dict entry, an entry without a usable URL, or an over-long URL is
    DROPPED — never raises, never guesses, never repairs. Titles and snippets are
    bounded because they are untrusted page-owner text; only the SNIPPET key
    differs between vendors, which is why it is a parameter."""
    if not isinstance(items, list):
        return ()
    out: list[SearchResult] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.strip() or len(url) > MAX_URL_CHARS:
            continue
        out.append(
            SearchResult(
                title=_bounded(item.get("title")),
                url=url.strip(),
                snippet=_bounded(item.get(snippet_key)),
            )
        )
        if len(out) >= limit:
            break
    return tuple(out)


def response_from(
    results: tuple[SearchResult, ...], *, provider: str, cost_usd: float
) -> SearchResponse:
    """Turn normalized results into the seam's response, and log the ONE line a
    provider may log: its name and the result COUNT (the status is logged by the
    client; the QUERY is never logged — it can carry what the user is looking at).

    Zero usable results is not a wire failure, but it IS a dead end for the model,
    so it returns `ok=False` with the Arabic note — while still carrying the cost,
    because the query was served and paid for."""
    logger.info("[search] %s results=%d", provider, len(results))
    if not results:
        return SearchResponse(
            ok=False, text_ar=NO_RESULTS_AR, provider=provider, cost_usd=cost_usd
        )
    return SearchResponse(
        ok=True, text_ar="", results=results, provider=provider, cost_usd=cost_usd
    )


def _bounded(value: Any) -> str:
    """Untrusted text → a bounded str. An ellipsis marks a cut so the model is
    never told a truncated snippet is the whole thing."""
    text = value.strip() if isinstance(value, str) else ""
    if len(text) <= MAX_SNIPPET_CHARS:
        return text
    return text[:MAX_SNIPPET_CHARS] + "…"


__all__ = [
    "MAX_RESULTS", "MAX_SNIPPET_CHARS", "MAX_URL_CHARS",
    "NO_PROVIDER_AR", "EMPTY_QUERY_AR", "NO_RESULTS_AR",
    "SearchResult", "SearchResponse", "SearchProvider", "NoSearchProvider",
    "clamp_results", "clean_query", "results_from_items", "response_from",
]
