# src/muthis/kernel/core_router.py
"""
build_core_router — the default kernel router's COMPOSITION, extracted from
tool_router.py under the ≤300-line law (§17.4: split, don't compress).

A MOVE ONLY: the function is byte-identical to its tool_router.py original, so
the byte-pinned V1 catalog (tests/snapshots/look_tools_v1.json) and the read
path are untouched by definition. It was the right thing to carve out because it
is COMPOSITION, not dispatch — the router class is a registry, and knowing which
four plugins exist is a different responsibility from routing a call. Splitting
them also keeps the security-critical dispatch file (the DEC-14 wrap site and
the DEC-15 raise site) small enough to read whole.

WHY THE DEPENDENCY POINTS THIS WAY: this module imports ToolRouter, never the
reverse. tool_router.py deliberately does NOT re-export `build_core_router` —
that would be a cycle (composition → registry → composition) needing a lazy or
bottom-of-file import to break, and the ≤300 law's companion clause is
"importable in isolation". Importers name this module directly instead; the
DEC-23 transport.py split could re-export precisely because its dependency ran
the other way.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from muthis_sdk import FilesCapability, PluginContext

from ..file_reader import ReadFileFn
from ..trust.confirm_gate import ConfirmGate
from .session_taint import SessionTaint
from .tool_router import ToolRouter


def build_core_router(
    *,
    read_file: Optional[ReadFileFn] = None,
    plugin_ledger: Optional[Callable[[str, Optional[float]], None]] = None,
    session_taint: Optional[SessionTaint] = None,
    confirm_gate: Optional[ConfirmGate] = None,
    turn_hooks: Sequence[Callable[[], None]] = (),
) -> ToolRouter:
    """The default kernel router: the four V1 tools mounted as core plugins
    (M4 dogfood) in the EXACT V1 catalog order — pointer, shapes, refresh,
    read — so descriptors() mirrors cloud.tool_schemas.LOOK_ONLY_TOOLS
    (snapshot-pinned). Only file_read is router-serviced; the other three are
    kernel_serviced declarations (conflict ruling C-1).

    `session_taint` (DEC-15), `confirm_gate` (DEC-16) and `turn_hooks` (DEC-37)
    are passed straight through to the router: this helper composes, it never
    decides policy — and it never inspects a hook, which is what keeps the
    carrier blind end to end. NONE of
    the four core tools is a taint raiser — `read_local_file` mounts untainted,
    on purpose (a user-chosen file on the user's own machine is not external
    content) — and none is high-impact, so none can ever reach the gate."""
    # Composition-point import (lazy, the ONE documented kernel→plugins
    # direction): the ToolRouter class itself stays plugin-agnostic, and
    # kernel modules keep importing in isolation without the plugins tree.
    from muthis_plugins.file_read import FileReadPlugin
    from muthis_plugins.look_pointer import LookPointerPlugin
    from muthis_plugins.look_shapes import LookShapesPlugin
    from muthis_plugins.screen_refresh import ScreenRefreshPlugin

    router = ToolRouter(plugin_ledger=plugin_ledger, session_taint=session_taint,
                        confirm_gate=confirm_gate, turn_hooks=turn_hooks)
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


__all__ = ["build_core_router"]
