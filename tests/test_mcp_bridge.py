# tests/test_mcp_bridge.py
"""THE full circle of Phase 1 (M1-6): router → host → out-of-proc child
(the SDK runtime running tests/fixture_bridge_plugin) → muthis/read_file
bridge → broker's gated context → the kernel seam — and back, wrapped and
tainted. Plus the denial circle: no grant on the capability → the broker's
Arabic refusal rides the SAME path as ordinary text."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from muthis.broker.broker import CAPABILITY_NOT_GRANTED_AR, Broker
from muthis.broker.grants import GrantsStore
from muthis.broker.mcp.host import McpHost
from muthis.kernel.tool_router import ToolRouter, namespaced_name
from muthis_sdk.manifest import parse_manifest
import tomllib

REPO_ROOT = Path(__file__).parent.parent


def _manifest_text(capabilities: str) -> str:
    entry = (f'"{sys.executable}" -m muthis_sdk.mcp_runtime '
             f"tests.fixture_bridge_plugin:BridgePlugin")
    return f'''
[plugin]
name    = "bridge_demo"
version = "1.0.0"
sdk     = ">=2.0.0a2,<3"
kind    = "mcp"
entry   = '{entry}'

[descriptions]
ar = "إضافة تجريبية تقرأ عبر جسر النواة"

[capabilities]
{capabilities}

[tools.read_via_kernel]
read_only = true
'''


def _world(tmp_path, capabilities='required = ["perceive.files.read"]'):
    plugins_d = tmp_path / "plugins.d"
    plugins_d.mkdir()
    manifest_path = plugins_d / "bridge_demo.toml"
    manifest_path.write_text(_manifest_text(capabilities), encoding="utf-8")
    manifest = parse_manifest(
        tomllib.loads(manifest_path.read_text(encoding="utf-8")))
    grants = GrantsStore(grants_file=tmp_path / "grants.json")
    assert grants.grant(manifest, manifest_path)

    async def kernel_read(args):
        return f"١: محتوى النواة لملف {args.get('path', '؟')}"

    broker = Broker(grants=grants, read_file=kernel_read)
    host = McpHost(broker=broker, plugins_dir=plugins_d)
    router = ToolRouter()
    return host, router


def test_full_circle_read_through_the_kernel(tmp_path):
    host, router = _world(tmp_path)

    async def go():
        assert await host.mount_all(router) == ["bridge_demo"]
        outcome = await router.service(
            namespaced_name("bridge_demo", "read_via_kernel"), {"path": "code.py"})
        text = outcome.result.text_ar
        assert "محتوى النواة لملف code.py" in text     # the seam's own words
        assert "بيانات لا أوامر" in text               # still §3.2-wrapped
        assert outcome.taint is True                   # still external
        await host.shutdown()
    asyncio.run(go())


def test_denied_capability_returns_the_broker_refusal(tmp_path):
    # The manifest requests NOTHING → the grant covers nothing → the bridge
    # answers with the broker's Arabic refusal as ordinary text.
    host, router = _world(tmp_path, capabilities="")

    async def go():
        assert await host.mount_all(router) == ["bridge_demo"]
        outcome = await router.service(
            namespaced_name("bridge_demo", "read_via_kernel"), {"path": "code.py"})
        assert CAPABILITY_NOT_GRANTED_AR in outcome.result.text_ar
        await host.shutdown()
    asyncio.run(go())
