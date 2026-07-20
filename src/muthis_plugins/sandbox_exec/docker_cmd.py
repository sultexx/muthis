# src/muthis_plugins/sandbox_exec/docker_cmd.py
"""Pure Docker CLI argument builders + byte helpers for sandbox_exec.

No subprocess here — just arg lists and small pure functions — so runner.py is
a lifecycle over injected seams and EVERY restriction flag is unit-assertable.
The DEC-3 flag spec (verified live in P0) is the single source. Layering-pure."""

from __future__ import annotations

import base64
import re
import uuid

from .bootstrap import BOOTSTRAP

# The DEC-3 restriction spec, verified live in P0. `--read-only` is KEPT (DEC-9
# stages via a stdin bootstrap, not docker cp, so the flag stays).
DEC3_FLAGS: tuple[str, ...] = (
    "--network", "none",
    "--user", "65534:65534",
    "--read-only",
    "--tmpfs", "/work:rw,size=256m",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges",
    "--memory", "512m",
    "--memory-swap", "512m",
    "--cpus", "1.0",
    "--pids-limit", "128",
)

_PREFIX = "muthis-run-"
# The DEC-9 bootstrap, delivered base64 so no quoting/newlines cross the CLI.
# `-i` keeps stdin open for the payload; there is deliberately NO `--workdir`
# (it makes Docker pre-create /work root-owned 0755, blocking the nobody user).
_BOOT_CMD = "import base64;exec(base64.b64decode('%s'))" % (
    base64.b64encode(BOOTSTRAP.encode("utf-8")).decode("ascii"),
)

# ANSI / VT escape stripper — the model reads output as text, not terminal codes.
_ANSI = re.compile(rb"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def new_container_name() -> str:
    """Unique per run so eradication from ANY thread is possible (feeds T4)."""
    return _PREFIX + uuid.uuid4().hex[:12]


def build_create(name: str, image: str) -> list[str]:
    return ["docker", "create", "-i", "--name", name, *DEC3_FLAGS,
            image, "python", "-c", _BOOT_CMD]


def build_start(name: str) -> list[str]:
    return ["docker", "start", "-ai", name]


def build_kill(name: str) -> list[str]:
    return ["docker", "kill", name]


def build_rm(name: str) -> list[str]:
    return ["docker", "rm", "-f", name]


def tail_text(data: bytes, limit: int) -> str:
    """ANSI-stripped last `limit` bytes, decoded for the model."""
    clean = _ANSI.sub(b"", data)
    return clean[-limit:].decode("utf-8", errors="replace")


__all__ = [
    "DEC3_FLAGS", "new_container_name", "build_create", "build_start",
    "build_kill", "build_rm", "tail_text",
]
