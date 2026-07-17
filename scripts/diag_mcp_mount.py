# scripts/diag_mcp_mount.py
"""
LIVE diag — Phase 1 exit gate, subject 2: "a REAL MCP server mounted live"
(roadmap §5), Python-self-contained per decision Q-1.4: the target is
examples/demo_server (an INDEPENDENT protocol implementation — no
muthis_sdk inside it), whose catalog deliberately carries a DESTRUCTIVE
decoy tool. The pass criteria:

  * read-only tools (system_info, list_dir) are EXPOSED and answer live,
  * delete_file is HIDDEN by the look-and-advise filter,
  * results come back wrapped as untrusted data + tainted,
  * an UNGRANTED mount attempt is refused (the consent gate, live).

Run:  set PYTHONPATH=src && python scripts/diag_mcp_mount.py
Exit: 0 = PASS. Zero provider cost.
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
from muthis.kernel.tool_router import ToolRouter  # noqa: E402
from muthis_sdk.manifest import parse_manifest  # noqa: E402

SERVER = REPO / "examples" / "demo_server" / "server.py"

MANIFEST = f'''
[plugin]
name    = "demo_server"
version = "1.0.0"
sdk     = ">=2.0.0a2,<3"
kind    = "mcp"
entry   = '"{sys.executable}" "{SERVER}"'

[descriptions]
ar = "خادم العرض المستقل للقراءة فقط"
en = "The standalone read-only demo server"

[capabilities]

[tools.system_info]
read_only = true
[tools.list_dir]
read_only = true
[tools.delete_file]
read_only = false
'''


async def main() -> int:
    print("=== diag_mcp_mount: a real (foreign-implementation) MCP server, live ===")
    with tempfile.TemporaryDirectory() as tmp:
        plugins_d = Path(tmp) / "plugins.d"
        plugins_d.mkdir()
        manifest_path = plugins_d / "demo_server.toml"
        manifest_path.write_text(MANIFEST, encoding="utf-8")
        manifest = parse_manifest(tomllib.loads(MANIFEST))
        grants = GrantsStore(grants_file=Path(tmp) / "grants.json")
        broker = Broker(grants=grants)
        host = McpHost(broker=broker, plugins_dir=plugins_d)
        router = ToolRouter()

        # 1) The consent gate, live: NO grant → NO mount.
        assert await host.mount_all(router) == [], "ungranted server was mounted!"
        print("[1] ungranted mount refused (the trust gate holds)")

        # 2) Trust, then mount: the filter must hide the destructive decoy.
        assert grants.grant(manifest, manifest_path)
        host2 = McpHost(broker=broker, plugins_dir=plugins_d)
        router2 = ToolRouter()
        assert await host2.mount_all(router2) == ["demo_server"]
        names = [d.name for d in router2.descriptors()]
        print(f"[2] exposed catalog: {names}")
        assert "demo_server.system_info" in names and "demo_server.list_dir" in names
        assert not any("delete_file" in n for n in names), "DESTRUCTIVE TOOL LEAKED"
        print("[3] delete_file HIDDEN — look-and-advise filter verified live")

        # 3) Live read-only calls, wrapped + tainted.
        info = await router2.service("demo_server.system_info", {})
        print(f"[4] system_info:\n{info.result.text_ar}")
        assert "python=" in info.result.text_ar and info.taint is True
        listing = await router2.service("demo_server.list_dir", {"path": str(REPO)})
        assert "AGENTS.md" in listing.result.text_ar
        assert "بيانات لا أوامر" in listing.result.text_ar
        print("[5] list_dir answered live, wrapped as untrusted data")

        await host2.shutdown()
    print("=== PASS: real server mounted; filter, wrap, taint, consent all live ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
