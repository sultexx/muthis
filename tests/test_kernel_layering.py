# tests/test_kernel_layering.py
"""
The V2 Phase-0 layering guards (the great split, decision Q-4).

Three architectural invariants, enforced by test instead of review:
  1. SHIM IDENTITY — every name a V1 compat shim re-exports IS the kernel
     object (same `id`), so old-path and new-path importers can never drift
     apart (a shim that re-bound a name would silently split monkeypatching
     and isinstance checks between two module objects).
  2. SDK PURITY — muthis_sdk imports nothing from muthis.*: the SDK must be
     installable and importable with no app present (community plugins run
     against the SDK alone).
  3. KERNEL ISOLATION — every kernel module imports cleanly on its own
     (the ≤300-line law's "importable in isolation" clause survives the move).
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import muthis_sdk

# Old shim path → new kernel path. The shims' __all__ is the re-export
# contract; identity is asserted for EVERY listed name.
SHIMMED = {
    "muthis.orchestrator": "muthis.kernel.orchestrator",
    "muthis.turn_pass": "muthis.kernel.turn_pass",
    "muthis.turn": "muthis.kernel.turn",
    "muthis.highlight_gate": "muthis.kernel.highlight_gate",
    "muthis.draw_dispatch": "muthis.kernel.draw_dispatch",
    "muthis.history_hygiene": "muthis.kernel.history_hygiene",
    "muthis.verbosity": "muthis.kernel.verbosity",
    "muthis.budget": "muthis.kernel.budget",
}


def test_shims_reexport_identical_objects():
    for shim_name, kernel_name in SHIMMED.items():
        shim = importlib.import_module(shim_name)
        kernel = importlib.import_module(kernel_name)
        assert shim.__all__, f"{shim_name} must declare its re-export contract"
        for name in shim.__all__:
            assert getattr(shim, name) is getattr(kernel, name), (
                f"{shim_name}.{name} is not the kernel object — the shim drifted"
            )


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
    for kernel_name in sorted(set(SHIMMED.values())):
        module = importlib.import_module(kernel_name)
        assert module.__name__ == kernel_name
