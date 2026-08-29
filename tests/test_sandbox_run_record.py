# tests/test_sandbox_run_record.py
"""The sandbox RUN RECORD — the instrument the 2026-08-29 evaluation proved missing,
and the DEC-61 privacy property that decides its shape.

WHAT WENT WRONG WITHOUT IT. Four containers ran during the live evaluation and
nothing survived to say what code they were given or what they printed: the
payload crosses on stdin and `docker rm -f` runs in a `finally`. So "did the
sandbox run the user's program?" was unanswerable from the record, and the
question had to be settled by reconstructing container lifetimes out of Docker's
own daemon log.

BOTH HALVES ARE ASSERTED, AND THAT IS THE POINT. A test that only checks the
canary is ABSENT passes trivially against a module that logs nothing at all —
which is the state this file exists to leave behind. So every privacy assertion
here is paired with a POSITIVE control proving the record was actually written,
exactly the pairing DEC-61's own two tests carry.
"""

from __future__ import annotations

import asyncio
import logging

from muthis_plugins.sandbox_exec.runner import SandboxOutcome
from muthis_plugins.sandbox_exec.service import SandboxService, log_run

# Canaries: if either reaches a default log, the privacy law is breached.
CODE_CANARY = "SECRET_TOKEN_IN_THE_USERS_PROGRAM = 'hunter2'"
STDOUT_CANARY = "PRIVATE_OUTPUT_THE_PROGRAM_PRINTED"


class _FakeRunner:
    def __init__(self, outcome=None):
        self.on_active = None
        self.calls = []
        self._outcome = outcome or SandboxOutcome(
            exit_code=0, stdout_tail=STDOUT_CANARY, wall_ms=7)

    async def run(self, args, *, attempt=1):
        self.calls.append((args, attempt))
        return self._outcome


def _run_once(caplog, code=CODE_CANARY):
    caplog.set_level(logging.INFO, logger="muthis.sandbox.service")
    svc = SandboxService(runner=_FakeRunner())
    asyncio.run(svc.run({"language": "python", "code": code}))
    return caplog.text


# ─────────────────── the record is WRITTEN (positive control) ────────────────

def test_a_serviced_run_is_recorded_at_all(caplog):
    """The control that fails on a module that logs nothing — without it every
    privacy assertion below is vacuously true."""
    text = _run_once(caplog)
    assert "[sandbox]" in text, "no run record was written at all"
    assert "exit=0" in text
    assert "7ms" in text
    assert "lang=python" in text


def test_the_record_carries_the_sizes_DEC61_permits(caplog):
    text = _run_once(caplog)
    assert f"{len(CODE_CANARY)} chars" in text
    assert f"stdout={len(STDOUT_CANARY)} chars" in text


# ───────────────────────── the DEC-61 privacy property ──────────────────────

def test_the_CODE_never_reaches_the_log_by_default(caplog):
    """Submitted code is USER CONTENT and strictly more sensitive than the path
    DEC-61 removed from the logs. It must not be written by default."""
    text = _run_once(caplog)
    assert CODE_CANARY not in text
    assert "hunter2" not in text


def test_the_STDOUT_never_reaches_the_log_by_default(caplog):
    text = _run_once(caplog)
    assert STDOUT_CANARY not in text


def test_no_digest_is_taken_of_stdout(caplog):
    """A hash of a handful of digits is inverted by brute force, so a stdout
    digest would be content wearing a fingerprint's clothes. The record carries
    stdout's LENGTH and nothing derived from its bytes."""
    import hashlib
    text = _run_once(caplog)
    full = hashlib.sha256(STDOUT_CANARY.encode()).hexdigest()
    assert full[:12] not in text


# ───────────── the fingerprint is a FUNCTION of the code (mechanism) ─────────

def test_the_digest_actually_tracks_the_code(caplog):
    """A constant string would satisfy "a digest is present". The property that
    makes the record useful is that DIFFERENT code fingerprints DIFFERENTLY and
    IDENTICAL code fingerprints IDENTICALLY — that is the whole comparison the
    incident needed."""
    a = _run_once(caplog, code="x = 1")
    caplog.clear()
    b = _run_once(caplog, code="x = 2")
    caplog.clear()
    a2 = _run_once(caplog, code="x = 1")

    def digest_of(text):
        # The LAST record's fingerprint — caplog.text accumulates within a test.
        for token in reversed(text.split()):
            if token.startswith("code="):
                return token[len("code="):]
        raise AssertionError(f"no digest in record: {text!r}")

    assert digest_of(a) != digest_of(b), "different code shares a fingerprint"
    assert digest_of(a) == digest_of(a2), "identical code fingerprints differently"


def test_the_same_program_fingerprints_the_same_from_a_CRLF_file(caplog):
    """THE COMPARISON THIS INSTRUMENT EXISTS FOR, and the defect measurement
    caught: every file on this Windows project is CRLF while a model emits LF.
    A digest over the raw strings answers "is this the same program?" with NO
    for every identical program — so the fingerprint is taken over normalized
    line endings, and the user's own file on disk must match what was sent."""
    crlf = "x = 1\r\nprint(x)\r\n"        # the file as it sits on disk
    lf = "x = 1\nprint(x)\n"              # the same program as the model sends it
    a = _run_once(caplog, code=crlf)
    caplog.clear()
    b = _run_once(caplog, code=lf)

    def digest_of(text):
        for token in reversed(text.split()):
            if token.startswith("code="):
                return token[len("code="):]
        raise AssertionError(f"no digest in record: {text!r}")

    assert digest_of(a) == digest_of(b), "CRLF and LF of one program disagree"


def test_indentation_is_still_inside_the_fingerprint(caplog):
    """The control on the normalization above: it must not become "ignore
    whitespace". A program that differs in indentation IS a different program,
    and in Python it is a different program in the strongest sense."""
    a = _run_once(caplog, code="if x:\n    y = 1\n")
    caplog.clear()
    b = _run_once(caplog, code="if x:\n        y = 1\n")

    def digest_of(text):
        for token in reversed(text.split()):
            if token.startswith("code="):
                return token[len("code="):]
        raise AssertionError(f"no digest in record: {text!r}")

    assert digest_of(a) != digest_of(b), "indentation vanished from the digest"


# ─────────────────── the opt-in half, on the stt.py precedent ────────────────

def test_MUTHIS_DEBUG_turns_the_content_on(caplog):
    """The gate must be a real switch. A gate that never opens is indistinguish-
    able from a module that cannot log content at all, and would make the
    default-off assertions above prove nothing about the gate."""
    caplog.set_level(logging.INFO, logger="muthis.sandbox.service")
    log_run({"language": "python", "code": CODE_CANARY},
            SandboxOutcome(exit_code=0, stdout_tail=STDOUT_CANARY, wall_ms=7),
            debug=True)
    assert CODE_CANARY in caplog.text
    assert STDOUT_CANARY in caplog.text


def test_the_gate_is_shut_when_the_flag_is_absent(monkeypatch, caplog):
    """The production read — MUTHIS_DEBUG unset means OFF, the `stt.py` shape."""
    monkeypatch.delenv("MUTHIS_DEBUG", raising=False)
    caplog.set_level(logging.INFO, logger="muthis.sandbox.service")
    log_run({"language": "python", "code": CODE_CANARY},
            SandboxOutcome(exit_code=0, stdout_tail=STDOUT_CANARY, wall_ms=7))
    assert CODE_CANARY not in caplog.text
    assert "[sandbox]" in caplog.text          # ... but the record still happened


# ───────────────────────────── the refused attempt ──────────────────────────

def test_a_gate_refusal_is_still_recorded(caplog):
    """The 4th run of a turn never reaches the runner, but the model ASKING is
    exactly the datum a pass-economy question wants — so it is not dropped."""
    caplog.set_level(logging.INFO, logger="muthis.sandbox.service")
    svc = SandboxService(runner=_FakeRunner())
    for _ in range(4):
        asyncio.run(svc.run({"language": "python", "code": "x"}))
    assert "REFUSED by gate" in caplog.text


def test_a_refusal_does_not_leak_the_code_either(caplog):
    caplog.set_level(logging.INFO, logger="muthis.sandbox.service")
    svc = SandboxService(runner=_FakeRunner())
    for _ in range(4):
        asyncio.run(svc.run({"language": "python", "code": CODE_CANARY}))
    assert CODE_CANARY not in caplog.text
