# src/muthis/broker/search/client.py
"""
SearchHttpClient — the THIRD long-lived HTTP client (DEC-18) and the seam's
never-raise wall.

WHY A THIRD CLIENT. The DEC-17 hardened fetcher is ZERO-CREDENTIAL BY LAW, so a
provider call — which MUST carry an API key — structurally cannot go through it,
and must not: the fetcher's whole safety argument is that it carries nothing
worth stealing to an attacker-chosen address. It equally must not share the
Anthropic client (the Clicky lesson — never mix a key-bearing pool with another
purpose). So a provider call runs on its OWN client, and its safety rests on a
DIFFERENT property, enforced structurally:

  THE DESTINATION IS NOT ATTACKER-INFLUENCEABLE.
  * The endpoint is a FIXED host taken from CONFIGURATION (`.env`), resolved once
    when the provider is constructed. It is never a tool argument, never model
    input, never derived from fetched content. (This matters most for SearXNG,
    whose base URL is user-supplied and legitimately private/localhost — a
    destination the hardened fetcher blocks BY DESIGN. That is correct for a
    USER-CONFIGURED trust decision; if a base URL could ever arrive from a tool
    argument, a tainted model could aim this key-bearing client at an internal
    service and use it as an SSRF proxy, bypassing every DEC-17 guard.)
  * A provider takes a QUERY STRING; the query rides in the request BODY or as a
    parameter, so it can never become the destination.
  * `follow_redirects=False` — a redirect would move a key-bearing request OFF
    the configured host, which is exactly the property being protected. A
    redirect therefore surfaces as an ordinary non-2xx → Arabic note.
  * `trust_env=False` — no ambient proxy / NETRC / host env may re-route it (the
    hardened fetcher's posture, kept).

THE KEY NEVER LEAVES THIS OBJECT. It is folded into the auth headers ONCE at
construction; providers hold no reference to it, and it is never logged, never in
an error message, never in a returned Arabic note. Logs carry the provider name,
the HTTP status and (from the provider) the result count — nothing else. In
particular an httpx exception's MESSAGE is never formatted into a log line: it
can contain the request URL, which for a GET provider embeds the user's QUERY
(the DEC-20 never-log-content discipline — a query can carry what is on the
user's screen), so only the exception TYPE is logged. A response BODY is never
logged either: a 401 body can echo the key back.

NEVER RAISES (Law 11): every wire failure returns a short Arabic note instead.
ONE request, no redirects — so the httpx timeout IS the total budget for a search
(the DEC-22 lesson: know what your total actually is; there is no redirect chain
and no second lookup to hide behind it).
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional, Union

import httpx

logger = logging.getLogger("muthis.broker.search")

# One request, no redirects → this IS the whole-operation budget (DEC-22 posture).
SEARCH_TIMEOUT_S = 10.0

# ─── Wire-level Arabic notes (seam-level notes live in protocol.py) ───────────
SEARCH_TIMEOUT_AR = "خدمة البحث تأخرت وانتهت المهلة. جرّب مرة ثانية."
SEARCH_FAILED_AR = "ما قدرت أوصل لخدمة البحث. تأكد من الاتصال أو جرّب بعد شوي."
SEARCH_MALFORMED_AR = "رد خدمة البحث جاء بصيغة ما أفهمها. جرّب مرة ثانية."


def build_search_client(*, timeout_s: float = SEARCH_TIMEOUT_S) -> httpx.AsyncClient:
    """The one long-lived key-bearing client, configured per the rules above."""
    return httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(timeout_s),
    )


class SearchHttpClient:
    """Owns the key and the wire. A provider hands it a fixed URL plus a payload
    and gets back parsed JSON or an Arabic note — never an exception."""

    def __init__(
        self,
        *,
        provider: str,
        auth_headers: Optional[Mapping[str, str]] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._provider = provider
        # The key lives HERE and nowhere else. Providers never keep a reference.
        self._headers = {"Accept": "application/json", **dict(auth_headers or {})}
        # An injected client is a COMPOSITION-ROOT / test seam (the HardenedFetcher
        # pattern). It cannot re-aim the request: every call passes an ABSOLUTE
        # URL, and httpx only applies a client base_url to a RELATIVE one.
        self._client = client or build_search_client()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_json(self, url: str, *, params: dict[str, Any]) -> Union[dict[str, Any], str]:
        return await self._json("GET", url, params=params)

    async def post_json(self, url: str, *, json: dict[str, Any]) -> Union[dict[str, Any], str]:
        return await self._json("POST", url, json=json)

    async def _json(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json: Optional[dict[str, Any]] = None,
    ) -> Union[dict[str, Any], str]:
        """One request to the CONFIGURED endpoint → a JSON object or an Arabic
        note. Each failure class gets its OWN note, so a removed branch changes
        the observable answer (DEC-12: a guard whose removal is invisible is not
        a guard)."""
        try:
            resp = await self._client.request(
                method, url, params=params, json=json, headers=self._headers
            )
        except httpx.TimeoutException:
            logger.info("[search] %s timeout", self._provider)
            return SEARCH_TIMEOUT_AR
        except httpx.HTTPError as exc:
            # TYPE only — an httpx message can carry the URL, and a GET URL
            # carries the user's query.
            logger.info("[search] %s transport-error (%s)", self._provider, type(exc).__name__)
            return SEARCH_FAILED_AR
        except Exception as exc:  # noqa: BLE001 — a search must never kill the turn
            logger.warning("[search] %s unexpected error (%s)", self._provider, type(exc).__name__)
            return SEARCH_FAILED_AR

        if resp.status_code >= 300:
            # Includes 401/403 (a bad key) and every 3xx: a redirect is REFUSED,
            # not followed, so the key never travels off the configured host. The
            # body is never read into the log — a 401 body can echo the key.
            logger.info("[search] %s status=%s", self._provider, resp.status_code)
            return SEARCH_FAILED_AR
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001 — HTML error pages, truncated bodies, ...
            logger.info("[search] %s malformed status=%s", self._provider, resp.status_code)
            return SEARCH_MALFORMED_AR
        if not isinstance(data, dict):
            logger.info("[search] %s malformed status=%s", self._provider, resp.status_code)
            return SEARCH_MALFORMED_AR
        logger.info("[search] %s status=%s", self._provider, resp.status_code)
        return data


__all__ = [
    "SEARCH_TIMEOUT_S",
    "SEARCH_TIMEOUT_AR", "SEARCH_FAILED_AR", "SEARCH_MALFORMED_AR",
    "build_search_client", "SearchHttpClient",
]
