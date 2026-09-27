"""
prodlog.py — the production durable log must be UNCHANGED by the harness, and
this module proves it by CONTENT, never by trust (DEC-154).

Two independent checks, because a log can be written two ways:

  * the DIRECTORY — every file under `~/.muthis/logs` (the log and any rotation
    siblings) is snapshotted as (size, mtime_ns, sha256) before a run and
    compared after: a changed, added or removed file is a finding;
  * the HANDLERS — no logger in this process may hold a handler outside a
    closed allow-list, checked by EXACT type, so a `FileHandler` (a
    `StreamHandler` subclass) or anything else unexpected is a finding.

WHY AN ALLOW-LIST, AND WHY THE SELF-TEST NEVER BUILDS A FILE HANDLER:
`tests/test_no_script_attaches_the_durable_log.py` forbids constructing any file
handler anywhere under `scripts/`, this module included. Evading that guard to
test this one would lower a guard, so the handler check is written so that a
NON-CONSOLE stream handler exercises the very branch a file handler would take.

The self-test proves both checks FIRE on a stand-in directory and a stand-in
handler — a check that has never fired is not a check that passed — and the real
directory is only ever read, to hash it.
"""

from __future__ import annotations

import hashlib
import logging
import pathlib
import sys
from typing import Iterable

LOG_DIR = pathlib.Path.home() / ".muthis" / "logs"


class ProductionLogChanged(RuntimeError):
    """Raised when either check finds the production log touched."""


def snapshot(directory: pathlib.Path = LOG_DIR) -> dict[str, tuple[int, int, str]]:
    if not directory.exists():
        return {}
    shot = {}
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        stat = path.stat()
        shot[path.relative_to(directory).as_posix()] = (
            stat.st_size, stat.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
    return shot


def changes(before: dict, after: dict) -> list[str]:
    found = [f"added: {name}" for name in sorted(set(after) - set(before))]
    found += [f"removed: {name}" for name in sorted(set(before) - set(after))]
    for name in sorted(set(before) & set(after)):
        (s0, m0, h0), (s1, m1, h1) = before[name], after[name]
        if (s0, h0) != (s1, h1):
            found.append(f"content changed: {name} ({s0} -> {s1} bytes)")
        elif m0 != m1:
            found.append(f"touched: {name} (mtime moved, content equal)")
    return found


def _allowed(handler: logging.Handler, extra: Iterable[type]) -> bool:
    kind = type(handler)
    if kind is logging.NullHandler or kind in tuple(extra):
        return True
    return kind is logging.StreamHandler and handler.stream in (sys.stderr, sys.stdout)


def foreign_handlers(extra_allowed: Iterable[type] = ()) -> list[str]:
    """Every handler on every logger that is not on the allow-list."""
    extra = tuple(extra_allowed)
    loggers = [logging.getLogger()] + [lg for lg in logging.Logger.manager.loggerDict.values()
                                       if isinstance(lg, logging.Logger)]
    return [f"{lg.name or 'root'}: {type(h).__name__}"
            for lg in loggers for h in lg.handlers if not _allowed(h, extra)]


class Guard:
    """Snapshot on entry, compare on exit; both checks, every time."""

    def __init__(self, directory: pathlib.Path = LOG_DIR, extra_allowed: Iterable[type] = ()):
        self.directory = directory
        self.extra = tuple(extra_allowed)
        self.before: dict = {}

    def __enter__(self) -> "Guard":
        problems = foreign_handlers(self.extra)
        if problems:
            raise ProductionLogChanged(f"a foreign log handler before the run: {problems}")
        self.before = snapshot(self.directory)
        return self

    def verify(self) -> list[str]:
        return (changes(self.before, snapshot(self.directory))
                + [f"foreign handler: {h}" for h in foreign_handlers(self.extra)])

    def __exit__(self, *exc) -> None:
        found = self.verify()
        if found:
            raise ProductionLogChanged("; ".join(found))


__all__ = ["Guard", "LOG_DIR", "ProductionLogChanged", "changes", "foreign_handlers",
           "snapshot"]
