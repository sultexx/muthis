# sdk/muthis_sdk/conformance/runner.py
"""
run_conformance(plugin_dir) — the kit's one entry point.

Loads the manifest, imports the plugin, and walks the Phase-0 check ladder.
The runner never raises for a plugin defect (defects are FAIL results); it
only raises for a missing directory — a caller bug, not a plugin bug.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..manifest import ManifestError, load_manifest
from . import checks


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str  # PASS / FAIL / SKIP
    detail: str


@dataclass
class ConformanceReport:
    plugin_dir: str
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.status != "FAIL" for r in self.results)

    def add(self, name: str, status: str, detail: str) -> None:
        self.results.append(CheckResult(name=name, status=status, detail=detail))


def _ensure_importable(plugin_dir: Path) -> None:
    """Make the plugin's package importable for BOTH supported layouts:
    an in-repo package (src/muthis_plugins/<name> → src/ on sys.path) and a
    standalone community repo (<repo>/<name> → repo root on sys.path)."""
    for candidate in (plugin_dir.parent, plugin_dir.parent.parent, Path.cwd()):
        path = str(candidate.resolve())
        if path not in sys.path:
            sys.path.insert(0, path)


def run_conformance(plugin_dir: str | Path) -> ConformanceReport:
    directory = Path(plugin_dir)
    if not directory.is_dir():
        raise NotADirectoryError(f"no such plugin directory: {directory}")
    report = ConformanceReport(plugin_dir=str(directory))
    _ensure_importable(directory)

    # 1) Manifest — everything else keys off it; a bad manifest short-circuits.
    try:
        manifest = load_manifest(directory)
    except ManifestError as exc:
        report.add("manifest", "FAIL", str(exc))
        return report
    report.add("manifest", "PASS",
               f"{manifest.name} {manifest.version} (kind={manifest.kind}, "
               f"sdk {manifest.sdk})")

    # 2) Arabic description health (independent of the entry import).
    report.add("arabic-description", *checks.check_arabic_description(manifest))

    # 3) Entry class import + instantiation.
    status, detail, plugin = checks.check_entry_class(manifest)
    report.add("entry-class", status, detail)
    if plugin is None:
        return report

    # 4) Descriptors + manifest consistency + schema structure.
    status, detail, descriptors = checks.check_descriptors(plugin)
    report.add("descriptors", status, detail)
    if not descriptors:
        return report
    report.add("manifest-consistency",
               *checks.check_manifest_consistency(manifest, descriptors))
    report.add("schema-structure", *checks.check_schema_structure(descriptors))

    # 5) The fake-kernel golden run (latency measured, warn-only).
    report.add("golden-run", *asyncio.run(checks.golden_run(plugin, descriptors)))

    # 6) The permission-violation suite (LIVE since Phase 1 M1-4: starved
    #    denial + undeclared-use detection; the Phase-0 SKIP retired).
    report.add("permission-violations",
               *asyncio.run(checks.permission_checks(plugin, descriptors, manifest)))
    return report
