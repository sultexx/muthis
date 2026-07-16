# sdk/muthis_sdk/__init__.py
"""
muthis-sdk — the public plugin contract for Mut'his V2.

Born in V2 Phase 0 (the kernel split). A plugin is: a `muthis-plugin.toml`
manifest + a `ToolPlugin` subclass that declares `ToolDescriptor`s and
executes tool calls against a kernel-provided `PluginContext`.

Contract rules (V2_ROADMAP.md §3.2, extending V1's Law 11): plugin execution
is STATELESS — no loops, no locks, no conversation memory inside the plugin;
the kernel alone owns every lifecycle. Every failure is returned as a short
Arabic note in a ToolResult, never raised (the FileReader pattern).

The capability enum is CLOSED (§3.3) and enforced-by-construction (§1.1):
input.mouse / input.keyboard / clipboard.write DO NOT EXIST here, so a
malicious plugin finds nothing to request. Phase 0 ships the declaration
layer only; the broker that ENFORCES grants arrives in Phase 1 behind these
same types.
"""

from .context import FilesCapability, PluginContext
from .manifest import ManifestError, PluginManifest, ToolEntry, load_manifest
from .plugin import ToolPlugin
from .types import (
    CAPABILITIES,
    ServiceOutcome,
    ToolDescriptor,
    ToolResult,
)

__version__ = "2.0.0a1"

__all__ = [
    "CAPABILITIES",
    "FilesCapability",
    "ManifestError",
    "PluginContext",
    "PluginManifest",
    "ServiceOutcome",
    "ToolDescriptor",
    "ToolEntry",
    "ToolPlugin",
    "ToolResult",
    "load_manifest",
    "__version__",
]
