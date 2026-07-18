# src/muthis/broker/mcp/__init__.py
"""
The MCP host layer (V2 Phase 1, roadmap §8) — ALL MCP knowledge lives under
this package; the kernel stays blind to it (§8.1: server tools reach the
kernel as ordinary ToolRouter descriptors, nothing more).

Module split (the ≤300 law, designed up front):
  client.py       — one stdio session: spawn, handshake, request/notify,
                    server→client bridge seam, teardown
  policy.py       — the look-and-advise exposure filter + result hygiene
                    (text-only, size caps, source wrapping, ALWAYS taint)
  proxy_plugin.py — the ToolPlugin adapter the router mounts (namespaced)
  host.py         — plugins.d loading, grants gate, lazy spawn, three
                    strikes, list_changed quarantine, shutdown

Import-free __init__ (the kernel/ pattern)."""
