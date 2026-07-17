# tests/test_kernel_layering.py
"""
The V2 layering guards (Phase 0 birth; Phase 1 M1-1 settled decision Q-4:
the compat shims are GONE and every consumer imports muthis.kernel.* —
the shim-identity test retired with the shims it guarded).

Two architectural invariants remain, enforced by test instead of review:
  1. SDK PURITY — muthis_sdk imports nothing from muthis.*: the SDK must be
     installable and importable with no app present (community plugins run
     against the SDK alone).
  2. KERNEL ISOLATION — every kernel module imports cleanly on its own
     (the ≤300-line law's "importable in isolation" clause).
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import muthis_sdk

KERNEL_MODULES = (
    "muthis.kernel.budget",
    "muthis.kernel.draw_dispatch",
    "muthis.kernel.highlight_gate",
    "muthis.kernel.history_hygiene",
    "muthis.kernel.orchestrator",
    "muthis.kernel.tool_router",
    "muthis.kernel.turn",
    "muthis.kernel.turn_pass",
    "muthis.kernel.verbosity",
)


def test_the_shims_are_gone():
    """Q-4 settled: the old flat paths must NOT resolve anymore — a revived
    shim would silently split imports again."""
    for retired in ("muthis.orchestrator", "muthis.turn", "muthis.budget",
                    "muthis.turn_pass", "muthis.highlight_gate",
                    "muthis.draw_dispatch", "muthis.history_hygiene",
                    "muthis.verbosity"):
        try:
            importlib.import_module(retired)
        except ModuleNotFoundError:
            continue
        raise AssertionError(f"{retired} still importable — a shim came back")


def test_sdk_imports_nothing_from_the_app():
    sdk_dir = Path(muthis_sdk.__file__).parent
    offending = []
    for source in sdk_dir.rglob("*.py"):
        for line_number, line in enumerate(
            source.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if re.match(r"\s*(from|import)\s+muthis(\.|\s|$)", line):
                offending.append(f"{source.name}:{line_number}: {line.strip()}")
    assert not offending, f"muthis_sdk must not import the app: {offending}"


def test_kernel_modules_import_in_isolation():
    for kernel_name in KERNEL_MODULES:
        module = importlib.import_module(kernel_name)
        assert module.__name__ == kernel_name
