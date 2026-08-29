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
from .deferral_notes import NAV_VERIFY_TOOL
from .mode_transition import ADVANCE, TransitionRequest
from .step_verification import (
    ADVANCED, after_advance, after_verification, verification_from,
)
from .verification_notes import VERIFY_NO_STEP_AR, verification_note
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


def _serviced_verification(call: ToolCall, prelude: Any) -> str:
    """ONE `navigator__verify`, serviced: the outcome, the transition DEC-106's
    machine makes of it, and the note that reports what actually happened.

    THE ADVANCE GOES THROUGH THE AUTHORITY LIKE EVERY OTHER ONE. This function
    decides nothing about whether the step MAY move — it hands `ADVANCE` to the
    single evaluation point and reports what came back, exactly as
    `navigator_service.py` does for the model's own `advance`. A proven LAST
    step is refused at the bound and gets the authority's own note; the
    verification does not become a special path around it.

    AND `ADVANCED` IS NEVER RESTED IN. On a successful advance the reset rides
    on `record_progress` (one home, both step-changing transitions); on a
    refused one the state is put back to `after_advance()` here, so no frame
    ever holds an edge.

    Never raises: the payload is model-authored and arrives already narrowed."""
    mode = prelude.session_mode
    if mode.current_step <= 0:            # 0 with no plan AND with no mode
        return VERIFY_NO_STEP_AR
    verification = verification_from(call.args)
    state = after_verification(mode.verification, verification)
    if state != ADVANCED:
        mode.record_verification(state)
        return verification_note(verification, state=state, advanced=False)
    outcome = prelude.authority.request(TransitionRequest(kind=ADVANCE))
    if not outcome.applied:
        mode.record_verification(after_advance())
        return outcome.note_ar or verification_note(
            verification, state=after_advance(), advanced=False)
    return verification_note(verification, state=after_advance(), advanced=True)


def log_pass(result: Any) -> None:
    """DEC-111 ② — ONE line per pass: the ordinal, and every tool the pass asked
    for. English, never raises, no arguments and no payloads.

    THE MINIMUM DATUM, AND WHY IT IS OBTAINABLE HERE AFTER ALL. DEC-117 measured
    this site (its option B) as "blind to the draw, the refresh and
    `tool_choice`" — true of the SERVICED PARAMETERS this function receives, and
    NOT true of `result`, which is the same per-turn object `consume()` appends
    EVERY accepted call to: draw, refresh, router-serviced, nav and run. The
    watermark slice below is therefore the whole pass, not the serviced half.

    `tool_choice` IS DELIBERATELY ABSENT AND DELIBERATELY NOT MISSED.
    `loop_tool_choice` is `"none" if gate.drawn else "auto"`, and `gate.drawn` is
    set by the first draw's PAIRING — so a reader of this table derives it: every
    pass is "auto" until a draw appears on an earlier line, and "none" from the
    pass after it. Recording the DRAW rather than the flag keeps the ground truth
    instead of a value computed from it, and costs no pinned file.

    NAMES ONLY — NEVER ARGUMENTS. A tool name is a control-flow fact; a tool
    argument is user content (a path, a query, a program), which DEC-61 governs
    and which the sandbox record handles under its own gate."""
    result.passes_serviced += 1
    fresh = result.tool_calls[result.tools_logged:]
    result.tools_logged = len(result.tool_calls)
    logger.info("[pass] #%d tools=%s", result.passes_serviced,
                ",".join(c.name for c in fresh) or "-")


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
    # DEC-111 ② — the pass's own line, FIRST: it records what the pass ASKED
    # FOR, which is settled by the time servicing begins, so it is written even
    # if a later arm below returns nothing at all.
    log_pass(result)
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
    # DEC-108 Gate 2B: the THIRD verb is serviced HERE, beside its two siblings,
    # and the ruling's four grounds are all visible at this line. It needs NO
    # FRAME — the model judged the screen it was shown and returns the outcome
    # through the tool, while the kernel validates REPRESENTATION and never
    # truth — so no `screenshot` parameter joins the signature above and the
    # coupling the trace flagged is never incurred. This site runs AFTER the
    # sync point, so a verification delays neither the draw nor the speech.
    #
    # THE VERB DOES NOT ROUTE THROUGH `service_navigator_call`. That module is a
    # TRANSLATION LAYER that decides nothing and never raises; verification is a
    # decision about representation, and P5 was rejected on exactly that law.
    # `mode.current_step` is 0 whenever there is no plan or no current step —
    # including no mode at all — so "an active step exists" is ONE existing read
    # and no new state.
    nav_result: Optional[tuple[ToolCall, str]] = None
    if nav is not None and prelude is not None:
        note = (_serviced_verification(nav, prelude)
                if nav.name == NAV_VERIFY_TOOL
                else service_navigator_call(nav, authority=prelude.authority,
                                            mode=prelude.session_mode))
        nav_result = (nav, note)
    return PassServiced(read_results=tuple(read_results),
                        run_result=run_result, nav_result=nav_result)


__all__ = ["PassServiced", "service_pass_calls", "log_pass"]
