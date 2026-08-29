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

import hashlib
import logging
import os
import subprocess
from typing import Any, Optional

from .docker_cmd import build_kill
from .runner import SandboxOutcome, SandboxRunner
from .sandbox_gate import SandboxGate

logger = logging.getLogger("muthis.sandbox.service")

# ─── THE RUN RECORD (DEC-61's two questions, answered for the sandbox) ────────
#
# WHY IT EXISTS. The live evaluation of 2026-08-29 could not answer "did the
# sandbox run the user's program?" because NOTHING survived the call: the code
# reaches the container over stdin and `docker rm -f` runs in a `finally`, so
# the only trace was Docker's own daemon log — four container lifecycles
# carrying neither the code sent nor the output returned. P0's D-3 reached
# 17/18 only because its harness STORED the snippet it sent; production stored
# nothing, so the exact defect that measurement was rebuilt to detect is the
# one defect invisible here.
#
# WHY THE CODE IS NOT WRITTEN DOWN BY DEFAULT. DEC-61 ruled the FILE PATH too
# sensitive to log at a time when content was already never logged — "log the
# EXTENSION, the OUTCOME and the SIZE" — and left the general rule for every
# later surface: classify by PERMANENCE and AUDIENCE, never by whether the
# datum feels secret. A log persists past the session, is read by other eyes,
# and travels in a bug report. Submitted code is USER CONTENT and is strictly
# more sensitive than the path DEC-61 removed, so persisting it by default
# would INVERT that law rather than extend it.
#
# SO THE DEFAULT IS A FINGERPRINT, NOT THE TEXT — AND THE SHAPE IS NOT INVENTED.
# `stt.py` already logs `Scribe OK (%d chars)` and gates the transcript itself
# behind MUTHIS_DEBUG=1. This is that precedent applied to the one module whose
# content is as sensitive as the user's own words.
#
# THE FINGERPRINT IS SUFFICIENT FOR THE QUESTION THAT WAS UNANSWERABLE, and the
# argument is short enough to check: compare the digest of the code sent against
# the digest of the file the user believes was run. DIFFER → the model sent
# something else, and the output is correct for a program nobody asked for.
# EQUAL → the sandbox ran the right program, so a spoken answer that disagrees
# with a deterministic program's output did not come from the sandbox. Neither
# branch needs the text. The limit is declared with it: for a NON-deterministic
# program the equal branch localizes the defect without settling it.
#
# STDOUT GETS A LENGTH AND NO DIGEST, DELIBERATELY. A digest is one-way only
# where the input space is large; the outputs this sandbox returns are routinely
# a handful of digits, and a hash of `211351` is inverted by brute force in
# microseconds. A digest there would be CONTENT WEARING A FINGERPRINT'S CLOTHES
# — worse than logging nothing, because it reads as protection. The same
# objection applies weakly to very short PROGRAMS, and is accepted knowingly:
# the code digest is the datum the incident actually required.
_DEBUG_ENV = "MUTHIS_DEBUG"


def _digest(text: str) -> str:
    """A short stable fingerprint — IDENTITY without content (DEC-61).

    LINE ENDINGS ARE NORMALIZED FIRST, AND THAT IS THE WHOLE POINT OF THE
    FINGERPRINT RATHER THAN A CONVENIENCE. This is a Windows project: every file
    on disk is CRLF, while a model composing a tool argument emits LF. Digesting
    the raw strings makes an IDENTICAL program fingerprint DIFFERENTLY from the
    user's own file — which is not a small inaccuracy but the instrument's worst
    possible failure, since the one question it exists to answer is "is this the
    same program?" and it would answer NO every time. Caught by measurement:
    `main.py` fingerprinted `01c041663ae4` read as text and `b9ba95a38cc2` read
    as bytes, for the same ten lines.

    Nothing else is normalized. Indentation and trailing whitespace stay inside
    the digest, because a program that differs there IS a different program."""
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(unified.encode("utf-8")).hexdigest()[:12]


def log_run(args: dict[str, Any], outcome: Optional[SandboxOutcome],
            *, debug: Optional[bool] = None) -> None:
    """Record ONE run_code servicing. English, never raises, never speaks.

    `outcome is None` means the per-turn gate refused the call — still a datum,
    and precisely the one a pass-economy question asks for, so it is recorded
    rather than dropped. `debug` is injected for the tests; production reads
    MUTHIS_DEBUG exactly as `stt.py` does."""
    code = str(args.get("code") or "")
    lang = str(args.get("language") or "?")
    if outcome is None:
        logger.info("[sandbox] REFUSED by gate — lang=%s code=%s (%d chars)",
                    lang, _digest(code), len(code))
        return
    logger.info(
        "[sandbox] lang=%s code=%s (%d chars, %d lines) → exit=%s %dms%s "
        "stdout=%d chars stderr=%d chars",
        lang, _digest(code), len(code), code.count("\n") + 1,
        outcome.exit_code, outcome.wall_ms,
        " TIMED-OUT" if outcome.timed_out else "",
        len(outcome.stdout_tail), len(outcome.stderr_tail),
    )
    # The content half — OFF unless deliberately switched on for a session, the
    # `stt.py` transcript gate exactly. Both halves are here so a debugging
    # session never has to reach for a different tool than the one it is using.
    on = os.getenv(_DEBUG_ENV) == "1" if debug is None else debug
    if on:
        logger.info("[sandbox] code sent: %r", code)
        logger.info("[sandbox] stdout returned: %r", outcome.stdout_tail)


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
            log_run(args, None)
            return refusal
        outcome = await self._runner.run(args, attempt=self._gate.runs)
        log_run(args, outcome)
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


__all__ = ["SandboxService", "format_outcome_ar", "log_run"]
