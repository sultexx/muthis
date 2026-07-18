# tests/test_broker.py
"""Broker — the grant → gated-PluginContext door (denial is an ABSENT seam,
never a different API; kernel seams are handed through, never rebuilt)."""

from __future__ import annotations

from muthis.broker.broker import CAPABILITY_NOT_GRANTED_AR, Broker
from muthis.broker.grants import GrantsStore
from muthis_sdk import load_manifest

MANIFEST_BOTH = """
[plugin]
name    = "demo"
version = "1.0.0"
sdk     = ">=2.0.0a1,<3"
kind    = "mcp"
entry   = "demo.plugin:DemoPlugin"

[descriptions]
ar = "إضافة تجريبية للوسيط"

[capabilities]
required = ["perceive.files.read", "perceive.screen"]

[tools.demo_tool]
read_only = true
"""


def _world(tmp_path, manifest_text=MANIFEST_BOTH, granted=True):
    d = tmp_path / "demo"
    d.mkdir()
    (d / "muthis-plugin.toml").write_text(manifest_text, encoding="utf-8")
    manifest = load_manifest(d)
    grants = GrantsStore(grants_file=tmp_path / "grants.json")
    if granted:
        grants.grant(manifest, d)

    async def read_seam(args):
        return "من النواة"

    async def capture_seam():
        return b"\x89PNG"

    broker = Broker(grants=grants, read_file=read_seam, capture=capture_seam)
    return broker, manifest, d


def test_granted_capabilities_ride_the_context(tmp_path):
    broker, manifest, d = _world(tmp_path)
    ctx = broker.context_for(manifest, d)
    assert ctx.files is not None and ctx.screen is not None


def test_ungranted_plugin_gets_a_bare_context(tmp_path):
    broker, manifest, d = _world(tmp_path, granted=False)
    ctx = broker.context_for(manifest, d)
    assert ctx.files is None and ctx.screen is None


def test_partial_grant_gates_per_capability(tmp_path):
    manifest_files_only = MANIFEST_BOTH.replace(
        'required = ["perceive.files.read", "perceive.screen"]',
        'required = ["perceive.files.read"]')
    broker, manifest, d = _world(tmp_path, manifest_text=manifest_files_only)
    ctx = broker.context_for(manifest, d)
    assert ctx.files is not None and ctx.screen is None


def test_manifest_drift_after_grant_denies_everything(tmp_path):
    broker, manifest, d = _world(tmp_path)
    (d / "muthis-plugin.toml").write_text(
        MANIFEST_BOTH + "\n# drifted\n", encoding="utf-8")
    ctx = broker.context_for(manifest, d)
    assert ctx.files is None and ctx.screen is None


def test_granted_but_unwired_seam_stays_absent(tmp_path):
    broker, manifest, d = _world(tmp_path)
    bare = Broker(grants=broker._grants, read_file=None, capture=None)
    ctx = bare.context_for(manifest, d)
    assert ctx.files is None and ctx.screen is None


def test_refusal_note_is_arabic():
    assert "غير ممنوحة" in CAPABILITY_NOT_GRANTED_AR
