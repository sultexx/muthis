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
#
# THE TERMINALITY NOTE (the voice-surface pass). MEASURED LIVE: with Docker down
# the model spent the WHOLE SandboxGate budget — three `docker create` calls at
# rc=1 in one turn, ~$0.12 — because the old text ("خدمة Docker غير متاحة الآن")
# reported only what did NOT happen, and the word «الآن» actively read as
# TRANSIENT. Retrying is what a competent agentic model does with an unexplained
# failure, and the agentic loop exists to retry.
#
# So this note carries the standing note law's three obligations (AGENTS.md,
# 2026-07-30; ruled in DEC-58): (1) the STATE ACHIEVED — nothing was built, run
# or changed, which also stops the model reasoning about partial state; (2)
# TERMINAL, said in those words and closing the attempt, with the reason it
# cannot be retried away; (3) the VALID NEXT STEP, named — because "do not do X"
# leaves a model with no sanctioned move and the helpful move is the wrong one.
#
# It is an INTERNAL DIRECTIVE (the «توجيه داخلي» family, the SandboxGate note's
# shape) so the model obeys it and never reads it aloud.
#
# PRECISION, because the honest answer is not simply "terminal": the condition is
# terminal FOR RETRYING — no further attempt this turn can succeed — while the
# thing that changes it is a USER action, not a model action. The note says
# exactly that instead of claiming Docker is permanently gone.
#
# THIS IS A MESSAGE CHANGE, NOT A GATE CHANGE (Sultan's ruling, and the DEC-42 /
# DEC-55-ruling-2 discipline): `SandboxGate` still allows ≤3 runs per turn, and
# no bound, cap or limit moved to make this note easier to write.
DOCKER_UNAVAILABLE_AR = (
    "توجيه داخلي (لا يراه المستخدم): ما نُفِّذ شي — خدمة Docker غير مشغّلة على "
    "جهاز المستخدم، فما انبنى صندوق ولا شُغِّل الكود ولا تغيّر عنده أي شيء. "
    "وهذه حالة نهائية في هذه الجولة ولا تُصلَح بإعادة المحاولة: لا تُشغّل الكود "
    "مرة ثانية الآن، لأن كل محاولة تالية تفشل بنفس السبب بالضبط. بدل المحاولة: "
    "خبّر المستخدم أن Docker غير مشغّل عنده وأنه يشغّله ثم يعيد طلبه، واشرح له "
    "الكود ووش المتوقّع يطلع منه بالكلام بدون تشغيل."
)
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
        on_active: Optional[Callable[[Optional[str]], None]] = None,
    ) -> None:
        self._image = image
        self._exec = exec_fn
        self._gate = stage_gate
        self._default_timeout = default_timeout_s
        self._max_timeout = max_timeout_s
        # T5: announced the LIVE container name (and None when it is gone) so the
        # F9 on_interrupt hook can eradicate it. Public: the service wires it.
        self.on_active = on_active

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
        self._announce(name)  # container is live — F9 can eradicate it now
        try:
            out, err, code, timed = await self._start(name, payload, timeout)
        finally:
            self._announce(None)     # container gone
            await self._reap(name)   # rm -f ALWAYS
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

    def _announce(self, name: Optional[str]) -> None:
        if self.on_active is None:
            return
        try:
            self.on_active(name)
        except Exception:  # noqa: BLE001 — tracking must never break a run
            logger.warning("[sandbox.runner] on_active seam raised — ignored")


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
