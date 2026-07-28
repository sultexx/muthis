# src/muthis/kernel/router_surfaces.py
"""
Router surfaces — everything about the ToolRouter that the MODEL sees.

Extracted VERBATIM from tool_router.py under the ≤300-line law (T5, 2026-07-25),
immediately before the confirm-gate call site that would have breached it — the
DEC-30 posture: extract at the addition that breaches, never compress, never
extract early. A MOVE ONLY, proven byte-identical by diff, so the model-visible
catalog and the refusal texts are untouched by definition.

The seam is a real one: the NAME a tool is offered under (DEC-11's `__`
separator), the CAP on how many tools may be offered at all, and the Arabic notes
the model reads when a call is declined are one responsibility — the router's
model-facing surface — while mounting and dispatching are another. Carving it out
keeps the file that is now the ONE untrusted-content wrap site (DEC-14), the ONE
taint-raise site (DEC-15) and the ONE confirmation site (DEC-16) short enough to
read whole, which is the whole point of keeping those three together.

RE-EXPORTED from tool_router.py (unlike `core_router.py`, which could not be):
the dependency here runs dispatch → surfaces, so nothing cycles, and every
existing importer of `tool_router.namespaced_name` / the notes keeps working
unchanged. Check the dependency direction before assuming a re-export is
available — DEC-30 records the case where it was not.

Pure stdlib, importable in isolation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from muthis_sdk import ServiceOutcome, ToolResult

if TYPE_CHECKING:  # runtime-free: router_registry imports THIS module, so a real
    from .router_registry import MountedRoute  # import here would be a cycle

# Kept on the router's logger: a mechanical extraction must not move a log name
# (the turn_pass.py / composition.py precedent).
logger = logging.getLogger("muthis.kernel.tool_router")

# Context-bloat brake (roadmap §3.2): every schema costs ~100-300 tokens, so
# the merged list is hard-capped; semantic filtering arrives when catalogs grow.
MAX_TOOLS = 24

# DEC-11: the namespace↔tool separator for NON-core plugin tools. A DOUBLE
# underscore — NOT a dot (the Anthropic tool-name pattern ^[a-zA-Z0-9_-]{1,128}$
# forbids dots; a live 400 surfaced it), and NOT a single _ (ambiguous with an
# underscore inside a tool name, which would break namespace parsing). THE
# single source of the separator — every namespaced name derives from here.
NAMESPACE_SEP = "__"


def namespaced_name(namespace: str, tool: str) -> str:
    """The model-visible name for a namespaced plugin tool (DEC-11)."""
    return f"{namespace}{NAMESPACE_SEP}{tool}"

# Arabic tool_result notes — the model-facing refusal surfaces (never spoken).
UNROUTED_TOOL_NOTE_AR = "هذه الأداة غير متاحة في هذه الجلسة."
KERNEL_SERVICED_NOTE_AR = "هذه الأداة تخدمها النواة مباشرة، لا هذا المسار."
PLUGIN_FAILED_NOTE_AR = "تعذّر تنفيذ الأداة لعطل داخلي في الإضافة."


def pre_dispatch_refusal(
    route: "Optional[MountedRoute]", tool: str
) -> Optional[ServiceOutcome]:
    """The two refusals that happen BEFORE any dispatch decision — or None when
    the call may proceed.

    Extracted here (T6b, 2026-07-28) because the NOTE and the outcome that
    carries it are ONE concern, and both notes already live in this module. What
    stays behind in `service()` is the part that is genuinely dispatch: the
    confirmation gate, the capability degradation, the plugin call, and the
    single wrap+raise exit. These two are route-LESS: they touch no session
    state, raise no taint, wrap nothing, and are attributed to nobody's budget —
    which is exactly why moving them costs the dispatch funnel no reasoning.

    Returned rather than raised, so the caller keeps its early-return shape and
    the never-raise wall (Law 11) is untouched."""
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
    return None


__all__ = [
    "KERNEL_SERVICED_NOTE_AR",
    "MAX_TOOLS",
    "NAMESPACE_SEP",
    "PLUGIN_FAILED_NOTE_AR",
    "UNROUTED_TOOL_NOTE_AR",
    "namespaced_name",
    "pre_dispatch_refusal",
]
