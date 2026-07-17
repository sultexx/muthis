# src/muthis/broker/__init__.py
"""
The Capability Broker (V2 Phase 1, roadmap §3.3) — the golden rule as
inspectable structure.

External plugin code never holds an OS handle: it receives a PluginContext
carrying ONLY the capability seams its GRANT covers, each seam backed by the
kernel's own gated implementation (FileReader with its secret/binary/size
refusals; the hide→settle→capture line). Grants are consented once per
manifest HASH (`python -m muthis.broker.trust <plugin-dir>`) and die the
moment the manifest changes — the privilege-diff rule.

Deliberately import-free __init__ (the kernel/ pattern): modules are
imported by full path, so package init can never cycle.
"""
