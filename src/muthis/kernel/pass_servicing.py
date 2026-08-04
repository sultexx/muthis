# src/muthis/kernel/pass_servicing.py
"""
What a pass ASKED FOR, serviced — extracted from `turn_pass.py` (DEC-73).

THE SEAM, AND WHY IT IS A REAL ONE. `TurnPass.consume()` did two jobs: DRAIN the
provider stream, and SERVICE what the stream asked for. The Option-A sync point
already marked the line between them — in the code and in the comments — so this
module is that line made structural. Draining is about events arriving; servicing
is about calls being answered, and they change for different reasons.

THE RECORD IS THE OTHER HALF, AND IT IS THE PART THAT PAYS FORWARD. `consume()`
returned a TUPLE that grew with every tool category: a 4-tuple heading for a
5-tuple, where each new category cost SIX separate edits — a local, a dispatch
branch, a servicing block, a tuple slot, the orchestrator's unpack position, and
a `build_tool_result_message` parameter. That is a funnel of its own. `PassServiced`
makes the next category cost the last three of those NOTHING: a new field is
additive at every call site. It is DEC-66's argument about a list of strings —
*a shape that cannot be extended without redesigning every producer and consumer
at once* — applied to the kernel's own return type.

**THIS IS NOT DEC-38's DISPATCH-FUNNEL SPLIT.** That one is `_execute_route`'s
dispatch inside `tool_router.py`, and it remains RESERVED and untouched — this
extraction costs that file zero lines.

ORDERING IS THE INVARIANT. The precondition is serviced BEFORE the read, because
`docs__query` in the same pass depends on the index `docs__open` builds. An
extraction that reordered these would answer the query against nothing, so the
order is asserted directly against this module rather than inferred.

A LEAF: it imports the router's own types and nothing from `turn_pass`, so
nothing cycles. Never raises — the router never raises, and every failure below
is already an Arabic note by the time it arrives.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Optional

from ..cloud.protocol import ToolCall
from .navigator_service import service_navigator_call

logger = logging.getLogger("muthis.orchestrator")


@dataclasses.dataclass(frozen=True)
class PassServiced:
    """Everything ONE pass asked for and got, as a value.

    FROZEN and defaulted: a pass that serviced nothing is the empty record, not
    `None`, so a consumer never branches on absence — the same reason
    `SessionTaint` defaults to a REAL instance rather than None.

    Field order mirrors the tuple this replaced, so the equivalence check that
    guards the extraction compares like with like."""

    read_results: tuple[tuple[ToolCall, str], ...] = ()
    run_result: Optional[tuple[ToolCall, str]] = None
    nav_result: Optional[tuple[ToolCall, str]] = None


async def service_pass_calls(
    *,
    router: Any,
    sandbox: Any,
    result: Any,
    precondition: Optional[ToolCall],
    read: Optional[ToolCall],
    run: Optional[ToolCall],
    nav: Optional[ToolCall] = None,
    prelude: Any = None,
) -> PassServiced:
    """Service the pass's calls AFTER the sync point, in the ONE right order.

    Called once per pass, from `TurnPass.consume()`, at the point the audio is
    already moving — local I/O and container work must never delay the spoken
    ack. Mutates `result.taint` because the turn-level taint flag is the
    orchestrator's, recorded here at the moment the provenance is known."""
    # Phase 4: service the pass's ONE read AFTER the audio is moving (local
    # I/O must never delay the spoken ack). Routed through the ToolRouter
    # (V2 Phase 0) at the SAME site with the same await discipline; the
    # router never raises — every failure is already an Arabic note.
    read_results: list[tuple[ToolCall, str]] = []
    # The precondition FIRST: `docs__query` in the same pass depends on the
    # index `docs__open` builds, so servicing them out of order would answer
    # the query against nothing.
    for routed_call in (precondition, read):
        if routed_call is None:
            continue
        outcome = await router.service(routed_call.name, routed_call.args)
        read_results.append((routed_call, outcome.result.text_ar))
        if outcome.taint and not result.taint:
            # §3.2: coarse turn-level taint — recorded here, enforced by
            # the high-impact gates when those tools exist (Phase 2).
            result.taint = True
            logger.info("[orchestrator] turn tainted by %s", outcome.provenance)
    # T5: service run_code AFTER the sync point too — bounded ≤3/turn by the
    # SandboxGate inside the servicer; the draw gate is never touched.
    run_result: Optional[tuple[ToolCall, str]] = None
    if run is not None and sandbox is not None:
        run_result = (run, await sandbox.run(run.args))
    # T4: the MODE verb, serviced AFTER the sync point like the two above.
    # The KERNEL owns the effect (DEC-73), so no router, no plugin and no
    # capability is involved — and the draw gate is never touched, which is
    # what leaves a step's one pointing intact. A None prelude keeps this
    # arm INERT rather than absent: the stub-first shape every seam here
    # already uses, so an unwired build degrades quietly instead of raising.
    nav_result: Optional[tuple[ToolCall, str]] = None
    if nav is not None and prelude is not None:
        nav_result = (nav, service_navigator_call(
            nav, authority=prelude.authority, mode=prelude.session_mode))
    return PassServiced(read_results=tuple(read_results),
                        run_result=run_result, nav_result=nav_result)


__all__ = ["PassServiced", "service_pass_calls"]
