# sdk/muthis_sdk/context.py
"""
PluginContext — the kernel-provided execution context a plugin runs against.

Phase 0 carries the bare capability seams the core plugins need (files.read).
The seams are plain injected callables: the kernel builds the context from its
OWN gated implementations (FileReader with ALL its secret-name/binary/size
gates stays kernel-side — V2_ROADMAP.md §3.3: the refusal-by-name is never
delegated to plugin code). In Phase 1 the broker wraps these same seams with
grant checks, so the plugin-facing surface never changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

# Mirrors the V1 read seam exactly (file_reader.ReadFileFn): the raw model
# args dict in, an Arabic tool_result string out, NEVER raises.
ReadFn = Callable[[dict[str, Any]], Awaitable[str]]


class FilesCapability:
    """The perceive.files.read seam. Present on the context only when the
    kernel granted it (Phase 0: wired for the file_read core plugin)."""

    def __init__(self, read: ReadFn) -> None:
        self.read = read


@dataclass
class PluginContext:
    """What the kernel hands a plugin for one execute() call.

    `files` is None unless the capability is wired — a plugin must degrade
    to a polite Arabic note when a capability it wants is absent, never
    crash (the conformance kit exercises exactly that path).
    """

    files: Optional[FilesCapability] = None
    locale: str = "ar"
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("muthis.plugins")
    )
