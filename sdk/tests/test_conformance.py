# sdk/tests/test_conformance.py
"""The conformance kit's own tests: a healthy fixture plugin must be
ADMISSIBLE, deliberately broken ones must be REJECTED, and the honesty
markers (Phase-1 SKIP) must always show."""

from __future__ import annotations

import sys
import textwrap

from muthis_sdk.cli import main as cli_main
from muthis_sdk.conformance import run_conformance

_GOOD_MANIFEST = """
[plugin]
name    = "{name}"
version = "1.0.0"
sdk     = ">=2.0.0a1,<3"
kind    = "native"
entry   = "{name}.plugin:FixturePlugin"

[descriptions]
ar = "إضافة تجريبية تفحصها عدّة المطابقة فحصًا كاملًا"
en = "A fixture plugin exercised by the conformance kit"

[capabilities]
required = ["perceive.files.read"]

[tools.echo_tool]
read_only = true
"""

_GOOD_PLUGIN = """
from muthis_sdk import ToolDescriptor, ToolPlugin, ToolResult

class FixturePlugin(ToolPlugin):
    def descriptors(self):
        return [ToolDescriptor(
            name="echo_tool",
            schema={
                "name": "echo_tool",
                "description": "Echoes for the kit.",
                "input_schema": {"type": "object", "properties": {}},
            },
        )]

    async def execute(self, tool, args, ctx):
        return ToolResult(text_ar="صدى العدّة")
"""


def _write_fixture(tmp_path, name, manifest=None, plugin_body=None):
    package = tmp_path / name
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "muthis-plugin.toml").write_text(
        (manifest or _GOOD_MANIFEST).format(name=name), encoding="utf-8")
    (package / "plugin.py").write_text(
        textwrap.dedent(plugin_body or _GOOD_PLUGIN), encoding="utf-8")
    return package


def test_healthy_fixture_is_admissible(tmp_path):
    package = _write_fixture(tmp_path, "kitfix_good")
    report = run_conformance(package)
    assert report.passed, [r for r in report.results if r.status == "FAIL"]
    statuses = {r.name: r.status for r in report.results}
    assert statuses["golden-run"] == "PASS"
    assert statuses["permission-violations"] == "PASS"  # LIVE since M1-4


def test_starved_context_crash_is_a_permission_violation(tmp_path):
    body = _GOOD_PLUGIN.replace(
        "    async def execute(self, tool, args, ctx):\n"
        '        return ToolResult(text_ar="صدى العدّة")',
        "    async def execute(self, tool, args, ctx):\n"
        "        return ToolResult(text_ar=await ctx.files.read(args))",
    )
    package = _write_fixture(tmp_path, "kitfix_starved_crash", plugin_body=body)
    report = run_conformance(package)   # ctx.files is None on the starved run
    assert not report.passed
    violation = next(r for r in report.results if r.name == "permission-violations")
    assert violation.status == "FAIL" and "starved" in violation.detail


def test_undeclared_capability_use_is_a_permission_violation(tmp_path):
    body = _GOOD_PLUGIN.replace(
        "    async def execute(self, tool, args, ctx):\n"
        '        return ToolResult(text_ar="صدى العدّة")',
        "    async def execute(self, tool, args, ctx):\n"
        "        if ctx.screen is not None:\n"
        "            await ctx.screen.capture()   # perceive.screen NOT in the manifest\n"
        '        return ToolResult(text_ar="صدى العدّة")',
    )
    package = _write_fixture(tmp_path, "kitfix_undeclared", plugin_body=body)
    report = run_conformance(package)
    assert not report.passed
    violation = next(r for r in report.results if r.name == "permission-violations")
    assert violation.status == "FAIL" and "not declared" in violation.detail


def test_broken_manifest_is_rejected(tmp_path):
    package = _write_fixture(
        tmp_path, "kitfix_noar",
        manifest=_GOOD_MANIFEST.replace(
            'ar = "إضافة تجريبية تفحصها عدّة المطابقة فحصًا كاملًا"', 'ar = ""'))
    report = run_conformance(package)
    assert not report.passed
    assert report.results[0].name == "manifest"
    assert report.results[0].status == "FAIL"


def test_raising_plugin_fails_the_golden_run(tmp_path):
    body = _GOOD_PLUGIN.replace(
        'return ToolResult(text_ar="صدى العدّة")', 'raise RuntimeError("boom")')
    package = _write_fixture(tmp_path, "kitfix_raiser", plugin_body=body)
    report = run_conformance(package)
    assert not report.passed
    golden = next(r for r in report.results if r.name == "golden-run")
    assert golden.status == "FAIL" and "never raise" in golden.detail


def test_schema_shape_defect_is_rejected(tmp_path):
    body = _GOOD_PLUGIN.replace(
        '"input_schema": {"type": "object", "properties": {}},', '')
    package = _write_fixture(tmp_path, "kitfix_badschema", plugin_body=body)
    report = run_conformance(package)
    assert not report.passed
    schema = next(r for r in report.results if r.name == "schema-structure")
    assert schema.status == "FAIL"


def test_manifest_descriptor_mismatch_is_rejected(tmp_path):
    body = _GOOD_PLUGIN.replace('"echo_tool"', '"other_tool"').replace(
        'name="echo_tool"', 'name="other_tool"')
    package = _write_fixture(tmp_path, "kitfix_mismatch", plugin_body=body)
    report = run_conformance(package)
    assert not report.passed
    consistency = next(r for r in report.results if r.name == "manifest-consistency")
    assert consistency.status == "FAIL"


def test_cli_exit_codes(tmp_path, capsys):
    good = _write_fixture(tmp_path, "kitfix_cli_good")
    assert cli_main(["plugin", "test", str(good)]) == 0
    assert "ADMISSIBLE" in capsys.readouterr().out

    bad = _write_fixture(
        tmp_path, "kitfix_cli_bad",
        manifest=_GOOD_MANIFEST.replace('required = ["perceive.files.read"]',
                                        'required = ["input.mouse"]'))
    assert cli_main(["plugin", "test", str(bad)]) == 1
    assert "REJECTED" in capsys.readouterr().out

    assert cli_main(["plugin", "test", str(tmp_path / "missing")]) == 2
