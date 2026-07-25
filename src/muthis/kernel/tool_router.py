# src/muthis/kernel/tool_router.py
"""
ToolRouter — the general dispatch registry (V2 Phase 0, roadmap part 2 §1:
"the one surgical change in V1").

Generalizes turn_pass's bespoke read_local_file servicing into a registry of
mounted ToolPlugins: merged descriptors offered to the model (capped,
namespaced for NON-core plugins) + service() dispatch of ONE tool call.

CRUCIAL RULE (approved plan, conflict ruling C-1): the DRAW path never crosses
this router. highlight_target / draw_shapes stay on draw_dispatch +
HighlightGate + the tool_choice="none" terminator, letter for letter; the
screen-refresh frame lifecycle (hide→settle→capture, scale bookkeeping,
Bug-3 strip) stays kernel state. Their descriptors are marked
kernel_serviced=True, and service() refuses them defensively. The router
services PERCEPTION tools only — in Phase 0 exactly read_local_file.

Failure discipline (the FileReader pattern, generalized): service() NEVER
raises into the turn — unknown tools, kernel-serviced tools, an absent
capability seam, and even a contract-breaching plugin that raises all come
back as a short Arabic tool_result note + an English log line.

UNTRUSTED-CONTENT WRAPPING (DEC-14): this boundary is the app's ONE wrap site.
Every result from a route mounted with taint=True leaves here framed in the
§3.2 nonce-bearing delimiters (untrusted_content.py) — a universal constant
every external tool inherits with ZERO lines in any plugin, because security a
plugin author can weaken is not security (DEC-4).

SESSION TAINT (DEC-15): the same boundary raises the session-sticky taint, in
the SAME branch as the wrap. Wrapping and raising are two consequences of ONE
decision — "this result is untrusted" — and must never become two independent
checks: a result that is WRAPPED but does not RAISE would leave the session
looking clean, so T5's confirmation would never fire on a session that has
already ingested adversarial content. `_outcome_for` is that single branch.

HIGH-IMPACT CLASSIFICATION (DEC-15): every route also carries the kernel's own
`RouteImpact` facts (trust/high_impact.py) — granted capabilities, the MCP
readOnlyHint — assigned by whoever MOUNTS the route (kernel code) and never by
the plugin. They are INERT here: the confirm gate that reads them is the next
commit, and mounting a fact nothing consumes yet is the stub-first order.

Mount-time errors DO raise (English ValueError): composition happens at app
start / in tests, where failing loudly is correct.

`build_core_router` — the four-V1-plugin COMPOSITION — lives in core_router.py
(extracted under the ≤300-line law). It is NOT re-exported here: the dependency
runs composition → registry, so re-exporting would be a cycle. Import it from
`muthis.kernel.core_router`. The MODEL-FACING surfaces (the DEC-11 name form, the
catalog cap, the Arabic refusal notes) live in router_surfaces.py — extracted the
same way but RE-EXPORTED below, because that dependency runs dispatch → surfaces
and cycles nothing, so no importer changed.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Callable, Optional

from muthis_sdk import (
    PluginContext,
    ServiceOutcome,
    ToolDescriptor,
    ToolPlugin,
    ToolResult,
)

from ..file_reader import FILE_READ_UNAVAILABLE_AR, READ_FILE_TOOL
from ..trust.high_impact import RouteImpact
from .router_surfaces import (
    KERNEL_SERVICED_NOTE_AR, MAX_TOOLS, NAMESPACE_SEP, PLUGIN_FAILED_NOTE_AR,
    UNROUTED_TOOL_NOTE_AR, namespaced_name,
)
from .session_taint import SessionTaint
from .untrusted_content import wrap_untrusted

logger = logging.getLogger("muthis.kernel.tool_router")


@dataclasses.dataclass(frozen=True)
class _Mounted:
    """One mounted route: the exposed descriptor + how to reach its plugin."""

    descriptor: ToolDescriptor  # as offered to the model (already namespaced)
    bare_name: str              # the plugin's own view of the tool name
    plugin: ToolPlugin
    ctx: PluginContext
    provenance: str
    taint: bool = False         # external route (MCP): outcomes untrusted by definition
    impact: RouteImpact = RouteImpact()  # DEC-15 facts, mounter-assigned (inert)


class ToolRouter:
    """Registry + merge + dispatch. Owned by the kernel; plugins are mounted
    at composition time and never mutate the registry themselves.

    `plugin_ledger` (V2 Phase 1, M1-3) is the budget attribution seam —
    Budget.record_plugin_call in production, None in bare tests. Every call
    that reaches a REAL route is recorded (successes AND plugin failures —
    both consumed a service attempt); unrouted/misrouted refusals are not
    attributed to anyone. The seam never raises into a turn."""

    def __init__(
        self, *,
        plugin_ledger: Optional[Callable[[str, Optional[float]], None]] = None,
        session_taint: Optional[SessionTaint] = None,
    ) -> None:
        self._routes: dict[str, _Mounted] = {}
        self._plugin_ledger = plugin_ledger
        # DEC-15: session-sticky taint, built at the composition root so its
        # LIFETIME is visibly the process's. The default is a REAL instance, not
        # None: a composition that forgot to inject one must still RECORD taint
        # (fail-closed) — an optional-and-silently-absent security seam is how a
        # session stays "clean" while untrusted content flows through it.
        self._session_taint = session_taint if session_taint is not None else SessionTaint()

    @property
    def session_taint(self) -> SessionTaint:
        """Read-only access for the kernel (T5's confirm gate reads this state).
        There is no setter and no clearing path — see session_taint.py."""
        return self._session_taint

    def _record(self, provenance: str, cost_usd: Optional[float]) -> None:
        if self._plugin_ledger is None:
            return
        try:
            self._plugin_ledger(provenance, cost_usd)
        except Exception:  # noqa: BLE001 — accounting must never kill a turn
            logger.exception("[tool_router] plugin ledger seam raised — ignored")

    def _outcome_for(self, route: _Mounted, tool: str, result: ToolResult) -> ServiceOutcome:
        """The single exit for every call that reached a REAL route — the app's
        ONE untrusted-content wrap site (DEC-14) and its ONE taint-raise site
        (DEC-15).

        BOTH consequences live under the SAME single condition, on purpose. They
        are one decision — "this result is untrusted" — and splitting them into
        two checks opens this milestone's worst hole: content that gets WRAPPED
        without RAISING leaves the session looking clean, so T5's confirmation
        never fires on a session that already ingested adversarial content. Keep
        this function at exactly ONE `if`; a second condition here is how the two
        drift apart (`test_session_taint.py` asserts that structurally).

        The wrap is keyed off the OUTCOME's own taint flag, so the flag the
        caller sees and the framing the model reads can never disagree.

        `is_error` deliberately does NOT gate the wrap: it is set by the plugin,
        so letting it skip the framing would hand a plugin author a switch that
        smuggles external text in unwrapped — exactly what DEC-4 forbids.
        Over-framing one of our own Arabic notes is harmless; under-framing
        external content is a hole, so this fails in the safe direction.

        The source is KERNEL-derived — the model-visible tool name, never a
        plugin's self-declaration (DEC-15). A content-bearing tool's real source
        URL rides in through this same parameter when T6 wires the web plugin.
        """
        outcome = ServiceOutcome(result=result, provenance=route.provenance,
                                 taint=route.taint)
        if not outcome.taint:
            return outcome
        self._session_taint.raise_taint(route.provenance)
        return dataclasses.replace(
            outcome,
            result=ToolResult(
                text_ar=wrap_untrusted(result.text_ar, source=tool),
                is_error=result.is_error,
            ),
        )

    def mount(
        self,
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
        plugin). Its default is fail-closed for an external route."""
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
            if exposed.name in self._routes:
                raise ValueError(f"tool name collision at mount: {exposed.name!r}")
            self._routes[exposed.name] = _Mounted(
                descriptor=exposed,
                bare_name=descriptor.name,
                plugin=plugin,
                ctx=ctx,
                provenance=provenance,
                taint=taint,
                impact=impact,
            )

    def descriptors(self) -> list[ToolDescriptor]:
        """The merged, capped descriptor list in mount order — the model-visible
        catalog. Core descriptors pass through BYTE-IDENTICAL (no namespace,
        no schema rewrite), which the M4 snapshot test pins."""
        merged = [route.descriptor for route in self._routes.values()]
        if len(merged) > MAX_TOOLS:
            logger.warning(
                "[tool_router] %d tools exceed the cap (%d) — truncating",
                len(merged), MAX_TOOLS,
            )
            merged = merged[:MAX_TOOLS]
        return merged

    async def service(self, tool: str, args: dict[str, Any]) -> ServiceOutcome:
        """Dispatch ONE call. Never raises — every failure is an Arabic note."""
        route = self._routes.get(tool)
        if route is None:
            logger.error("[tool_router] unrouted tool %r refused", tool)
            return ServiceOutcome(
                result=ToolResult(text_ar=UNROUTED_TOOL_NOTE_AR, is_error=True),
                provenance="kernel:unrouted",
            )
        if route.descriptor.kernel_serviced:
            # Defensive: draw/refresh calls are intercepted upstream and must
            # never arrive here — answering politely keeps the turn alive.
            logger.error("[tool_router] kernel-serviced tool %r reached service()", tool)
            return ServiceOutcome(
                result=ToolResult(text_ar=KERNEL_SERVICED_NOTE_AR, is_error=True),
                provenance="kernel:misroute",
            )
        if route.bare_name == READ_FILE_TOOL and route.ctx.files is None:
            # Phase-0 capability degradation, ruled in the KERNEL so the V1
            # Arabic note stays single-sourced (file_reader.py). The Phase-1
            # broker generalizes this from manifest capability requirements.
            self._record(route.provenance, None)
            return self._outcome_for(
                route, tool,
                ToolResult(text_ar=FILE_READ_UNAVAILABLE_AR, is_error=True))
        try:
            result = await route.plugin.execute(route.bare_name, args, route.ctx)
        except Exception:  # noqa: BLE001 — the never-raise wall (contract breach)
            logger.exception("[tool_router] plugin %r raised — contract breach", tool)
            self._record(route.provenance, None)
            return self._outcome_for(
                route, tool,
                ToolResult(text_ar=PLUGIN_FAILED_NOTE_AR, is_error=True))
        outcome = self._outcome_for(route, tool, result)
        self._record(route.provenance, outcome.cost_usd)
        return outcome


__all__ = [
    "MAX_TOOLS",
    "NAMESPACE_SEP",
    "SessionTaint",
    "namespaced_name",
    "KERNEL_SERVICED_NOTE_AR",
    "PLUGIN_FAILED_NOTE_AR",
    "UNROUTED_TOOL_NOTE_AR",
    "ToolRouter",
]
