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


# perceive.screen: returns the downscaled payload PNG (the kernel's own
# hide→settle→capture line produced it) or None when capture failed.
CaptureFn = Callable[[], Awaitable[Optional[bytes]]]


class ScreenCapability:
    """The perceive.screen seam (V2 Phase 1, sdk 2.0.0a2). In-proc plugins
    get the kernel callable directly; out-of-proc plugins get a transparent
    stub the MCP runtime backs with a muthis/capture profile request."""

    def __init__(self, capture: CaptureFn) -> None:
        self.capture = capture


# net.fetch: a URL STRING in, the broker's readable-fetch result out. Typed
# loosely on purpose — the RESULT type (muthis.broker.net.FetchResult) belongs
# to the app, and the SDK stays dependency-free and importable in isolation, so
# it must not import it. A plugin reads the fields it needs (`ok` / `text_ar` /
# `content` / `domain`) and degrades politely on a failure.
FetchReadableFn = Callable[[str], Awaitable[Any]]


class NetCapability:
    """The net.fetch seam (V2 Phase 2, sdk 2.0.0a3 — DEC-17 / DEC-24).

    ONE verb: `fetch_readable(url)`. What is ABSENT is the design — no socket,
    no HTTP client, no base URL, no header/method/redirect surface, nothing a
    plugin could use to CONSTRUCT a request. A plugin hands over a URL string
    and receives readable content, so every DEC-17 defense (resolve-once IP
    pinning, per-hop re-validation, robots, the size/type caps, the total
    wall-clock budget) lives in the broker where a plugin author cannot weaken
    it (§3.3 — external plugin code holds no OS handle; DEC-4 — security a
    plugin author can weaken is not security).

    The contract is BINARY (M1-4, restated by DEC-24): granted AND wired → this
    object rides the context; denied → `ctx.net` is None. There is deliberately
    no third state and, in particular, no stub that refuses: a refusing stub is
    a DIFFERENT API for a denied plugin, which is precisely what M1-4 forbids.
    """

    def __init__(self, fetch_readable: FetchReadableFn) -> None:
        self.fetch_readable = fetch_readable


@dataclass
class PluginContext:
    """What the kernel hands a plugin for one execute() call.

    `files` is None unless the capability is wired — a plugin must degrade
    to a polite Arabic note when a capability it wants is absent, never
    crash (the conformance kit exercises exactly that path). The same rule
    governs `screen` and `net`: absence IS the denial, and a plugin reads it
    with a plain `is None` check, never a try/except around a refusing call.
    """

    files: Optional[FilesCapability] = None
    screen: Optional[ScreenCapability] = None
    net: Optional[NetCapability] = None
    locale: str = "ar"
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("muthis.plugins")
    )
