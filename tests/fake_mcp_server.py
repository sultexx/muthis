# tests/fake_mcp_server.py
"""
A deliberately INDEPENDENT MCP stdio server for the client/host tests —
plain sync stdio, NO muthis_sdk import: if our hand-rolled client talks to
this hand-rolled server, the protocol slice is cross-validated against a
second implementation, not against itself.

Modes (argv[1], default "standard"):
  standard      full catalog (read-only / destructive / unhinted / open-world)
  badversion    initialize answers an unknown protocolVersion
  crash-on-call handshake + tools/list fine; any tools/call exits(1)
  hang          tools/call sleeps far past the client timeout
  listchange    emits notifications/tools/list_changed right after startup
NOT a pytest module (no test_ prefix); spawned via sys.executable.
"""

import json
import sys
import time

MODE = sys.argv[1] if len(sys.argv) > 1 else "standard"

TOOLS = [
    {"name": "echo_ro", "description": "Echo text back (read-only).",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
     "annotations": {"readOnlyHint": True}},
    {"name": "fetch_open", "description": "Read-only but open-world.",
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": {"readOnlyHint": True, "openWorldHint": True}},
    {"name": "big_ro", "description": "Huge read-only payload.",
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": {"readOnlyHint": True}},
    {"name": "img_ro", "description": "Image + text payload.",
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": {"readOnlyHint": True}},
    {"name": "delete_all", "description": "Destructive tool.",
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": {"destructiveHint": True}},
    {"name": "mystery", "description": "No annotations at all.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def text_result(text):
    return {"content": [{"type": "text", "text": text}]}


def handle_call(params):
    name = params.get("name", "")
    args = params.get("arguments") or {}
    if MODE == "crash-on-call":
        sys.exit(1)
    if MODE == "hang":
        time.sleep(60)
    if name == "echo_ro":
        return text_result(f"echo:{args.get('text', '')}")
    if name == "fetch_open":
        return text_result("open world data")
    if name == "big_ro":
        return text_result("X" * 20_000)
    if name == "img_ro":
        return {"content": [
            {"type": "image", "data": "aGk=", "mimeType": "image/png"},
            {"type": "text", "text": "caption text"},
        ]}
    return text_result(f"unknown tool {name}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method = msg.get("method")
        msg_id = msg.get("id")
        if method == "initialize":
            version = ("9999-01-01" if MODE == "badversion"
                       else msg["params"].get("protocolVersion", "2025-06-18"))
            send({"jsonrpc": "2.0", "id": msg_id, "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "fake-foreign-server", "version": "1.0"},
            }})
        elif method == "notifications/initialized":
            if MODE == "listchange":
                send({"jsonrpc": "2.0",
                      "method": "notifications/tools/list_changed"})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            send({"jsonrpc": "2.0", "id": msg_id,
                  "result": handle_call(msg.get("params") or {})})
        elif msg_id is not None:
            send({"jsonrpc": "2.0", "id": msg_id,
                  "error": {"code": -32601, "message": f"no method {method}"}})


if __name__ == "__main__":
    main()
