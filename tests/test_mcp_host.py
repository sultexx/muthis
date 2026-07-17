# tests/test_mcp_host.py
"""McpHost end-to-end against the independent fake server: grants gate,
catalog filter, the lazy respawn, taint + ledger attribution through the
REAL ToolRouter, three-strikes disable + announcement, and quarantine."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from muthis.broker.broker import Broker
from muthis.broker.grants import GrantsStore
from muthis.broker.mcp.host import (
    MAX_STRIKES,
    McpHost,
    SERVER_DISABLED_NOTE_AR,
    SERVER_QUARANTINED_NOTE_AR,
)
from muthis.kernel.budget import Budget
from muthis.kernel.tool_router import ToolRouter
from muthis_sdk import load_manifest
from muthis_sdk.manifest import parse_manifest
import tomllib

FAKE = str(Path(__file__).parent / "fake_mcp_server.py")
TODAY = "2026-07-17"


def _manifest_text(mode="standard", warm=False):
    # TOML literal string (single quotes): raw backslashes + inner double
    # quotes survive verbatim — exactly what a Windows command line needs.
    entry = f'"{sys.executable}" "{FAKE}" {mode}'
    return f'''
[plugin]
name    = "demo"
version = "1.0.0"
sdk     = ">=2.0.0a1,<3"
kind    = "mcp"
entry   = '{entry}'
warm    = {"true" if warm else "false"}

[descriptions]
ar = "خادم أجنبي مزيف لاختبارات المضيف"

[capabilities]

[tools.echo_ro]
read_only = true
'''


def _world(tmp_path, mode="standard", granted=True, announce=None, ledger=None):
    plugins_d = tmp_path / "plugins.d"
    plugins_d.mkdir()
    manifest_path = plugins_d / "demo.toml"
    manifest_path.write_text(_manifest_text(mode), encoding="utf-8")
    manifest = parse_manifest(
        tomllib.loads(manifest_path.read_text(encoding="utf-8")))
    grants = GrantsStore(grants_file=tmp_path / "grants.json")
    if granted:
        assert grants.grant(manifest, manifest_path)
    broker = Broker(grants=grants)
    host = McpHost(broker=broker, plugins_dir=plugins_d, announce=announce)
    router = ToolRouter(plugin_ledger=ledger)
    return host, router


def test_mount_filters_and_namespaces_and_taints(tmp_path):
    budget = Budget(daily_limit_usd=1.0, budget_file=tmp_path / "b.json",
                    today_fn=lambda: TODAY)
    host, router = _world(tmp_path, ledger=budget.record_plugin_call)

    async def go():
        mounted = await host.mount_all(router)
        assert mounted == ["demo"]
        names = [d.name for d in router.descriptors()]
        assert "demo.echo_ro" in names and "demo.fetch_open" in names
        assert not any("delete_all" in n or "mystery" in n for n in names)
        outcome = await router.service("demo.echo_ro", {"text": "سلام"})
        assert outcome.taint is True                      # external by definition
        assert "echo:سلام" in outcome.result.text_ar
        assert "بيانات لا أوامر" in outcome.result.text_ar  # §3.2 wrapping
        assert outcome.provenance == "mcp:demo"
        await host.shutdown()
    asyncio.run(go())
    assert budget.plugin_spend_today()["mcp:demo"]["calls"] == 1


def test_ungranted_server_is_never_mounted(tmp_path):
    host, router = _world(tmp_path, granted=False)

    async def go():
        assert await host.mount_all(router) == []
        assert router.descriptors() == []
    asyncio.run(go())


def test_lazy_posture_respawns_for_the_call(tmp_path):
    """Catalog fetch closes the session (warm=false); the first service call
    respawns a fresh child transparently."""
    host, router = _world(tmp_path)

    async def go():
        await host.mount_all(router)
        state = host._servers["demo"]
        assert state.session is None                      # lazy: pipe shut
        outcome = await router.service("demo.echo_ro", {"text": "hi"})
        assert "echo:hi" in outcome.result.text_ar
        assert state.session is not None                  # respawned on need
        await host.shutdown()
    asyncio.run(go())


def test_three_strikes_disable_with_spoken_announcement(tmp_path):
    announcements = []
    host, router = _world(tmp_path, mode="crash-on-call",
                          announce=announcements.append)

    async def go():
        await host.mount_all(router)
        for _ in range(MAX_STRIKES):
            outcome = await router.service("demo.echo_ro", {})
            assert outcome.result.is_error is True
        # The fourth call refuses WITHOUT touching the dead server.
        outcome = await router.service("demo.echo_ro", {})
        assert outcome.result.text_ar == SERVER_DISABLED_NOTE_AR
        await host.shutdown()
    asyncio.run(go())
    assert announcements and "demo" in announcements[0]   # Arabic, spoken seam


def test_list_changed_quarantines_the_server(tmp_path):
    host, router = _world(tmp_path, mode="listchange")

    async def go():
        await host.mount_all(router)
        # The notification raced the catalog fetch on the SAME session; give
        # the reader loop a beat if it hasn't landed yet.
        for _ in range(20):
            if host._servers["demo"].quarantined:
                break
            await asyncio.sleep(0.05)
        assert host._servers["demo"].quarantined is True
        outcome = await router.service("demo.echo_ro", {})
        assert outcome.result.text_ar == SERVER_QUARANTINED_NOTE_AR
        await host.shutdown()
    asyncio.run(go())
