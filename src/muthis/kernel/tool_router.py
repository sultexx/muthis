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
and cycles nothing, so no importer changed. The `MountedRoute` record moved
to router_registry.py the same way, and for the same reason.
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
from ..trust.confirm_gate import ConfirmGate
from ..trust.high_impact import RouteImpact
from .router_registry import MountedRoute, mount_plugin
from .router_surfaces import (
    KERNEL_SERVICED_NOTE_AR, MAX_TOOLS, NAMESPACE_SEP, PLUGIN_FAILED_NOTE_AR,
    UNROUTED_TOOL_NOTE_AR, namespaced_name,
)
from .session_taint import SessionTaint
from .untrusted_content import wrap_untrusted

logger = logging.getLogger("muthis.kernel.tool_router")


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
        confirm_gate: Optional[ConfirmGate] = None,
    ) -> None:
        self._routes: dict[str, MountedRoute] = {}
        self._plugin_ledger = plugin_ledger
        # DEC-15: session-sticky taint, built at the composition root so its
        # LIFETIME is visibly the process's. The default is a REAL instance, not
        # None: a composition that forgot to inject one must still RECORD taint
        # (fail-closed) — an optional-and-silently-absent security seam is how a
        # session stays "clean" while untrusted content flows through it.
        self._session_taint = session_taint if session_taint is not None else SessionTaint()
        # DEC-16: same injection discipline, same reason — a None gate would be
        # an open door, so an absent one is a REAL gate, not no gate.
        self._confirm_gate = confirm_gate if confirm_gate is not None else ConfirmGate()

    @property
    def session_taint(self) -> SessionTaint:
        """Read-only access for the kernel (the confirm gate reads this state).
        There is no setter and no clearing path — see session_taint.py."""
        return self._session_taint

    @property
    def confirm_gate(self) -> ConfirmGate:
        """Read-only access for `TurnPass`, which owns neither seam but holds the
        router and the raw transcript — that is what keeps the orchestrator
        byte-identical (DEC-19 zero touch)."""
        return self._confirm_gate

    def _record(self, provenance: str, cost_usd: Optional[float]) -> None:
        if self._plugin_ledger is None:
            return
        try:
            self._plugin_ledger(provenance, cost_usd)
        except Exception:  # noqa: BLE001 — accounting must never kill a turn
            logger.exception("[tool_router] plugin ledger seam raised — ignored")

    async def _execute_route(
        self, route: MountedRoute, args: dict[str, Any]
    ) -> tuple[ToolResult, Optional[float]]:
        """Run the route and come back with its RESULT and what it COST.

        DEC-34, candidate (1): the ROUTER obtains the cost, so the figure never
        leaves kernel scope. The rejected alternative — a `cost_usd` on the
        plugin-facing `ToolResult` — would have let a PLUGIN declare a number
        that `record_plugin_call` adds to the SOVEREIGN daily total gating
        `can_afford`. This milestone has refused that shape three times already
        (`is_error` may not gate the wrap, DEC-29; a declared `read_only` may not
        drive impact, T5; a plugin may not wrap its own output, DEC-14), and the
        budget is the one place where it could exhaust the ceiling Rule 10 exists
        to defend.

        `execute_with_cost` is DUCK-TYPED and OPTIONAL: a plugin that does not
        offer it is run through the ordinary `execute()` and reports no cost,
        which the ledger records as ZERO while still counting the call. KNOWN
        LIMIT (DEC-34): that silence is invisible — a future THIRD-PARTY PAID
        plugin would record zero forever without warning. It has no victim today
        (the one paid path is first-party), and the fix is additive when it does."""
        carrier = getattr(route.plugin, "execute_with_cost", None)
        if carrier is None:
            return await route.plugin.execute(route.bare_name, args, route.ctx), None
        carried = await carrier(route.bare_name, args, route.ctx)
        # getattr, not attribute access: a carrier is an informal contract, and a
        # malformed one must degrade to "no cost" rather than raise into a turn.
        return carried.result, getattr(carried, "cost_usd", None)

    def _outcome_for(self, route: MountedRoute, tool: str, result: ToolResult,
                     cost_usd: Optional[float] = None) -> ServiceOutcome:
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
                                 taint=route.taint, cost_usd=cost_usd)
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
        """Register every descriptor a plugin offers — see `mount_plugin`, which
        holds the real body (registration versus dispatch, router_registry.py).
        Kept as a delegating method because every caller mounts through a router
        instance and none of them should have to know where the body lives."""
        mount_plugin(self._routes, plugin, ctx=ctx, namespace=namespace,
                     provenance=provenance, taint=taint, impact=impact)

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
        # DEC-16: the confirmation chokepoint — placed BEFORE every path that
        # could execute or degrade, so a refused call simply never happens. The
        # classification is the route's (DEC-15, kernel-assigned at mount) and
        # the decision is the gate's; the router only joins them to the session
        # state it already holds. `external=route.taint` is the deliberate
        # coupling recorded in DECISIONS.md: the mount's taint flag IS this
        # router's externality signal, and one fact keeps one home.
        refusal_ar = self._confirm_gate.refusal_for(
            tool, args, tainted=self._session_taint.tainted,
            high_impact=route.impact.high_impact(external=route.taint))
        if refusal_ar is not None:
            # Kernel-authored text about a call that never ran: no plugin was
            # reached, so it is neither wrapped (nothing external came back) nor
            # attributed to anyone's budget.
            return ServiceOutcome(
                result=ToolResult(text_ar=refusal_ar, is_error=True),
                provenance="kernel:confirm")
        if route.bare_name == READ_FILE_TOOL and route.ctx.files is None:
            # Phase-0 capability degradation, ruled in the KERNEL so the V1
            # Arabic note stays single-sourced (file_reader.py). The Phase-1
            # broker generalizes this from manifest capability requirements.
            self._record(route.provenance, None)
            return self._outcome_for(
                route, tool,
                ToolResult(text_ar=FILE_READ_UNAVAILABLE_AR, is_error=True))
        try:
            result, cost_usd = await self._execute_route(route, args)
        except Exception:  # noqa: BLE001 — the never-raise wall (contract breach)
            logger.exception("[tool_router] plugin %r raised — contract breach", tool)
            self._record(route.provenance, None)
            return self._outcome_for(
                route, tool,
                ToolResult(text_ar=PLUGIN_FAILED_NOTE_AR, is_error=True))
        outcome = self._outcome_for(route, tool, result, cost_usd)
        # UNCHANGED line, now carrying a real figure: the outcome the caller sees
        # and the amount charged are read from ONE place, so they cannot disagree
        # (the same rule `_outcome_for` applies to the wrap and its taint flag).
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
