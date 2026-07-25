# src/muthis/broker/mcp/host.py
"""
McpHost — plugins.d loading, the grants gate, session lifecycle, strikes,
quarantine, and the router mount (roadmap §8.2/§8.5).

plugins.d/<name>.toml is a full muthis-plugin.toml manifest (kind="mcp",
entry = the child command line). The gate order per file:
manifest parses → kind is mcp → a HASH-CURRENT grant exists (else skipped
with the trust-flow hint) → catalog fetch (spawn → initialize →
tools/list → policy filter; the session then closes unless warm=true —
the lazy posture) → mounted into the router NAMESPACED, provenance
"mcp:<name>", taint=True (external = untrusted by definition).

Containment: per-call timeout (client), consecutive-failure strikes —
the third disables the server for the session with a spoken Arabic
announcement through the injected seam; tools/list_changed QUARANTINES
the server (its calls refuse politely) until the app restarts and the
catalog is re-fetched under the same grant. Every failure that reaches a
turn is a short Arabic ToolResult note, never an exception (§8.5).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from muthis_sdk import ManifestError, PluginManifest, ToolResult
from muthis_sdk.manifest import parse_manifest

from ...trust.high_impact import RouteImpact
from ..broker import Broker
from .client import McpSession, McpSessionError
from .policy import ExposedTool, filter_tools, sanitize_result
from .proxy_plugin import McpProxyPlugin

logger = logging.getLogger("muthis.broker.mcp.host")

DEFAULT_PLUGINS_DIR = "plugins.d"
MAX_STRIKES = 3

SERVER_FAILED_NOTE_AR = "تعذّر تنفيذ أداة الإضافة الخارجية هذه المرة."
SERVER_DISABLED_NOTE_AR = "هذه الإضافة معطَّلة لبقية الجلسة بعد ثلاثة إخفاقات متتالية."
SERVER_QUARANTINED_NOTE_AR = (
    "هذه الإضافة في الحجر الصحي: غيّرت قائمة أدواتها أثناء التشغيل، "
    "وتُستأنف بعد إعادة تشغيل مطحس.")
DISABLED_ANNOUNCE_AR = "عطّلت إضافة {name} — تعثّرت ثلاث مرات متتالية."


@dataclass
class _ServerState:
    manifest: PluginManifest
    manifest_path: Path
    exposed: list[ExposedTool] = field(default_factory=list)
    session: Optional[McpSession] = None
    strikes: int = 0
    disabled: bool = False
    quarantined: bool = False


class McpHost:
    """One per app. Owns every MCP session lifecycle (Law 11: the kernel's
    delegate for this one concern; plugins own nothing)."""

    def __init__(
        self,
        *,
        broker: Broker,
        plugins_dir: str | Path = DEFAULT_PLUGINS_DIR,
        announce: Optional[Callable[[str], None]] = None,  # Arabic, spoken later
    ) -> None:
        self._broker = broker
        self._plugins_dir = Path(plugins_dir)
        self._announce = announce
        self._servers: dict[str, _ServerState] = {}

    # ─────────────────────────── Mounting ───────────────────────────

    async def mount_all(self, router) -> list[str]:
        """Load plugins.d, gate, fetch catalogs, mount. Returns the mounted
        server names (English log surface). Never raises past a file."""
        mounted: list[str] = []
        if not self._plugins_dir.is_dir():
            logger.info("[mcp-host] no %s directory — nothing to mount", self._plugins_dir)
            return mounted
        for manifest_path in sorted(self._plugins_dir.glob("*.toml")):
            try:
                manifest = parse_manifest(
                    tomllib.loads(manifest_path.read_text(encoding="utf-8")),
                    source=str(manifest_path))
            except (ManifestError, OSError, tomllib.TOMLDecodeError) as exc:
                logger.warning("[mcp-host] skipping %s: %s", manifest_path.name, exc)
                continue
            if manifest.kind != "mcp":
                logger.warning("[mcp-host] %s is kind=%s — plugins.d hosts mcp only",
                               manifest.name, manifest.kind)
                continue
            if not self._broker.has_grant(manifest, manifest_path):
                logger.warning(
                    "[mcp-host] %s has no valid grant — not mounted (trust flow: "
                    "python -m muthis.broker.trust %s)", manifest.name, manifest_path)
                continue
            state = _ServerState(manifest=manifest, manifest_path=manifest_path)
            try:
                await self._fetch_catalog(state)
            except McpSessionError as exc:
                logger.error("[mcp-host] %s catalog fetch failed: %s", manifest.name, exc)
                continue
            if not state.exposed:
                logger.info("[mcp-host] %s exposes no read-only tools — mounted "
                            "empty (look-and-advise filter)", manifest.name)
            self._servers[manifest.name] = state
            router.mount(
                McpProxyPlugin(manifest.name, state.exposed, self._call_factory(state)),
                namespace=manifest.name,
                provenance=f"mcp:{manifest.name}",
                taint=True,
                # DEC-15: the kernel READ this hint — `filter_tools` exposes a
                # tool only when its own catalog carried readOnlyHint=true — so
                # the host may state it. Stating it is not optional politeness:
                # the classification defaults to fail-closed, so an external
                # mount that stays silent is high-impact, which is exactly how
                # "MCP tools lacking readOnlyHint" is expressed.
                impact=RouteImpact(read_only_hint=True),
            )
            mounted.append(manifest.name)
        return mounted

    async def _fetch_catalog(self, state: _ServerState) -> None:
        session = await self._open_session(state)
        try:
            result = await session.call("tools/list")
            tools = result.get("tools")
            state.exposed = filter_tools(
                state.manifest.name, tools if isinstance(tools, list) else [])
        finally:
            if not state.manifest.warm:
                await session.close()   # lazy posture: catalog cached, pipe shut
                state.session = None

    async def _open_session(self, state: _ServerState) -> McpSession:
        if state.session is not None:
            return state.session
        session = McpSession(
            state.manifest.name, state.manifest.entry,
            bridge=self._bridge_factory(state),
            on_list_changed=lambda: self._quarantine(state))
        await session.start()
        state.session = session
        return session

    # ─────────────────── The muthis-profile/1 bridge (M1-6) ───────────────────

    def _bridge_factory(self, state: _ServerState):
        """Server→client requests, serviced INSIDE the kernel through the
        broker's gated context — the §8.4 door. The grant check is the
        context itself: an ungranted capability is an ABSENT seam, answered
        with the broker's Arabic refusal as ordinary result text (the same
        never-raise surface FileReader taught everything else)."""
        async def bridge(method: str, params: dict[str, Any]) -> dict[str, Any]:
            from ..broker import CAPABILITY_NOT_GRANTED_AR
            ctx = self._broker.context_for(state.manifest, state.manifest_path)
            if method == "muthis/read_file":
                if ctx.files is None:
                    return {"text": CAPABILITY_NOT_GRANTED_AR}
                return {"text": await ctx.files.read(params.get("args") or {})}
            if method == "muthis/capture":
                if ctx.screen is None:
                    return {"image_base64": None,
                            "note_ar": CAPABILITY_NOT_GRANTED_AR}
                png = await ctx.screen.capture()
                encoded = (base64.standard_b64encode(png).decode("ascii")
                           if png else None)
                return {"image_base64": encoded}
            raise ValueError(f"bridge method out of profile: {method}")
        return bridge

    # ─────────────────────────── Calls ───────────────────────────

    def _call_factory(self, state: _ServerState):
        async def host_call(tool: str, args: dict[str, Any]) -> ToolResult:
            return await self._call(state, tool, args)
        return host_call

    async def _call(self, state: _ServerState, tool: str, args: dict[str, Any]) -> ToolResult:
        if state.disabled:
            return ToolResult(text_ar=SERVER_DISABLED_NOTE_AR, is_error=True)
        if state.quarantined:
            return ToolResult(text_ar=SERVER_QUARANTINED_NOTE_AR, is_error=True)
        try:
            session = await self._open_session(state)
            result = await session.call(
                "tools/call", {"name": tool, "arguments": args})
        except McpSessionError as exc:
            return self._strike(state, exc)
        state.strikes = 0
        # Hygiene only. The §3.2 framing + the source naming happen at the
        # ToolRouter boundary (DEC-14), which sees this route's taint=True
        # mount above — so the model reads this text nonce-wrapped, once.
        return ToolResult(text_ar=sanitize_result(result))

    def _strike(self, state: _ServerState, exc: McpSessionError) -> ToolResult:
        state.strikes += 1
        logger.error("[mcp-host] %s strike %d/%d: %s",
                     state.manifest.name, state.strikes, MAX_STRIKES, exc)
        if state.session is not None:
            # A failed session is not trusted to stay coherent — drop it;
            # the next call respawns fresh (backoff across SESSIONS is the
            # documented next-session policy, not an in-turn wait).
            session, state.session = state.session, None
            asyncio.get_running_loop().create_task(session.close())
        if state.strikes >= MAX_STRIKES:
            state.disabled = True
            note = DISABLED_ANNOUNCE_AR.format(name=state.manifest.name)
            logger.warning("[mcp-host] %s DISABLED for the session", state.manifest.name)
            if self._announce is not None:
                self._announce(note)
            return ToolResult(text_ar=SERVER_DISABLED_NOTE_AR, is_error=True)
        return ToolResult(text_ar=SERVER_FAILED_NOTE_AR, is_error=True)

    def _quarantine(self, state: _ServerState) -> None:
        if not state.quarantined:
            state.quarantined = True
            logger.warning("[mcp-host] %s QUARANTINED — tools/list_changed mid-"
                           "session (re-approval = app restart re-fetches the "
                           "catalog under the same grant)", state.manifest.name)

    # ─────────────────────────── Teardown ───────────────────────────

    async def shutdown(self) -> None:
        for state in self._servers.values():
            if state.session is not None:
                await state.session.close()
                state.session = None


__all__ = [
    "DISABLED_ANNOUNCE_AR",
    "MAX_STRIKES",
    "McpHost",
    "SERVER_DISABLED_NOTE_AR",
    "SERVER_FAILED_NOTE_AR",
    "SERVER_QUARANTINED_NOTE_AR",
]
