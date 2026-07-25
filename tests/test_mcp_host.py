# tests/test_mcp_host.py
"""McpHost end-to-end against the independent fake server: grants gate,
catalog filter, the lazy respawn, taint + ledger attribution through the
REAL ToolRouter, three-strikes disable + announcement, and quarantine."""

from __future__ import annotations

import asyncio
import re
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
from muthis.kernel.tool_router import ToolRouter, namespaced_name
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
        echo, fetch = namespaced_name("demo", "echo_ro"), namespaced_name("demo", "fetch_open")
        assert echo in names and fetch in names
        assert not any("delete_all" in n or "mystery" in n for n in names)
        outcome = await router.service(echo, {"text": "سلام"})
        assert outcome.taint is True                      # external by definition
        assert "echo:سلام" in outcome.result.text_ar
        # §3.2 wrapping, applied at the ROUTER since T4 (DEC-14) — the real
        # child's result comes back framed ONCE, with a nonce in both ends so
        # the server cannot forge the close. Phase 1 wrapped in policy.py; that
        # copy is gone, and `count == 1` is what keeps it gone on this path.
        text = outcome.result.text_ar
        assert "بيانات لا أوامر" in text
        assert text.count("محتوى خارجي غير موثوق") == 1
        assert text.count("نهاية المحتوى الخارجي") == 1
        nonces = re.findall(r"الرقم: ([0-9a-f]+)\]", text)
        assert len(nonces) == 2 and nonces[0] == nonces[1]
        assert outcome.provenance == "mcp:demo"
        # DEC-15 on the REAL path: an MCP result raises the session-sticky taint
        # in the SAME router branch that framed it — a real live consumer of the
        # taint=True mount above, not a synthetic route.
        assert router.session_taint.tainted is True
        await host.shutdown()
    asyncio.run(go())
    assert budget.plugin_spend_today()["mcp:demo"]["calls"] == 1


def test_the_session_starts_clean_before_any_mcp_call(tmp_path):
    """The other side of the same fact: mounting an external server does NOT
    taint the session — INGESTING its content does. Without this, the raise
    test above would pass on a router that was born tainted."""
    host, router = _world(tmp_path)

    async def go():
        await host.mount_all(router)
        assert router.session_taint.tainted is False   # mounted, not yet used
        await router.service(namespaced_name("demo", "echo_ro"), {"text": "hi"})
        assert router.session_taint.tainted is True
        await host.shutdown()
    asyncio.run(go())


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
        outcome = await router.service(namespaced_name("demo", "echo_ro"), {"text": "hi"})
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
            outcome = await router.service(namespaced_name("demo", "echo_ro"), {})
            assert outcome.result.is_error is True
        # The fourth call refuses WITHOUT touching the dead server. The note is
        # CONTAINED rather than equal because a tainted route's every result is
        # framed since T4 (DEC-14) — `is_error` is plugin-set, so letting it
        # skip the frame would hand a plugin a switch that smuggles external
        # text in unwrapped. Uniform framing is the safe direction.
        outcome = await router.service(namespaced_name("demo", "echo_ro"), {})
        assert SERVER_DISABLED_NOTE_AR in outcome.result.text_ar
        assert "محتوى خارجي غير موثوق" in outcome.result.text_ar
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
        outcome = await router.service(namespaced_name("demo", "echo_ro"), {})
        assert SERVER_QUARANTINED_NOTE_AR in outcome.result.text_ar  # framed (DEC-14)
        await host.shutdown()
    asyncio.run(go())
