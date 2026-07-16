# sdk/muthis_sdk/types.py
"""
Core value types of the plugin contract. Zero third-party deps (stdlib only),
importable in isolation — the cloud/protocol.py culture carried into the SDK.

`CAPABILITIES` is the CLOSED privilege enum of V2_ROADMAP.md §3.3. The golden
rule (§1.1 — "look and advise only, enforced by construction") lives HERE:
there is no input.mouse, no input.keyboard, no clipboard.write member, and
manifest validation rejects unknown names — a malicious plugin finds nothing
to ask for. Phase 0 ships the declaration; the Phase-1 broker enforces grants
behind these same types without a contract break.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# The closed capability enum (V2_ROADMAP.md §3.3). Frozen on purpose: adding a
# member is a CONSTITUTIONAL amendment, not a code change. Input-control and
# filesystem-write capabilities deliberately DO NOT EXIST.
CAPABILITIES: frozenset[str] = frozenset(
    {
        "perceive.screen",
        "perceive.files.read",
        "annotate.overlay",
        "speak.caption",
        "net.fetch",
        "sandbox.execute",
        "cache.session",
    }
)


@dataclass(frozen=True)
class ToolDescriptor:
    """One tool a plugin offers the model.

    `schema` is the EXACT model-visible tool dict (name / description /
    input_schema) merged into the provider request — the kernel treats it as
    opaque bytes, which is what makes byte-identical V1 re-founding possible.

    `kernel_serviced` marks tools whose EXECUTION never leaves the kernel
    (the V1 draw circuit and the screen-refresh frame lifecycle): the plugin
    contributes the declaration; the kernel intercepts the call before any
    router dispatch (V2_ROADMAP.md part 2 §1 — the draw path never crosses
    the router).
    """

    name: str
    schema: dict[str, Any]
    read_only: bool = True
    kernel_serviced: bool = False
    description_ar: str = ""
    description_en: str = ""


@dataclass(frozen=True)
class ToolResult:
    """What a plugin execution returns to the conversation.

    `text_ar` is the Arabic tool_result note the model reads (user-facing
    surface → Arabic, per the language-split law). Failures are ordinary
    ToolResults with `is_error=True` — plugins NEVER raise into the kernel.
    """

    text_ar: str
    is_error: bool = False


@dataclass(frozen=True)
class ServiceOutcome:
    """A routed service call's outcome, as the kernel's ToolRouter returns it.

    `provenance` names the servicing plugin (e.g. "core:file_read") for logs
    and, later, the per-plugin budget ledger. `taint` and `cost_usd` are
    Phase-1 fields (untrusted-content flag; per-plugin cost attribution) —
    declared now so the broker lands without a contract break.
    """

    result: ToolResult
    provenance: str
    taint: bool = False
    cost_usd: Optional[float] = None
    extras: dict[str, Any] = field(default_factory=dict)
