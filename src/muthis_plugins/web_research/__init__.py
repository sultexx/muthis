# src/muthis_plugins/web_research/__init__.py
"""web_research — the web surface: search for sources, then read ONE at a time.

V2 Phase 2, Milestone 2 (T6a). A first-party NATIVE plugin that eats the same
dogfood as any community plugin would: it holds no key, no client, no endpoint
and no socket, and reaches the network only through the broker-owned
`ctx.net.fetch_readable` capability (DEC-17 / DEC-24). The search provider is
INJECTED, never a capability (DEC-27).
"""

from .fetch_gate import FetchGate, MAX_FETCHES_PER_TURN
from .plugin import WebResearchPlugin

__all__ = ["WebResearchPlugin", "FetchGate", "MAX_FETCHES_PER_TURN"]
