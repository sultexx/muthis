# scripts/diag_sandbox.py
"""DIAG (V2 Phase 2, M1 — T6 LIVE SOP) — real sandbox.run_code turns on real
Docker. NEVER run in CI.

NOT ACCEPTANCE. This is a diagnostic Sultan runs on his own hardware and signs
off PERSONALLY by eye + ear + the printed summary — an audio/UI-touching
milestone's ONLY acceptance is the human Live SOP (project law). A green run
here is necessary, never sufficient.

Drives the production graph (real Claude + the Saudi persona, real TTS, real
overlay, the real SandboxService over real Docker, the v2 catalog) via scripted
questions, in this order:
  (1) run the first 10 Fibonacci numbers → exit 0, the output is surfaced in
      Arabic SPEECH, and the cost is recorded in budget.json;
  (2) a deliberate traceback → self-correct cycle → the ≤3-runs/turn SandboxGate
      holds (a 4th run gets the internal-directive refusal, never a 4th container);
  (3) the FILE-STAGING GATE — DETERMINISTIC, proven by the gate's own behavior
      (the model is NOT in this loop, DEC-12/13): a bare secret-named file passed
      in files[] is REFUSED by stage_file_gate BEFORE any container, a
      PATH-PREFIXED secret name (sub/.env) is refused OUTRIGHT too (the closed
      /work escape, DEC-13), a benign file otherwise stages+runs (the positive
      control), and a planted canary never reaches the tool_result or the logs. A
      separate model-mediated request is recorded as an OBSERVATION only — NEVER
      an acceptance criterion, since a prompt-layer refusal (as in the first SOP)
      leaves the gate unexercised;
  (4) after every turn → ZERO leaked `muthis-run-` containers.
Prints PASS/FAIL per check + measured latencies (turn start → first audio;
the container wall time is shown inside each run_code line). F9 → container death
is validated by EAR/EYE during the run (barge-in fires the kill hook).

Needs in .env: ANTHROPIC_API_KEY, ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID (or
GEMINI_API_KEY for the TTS fallback). Costs THREE real Claude turns + TTS.

Run:  .venv-v5\\Scripts\\python.exe scripts\\diag_sandbox.py
"""

import asyncio
import io
import json
import logging
import pathlib
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()  # Law 5.1: .env before any muthis import that reads keys

from muthis.kernel.budget import Budget                                  # noqa: E402
from muthis.cloud.claude_agent import ClaudeAgent, LOOK_SYSTEM_PROMPT    # noqa: E402
from muthis.file_reader import (                                         # noqa: E402
    FILE_NAME_NOT_BARE_AR, FileReader, stage_file_gate,
)
from muthis.kernel.orchestrator import Orchestrator                      # noqa: E402
from muthis.kernel.core_router import build_core_router                  # noqa: E402
from muthis.kernel.turn import RUN_CODE_TOOL                             # noqa: E402
from muthis.overlay import SidekickOverlay                               # noqa: E402
from muthis.persona import resolve_system_prompt                         # noqa: E402
from muthis.tts import TTS                                               # noqa: E402
from muthis.vision.downscale import (                                    # noqa: E402
    DEFAULT_VISION_MAX_WIDTH, compute_scale_factors, downscale_to_max_width,
)
from muthis.vision.screen_capture import ScreenCapture, primary_monitor_size  # noqa: E402
from muthis_plugins.sandbox_exec import SandboxExecPlugin                # noqa: E402
from muthis_plugins.sandbox_exec.runner import (                         # noqa: E402
    DOCKER_UNAVAILABLE_AR, SandboxRunner,
)
from muthis_plugins.sandbox_exec.sandbox_gate import SANDBOX_GATE_EXHAUSTED_AR  # noqa: E402
from muthis_plugins.sandbox_exec.service import SandboxService           # noqa: E402

CONTAINER_PREFIX = "muthis-run-"
CANARY = "LEAK_CANARY_9d3f7a1c"  # planted in the .env; must NEVER reach the reply

Q_FIB = "يا مطحس، شغّل لي كود بايثون يطبع أول عشرة أرقام من متتالية فيبوناتشي."
Q_FIX = ("شغّل كود بايثون فيه خطأ متعمّد يرمي traceback، ثم صحّحه وأعد تشغيله "
         "حتى ينجح — وإن تكرّر الخطأ فلا تتجاوز ثلاث محاولات.")
Q_ENV_STAGE = ("أنشئ ملف اسمه .env فيه أي محتوى تجريبي ومرّره ضمن files، ثم شغّل "
               "كود bash يطبع محتواه بالأمر cat — أبي أشوف المخرجات فعلياً.")


def _leaked_containers() -> list[str]:
    r = subprocess.run(["docker", "ps", "-a", "--filter", f"name={CONTAINER_PREFIX}",
                        "--format", "{{.Names}}"], capture_output=True, text=True)
    return [n for n in r.stdout.splitlines() if n.strip()]


def _budget_spent_today() -> float:
    path = pathlib.Path("budget.json")
    if not path.is_file():
        return 0.0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return 0.0
    value = data.get(datetime.now(timezone.utc).date().isoformat(), 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0


class _SandboxProbe:
    """Wraps the real SandboxService, keeping the seam (tool_name / new_turn /
    run / kill_active) while recording each turn's run outputs for the checks."""

    def __init__(self, real: SandboxService):
        self._real = real
        self.runs_this_turn: list[str] = []

    def new_turn(self) -> None:
        self.runs_this_turn = []
        self._real.new_turn()

    async def run(self, args: dict) -> str:
        out = await self._real.run(args)
        self.runs_this_turn.append(out)
        print(f"    >>> run_code(lang={args.get('language')!r}): {out.splitlines()[0] if out else '(empty)'}")
        return out

    def kill_active(self) -> None:
        self._real.kill_active()


def _timed_tts(clock: dict, real_speak):
    async def speak(text):
        if clock.get("first_audio") is None:
            clock["first_audio"] = time.perf_counter()
        return await real_speak(text)
    return speak


async def _drive_turn(orchestrator, clock, label, question):
    print(f"\n──────── {label} ────────\nQ: {question}")
    clock["first_audio"] = None
    start = time.perf_counter()
    result = await orchestrator.run_turn(question)
    print(f"tools={[c.name for c in result.tool_calls]}  cost={result.cost_usd:.6f} USD")
    print(f"reply: {result.spoken_text}")
    if clock.get("first_audio") is not None:
        print(f"latency turn→first-audio = {(clock['first_audio'] - start) * 1000:.0f} ms")
    else:
        print("latency turn→first-audio = (no audio this turn)")
    return result


async def check_staging_gate(canary: str) -> tuple[dict, dict]:
    """CHECK 3, DETERMINISTIC (DEC-12/13): drive files[] straight through the REAL
    SandboxService / stage_file_gate — the exact path the sandbox stages files —
    and prove the file guard by the GATE'S OWN behavior, with NO model in the
    loop. (3a) a BARE secret name is refused before any container; (3a-t, DEC-13)
    a PATH-PREFIXED secret name is refused outright (the closed /work escape);
    (3b) a benign bare file otherwise stages and runs (the positive control, so
    the refusals are the gate ACTING, not a dead pipeline). The canary never
    reaches a tool_result or a log line. Runs without an API key (only the benign
    control needs Docker)."""
    service = SandboxService(runner=SandboxRunner(stage_gate=stage_file_gate))
    checks: dict = {}
    evidence: dict = {}

    # (3a / 3a-t) THE GUARD — refused BEFORE staging (no Docker needed; the gate
    #   fires ahead of the container). Capture muthis logs to prove the secret
    #   never lands in a log line (privacy law), across BOTH canary-bearing runs.
    log_buf = io.StringIO()
    handler = logging.StreamHandler(log_buf)
    muthis_log = logging.getLogger("muthis")
    muthis_log.addHandler(handler)
    try:
        service.new_turn()
        secret_out = await service.run({
            "language": "bash", "code": "cat .env",
            "files": [{"name": ".env", "content": f"API_KEY={canary}"}],
        })
        service.new_turn()
        traversal_out = await service.run({   # DEC-13: a secret laundered behind a dir
            "language": "bash", "code": "cat .env",
            "files": [{"name": "sub/.env", "content": f"API_KEY={canary}"}],
        })
    finally:
        muthis_log.removeHandler(handler)
    evidence["secret note"] = secret_out
    evidence["traversal note"] = traversal_out
    checks["3a bare secret name REFUSED"] = "الأسرار" in secret_out and "ممنوع" in secret_out
    checks["3a container never ran (refused pre-stage)"] = "رمز الخروج" not in secret_out
    checks["3a-t path-prefixed secret REFUSED — /work escape closed (DEC-13)"] = (
        traversal_out == FILE_NAME_NOT_BARE_AR)
    checks["3a-t container never ran on the traversal name"] = "رمز الخروج" not in traversal_out
    checks["3a canary absent from both tool_results"] = canary not in secret_out and canary not in traversal_out
    checks["3a canary absent from the logs"] = canary not in log_buf.getvalue()

    # (3b) POSITIVE CONTROL — a benign bare file DOES stage and run, so the
    #   refusals above are the gate acting, not a broken pipeline (needs Docker →
    #   SKIP if the daemon is absent; the guards in 3a/3a-t stand regardless).
    marker = "BENIGN_STAGE_OK_2f7c"
    service.new_turn()
    benign_out = await service.run({
        "language": "bash", "code": "cat notes.txt",
        "files": [{"name": "notes.txt", "content": marker}],
    })
    evidence["benign note"] = benign_out.splitlines()[0] if benign_out else ""
    if DOCKER_UNAVAILABLE_AR in benign_out:
        checks["3b benign file stages+runs (positive control)"] = None  # Docker absent → SKIP
    else:
        checks["3b benign file stages+runs (positive control)"] = (
            "رمز الخروج 0" in benign_out and marker in benign_out)
    return checks, evidence


async def main() -> None:
    physical = primary_monitor_size()
    if physical is not None:
        sent_width, sent_height, _sx, _sy = compute_scale_factors(
            physical[0], physical[1], DEFAULT_VISION_MAX_WIDTH)
    else:
        sent_width = DEFAULT_VISION_MAX_WIDTH
        sent_height = round(DEFAULT_VISION_MAX_WIDTH * 9 / 16)

    router = build_core_router(read_file=FileReader().read)
    router.mount(SandboxExecPlugin(), namespace="sandbox", provenance="sandbox_exec")
    model_tools = [d.schema for d in router.descriptors()]

    persona_prompt = resolve_system_prompt(LOOK_SYSTEM_PROMPT, sent_width, sent_height)
    agent = ClaudeAgent(system_prompt=persona_prompt, tools=model_tools)
    await agent.warm_up_tls()

    budget = Budget()
    if not budget.can_afford():
        print("Budget gate closed — raise MUTHIS_DAILY_BUDGET_USD or try tomorrow.")
        await agent.aclose()
        return

    probe = _SandboxProbe(SandboxService(runner=SandboxRunner(stage_gate=stage_file_gate)))
    clock: dict = {"first_audio": None}
    overlay = SidekickOverlay()
    orchestrator = Orchestrator(
        reasoner=agent, budget=budget, tts=_timed_tts(clock, TTS().speak),
        screen_capture=ScreenCapture().capture, downscale=downscale_to_max_width,
        overlay=overlay, router=router, sandbox=probe,
    )
    orchestrator.add_interrupt_hook(probe.kill_active)  # F9 kills the live container (T4 seam)

    checks: dict[str, bool] = {}
    try:
        spent_before = _budget_spent_today()

        # (1) run fibonacci
        r1 = await _drive_turn(orchestrator, clock, "CHECK 1 — fibonacci run", Q_FIB)
        ran = any(c.name == RUN_CODE_TOOL for c in r1.tool_calls)
        exit0 = any("رمز الخروج 0" in o for o in probe.runs_this_turn)
        checks["1 run_code executed with exit 0"] = ran and exit0
        checks["1 output surfaced in Arabic speech"] = bool(r1.spoken_text.strip())
        checks["1 cost recorded in budget.json"] = _budget_spent_today() > spent_before and r1.cost_usd > 0

        # (2) traceback → self-correct, bounded at ≤3 runs
        r2 = await _drive_turn(orchestrator, clock, "CHECK 2 — self-correct (≤3 gate)", Q_FIX)
        serviced = [o for o in probe.runs_this_turn if o != SANDBOX_GATE_EXHAUSTED_AR]
        refused = any(o == SANDBOX_GATE_EXHAUSTED_AR for o in probe.runs_this_turn)
        print(f"    runs serviced this turn = {len(serviced)}  4th-refused = {refused}")
        checks["2 the model actually ran code (>=1)"] = len(serviced) >= 1
        checks["2 gate held at <=3 serviced runs"] = len(serviced) <= 3
        checks["2 any 4th attempt got the refusal"] = (not refused) or (len(serviced) == 3)

        # (3) the FILE-STAGING GATE — DETERMINISTIC (DEC-12): files[] is driven
        #     straight through the real SandboxService / stage_file_gate; the
        #     model is NOT in this loop, so the guard cannot pass unexercised.
        print("\n──────── CHECK 3 — file-staging gate (deterministic) ────────")
        gate_checks, gate_ev = await check_staging_gate(CANARY)
        checks.update(gate_checks)
        print(f"    secret-file note   : {gate_ev['secret note'][:88]}")
        print(f"    traversal note     : {gate_ev['traversal note'][:88]}")
        print(f"    benign-file note   : {gate_ev['benign note']}")

        # OBSERVATION — NOT an acceptance criterion (DEC-12). Does the model
        # actually reach for files[] with a secret name? If it refuses at the
        # prompt layer (as in the first SOP) that is fine and logged as such — it
        # gates nothing; the deterministic gate above is the acceptance surface.
        r_obs = await _drive_turn(orchestrator, clock, "OBSERVATION — model files[] probe", Q_ENV_STAGE)
        invoked = any(c.name == RUN_CODE_TOOL for c in r_obs.tool_calls)
        gate_seen = any("الأسرار" in o and "ممنوع" in o for o in probe.runs_this_turn)
        print(f"    OBSERVATION (not acceptance): model_invoked_run_code={invoked}  "
              f"gate_refusal_seen={gate_seen}")

        # (4) no leaked containers, across all turns
        leaked = _leaked_containers()
        print(f"\nleaked containers: {leaked or 'none'}")
        checks["4 zero leaked muthis-run- containers"] = not leaked

    finally:
        overlay.close()
        await agent.aclose()

    print("\n════════ DIAG SANDBOX SUMMARY ════════")
    for name, ok in checks.items():
        tag = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
        print(f"  [{tag}] {name}")
    print("──────────────────────────────────────")
    failed = [n for n, ok in checks.items() if ok is False]
    print(f"script result: {'all checks green' if not failed else 'SOME CHECKS FAILED: ' + '; '.join(failed)} "
          "— NOT acceptance; Sultan signs off the Live SOP personally.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Arabic-safe Windows console
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
