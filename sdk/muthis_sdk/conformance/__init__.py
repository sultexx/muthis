# sdk/muthis_sdk/conformance/__init__.py
"""
The conformance kit (born in V2 Phase 0) — `muthis plugin test <dir>`.

Roadmap §3.6: a fake kernel + golden runs checking schema validity,
permission-violation refusal, the latency budget, and Arabic-description
health. Passing is the registry admission bar. Phase 0 ships the manifest/
schema/Arabic/golden-run checks; the permission-violation suite is reported
honestly as SKIPPED until the Phase-1 broker exists to violate.
"""

from .runner import CheckResult, ConformanceReport, run_conformance

__all__ = ["CheckResult", "ConformanceReport", "run_conformance"]
