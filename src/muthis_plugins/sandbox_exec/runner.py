# src/muthis_plugins/sandbox_exec/runner.py
"""SandboxRunner — one container lifecycle per run (V2 Phase 2, M1, T2).

DEC-9 staging: `create -i` (bootstrap command, all DEC-3 flags incl.
`--read-only`) -> `start -ai` (feed the base64 payload on stdin; the bootstrap
writes files+code into the tmpfs `/work` and execs) -> bounded readers (64
KiB/stream, ANSI-stripped) -> wait, with a wall timeout that triggers
`docker kill` -> finally `docker rm -f`. NEVER raises: no Docker, a timeout, an
OOM, or a staging refusal all come back as a short Arabic note.

Runs OVER injected seams (an asyncio subprocess factory + the FileReader gate)
so it is fully fake-testable, and imports muthis_sdk + stdlib only — the kernel
stays blind to Docker (DEC-3-C); the real seams are injected at composition."""

from __future__ import annotations

import asyncio
import logging
import time
from asyncio.subprocess import PIPE
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from .bootstrap import LANG_RUN, build_payload
from .docker_cmd import (
    build_create, build_kill, build_rm, build_start, new_container_name, tail_text,
)
from .schema import DEFAULT_TIMEOUT_S, MAX_TIMEOUT_S, MAX_TOTAL_FILE_BYTES

logger = logging.getLogger("muthis.sandbox.runner")

DEFAULT_IMAGE = "python:3.12-slim"
STREAM_TAIL_BYTES = 64 * 1024  # 64 KiB per stream (bounded readers)

# Injected seams. `ExecFn` is asyncio.create_subprocess_exec-shaped; `StageGateFn`
# is the FileReader gate: (name, content) -> None if OK else an Arabic reason.
ExecFn = Callable[..., Awaitable[Any]]
StageGateFn = Callable[[str, bytes], Optional[str]]

# Model-facing Arabic notes (logs stay English).
DOCKER_UNAVAILABLE_AR = "تعذّر تشغيل الصندوق المعزول — خدمة Docker غير متاحة الآن."
TIMEOUT_AR = "تجاوز التشغيل المهلة المحدّدة فأوقفته."
FILES_TOO_LARGE_AR = "الملفات المرفقة أكبر من الحد المسموح (١ ميغابايت)."
BAD_LANGUAGE_AR = "هذه اللغة غير مدعومة في الصندوق."
NO_CODE_AR = "ما فيه كود لأشغّله."
STAGING_UNAVAILABLE_AR = "تعذّر تجهيز الملفات بأمان في هذه الجلسة."
INTERNAL_ERROR_AR = "صار خطأ غير متوقّع أثناء التشغيل المعزول."


@dataclass(frozen=True)
class SandboxOutcome:
    """The §2.1 result surface. On a hard failure only `note_ar` is set; on a
    timeout `note_ar` carries the timeout note AND the partial fields survive."""

    exit_code: Optional[int] = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    wall_ms: int = 0
    attempt: int = 1
    timed_out: bool = False
    note_ar: Optional[str] = None


class SandboxRunner:
    """Stateless per call (Law 11): no loops, no retries — one container, one
    result. The self-correction loop is the kernel's agentic loop; the ≤3-runs
    bound is SandboxGate (T3)."""

    def __init__(
        self, *,
        image: str = DEFAULT_IMAGE,
        exec_fn: ExecFn = asyncio.create_subprocess_exec,
        stage_gate: Optional[StageGateFn] = None,
        default_timeout_s: int = DEFAULT_TIMEOUT_S,
        max_timeout_s: int = MAX_TIMEOUT_S,
    ) -> None:
        self._image = image
        self._exec = exec_fn
        self._gate = stage_gate
        self._default_timeout = default_timeout_s
        self._max_timeout = max_timeout_s

    async def run(self, args: dict[str, Any], *, attempt: int = 1) -> SandboxOutcome:
        """Service one run_code call. Never raises — the outer wall."""
        try:
            return await self._run(args, attempt)
        except Exception:  # noqa: BLE001 — plugins/engines return, never raise
            logger.exception("[sandbox.runner] unexpected failure")
            return SandboxOutcome(attempt=attempt, note_ar=INTERNAL_ERROR_AR)

    # ───────────────────────────── internals ─────────────────────────────

    async def _run(self, args: dict[str, Any], attempt: int) -> SandboxOutcome:
        language = str(args.get("language") or "").strip()
        if language not in LANG_RUN:
            return SandboxOutcome(attempt=attempt, note_ar=BAD_LANGUAGE_AR)
        code = str(args.get("code") or "")
        if not code.strip():
            return SandboxOutcome(attempt=attempt, note_ar=NO_CODE_AR)
        staged = self._stage(args.get("files"))
        if isinstance(staged, str):  # a gate / size refusal note
            return SandboxOutcome(attempt=attempt, note_ar=staged)
        timeout = self._clamp_timeout(args.get("timeout_s"))
        payload = build_payload(language, code, staged, str(args.get("stdin") or ""))
        return await self._lifecycle(payload, timeout, attempt)

    def _stage(self, files_arg: Any):
        """Gate model-provided files[] through FileReader; return the (name,
        bytes) list or an Arabic refusal note."""
        if not files_arg:
            return []
        if self._gate is None:
            return STAGING_UNAVAILABLE_AR
        staged: list[tuple[str, bytes]] = []
        total = 0
        for entry in files_arg:
            name = str((entry or {}).get("name") or "").strip()
            data = str((entry or {}).get("content") or "").encode("utf-8")
            total += len(data)
            if total > MAX_TOTAL_FILE_BYTES:
                return FILES_TOO_LARGE_AR
            if not name:
                continue
            refusal = self._gate(name, data)  # FileReader secret-name / binary
            if refusal:
                return refusal
            staged.append((name, data))
        return staged

    def _clamp_timeout(self, raw: Any) -> float:
        try:
            seconds = int(raw) if raw is not None else self._default_timeout
        except (TypeError, ValueError):
            seconds = self._default_timeout
        return float(max(1, min(seconds, self._max_timeout)))

    async def _lifecycle(self, payload: bytes, timeout: float, attempt: int) -> SandboxOutcome:
        name = new_container_name()
        started = time.perf_counter()
        try:
            create_rc, _out, _err = await self._short(build_create(name, self._image))
        except Exception:  # noqa: BLE001 — docker binary missing / daemon down
            logger.warning("[sandbox.runner] create could not spawn docker")
            return SandboxOutcome(attempt=attempt, note_ar=DOCKER_UNAVAILABLE_AR)
        if create_rc != 0:
            logger.warning("[sandbox.runner] create rc=%s", create_rc)
            await self._reap(name)
            return SandboxOutcome(attempt=attempt, note_ar=DOCKER_UNAVAILABLE_AR)
        try:
            out, err, code, timed = await self._start(name, payload, timeout)
        finally:
            await self._reap(name)  # rm -f ALWAYS
        return SandboxOutcome(
            exit_code=code,
            stdout_tail=tail_text(out, STREAM_TAIL_BYTES),
            stderr_tail=tail_text(err, STREAM_TAIL_BYTES),
            wall_ms=int((time.perf_counter() - started) * 1000),
            attempt=attempt, timed_out=timed,
            note_ar=TIMEOUT_AR if timed else None,
        )

    async def _start(self, name: str, payload: bytes, timeout: float):
        proc = await self._exec(*build_start(name), stdin=PIPE, stdout=PIPE, stderr=PIPE)
        proc.stdin.write(payload)
        await proc.stdin.drain()
        proc.stdin.close()
        readers = asyncio.gather(_read_tail(proc.stdout), _read_tail(proc.stderr))
        timed = False
        try:
            out, err = await asyncio.wait_for(asyncio.shield(readers), timeout)
        except asyncio.TimeoutError:
            await self._short(build_kill(name))  # the external clock owns eradication
            out, err = await readers
            timed = True
        code = await proc.wait()
        return out, err, code, timed

    async def _short(self, argv: list[str]):
        proc = await self._exec(*argv, stdin=None, stdout=PIPE, stderr=PIPE)
        out, err = await proc.communicate()
        return proc.returncode, out, err

    async def _reap(self, name: str) -> None:
        try:
            await self._short(build_rm(name))
        except Exception:  # noqa: BLE001 — teardown must never surface
            logger.warning("[sandbox.runner] rm -f failed for %s", name)


async def _read_tail(reader: Any, cap: int = STREAM_TAIL_BYTES) -> bytes:
    """Drain a stream keeping only its last `cap` bytes (bounded memory, tail)."""
    buf = bytearray()
    while True:
        chunk = await reader.read(65536)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > cap:
            del buf[:-cap]
    return bytes(buf)


__all__ = ["SandboxRunner", "SandboxOutcome", "ExecFn", "StageGateFn",
           "DEFAULT_IMAGE", "DOCKER_UNAVAILABLE_AR", "TIMEOUT_AR",
           "FILES_TOO_LARGE_AR", "BAD_LANGUAGE_AR", "NO_CODE_AR",
           "STAGING_UNAVAILABLE_AR", "INTERNAL_ERROR_AR"]
