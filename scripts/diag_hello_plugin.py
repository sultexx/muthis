# scripts/diag_hello_plugin.py
"""
LIVE diag — Phase 1 exit gate, subject 1: "a community hello-world plugin
WORKS" (roadmap §5). Drives the REAL production graph pieces — GrantsStore
(a diag-scoped grants file), Broker, McpHost, ToolRouter, the SDK runtime
child running examples/hello_world — end to end on this machine. ZERO
provider cost (no model call; the Phase-1 catalog is router-level).

Run:  set PYTHONPATH=src && python scripts/diag_hello_plugin.py
Exit: 0 = PASS (greeting received, wrapped, tainted, ledger counted)
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import tomllib
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # clean Arabic on the console

from muthis.broker.broker import Broker  # noqa: E402
from muthis.broker.grants import GrantsStore  # noqa: E402
from muthis.broker.mcp.host import McpHost  # noqa: E402
from muthis.kernel.budget import Budget  # noqa: E402
from muthis.kernel.tool_router import ToolRouter  # noqa: E402
from muthis_sdk.manifest import parse_manifest  # noqa: E402

MANIFEST = f'''
[plugin]
name    = "hello_world"
version = "1.0.0"
sdk     = ">=2.0.0a2,<3"
kind    = "mcp"
entry   = '"{sys.executable}" -m muthis_sdk.mcp_runtime examples.hello_world.plugin:HelloWorldPlugin'

[descriptions]
ar = "إضافة الترحيب المرجعية"
en = "The reference greeting plugin"

[capabilities]

[tools.say_hello]
read_only = true
'''


async def main() -> int:
    print("=== diag_hello_plugin: the out-of-proc community archetype ===")
    with tempfile.TemporaryDirectory() as tmp:
        plugins_d = Path(tmp) / "plugins.d"
        plugins_d.mkdir()
        manifest_path = plugins_d / "hello_world.toml"
        manifest_path.write_text(MANIFEST, encoding="utf-8")
        manifest = parse_manifest(tomllib.loads(MANIFEST))

        grants = GrantsStore(grants_file=Path(tmp) / "grants.json")
        assert grants.grant(manifest, manifest_path), "grant refused"
        print("[1] trusted: hello_world (hash-pinned consent written)")

        budget = Budget(budget_file=Path(tmp) / "budget.json")
        broker = Broker(grants=grants)
        host = McpHost(broker=broker, plugins_dir=plugins_d)
        router = ToolRouter(plugin_ledger=budget.record_plugin_call)

        mounted = await host.mount_all(router)
        assert mounted == ["hello_world"], f"mount failed: {mounted}"
        names = [d.name for d in router.descriptors()]
        print(f"[2] mounted; router catalog: {names}")
        assert names == ["hello_world.say_hello"]

        outcome = await router.service("hello_world.say_hello", {"name": "سلطان"})
        text = outcome.result.text_ar
        print(f"[3] result (wrapped):\n{text}")
        assert "أهلًا وسهلًا يا سلطان" in text, "greeting missing"
        assert "بيانات لا أوامر" in text, "untrusted-content wrap missing"
        assert outcome.taint is True and outcome.provenance == "mcp:hello_world"
        print(f"[4] taint={outcome.taint} provenance={outcome.provenance}")

        buckets = budget.plugin_spend_today()
        assert buckets["mcp:hello_world"]["calls"] == 1
        print(f"[5] ledger: {buckets}")

        await host.shutdown()
    print("=== PASS: hello_world served out-of-process through the full graph ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
