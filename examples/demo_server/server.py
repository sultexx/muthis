# examples/demo_server/server.py
"""
The self-contained "real foreign server" for the Phase-1 live gate
(decision Q-1.4: pure Python, no node/npx). A genuinely useful read-only
MCP stdio server implemented INDEPENDENTLY of muthis_sdk — in protocol
terms it is a foreign implementation, which is exactly what the mount
diag must prove against.

Tools:
  system_info  (readOnlyHint)   OS / Python / machine facts
  list_dir     (readOnlyHint)   names + sizes of one directory level
  delete_file  (destructiveHint) — EXISTS ON PURPOSE and does nothing but
        prove the look-and-advise filter live: Mut'his must HIDE it.

Run: python examples/demo_server/server.py   (spawned by the host)
"""

import json
import os
import platform
import sys
from pathlib import Path

for _stream in (sys.stdin, sys.stdout):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

TOOLS = [
    {"name": "system_info",
     "description": "Report OS, Python and machine facts (read-only).",
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": {"readOnlyHint": True}},
    {"name": "list_dir",
     "description": "List one directory level: names and sizes (read-only).",
     "inputSchema": {"type": "object",
                     "properties": {"path": {"type": "string"}},
                     "required": ["path"]},
     "annotations": {"readOnlyHint": True}},
    {"name": "delete_file",
     "description": "Delete a file (DESTRUCTIVE — Mut'his must never see this).",
     "inputSchema": {"type": "object",
                     "properties": {"path": {"type": "string"}},
                     "required": ["path"]},
     "annotations": {"destructiveHint": True}},
]


def send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def text(result_text):
    return {"content": [{"type": "text", "text": result_text}]}


def call(name, args):
    if name == "system_info":
        return text(
            f"os={platform.system()} {platform.release()} | "
            f"python={platform.python_version()} | machine={platform.machine()} | "
            f"cpu_count={os.cpu_count()}")
    if name == "list_dir":
        target = Path(str(args.get("path", ".")))
        if not target.is_dir():
            return text(f"not a directory: {target}")
        lines = []
        for entry in sorted(target.iterdir())[:50]:
            size = entry.stat().st_size if entry.is_file() else "<dir>"
            lines.append(f"{entry.name}  {size}")
        return text("\n".join(lines) or "(empty)")
    if name == "delete_file":
        # Never reachable through Mut'his (the filter hides it); even called
        # directly this demo deletes nothing — it only proves the boundary.
        return text("refused: demo server never deletes anything")
    return text(f"unknown tool {name}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method, msg_id = msg.get("method"), msg.get("id")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": msg_id, "result": {
                "protocolVersion": msg["params"].get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "muthis-demo-server", "version": "1.0"}}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            params = msg.get("params") or {}
            send({"jsonrpc": "2.0", "id": msg_id,
                  "result": call(params.get("name"), params.get("arguments") or {})})
        elif msg_id is not None:
            send({"jsonrpc": "2.0", "id": msg_id,
                  "error": {"code": -32601, "message": f"no method {method}"}})


if __name__ == "__main__":
    main()
