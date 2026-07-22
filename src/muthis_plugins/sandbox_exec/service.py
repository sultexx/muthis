# src/muthis_plugins/sandbox_exec/service.py
"""SandboxService — the turn-aware executor behind sandbox.run_code (T5).

The plugin (SandboxExecPlugin) is a DECLARATION for the model catalog; the
actual servicing lives HERE, in the plugin domain (never the sealed kernel —
DEC-3-C). This object bundles the per-turn SandboxGate (≤3 runs/turn), the
SandboxRunner (one container per run), and the live-container name for F9
eradication. The kernel's turn_pass calls run() after the sync point (like the
read servicing); the orchestrator resets the gate per turn via new_turn(); F9
fires kill_active() through the T4 on_interrupt hook. Never raises — every
failure is a short Arabic note. muthis_sdk + stdlib + sibling modules only."""

from __future__ import annotations

import logging
import subprocess
from typing import Any, Optional

from .docker_cmd import build_kill
from .runner import SandboxOutcome, SandboxRunner
from .sandbox_gate import SandboxGate

logger = logging.getLogger("muthis.sandbox.service")


def format_outcome_ar(outcome: SandboxOutcome) -> str:
    """The Arabic tool_result the model reads: the exit code + stdout/stderr
    tails so it can read the output and self-correct, or the failure note."""
    if outcome.exit_code is None:            # a hard failure (no Docker / staging refusal)
        return outcome.note_ar or "تعذّر التشغيل."
    parts = [f"انتهى التشغيل برمز الخروج {outcome.exit_code} خلال {outcome.wall_ms}ms."]
    if outcome.timed_out and outcome.note_ar:
        parts.append(outcome.note_ar)
    if outcome.stdout_tail:
        parts.append("المخرَج:\n" + outcome.stdout_tail)
    if outcome.stderr_tail:
        parts.append("الأخطاء:\n" + outcome.stderr_tail)
    if not outcome.stdout_tail and not outcome.stderr_tail:
        parts.append("(لا مخرجات).")
    return "\n".join(parts)


class SandboxService:
    """Turn-aware run_code servicer. Built once at composition (main.py) from a
    SandboxRunner + a SandboxGate; wires the runner's on_active seam to track
    the live container for eradication. The kernel matches run_code on
    turn.RUN_CODE_TOOL (derived from the ONE separator), so this holds no name."""

    def __init__(self, *, runner: SandboxRunner, gate: Optional[SandboxGate] = None) -> None:
        self._runner = runner
        self._gate = gate or SandboxGate()
        self._active: Optional[str] = None
        runner.on_active = self._track  # the runner announces its live container here

    def _track(self, name: Optional[str]) -> None:
        self._active = name

    def new_turn(self) -> None:
        """Fresh per-turn run budget — the orchestrator calls this at turn start
        (mirrors the per-turn HighlightGate rebuild)."""
        self._gate.reset()

    async def run(self, args: dict[str, Any]) -> str:
        """Service ONE run_code call, bounded by the ≤3/turn gate. Returns the
        Arabic tool_result; NEVER raises."""
        refusal = self._gate.consume()
        if refusal is not None:              # the 4th run of the turn
            return refusal
        outcome = await self._runner.run(args, attempt=self._gate.runs)
        return format_outcome_ar(outcome)

    def kill_active(self) -> None:
        """The F9 on_interrupt hook CONTENT (fire-and-forget, run on the hook's
        own daemon thread — T4's contract): eradicate the live container. Sync
        and never raises."""
        name = self._active
        if not name:
            return
        try:
            subprocess.run(build_kill(name), capture_output=True, timeout=10)
        except Exception:  # noqa: BLE001 — F9 eradication must never surface
            logger.warning("[sandbox.service] kill of %s failed — ignored", name)


__all__ = ["SandboxService", "format_outcome_ar"]
