# src/muthis/trust/high_impact.py
"""
High-impact classification — WHICH calls need the user's spoken approval once
the session is tainted (DEC-15, refining DEC-3-A).

THE PRINCIPLE, in one sentence: **the effect ESCAPES the isolation.** A call is
high-impact when its effect leaves the machine — or leaves a container we
control — and can therefore be turned against the user by content that is
already sitting in the model's context. A call whose effect is CONTAINED is not
high-impact no matter how tainted the session is: confirmation friction there
buys nothing and would put a permission prompt in front of the flagship
"proof of run" flow that DEC-3-A exists to protect.

  HIGH-IMPACT  `web.search` / `web.fetch` (the T6 mounts), a network-ENABLED
               sandbox run, and MCP tools LACKING `readOnlyHint`.
  NOT          a network-LESS sandbox run — the isolation IS the containment
               (`--network none`, `nobody`, `--cap-drop ALL`, `--read-only`,
               ephemeral; a PRIMARY tested guarantee, proven live in M1, which
               is what distinguishes it from the DEC-13 case where the
               protection was incidental to another layer) — and the V1 four:
               pointing, drawing, a screen refresh and a local read send
               nothing anywhere.

WHERE THE FACTS COME FROM — the load-bearing part. Classification is
KERNEL-SIDE, derived from the GRANTED CAPABILITY or the MCP hint (DEC-15), and
NEVER from a plugin's self-declaration. `ToolDescriptor.read_only` is set by the
PLUGIN, so reading it here would let a plugin declare itself low-impact and
nullify the gate outright — the same reason `is_error` deliberately does not
gate the DEC-14 wrap (DEC-29): a security decision a plugin author can flip is
not a security decision. The two facts below are supplied by whoever MOUNTS the
route — the composition root, the MCP host — which is kernel code, and they are
the ONLY inputs this module has.

`net.fetch` IS the network question. The roadmap pins `--network none` as a
permanent default and makes opening the network a SEPARATE privilege; the
sandbox's `run_code` schema has no network parameter at all today, so there is
no argument to inspect and inventing one would be a guess. The capability grant
is the kernel-side fact DEC-15 names: a route granted `net.fetch` CAN reach the
network, a route without it CANNOT. HONEST LIMIT, recorded rather than hidden:
this is ROUTE-level, so the day the per-run network privilege lands, a sandbox
route holding `net.fetch` classifies EVERY run high-impact under taint —
including network-less ones. That is friction in the SAFE direction, and
refining it to per-run belongs with the privilege that introduces the parameter
(building it now would be a stub against a schema that does not exist).

THE DEFAULT IS FAIL-CLOSED, and that is how "MCP tools lacking readOnlyHint" is
expressed: an external route mounted WITHOUT the kernel stating the hint is
high-impact. Phase 1's exposure filter happens to hide unhinted tools today
(`broker/mcp/policy.py`), but resting the classification on that would be
CIRCUMSTANTIAL protection — "it is safe for another reason" is precisely the
reasoning DEC-13 rejects — and that filter is documented to relax when manual
enablement arrives.

Pure stdlib, importable in isolation, no state. It contains no Arabic: like
`session_taint.py` it addresses neither the model nor the user, and under the
language-separation law that absence is what makes the claim structural.
"""

from __future__ import annotations

import dataclasses

# The capability that means "this route can reach the network". Spelled once
# here so it cannot drift from the closed SDK enum (`muthis_sdk.CAPABILITIES`),
# which a test pins — asserted rather than imported, so this module stays
# stdlib-only and importable in isolation.
NETWORK_CAPABILITY = "net.fetch"


@dataclasses.dataclass(frozen=True)
class RouteImpact:
    """The kernel's OWN facts about one mounted route.

    `capabilities` — what the kernel GRANTED this route, never what the plugin
    asked for. `read_only_hint` — True only when the kernel itself read a
    `readOnlyHint` annotation off the server's catalog; the default False is the
    fail-closed case documented above.

    `external` is deliberately NOT a field. The router already carries that fact
    as the mount's `taint` flag (external = untrusted by definition, §8.5), and a
    second copy of one fact is exactly how two classifications drift apart — the
    failure DEC-15 warns about for the wrap/raise pair. It is passed in at the
    single call site instead.
    """

    capabilities: frozenset[str] = frozenset()
    read_only_hint: bool = False

    def high_impact(self, *, external: bool) -> bool:
        """Does this route's effect escape the isolation? (DEC-15.)"""
        if NETWORK_CAPABILITY in self.capabilities:
            return True
        return external and not self.read_only_hint


__all__ = ["NETWORK_CAPABILITY", "RouteImpact"]
