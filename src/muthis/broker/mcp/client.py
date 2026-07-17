# src/muthis/broker/mcp/client.py
"""
McpSession — ONE stdio MCP server child process, from spawn to kill.

Lifecycle contract (roadmap §8.2): spawn → initialize (protocol version
PINNED; sampling never advertised; the experimental muthis-profile/1
offered) → notifications/initialized → serve requests. Every outgoing
request carries a timeout (default 20 s) — the kernel owns the clock,
never the child. close() terminates, waits a grace, then kills; the
reader task is cancelled and the pipes dropped.

Server→client REQUESTS (the muthis-profile bridge, M1-6) are routed to
the injected `bridge` seam; without one — or for any method outside the
profile — the session answers METHOD_NOT_FOUND politely. Sampling
requests are ALWAYS refused (roadmap §8.4: cost + injection channel).

stderr is drained to the English log (a silent pipe deadlocks a chatty
child on Windows; a dropped pipe loses its diagnostics).
"""

from __future__ import annotations

import asyncio
import logging
import shlex
from typing import Any, Awaitable, Callable, Optional

from muthis_sdk.mcp import (
    MUTHIS_PROFILE,
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    error_response,
    is_notification,
    is_request,
    is_response,
    notification,
    request,
    write_message,
)
from muthis_sdk.mcp.framing import FramingError, read_message
from muthis_sdk.mcp.messages import INTERNAL_ERROR, METHOD_NOT_FOUND

logger = logging.getLogger("muthis.broker.mcp.client")

CALL_TIMEOUT_S = 20.0     # per JSON-RPC request (roadmap §8.5)
INIT_TIMEOUT_S = 10.0
KILL_GRACE_S = 3.0

LIST_CHANGED_METHOD = "notifications/tools/list_changed"

# The server→client methods the muthis-profile bridge may service (Q-1.2:
# annotate is deliberately NOT here). Everything else: METHOD_NOT_FOUND.
BRIDGE_METHODS = frozenset({"muthis/read_file", "muthis/capture"})

BridgeFn = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class McpSessionError(Exception):
    """Spawn/handshake/protocol failure — the host turns it into a strike."""


class McpSession:
    def __init__(
        self,
        name: str,
        entry: str,
        *,
        bridge: Optional[BridgeFn] = None,
        on_list_changed: Optional[Callable[[], None]] = None,
        call_timeout_s: float = CALL_TIMEOUT_S,
    ) -> None:
        self.name = name
        self._entry = entry
        self._bridge = bridge
        self._on_list_changed = on_list_changed
        self._call_timeout_s = call_timeout_s
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 0
        self.server_info: dict[str, Any] = {}

    # ─────────────────────────── Lifecycle ───────────────────────────

    async def start(self) -> None:
        # posix=False keeps Windows backslashes intact but ALSO keeps the
        # surrounding quotes on quoted tokens — strip them, or spawn gets a
        # literally-quoted argv[0] (WinError 2).
        argv = [token[1:-1] if len(token) > 1 and token[0] == token[-1] == '"' else token
                for token in shlex.split(self._entry, posix=False)]
        if not argv:
            raise McpSessionError(f"{self.name}: empty entry command")
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise McpSessionError(f"{self.name}: cannot spawn {argv[0]!r}: {exc}") from exc
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        await self._handshake()

    async def _handshake(self) -> None:
        result = await self.call(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                # Sampling is deliberately ABSENT — never advertised (§8.4).
                "capabilities": {"experimental": {MUTHIS_PROFILE: {}}},
                "clientInfo": {"name": "muthis", "version": "2.0"},
            },
            timeout_s=INIT_TIMEOUT_S,
        )
        version = result.get("protocolVersion")
        if version not in SUPPORTED_PROTOCOL_VERSIONS:
            await self.close()
            raise McpSessionError(
                f"{self.name}: unsupported protocol version {version!r} "
                f"(we accept {sorted(SUPPORTED_PROTOCOL_VERSIONS)})")
        self.server_info = result.get("serverInfo", {}) or {}
        await self._send(notification("notifications/initialized"))
        logger.info("[mcp] %s up: %s (protocol %s)", self.name,
                    self.server_info.get("name", "?"), version)

    def _fail_pending(self, reason: str) -> None:
        """Fail every in-flight request NOW — a dead/closing session must
        strike immediately, never sit out the per-call timeout."""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(McpSessionError(reason))
        self._pending.clear()

    async def close(self) -> None:
        for task in (self._reader_task, self._stderr_task):
            if task is not None:
                task.cancel()
        self._fail_pending(f"{self.name}: session closed")
        proc = self._proc
        self._proc = None
        if proc is None or proc.returncode is not None:
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=KILL_GRACE_S)
        except (TimeoutError, asyncio.TimeoutError):
            logger.warning("[mcp] %s ignored terminate — killing", self.name)
            proc.kill()
            await proc.wait()

    # ─────────────────────────── Requests ───────────────────────────

    async def call(self, method: str, params: Optional[dict[str, Any]] = None,
                   *, timeout_s: Optional[float] = None) -> dict[str, Any]:
        """One request → its result dict. Timeout/error/closure raise
        McpSessionError — the HOST translates those into strikes + Arabic
        notes; nothing here reaches a turn directly."""
        if self._proc is None or self._proc.stdin is None:
            raise McpSessionError(f"{self.name}: session not running")
        self._next_id += 1
        msg_id = self._next_id
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        await self._send(request(msg_id, method, params))
        try:
            reply = await asyncio.wait_for(
                future, timeout=self._call_timeout_s if timeout_s is None else timeout_s)
        except (TimeoutError, asyncio.TimeoutError):
            raise McpSessionError(f"{self.name}: {method} timed out") from None
        finally:
            self._pending.pop(msg_id, None)
        if "error" in reply:
            err = reply["error"] or {}
            raise McpSessionError(
                f"{self.name}: {method} failed [{err.get('code')}] {err.get('message')}")
        result = reply.get("result")
        return result if isinstance(result, dict) else {"value": result}

    async def _send(self, message: dict[str, Any]) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        await write_message(self._proc.stdin, message)

    # ─────────────────────────── Read loop ───────────────────────────

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        reader = self._proc.stdout
        try:
            while True:
                try:
                    message = await read_message(reader)
                except FramingError as exc:
                    logger.error("[mcp] %s broken frame: %s", self.name, exc)
                    continue  # skip the frame; persistent breakage ends in EOF
                if message is None:
                    logger.info("[mcp] %s closed its stdout (EOF)", self.name)
                    break
                await self._dispatch(message)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — the loop must die loudly in logs only
            logger.exception("[mcp] %s reader crashed", self.name)
        finally:
            # A server that stopped talking can never answer an in-flight
            # request — fail them NOW (the 60s-vs-instant strike lesson,
            # caught by test_three_strikes: 3 × the 20s timeout).
            self._fail_pending(f"{self.name}: server stream ended")

    async def _dispatch(self, message: dict[str, Any]) -> None:
        if is_response(message):
            future = self._pending.get(message.get("id"))
            if future is not None and not future.done():
                future.set_result(message)
            return
        if is_notification(message):
            if message.get("method") == LIST_CHANGED_METHOD and self._on_list_changed:
                self._on_list_changed()
            return
        if is_request(message):
            await self._serve_peer_request(message)

    async def _serve_peer_request(self, message: dict[str, Any]) -> None:
        """The server→client door — profile methods only, bridge-gated."""
        method = message.get("method", "")
        msg_id = message.get("id")
        if method.startswith("sampling/"):
            await self._send(error_response(
                msg_id, METHOD_NOT_FOUND, "sampling is refused by policy"))
            return
        if method not in BRIDGE_METHODS or self._bridge is None:
            await self._send(error_response(
                msg_id, METHOD_NOT_FOUND, f"unsupported method: {method}"))
            return
        try:
            result = await self._bridge(method, message.get("params") or {})
            await self._send({"jsonrpc": "2.0", "id": msg_id, "result": result})
        except Exception as exc:  # noqa: BLE001 — the bridge wall
            logger.exception("[mcp] %s bridge failed for %s", self.name, method)
            await self._send(error_response(msg_id, INTERNAL_ERROR, str(exc)))

    async def _drain_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        try:
            while True:
                line = await self._proc.stderr.readline()
                if not line:
                    break
                logger.debug("[mcp:%s! ] %s", self.name,
                             line.decode("utf-8", "replace").rstrip())
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            pass


__all__ = ["BRIDGE_METHODS", "CALL_TIMEOUT_S", "McpSession", "McpSessionError"]
