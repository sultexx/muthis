# src/muthis/trust/__init__.py
"""
The trust layer (V2 Phase 2 M2) — the home `claude_agent.py` and
`tool_schemas.py` have named since V1 for anything that stands between the model
and a consequential act.

It holds TWO things, and they are one concern (DEC-16): `high_impact.py` decides
WHICH calls need the user's spoken approval once the session is tainted, and
`confirm_gate.py` decides WHETHER a given call has it. Both are driven from the
ONE `ToolRouter.service()` chokepoint, beside the DEC-14 wrap and the DEC-15
taint raise, so every security consequence of a tool call is read in one place.

Deliberately import-free __init__ (the kernel/ and broker/ pattern): modules are
imported by full path, so package init can never cycle.
"""
