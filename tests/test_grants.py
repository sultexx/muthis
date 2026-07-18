# tests/test_grants.py
"""GrantsStore — consent, hash pinning, the update-diff invalidation rule,
and the budget.py file-discipline contract (atomic, never-raise, corrupt→empty)."""

from __future__ import annotations

import json

from muthis.broker.grants import GrantsStore, manifest_sha256
from muthis.broker.trust import main as trust_main
from muthis_sdk import load_manifest

MANIFEST = """
[plugin]
name    = "demo"
version = "1.0.0"
sdk     = ">=2.0.0a1,<3"
kind    = "mcp"
entry   = "demo.plugin:DemoPlugin"

[descriptions]
ar = "إضافة تجريبية لاختبار مخزن الموافقات"

[capabilities]
required = ["perceive.files.read"]
optional = ["perceive.screen"]

[tools.demo_tool]
read_only = true
"""


def _plugin_dir(tmp_path, manifest=MANIFEST):
    d = tmp_path / "demo"
    d.mkdir()
    (d / "muthis-plugin.toml").write_text(manifest, encoding="utf-8")
    return d


def test_grant_then_lookup_by_current_hash(tmp_path):
    d = _plugin_dir(tmp_path)
    store = GrantsStore(grants_file=tmp_path / "grants.json")
    assert store.grant(load_manifest(d), d)
    granted = store.granted_capabilities("demo", manifest_sha256(d))
    assert granted == frozenset({"perceive.files.read", "perceive.screen"})


def test_manifest_change_invalidates_the_grant(tmp_path):
    d = _plugin_dir(tmp_path)
    store = GrantsStore(grants_file=tmp_path / "grants.json")
    store.grant(load_manifest(d), d)
    # The update-diff rule: ANY byte change re-requires consent.
    (d / "muthis-plugin.toml").write_text(
        MANIFEST.replace('version = "1.0.0"', 'version = "1.0.1"'), encoding="utf-8")
    assert store.granted_capabilities("demo", manifest_sha256(d)) is None


def test_no_grant_and_revoke(tmp_path):
    d = _plugin_dir(tmp_path)
    store = GrantsStore(grants_file=tmp_path / "grants.json")
    assert store.granted_capabilities("demo", manifest_sha256(d)) is None
    store.grant(load_manifest(d), d)
    assert store.revoke("demo") is True
    assert store.granted_capabilities("demo", manifest_sha256(d)) is None
    assert store.revoke("demo") is False


def test_grants_survive_reload_and_corruption_degrades(tmp_path):
    d = _plugin_dir(tmp_path)
    path = tmp_path / "grants.json"
    GrantsStore(grants_file=path).grant(load_manifest(d), d)
    assert GrantsStore(grants_file=path).granted_capabilities(
        "demo", manifest_sha256(d)) is not None
    path.write_text("{corrupt", encoding="utf-8")
    assert GrantsStore(grants_file=path).granted_capabilities(
        "demo", manifest_sha256(d)) is None  # refuse politely, never crash


def test_trust_cli_grants_and_revokes(tmp_path, capsys):
    d = _plugin_dir(tmp_path)
    grants = str(tmp_path / "grants.json")
    assert trust_main([str(d), "--yes", "--grants-file", grants]) == 0
    out = capsys.readouterr().out
    assert "granted" in out and "sha256" in out
    data = json.loads((tmp_path / "grants.json").read_text(encoding="utf-8"))
    assert data["plugins"]["demo"]["capabilities"] == [
        "perceive.files.read", "perceive.screen"]
    assert trust_main(["--revoke", "demo", "--grants-file", grants]) == 0
    assert trust_main(["--revoke", "demo", "--grants-file", grants]) == 1


def test_trust_cli_rejects_invalid_manifest(tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "muthis-plugin.toml").write_text("[plugin]\nname='x'", encoding="utf-8")
    assert trust_main([str(d), "--yes", "--grants-file",
                       str(tmp_path / "g.json")]) == 1
