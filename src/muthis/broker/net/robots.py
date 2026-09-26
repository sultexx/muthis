# src/muthis/broker/net/robots.py
"""
Robots policy for the hardened fetcher (DEC-17): fetch, parse, and cache
robots.txt per domain, and decide — for the honest MuthisBot agent — whether a
URL may be fetched. A refusal is how the fetcher earns its Arabic "open it on
your screen and I'll read it for you" note — the vision-path redirect that
showcases LOOK-only instead of a dead end. Kept apart from the SSRF fetch loop
so `fetcher.py` stays under the ≤300-line law.

robots.txt is fetched through the SAME hardened path (the injected `fetch_text`
seam = the fetcher's own validated fetch), so a robots URL pointing at an
internal address is refused exactly like any other page — robots can never be
an SSRF side-door.

WHAT A ROBOTS.TXT FETCH MEANS — RFC 9309 §2.3.1, sorted by the seam:
  * a 2xx: the rules are parsed and obeyed; a line that does not parse is
    skipped and the rest are used (§2.3.1.5);
  * a 4xx, or more than five redirects: "unavailable" — the crawler MAY access
    anything (§2.3.1.3, §2.3.1.2), so the URL is allowed;
  * a 5xx or a network failure: "unreachable" — the crawler MUST assume
    COMPLETE DISALLOW (§2.3.1.4). The seam hands back a `Refusal` carrying the
    note the model reads, and it is NEVER cached: an outage is a state, not a
    rule, so the next fetch asks again;
  * a refusal of OUR OWN reads no rules and allows: after the SSRF guard, the
    page fetch meets the same guard next, with its own note; after the 2 MB
    cap, see the limits below.

HONEST LIMITS — RFC 9309 clauses this module does NOT meet, recorded so that no
comment here claims more than the code does. The matcher is the stdlib
`RobotFileParser`, which predates the RFC: a path rule matches as a plain
prefix, with no `*` or `$` (§2.2.3: MUST support both); the FIRST matching rule
wins, not the most specific (§2.2.2); the agent token matches as a substring,
and only the first matching group is read where §2.2.1 combines them. Rules are
cached for the process, where §2.4 says a copy SHOULD NOT outlive 24 hours. A
robots.txt over the 2 MB cap is refused whole, so it allows, where §2.5 asks
that at least the first 500 KiB be parsed. Pure stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union
from urllib.parse import SplitResult, urlsplit
from urllib.robotparser import RobotFileParser

# WHY a URL is refused — the tag the fetcher logs; the model reads `note`.
DISALLOWED = "disallowed"    # an explicit rule for this agent and path
UNREACHABLE = "unreachable"  # §2.3.1.4: a 5xx or a network failure


@dataclass(frozen=True)
class Refusal:
    """A refused URL: why (`DISALLOWED` / `UNREACHABLE`) and the note the model
    reads. An instance is always truthy, so no refusal can pass as allowed."""

    reason: str
    note: str


# (robots_url) -> the decoded rules on a 2xx; an UNREACHABLE `Refusal` on a 5xx
# or a network failure; None when there are no rules to obey (a 4xx, the
# redirect cap, a refusal of ours).
FetchText = Callable[[str], Awaitable[Union[str, Refusal, None]]]


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
    fetcher's own hardened fetch (so robots is SSRF-guarded too); an explicit
    Disallow is refused with `disallowed_note`; `enabled` lets a test/consumer
    turn robots off explicitly."""

    def __init__(
        self,
        *,
        fetch_text: FetchText,
        user_agent_token: str,
        disallowed_note: str,
        enabled: bool = True,
    ) -> None:
        self._fetch_text = fetch_text
        self._token = user_agent_token
        self._disallowed = Refusal(DISALLOWED, disallowed_note)
        self._enabled = enabled
        self._parsers: dict[str, Optional[RobotFileParser]] = {}

    async def refusal(self, url: str) -> Optional[Refusal]:
        """None when `url` may be fetched; otherwise why not, and the note."""
        if not self._enabled:
            return None
        parts = urlsplit(url)
        domain = parts.hostname or ""
        if not domain:
            return None
        if domain not in self._parsers:
            loaded = await self._load(parts)
            if isinstance(loaded, Refusal):  # unreachable — NEVER cached (§2.3.1.4)
                return loaded
            self._parsers[domain] = loaded
        parser = self._parsers[domain]
        if parser is None:  # no rules to obey — unavailable (§2.3.1.3) → allow
            return None
        try:
            return None if parser.can_fetch(self._token, url) else self._disallowed
        except Exception:  # noqa: BLE001 — a parser surprise must not block a turn
            return None

    async def _load(self, parts: SplitResult) -> Union[RobotFileParser, Refusal, None]:
        origin = robots_origin(parts)
        if origin is None:
            return None
        text = await self._fetch_text(origin + "/robots.txt")
        if text is None or isinstance(text, Refusal):  # no rules / unreachable
            return text
        parser = RobotFileParser()
        try:
            parser.parse(text.splitlines())
        except Exception:  # noqa: BLE001
            return None
        return parser


__all__ = ["RobotsCache", "Refusal", "DISALLOWED", "UNREACHABLE", "robots_origin", "FetchText"]
