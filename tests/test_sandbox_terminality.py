# tests/test_sandbox_terminality.py
"""
The Docker-unavailable note carries TERMINALITY (the voice-surface pass, item 2).

**THE DEFECT WAS MEASURED LIVE, AND IT WAS EXPENSIVE.** With Docker down, the
model spent the WHOLE `SandboxGate` budget — three `docker create` calls at rc=1
inside one turn, ~$0.12 — on a condition no retry could fix. The old note read
«خدمة Docker غير متاحة الآن»: it reported only what did NOT happen, and «الآن»
actively signalled TRANSIENT. Retrying is exactly what a competent agentic model
does with an unexplained failure, and the agentic loop exists to retry.

This is DEC-35's shape repeating and the standing note law (AGENTS.md 2026-07-30,
ruled in DEC-58) applied: a refusal that does not communicate terminality invites
rational retry.

**A MESSAGE CHANGE, NOT A GATE CHANGE** — Sultan's ruling, and the DEC-42 /
DEC-55-ruling-2 discipline that a note is never made easier to write by moving a
gate. `test_the_gate_did_not_move` asserts that rather than promising it.

**THE HONEST LIMIT, and it is the whole reason this file says so out loud:** the
acceptance — *a Docker-down turn performs ONE create attempt, not three* — is
MODEL BEHAVIOUR. Every check below proves the note's TEXT and its delivery. None
of them can prove the note CHANGES BEHAVIOUR (DEC-62 measured exactly this gap:
K1–K7 were green while the live model re-opened anyway). Only Sultan's live SOP
run closes the acceptance.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from muthis.trust.confirm_gate import DIRECTIVE_MARKER_AR
from muthis_plugins.sandbox_exec.runner import DOCKER_UNAVAILABLE_AR, SandboxRunner
from muthis_plugins.sandbox_exec.sandbox_gate import MAX_SANDBOX_RUNS, SandboxGate
from muthis_plugins.sandbox_exec.service import SandboxService

from test_sandbox_runner import FakeDocker

CODE = {"language": "python", "code": "print(1)"}

# The three obligations of the standing note law, one anchor each. Asserted as
# SUBSTRINGS OF THE CONSTANT, never as `outcome.note_ar == DOCKER_UNAVAILABLE_AR`
# — that equality is satisfied by ANY text, including the old one, because both
# sides move together. `test_sandbox_runner.py` holds exactly that equality, which
# is why it stayed green through this change and why this file exists.
STATE_ACHIEVED = "ما نُفِّذ شي"
NOTHING_CHANGED = "ولا تغيّر عنده أي شيء"
TERMINAL = "حالة نهائية في هذه الجولة ولا تُصلَح بإعادة المحاولة"
DO_NOT_RETRY = "لا تُشغّل الكود مرة ثانية الآن"
NEXT_STEP = "خبّر المستخدم أن Docker غير مشغّل عنده وأنه يشغّله ثم يعيد طلبه"

# The wording that CAUSED the retries. Its absence is asserted, because a revert
# to a transient-sounding note is the regression this file guards.
OLD_TRANSIENT_WORDING = "خدمة Docker غير متاحة الآن"


def _run(runner: SandboxRunner, args: dict) -> object:
    return asyncio.run(runner.run(args))


# ───────────────────────── the note itself ──────────────────────────────────

def test_the_note_carries_all_three_obligations() -> None:
    """(1) what WAS accomplished, (2) TERMINAL or transient, (3) the valid NEXT
    STEP. Each is a distinct clause: a note satisfying two of three is the exact
    partial fix DEC-58 rejected."""
    for clause in (STATE_ACHIEVED, NOTHING_CHANGED, TERMINAL, DO_NOT_RETRY, NEXT_STEP):
        assert DOCKER_UNAVAILABLE_AR.count(clause) == 1, f"missing clause: {clause!r}"


def test_the_transient_wording_that_caused_the_retries_is_gone() -> None:
    """«غير متاحة الآن» reads as "try later". The positive control for the whole
    change: without this, a revert restores the defect with every test green."""
    assert OLD_TRANSIENT_WORDING not in DOCKER_UNAVAILABLE_AR


def test_the_note_is_an_internal_directive_the_model_never_reads_aloud() -> None:
    """The SandboxGate note's shape. Checked against the LIVE marker constant so
    the two families cannot drift apart."""
    assert DIRECTIVE_MARKER_AR in DOCKER_UNAVAILABLE_AR


def test_the_note_names_a_user_action_not_a_model_retry() -> None:
    """PRECISION the honest answer needs: the condition is terminal FOR RETRYING,
    while the thing that changes it is a USER action. A note claiming Docker is
    permanently gone would be false; one implying the model can fix it restores
    the loop."""
    assert "يشغّله ثم يعيد طلبه" in DOCKER_UNAVAILABLE_AR
    assert "بدون تشغيل" in DOCKER_UNAVAILABLE_AR  # the fallback that still helps


def test_the_note_is_arabic_only() -> None:
    """The language split: a model-facing note carries no log text. "Docker" is
    the product name the user must recognise and is the one permitted Latin
    token."""
    latin = {w for w in DOCKER_UNAVAILABLE_AR.split() if w.isascii() and w.isalpha()}
    assert latin == {"Docker"}, f"unexpected Latin tokens: {latin}"


# ───────────────────────── delivery on BOTH paths ───────────────────────────

def test_both_docker_down_paths_deliver_the_note() -> None:
    """`_lifecycle` has two Docker-down exits — the binary failing to spawn, and
    `create` returning non-zero. A note fixed on one path only would still lose
    the budget on the other."""
    raised = _run(SandboxRunner(exec_fn=FakeDocker(raise_on_create=True)), CODE)
    assert raised.note_ar == DOCKER_UNAVAILABLE_AR and raised.exit_code is None
    failed = _run(SandboxRunner(exec_fn=FakeDocker(create_rc=1)), CODE)
    assert failed.note_ar == DOCKER_UNAVAILABLE_AR and failed.exit_code is None


def test_the_model_reads_the_note_verbatim_through_the_real_service() -> None:
    """END-TO-END through the REAL `SandboxService`: `format_outcome_ar` must pass
    a hard-failure note through UNCHANGED. A wrapper that prefixed or truncated it
    would drop the terminality clause without failing any check above."""
    service = SandboxService(runner=SandboxRunner(exec_fn=FakeDocker(create_rc=1)))
    text = asyncio.run(service.run(CODE))
    assert text == DOCKER_UNAVAILABLE_AR


# ───────────────────────── the gate did NOT move ────────────────────────────

def test_the_gate_did_not_move() -> None:
    """THE DISCIPLINE, ASSERTED RATHER THAN PROMISED. Sultan ruled this a message
    change; a note is never made easier to write by loosening a bound. The ≤3
    budget is untouched, and a Docker-down service still ALLOWS three runs —
    which is also the honest statement of this fix's limit: nothing deterministic
    stops the retries, so the note is the entire lever."""
    assert MAX_SANDBOX_RUNS == 3
    gate = SandboxGate()
    assert [gate.consume() is None for _ in range(3)] == [True, True, True]
    assert gate.consume() is not None  # the 4th is still refused

    service = SandboxService(runner=SandboxRunner(exec_fn=FakeDocker(create_rc=1)),
                             gate=SandboxGate())
    served = [asyncio.run(service.run(CODE)) for _ in range(3)]
    assert served == [DOCKER_UNAVAILABLE_AR] * 3, "the gate's allowance changed"


def test_a_docker_down_run_still_consumes_exactly_one_slot_per_call() -> None:
    """The accounting the acceptance rests on: ONE call, ONE slot, ONE create
    attempt. If the model obeys the note it makes one call and the turn costs one
    attempt — the deterministic half of "ONE create attempt, not three"."""
    docker = FakeDocker(create_rc=1)
    gate = SandboxGate()
    service = SandboxService(runner=SandboxRunner(exec_fn=docker), gate=gate)
    asyncio.run(service.run(CODE))
    assert gate.runs == 1
    creates = [c for c in docker.calls if len(c) > 1 and c[1] == "create"]
    assert len(creates) == 1, f"one call produced {len(creates)} create attempts"
