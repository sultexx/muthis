# src/muthis/broker/net/robots.py
"""
Robots policy for the hardened fetcher (DEC-17): fetch, parse, and cache
robots.txt per domain, and answer `can_fetch` for the honest MuthisBot agent.
A Disallow is how the fetcher earns its Arabic "open it on your screen and I'll
read it for you" note — the vision-path redirect that showcases LOOK-only
instead of a dead end. Kept apart from the SSRF fetch loop so `fetcher.py`
stays under the ≤300-line law.

robots.txt is fetched through the SAME hardened path (the injected `fetch_text`
seam = the fetcher's own validated fetch), so a robots URL pointing at an
internal address is refused exactly like any other page — robots can never be
an SSRF side-door. A miss / unreachable / unparseable robots defaults to ALLOW
(the crawler standard); only an EXPLICIT Disallow returns False. Pure stdlib.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Optional
from urllib.parse import SplitResult, urlsplit
from urllib.robotparser import RobotFileParser

# (origin_url) -> the decoded robots.txt text, or None when it could not be
# safely / successfully fetched (blocked, unreachable, over cap, ...).
FetchText = Callable[[str], Awaitable[Optional[str]]]


def robots_origin(parts: SplitResult) -> Optional[str]:
    """scheme://host[:port] from a parsed URL, dropping any userinfo; None when
    the host or port is unusable."""
    host = parts.hostname
    if not host:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    netloc = host if port is None else f"{host}:{port}"
    return f"{parts.scheme}://{netloc}"


class RobotsCache:
    """Per-domain robots.txt decisions for the session. `fetch_text` is the
    fetcher's own hardened fetch (so robots is SSRF-guarded too); `enabled`
    lets a test/consumer turn robots off explicitly."""

    def __init__(
        self,
        *,
        fetch_text: FetchText,
        user_agent_token: str,
        enabled: bool = True,
    ) -> None:
        self._fetch_text = fetch_text
        self._token = user_agent_token
        self._enabled = enabled
        self._parsers: dict[str, Optional[RobotFileParser]] = {}

    async def allows(self, url: str) -> bool:
        if not self._enabled:
            return True
        parts = urlsplit(url)
        domain = parts.hostname or ""
        if not domain:
            return True
        if domain not in self._parsers:
            self._parsers[domain] = await self._load(parts)
        parser = self._parsers[domain]
        if parser is None:  # no rules available → allow (the standard)
            return True
        try:
            return parser.can_fetch(self._token, url)
        except Exception:  # noqa: BLE001 — a parser surprise must not block a turn
            return True

    async def _load(self, parts: SplitResult) -> Optional[RobotFileParser]:
        origin = robots_origin(parts)
        if origin is None:
            return None
        text = await self._fetch_text(origin + "/robots.txt")
        if text is None:  # blocked / unreachable → no rules
            return None
        parser = RobotFileParser()
        try:
            parser.parse(text.splitlines())
        except Exception:  # noqa: BLE001
            return None
        return parser


__all__ = ["RobotsCache", "robots_origin", "FetchText"]
