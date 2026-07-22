# tests/test_sandbox_runner.py
"""T2 — the SandboxRunner engine, over a FAKE subprocess seam (no real Docker).

Asserts: the create command carries EVERY DEC-3 restriction flag (incl.
`--read-only`) + `-i` + the base64 bootstrap; DEC-9 staging is stdin-only (no
`docker cp` ANYWHERE); files pass the REAL FileReader gate; a timeout triggers
`docker kill`; the container is always `rm -f`'d; a raising subprocess degrades
to an Arabic note; output is bounded (64 KiB) and ANSI-stripped."""

from __future__ import annotations

import asyncio
import json
from typing import Optional

# The test MAY import the kernel to build a real gate; the runner stays
# layering-pure and only ever sees the injected seam.
from muthis.file_reader import FILE_BLOCKED_AR, FILE_NOT_TEXT_AR, _blocked_name
from muthis_plugins.sandbox_exec.docker_cmd import DEC3_FLAGS
from muthis_plugins.sandbox_exec.runner import (
    DOCKER_UNAVAILABLE_AR,
    TIMEOUT_AR,
    SandboxRunner,
)


def filereader_gate(name: str, content: bytes) -> Optional[str]:
    """A real FileReader-backed staging gate (secret-name + binary)."""
    if _blocked_name(name):
        return FILE_BLOCKED_AR
    if b"\x00" in content[:4096]:
        return FILE_NOT_TEXT_AR
    return None


# ─── the fake asyncio subprocess seam ────────────────────────────────────────

class _Reader:
    def __init__(self, chunks, block: Optional[asyncio.Event] = None):
        self._chunks = list(chunks)
        self._block = block

    async def read(self, n: int = -1) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        if self._block is not None:
            await self._block.wait()  # "running" until docker kill lands
        return b""


class _Writer:
    def __init__(self):
        self.buf = bytearray()
        self.closed = False

    def write(self, b):
        self.buf.extend(b)

    async def drain(self):
        pass

    def close(self):
        self.closed = True


class _Proc:
    def __init__(self, *, rc=0, out=b"", err=b"", block=None):
        self.stdin = _Writer()
        self.stdout = _Reader([out] if out else [], block)
        self.stderr = _Reader([err] if err else [], block)
        self._rc, self._block = rc, block
        self.returncode = None

    async def communicate(self, input=None):
        self.returncode = self._rc
        return b"", b""

    async def wait(self):
        if self._block is not None:
            await self._block.wait()
        self.returncode = self._rc
        return self._rc


class FakeDocker:
    """Scriptable exec_fn. Records every argv; `hang` makes `start` block until
    a `docker kill` arrives (the timeout path)."""

    def __init__(self, *, create_rc=0, start_rc=0, out=b"", err=b"",
                 hang=False, raise_on_create=False):
        self.calls: list[list[str]] = []
        self._cfg = dict(create_rc=create_rc, start_rc=start_rc, out=out, err=err,
                         hang=hang, raise_on_create=raise_on_create)
        self._kill = asyncio.Event()
        self.start_proc: Optional[_Proc] = None

    async def __call__(self, *argv, stdin=None, stdout=None, stderr=None):
        self.calls.append(list(argv))
        sub = argv[1] if len(argv) > 1 else ""
        if sub == "create":
            if self._cfg["raise_on_create"]:
                raise FileNotFoundError("docker not found")
            return _Proc(rc=self._cfg["create_rc"])
        if sub == "kill":
            self._kill.set()
            return _Proc(rc=0)
        if sub == "start":
            block = self._kill if self._cfg["hang"] else None
            self.start_proc = _Proc(
                rc=137 if self._cfg["hang"] else self._cfg["start_rc"],
                out=self._cfg["out"], err=self._cfg["err"], block=block)
            return self.start_proc
        return _Proc(rc=0)  # rm and anything else

    def ran(self, sub: str) -> bool:
        return any(len(c) > 1 and c[1] == sub for c in self.calls)

    def cmd(self, sub: str) -> list[str]:
        return next(c for c in self.calls if len(c) > 1 and c[1] == sub)


def _run(runner, args, **kw):
    return asyncio.run(runner.run(args, **kw))


# ─── tests ───────────────────────────────────────────────────────────────────

def test_create_carries_every_dec3_flag_and_the_bootstrap():
    fake = FakeDocker(out=b"hi\n")
    outcome = _run(SandboxRunner(exec_fn=fake, stage_gate=filereader_gate),
                   {"language": "python", "code": "print('hi')"})
    create = fake.cmd("create")
    for flag in DEC3_FLAGS:
        assert flag in create, f"missing DEC-3 flag {flag}"
    assert "--read-only" in create           # DEC-9 keeps it
    assert "-i" in create and "--workdir" not in create
    assert create[-3:-1] == ["python", "-c"]  # the base64 bootstrap command
    assert outcome.exit_code == 0 and "hi" in outcome.stdout_tail
    assert outcome.note_ar is None and fake.ran("rm")  # always reaped


def test_staging_is_stdin_only_never_docker_cp():
    fake = FakeDocker(out=b"ok")
    _run(SandboxRunner(exec_fn=fake, stage_gate=filereader_gate),
         {"language": "python", "code": "print(1)",
          "files": [{"name": "data.txt", "content": "hello"}]})
    assert not fake.ran("cp")  # DEC-9: NO docker cp anywhere
    payload = json.loads(bytes(fake.start_proc.stdin.buf).decode("utf-8"))
    assert "data.txt" in payload["files"]          # staged over stdin
    assert payload["argv"] == ["python", "/work/main.py"]


def test_files_pass_the_real_filereader_gate():
    runner = SandboxRunner(exec_fn=FakeDocker(), stage_gate=filereader_gate)
    secret = _run(runner, {"language": "python", "code": "print(1)",
                           "files": [{"name": ".env", "content": "K=V"}]})
    assert secret.note_ar == FILE_BLOCKED_AR and secret.exit_code is None
    binary = _run(runner, {"language": "python", "code": "print(1)",
                           "files": [{"name": "b.bin", "content": "a\x00b"}]})
    assert binary.note_ar == FILE_NOT_TEXT_AR


def test_timeout_triggers_docker_kill():
    fake = FakeDocker(hang=True)
    outcome = _run(SandboxRunner(exec_fn=fake, stage_gate=filereader_gate),
                   {"language": "python", "code": "while True: pass", "timeout_s": 1})
    assert fake.ran("kill")            # the eradication primitive fired
    assert outcome.timed_out and outcome.exit_code == 137
    assert outcome.note_ar == TIMEOUT_AR and fake.ran("rm")


def test_missing_docker_and_create_failure_degrade_to_a_note():
    raised = _run(SandboxRunner(exec_fn=FakeDocker(raise_on_create=True)),
                  {"language": "python", "code": "print(1)"})
    assert raised.note_ar == DOCKER_UNAVAILABLE_AR and raised.exit_code is None
    failed = FakeDocker(create_rc=1)
    outcome = _run(SandboxRunner(exec_fn=failed), {"language": "python", "code": "print(1)"})
    assert outcome.note_ar == DOCKER_UNAVAILABLE_AR and failed.ran("rm")


def test_output_is_ansi_stripped_and_tail_bounded():
    big = b"\x1b[31m" + b"A" * 70000 + b"\x1b[0m"
    outcome = _run(SandboxRunner(exec_fn=FakeDocker(out=big), stage_gate=filereader_gate),
                   {"language": "python", "code": "print('x')"})
    assert "\x1b" not in outcome.stdout_tail            # ANSI stripped
    assert len(outcome.stdout_tail) <= 64 * 1024        # bounded to 64 KiB (tail)
    assert set(outcome.stdout_tail) == {"A"}
