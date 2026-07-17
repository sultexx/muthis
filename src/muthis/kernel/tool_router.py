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

Mount-time errors DO raise (English ValueError): composition happens at app
start / in tests, where failing loudly is correct.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Optional

from muthis_sdk import (
    FilesCapability,
    PluginContext,
    ServiceOutcome,
    ToolDescriptor,
    ToolPlugin,
    ToolResult,
)

from ..file_reader import FILE_READ_UNAVAILABLE_AR, READ_FILE_TOOL, ReadFileFn

logger = logging.getLogger("muthis.kernel.tool_router")

# Context-bloat brake (roadmap §3.2): every schema costs ~100-300 tokens, so
# the merged list is hard-capped; semantic filtering arrives when catalogs grow.
MAX_TOOLS = 24

# Arabic tool_result notes — the model-facing refusal surfaces (never spoken).
UNROUTED_TOOL_NOTE_AR = "هذه الأداة غير متاحة في هذه الجلسة."
KERNEL_SERVICED_NOTE_AR = "هذه الأداة تخدمها النواة مباشرة، لا هذا المسار."
PLUGIN_FAILED_NOTE_AR = "تعذّر تنفيذ الأداة لعطل داخلي في الإضافة."


@dataclasses.dataclass(frozen=True)
class _Mounted:
    """One mounted route: the exposed descriptor + how to reach its plugin."""

    descriptor: ToolDescriptor  # as offered to the model (already namespaced)
    bare_name: str              # the plugin's own view of the tool name
    plugin: ToolPlugin
    ctx: PluginContext
    provenance: str


class ToolRouter:
    """Registry + merge + dispatch. Owned by the kernel; plugins are mounted
    at composition time and never mutate the registry themselves."""

    def __init__(self) -> None:
        self._routes: dict[str, _Mounted] = {}

    def mount(
        self,
        plugin: ToolPlugin,
        *,
        ctx: Optional[PluginContext] = None,
        namespace: Optional[str] = None,
        provenance: str = "plugin",
    ) -> None:
        """Register every descriptor a plugin offers.

        `namespace` gates the roadmap §3.2 name fencing: community/MCP tools
        are exposed as "<ns>.<tool>" (schema name rewritten to match); CORE
        native plugins mount with namespace=None and keep their V1 names
        verbatim — the zero-behavior exemption (conflict ruling C-3)."""
        ctx = ctx if ctx is not None else PluginContext()
        for descriptor in plugin.descriptors():
            exposed = descriptor
            if namespace:
                exposed_name = f"{namespace}.{descriptor.name}"
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
            return ServiceOutcome(
                result=ToolResult(text_ar=FILE_READ_UNAVAILABLE_AR, is_error=True),
                provenance=route.provenance,
            )
        try:
            result = await route.plugin.execute(route.bare_name, args, route.ctx)
        except Exception:  # noqa: BLE001 — the never-raise wall (contract breach)
            logger.exception("[tool_router] plugin %r raised — contract breach", tool)
            return ServiceOutcome(
                result=ToolResult(text_ar=PLUGIN_FAILED_NOTE_AR, is_error=True),
                provenance=route.provenance,
            )
        return ServiceOutcome(result=result, provenance=route.provenance)


def build_core_router(*, read_file: Optional[ReadFileFn] = None) -> ToolRouter:
    """The default kernel router: the four V1 tools mounted as core plugins
    (M4 dogfood) in the EXACT V1 catalog order — pointer, shapes, refresh,
    read — so descriptors() mirrors cloud.tool_schemas.LOOK_ONLY_TOOLS
    (snapshot-pinned). Only file_read is router-serviced; the other three are
    kernel_serviced declarations (conflict ruling C-1)."""
    # Composition-point import (lazy, the ONE documented kernel→plugins
    # direction): the ToolRouter class itself stays plugin-agnostic, and
    # kernel modules keep importing in isolation without the plugins tree.
    from muthis_plugins.file_read import FileReadPlugin
    from muthis_plugins.look_pointer import LookPointerPlugin
    from muthis_plugins.look_shapes import LookShapesPlugin
    from muthis_plugins.screen_refresh import ScreenRefreshPlugin

    router = ToolRouter()
    router.mount(LookPointerPlugin(), provenance="core:look_pointer")
    router.mount(LookShapesPlugin(), provenance="core:look_shapes")
    router.mount(ScreenRefreshPlugin(), provenance="core:screen_refresh")
    files = FilesCapability(read=read_file) if read_file is not None else None
    router.mount(
        FileReadPlugin(),
        ctx=PluginContext(files=files),
        namespace=None,  # core: V1 names verbatim (C-3 exemption)
        provenance="core:file_read",
    )
    return router


__all__ = [
    "MAX_TOOLS",
    "KERNEL_SERVICED_NOTE_AR",
    "PLUGIN_FAILED_NOTE_AR",
    "UNROUTED_TOOL_NOTE_AR",
    "ToolRouter",
    "build_core_router",
]
