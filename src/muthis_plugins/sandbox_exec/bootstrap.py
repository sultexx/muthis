# src/muthis_plugins/sandbox_exec/bootstrap.py
"""The DEC-9 in-container staging bootstrap + the per-language run map.

The container command runs this fixed python script (delivered base64 in the
`docker create` argv, so no quoting or newlines cross the CLI). It reads the
JSON payload from stdin, writes the staged files + the user code into the
writable tmpfs `/work`, and execs the interpreter from `cwd=/work` with the
user's stdin piped in — NO docker cp, keeping every DEC-3 flag (incl.
`--read-only`). Layering-pure (stdlib only)."""

from __future__ import annotations

import base64
import json
from typing import Any

# language -> (code filename under /work, argv to run it). Absolute /work paths
# so the container's cwd never matters; the code is always a file we write.
LANG_RUN: dict[str, tuple[str, list[str]]] = {
    "python": ("main.py", ["python", "/work/main.py"]),
    "node": ("main.js", ["node", "/work/main.js"]),
    "bash": ("main.sh", ["bash", "/work/main.sh"]),
    "sqlite": ("main.sql", ["sqlite3", ":memory:", ".read /work/main.sql"]),
}

# The staging script. `with` blocks flush + close each file BEFORE the exec, so
# the interpreter never reads a half-written file; a missing interpreter exits
# 127 with a clear stderr line instead of a traceback.
BOOTSTRAP = r'''
import sys, json, base64, subprocess
p = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
for _name, _b64 in p.get("files", {}).items():
    with open("/work/" + _name, "wb") as _f:
        _f.write(base64.b64decode(_b64))
with open("/work/" + p["main"], "wb") as _f:
    _f.write(base64.b64decode(p["code_b64"]))
_stdin = base64.b64decode(p.get("stdin_b64", ""))
try:
    _r = subprocess.run(p["argv"], cwd="/work", input=_stdin)
    sys.exit(_r.returncode)
except FileNotFoundError:
    sys.stderr.write("sandbox: interpreter not available in image\n")
    sys.exit(127)
'''


def build_payload(language: str, code: str, files: list[tuple[str, bytes]],
                  stdin: str) -> bytes:
    """The stdin wire (DEC-9): JSON with base64'd contents. `files` are the
    (name, bytes) pairs that ALREADY passed the FileReader gates."""
    main, argv = LANG_RUN[language]
    payload: dict[str, Any] = {
        "main": main,
        "argv": argv,
        "code_b64": base64.b64encode(code.encode("utf-8")).decode("ascii"),
        "files": {name: base64.b64encode(content).decode("ascii")
                  for name, content in files},
        "stdin_b64": (base64.b64encode(stdin.encode("utf-8")).decode("ascii")
                      if stdin else ""),
    }
    return json.dumps(payload).encode("utf-8")


__all__ = ["BOOTSTRAP", "LANG_RUN", "build_payload"]
