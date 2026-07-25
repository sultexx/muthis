# src/muthis/kernel/router_registry.py
"""
The router's REGISTRATION half: `MountedRoute` (the record of ONE mounted route)
and `mount_plugin` (what puts one there), both extracted from tool_router.py
under the ≤300-line law.

TWO EXTRACTIONS, ONE SEAM. `MountedRoute` moved first (T5, 2026-07-25) as a pure
byte-identical move — only the class NAME changed, because the name now crosses a
module boundary and a leading underscore would be a promise of privacy the import
already breaks. `mount_plugin` followed (T6b, 2026-07-25) as the pre-approved
successor, when the DEC-34 cost bridge needed headroom in the dispatch file. The
seam they share is real: REGISTRATION (what exists, under what name, with which
kernel-assigned facts) is a different question from DISPATCH (what happens when a
call arrives) — and dispatch is where the three security consequences live (the
DEC-14 wrap, the DEC-15 raise, the DEC-16 confirmation), so keeping it short
enough to read whole is the point of both moves.

`mount_plugin` is BEHAVIOUR-identical, not byte-identical: a method that mutated
`self._routes` becomes a function that takes the registry. That is the whole
delta — every line of the body, the collision check, the namespacing and the
record construction are the originals, and `ToolRouter.mount` remains as a
delegating wrapper so no caller changed. Equivalence was proven the way the
invariant's shape demands rather than by a green suite: every field of every
MountedRoute, plus registry ORDER and ctx identity SHARING, was dumped across six
real compositions before and after the move and required to be byte-identical
JSON (including the collision ValueError's message and the failed mount leaving
the registry untouched).

RE-EXPORTED from tool_router.py: the dependency runs dispatch → registry, so
nothing cycles (contrast `core_router.py`, where it ran the other way — DEC-30).

Pure stdlib + the SDK's value types; importable in isolation.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin

from ..trust.high_impact import RouteImpact
from .router_surfaces import namespaced_name


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


def mount_plugin(
    routes: dict[str, MountedRoute],
    plugin: ToolPlugin,
    *,
    ctx: Optional[PluginContext] = None,
    namespace: Optional[str] = None,
    provenance: str = "plugin",
    taint: bool = False,
    impact: RouteImpact = RouteImpact(),
) -> None:
    """Register every descriptor a plugin offers.

    `namespace` gates the roadmap §3.2 name fencing: community/MCP tools
    are exposed as "<ns>.<tool>" (schema name rewritten to match); CORE
    native plugins mount with namespace=None and keep their V1 names
    verbatim — the zero-behavior exemption (conflict ruling C-3).

    `impact` is the DEC-15 high-impact classification for this route, stated
    by the KERNEL-side mounter from what it granted / read (never by the
    plugin). Its default is fail-closed for an external route.

    `routes` is the registry to mutate — the ONLY difference from the method
    this was carved out of, which reached the same dict through `self`."""
    ctx = ctx if ctx is not None else PluginContext()
    for descriptor in plugin.descriptors():
        exposed = descriptor
        if namespace:
            exposed_name = namespaced_name(namespace, descriptor.name)
            exposed = dataclasses.replace(
                descriptor,
                name=exposed_name,
                schema={**descriptor.schema, "name": exposed_name},
            )
        if exposed.name in routes:
            raise ValueError(f"tool name collision at mount: {exposed.name!r}")
        routes[exposed.name] = MountedRoute(
            descriptor=exposed,
            bare_name=descriptor.name,
            plugin=plugin,
            ctx=ctx,
            provenance=provenance,
            taint=taint,
            impact=impact,
        )


__all__ = ["MountedRoute", "mount_plugin"]
