# tests/test_gate_coverage.py
"""
DEC-143 RULING ② — no route that can reach the network is mounted outside the
confirm gate's coverage. A GUARD, not a note.

WHY THIS EXISTS. DEC-143 accepted a turn grant for `web__search` on one ground:
search reaches ONE configured provider, and every path to an attacker-chosen
endpoint runs through `web__fetch`, which stays per call. That sentence is true of
the PRODUCTION composition and of nothing wider, so it needs a guard that fails
the moment it stops being true — not a paragraph that goes on saying it.

THE FINDING THIS GUARD STANDS ON, recorded in its own right: every MCP route is
mounted `read_only_hint=True` UNCONDITIONALLY (`broker/mcp/host.py`), so it is
never gated, whatever the server behind it does. That is a blanket mount-time
claim, and it can be FALSE for a server that sends data out — an MCP server is an
external process whose network reach the kernel cannot see. Nothing else in the
tree answers that case, which makes this guard the ONLY protection against it,
not a redundant one. Today MCP is dormant by CONFIGURATION: no server is
registered. Enabling one reddens this suite and REOPENS DEC-143 by construction.

THE TWO LIMITS, recorded with the ruling that accepted them:
  * PER-MACHINE BY DESIGN. Registrations (`plugins.d/*.toml`) are git-ignored, so
    this guard turns red on the machine where a server is enabled — the machine
    that would run it — and stays green on a clean checkout.
  * IT TRUSTS THE LAUNCH FROM THE REPO ROOT. The host reads the RELATIVE
    `plugins.d`, and the app is launched `python -m muthis.main` from the root
    (AGENTS.md, "Build & Run"); a launch from elsewhere reads a directory this
    guard never sees.

HOW THE PRODUCTION ROUTER IS REACHED, without importing `muthis.main` (the
standing rule): `_v8_router()` builds it through the REAL mount functions in
production order, and the inventory below pins every mount site `main.py` and
the composition root actually call — so a new mount reddens this file until it
is classified, the DEC-40 lesson applied to coverage.

Run:  set PYTHONPATH=src && python -m pytest tests/test_gate_coverage.py -q
"""

from __future__ import annotations

import ast
import pathlib

from muthis.broker.mcp.host import DEFAULT_PLUGINS_DIR
from muthis.trust.high_impact import NETWORK_CAPABILITY, RouteImpact
from test_navigator_verify_mount import _v8_router   # the production router, not a copy

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAIN_PY = ROOT / "src" / "muthis" / "main.py"
COMPOSITION_PY = ROOT / "src" / "muthis" / "composition.py"
MCP_HOST_PY = ROOT / "src" / "muthis" / "broker" / "mcp" / "host.py"

# Every production mount site, in source order. A site that is not here is a
# route nobody has classified.
MOUNT_INVENTORY = {
    MAIN_PY: ["router.mount", "mount_web_research", "mount_doc_rag", "mount_navigator",
              "mount_navigator_verify", "mcp_host.mount_all"],
    COMPOSITION_PY: ["build_core_router"],
}

# The ONLY routes allowed to be external yet ungated, each with its reason. An
# exemption must also have NO network seam, or it would hide exactly what this
# file exists to catch.
EXEMPT = {
    "docs__open": "DEC-51: a LOCAL document — tainted because nobody inspected it, "
                  "but it sends nothing anywhere",
    "docs__query": "DEC-51: retrieval over that same local document",
}


def _mount_calls(path: pathlib.Path) -> list[str]:
    calls = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = f"{getattr(func.value, 'id', '?')}.{func.attr}"
        else:
            continue
        if "mount" in name or name == "build_core_router":
            calls.append((node.lineno, name))
    return [name for _line, name in sorted(calls)]


def _can_reach_the_network(route) -> bool:
    """What the kernel can KNOW, never guess: a granted `net.fetch`, a network seam
    in the route's context, or an EXTERNAL route whose server the kernel cannot see
    into."""
    return (NETWORK_CAPABILITY in route.impact.capabilities
            or route.ctx.net is not None or route.taint)


def test_every_production_mount_site_is_accounted_for():
    for path, expected in MOUNT_INVENTORY.items():
        assert _mount_calls(path) == expected, (
            f"{path.name}'s mount sites changed: {_mount_calls(path)} — classify the new "
            "route here before it can reach the model")


def test_every_route_that_can_reach_the_network_is_under_the_gate():
    routes = _v8_router()._routes                     # noqa: SLF001 — where the facts live
    for name, reason in EXEMPT.items():
        route = routes[name]
        assert route.ctx.net is None and NETWORK_CAPABILITY not in route.impact.capabilities, (
            f"{name} is exempt ({reason}) yet holds a network seam — the exemption hides one")
    outside = {name for name, route in routes.items()
               if _can_reach_the_network(route)
               and not route.impact.high_impact(external=route.taint)}
    assert outside == set(EXEMPT), (
        f"routes that can reach the network are mounted OUTSIDE the confirm gate: "
        f"{sorted(outside - set(EXEMPT))} — DEC-143's ground no longer holds")


def test_the_MCP_registry_is_EMPTY_because_every_MCP_route_mounts_ungated():
    """The finding, pinned where it lives, then the registry it makes dangerous."""
    host = ast.parse(MCP_HOST_PY.read_text(encoding="utf-8"))
    impacts = [ast.unparse(kw.value) for node in ast.walk(host)
               if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "mount"
               for kw in node.keywords if kw.arg == "impact"]
    assert impacts == ["RouteImpact(read_only_hint=True)"], (
        f"the MCP host changed how it classifies its routes: {impacts} — re-read this "
        "guard's reasoning before trusting it either way")
    assert RouteImpact(read_only_hint=True).high_impact(external=True) is False

    registered = sorted((ROOT / DEFAULT_PLUGINS_DIR).glob("*.toml"))
    assert registered == [], (
        f"an MCP server is registered on this machine: {[p.name for p in registered]}. "
        "Its routes mount read_only_hint=True and are NEVER gated, whatever the server "
        "sends out — so 'every path to attacker infrastructure runs through fetch' is no "
        "longer true. DEC-143 is REOPENED: rule on MCP's coverage before enabling it.")
