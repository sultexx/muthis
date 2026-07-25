# src/muthis/kernel/router_registry.py
"""
MountedRoute — the record of ONE mounted route, extracted from tool_router.py
under the ≤300-line law (T5, 2026-07-25).

A PURE MOVE, proven byte-identical by diff: only the class NAME changed, because
the name now crosses a module boundary and a leading underscore would be a
promise of privacy the import already breaks. Every field, default, comment and
the docstring are the originals.

WHY THIS ONE, and why only this one. The confirm gate (DEC-16) is the third
security consequence to land at `ToolRouter.service()`, and its call site pushed
the file to 301/300. `MountedRoute` is the cheapest thing there that is genuinely
a separate idea — a passive RECORD of what a mount decided (what the model sees,
how to reach the plugin, and the kernel's own taint / impact classification),
carrying no behaviour at all — so moving it costs the dispatch file nothing it
needs to reason about. The larger registration/dispatch split (`mount()` moving
here too) is PRE-APPROVED for the next time the router needs headroom, most
likely a T7 fix; it is deliberately NOT taken now, because it is a refactor
rather than a move and landing one immediately before an authorization gate would
muddy attribution if anything later broke.

RE-EXPORTED from tool_router.py: the dependency runs dispatch → record, so
nothing cycles (contrast `core_router.py`, where it ran the other way — DEC-30).

Pure stdlib + the SDK's value types; importable in isolation.
"""

from __future__ import annotations

import dataclasses

from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin

from ..trust.high_impact import RouteImpact


@dataclasses.dataclass(frozen=True)
class MountedRoute:
    """One mounted route: the exposed descriptor + how to reach its plugin."""

    descriptor: ToolDescriptor  # as offered to the model (already namespaced)
    bare_name: str              # the plugin's own view of the tool name
    plugin: ToolPlugin
    ctx: PluginContext
    provenance: str
    taint: bool = False         # external route (MCP): outcomes untrusted by definition
    impact: RouteImpact = RouteImpact()  # DEC-15 facts, mounter-assigned (inert)


__all__ = ["MountedRoute"]
