# tests/test_sandbox_exec.py
"""T1 of Phase-2 Milestone 1 — the sandbox_exec `run_code` contract + skeleton.

The engine (Docker) is T2; here we prove the CONTRACT: the manifest loads with
the execution capability, the descriptor/schema are consistent, the plugin is
stateless and never raises (returns an Arabic note until the runner lands), and
the whole package is registry-ADMISSIBLE via the conformance kit."""

from __future__ import annotations

import asyncio
from pathlib import Path

import muthis_plugins
from muthis_plugins.common import KERNEL_SERVICED_AR
from muthis_plugins.sandbox_exec import SandboxExecPlugin
from muthis_plugins.sandbox_exec.schema import (
    DEFAULT_TIMEOUT_S,
    LANGUAGES,
    MAX_TIMEOUT_S,
    RUN_CODE_SCHEMA,
)
from muthis_sdk import FilesCapability, PluginContext, load_manifest
from muthis_sdk.conformance import run_conformance

PACKAGE_DIR = Path(muthis_plugins.__file__).parent / "sandbox_exec"


def test_manifest_declares_the_execution_capability():
    manifest = load_manifest(PACKAGE_DIR)
    assert manifest.name == "sandbox_exec" and manifest.kind == "native"
    assert manifest.capabilities_required == ("sandbox.execute",)
    assert manifest.capabilities_optional == ("net.fetch",)
    assert [t.name for t in manifest.tools] == ["run_code"]
    assert manifest.tools[0].read_only is True
    assert manifest.entry.endswith("SandboxExecPlugin")


def test_descriptor_and_schema_are_consistent():
    (descriptor,) = SandboxExecPlugin().descriptors()
    assert descriptor.name == "run_code"
    assert descriptor.read_only is True and descriptor.kernel_serviced is True
    # the descriptor exposes the exact schema object (one source of truth)
    assert descriptor.schema is RUN_CODE_SCHEMA
    assert RUN_CODE_SCHEMA["name"] == "run_code"
    input_schema = RUN_CODE_SCHEMA["input_schema"]
    assert input_schema["required"] == ["language", "code"]
    assert input_schema["properties"]["language"]["enum"] == list(LANGUAGES)
    # the data-model bounds are the single source T2 will enforce
    assert (DEFAULT_TIMEOUT_S, MAX_TIMEOUT_S) == (20, 60)
    assert str(DEFAULT_TIMEOUT_S) in input_schema["properties"]["timeout_s"]["description"]


def test_execute_returns_a_note_and_never_raises():
    async def _fake_read(args):
        return "غير مستخدَم"

    plugin = SandboxExecPlugin()
    args = {"language": "python", "code": "print(1)"}
    # Starved context (the broker's denial posture) and a capability-equipped
    # context both degrade to the same note — T1 touches no seam; the engine is T2.
    for ctx in (PluginContext(), PluginContext(files=FilesCapability(read=_fake_read))):
        result = asyncio.run(plugin.execute("run_code", args, ctx))
        assert result.text_ar == KERNEL_SERVICED_AR and result.is_error is True


def test_conformance_kit_reports_admissible():
    report = run_conformance(str(PACKAGE_DIR))
    failed = [f"{r.name}: {r.detail}" for r in report.results if r.status == "FAIL"]
    assert report.passed, f"sandbox_exec must be ADMISSIBLE; failures: {failed}"
