# tests/test_high_impact.py
"""
DEC-15 — high-impact classification: WHICH calls need spoken approval once the
session is tainted. Classification only; the gate that consumes it is T5's
second commit, so everything here is deliberately INERT in production.

THE PROPERTY UNDER TEST: the classification is KERNEL-SIDE. Every input comes
from the mounter (granted capability / the MCP hint the kernel itself read), and
NOTHING comes from the plugin — a plugin that could declare itself low-impact
would nullify the gate, which is the same hole `is_error` would open in the
DEC-14 wrap (DEC-29).

The second property is the DEC-15 REFINEMENT of DEC-3-A: a network-LESS sandbox
run is NOT high-impact even under ACTIVE taint, because the isolation IS the
containment. It is asserted explicitly and on the REAL plugin, mounted exactly
as the composition root mounts it — a regression there would put a permission
prompt back in front of the flagship "proof of run" flow.

Mutation-verified (DEC-12): flipping the fail-closed `read_only_hint` default,
dropping the `net.fetch` branch, ignoring the hint, letting the classification
read the plugin's own `read_only`, renaming the capability away from the SDK
enum, and removing the host's stated hint each turn a test RED.

Run:  set PYTHONPATH=src && python -m pytest tests/test_high_impact.py -q
"""

from __future__ import annotations

import ast
import asyncio
import pathlib

import muthis_sdk
from muthis.kernel.core_router import build_core_router
from muthis.kernel.tool_router import ToolRouter, namespaced_name
from muthis.trust.high_impact import NETWORK_CAPABILITY, RouteImpact
from muthis_sdk import ToolDescriptor, ToolPlugin, ToolResult
from muthis_plugins.sandbox_exec import SandboxExecPlugin

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
HIGH_IMPACT_PY = SRC / "muthis" / "trust" / "high_impact.py"
HOST_PY = SRC / "muthis" / "broker" / "mcp" / "host.py"

NETWORK = frozenset({NETWORK_CAPABILITY})


class _Plugin(ToolPlugin):
    """A plugin that DECLARES its own read-only-ness — the thing the
    classification must never listen to."""

    def __init__(self, name: str, read_only: bool = True) -> None:
        self._name, self._read_only = name, read_only

    def descriptors(self):
        return [ToolDescriptor(
            name=self._name,
            schema={"name": self._name, "description": "d", "input_schema": {}},
            read_only=self._read_only,
            kernel_serviced=False)]

    async def execute(self, tool, args, ctx):
        return ToolResult(text_ar="نتيجة")


def _impact_of(router: ToolRouter, tool: str) -> bool:
    """The route's classification, read where it is STORED.

    The facts are deliberately inert this commit — no production code consumes
    them yet — so the mount is the only place to observe them. The end-to-end
    behavioural proof (refused / allowed) arrives with the gate."""
    route = router._routes[tool]                      # noqa: SLF001 — see above
    return route.impact.high_impact(external=route.taint)


# ─── The classification itself ───────────────────────────────────────────────

def test_a_route_granted_the_network_capability_is_high_impact():
    """`web.search` / `web.fetch` (T6) and a network-ENABLED sandbox run are one
    case, not three: the effect leaves the machine. The kernel-side fact is the
    GRANT — the sandbox schema has no network parameter to inspect."""
    assert RouteImpact(capabilities=NETWORK).high_impact(external=True) is True
    assert RouteImpact(capabilities=NETWORK).high_impact(external=False) is True


def test_an_external_route_without_the_read_only_hint_is_high_impact():
    """DEC-15's "MCP tools lacking readOnlyHint"."""
    assert RouteImpact().high_impact(external=True) is True


def test_an_external_route_carrying_the_read_only_hint_is_not_high_impact():
    assert RouteImpact(read_only_hint=True).high_impact(external=True) is False


def test_a_local_route_is_not_high_impact():
    """The V1 four: pointing, drawing, a refresh and a local read send nothing
    anywhere, so no effect can escape."""
    assert RouteImpact().high_impact(external=False) is False
    assert RouteImpact(read_only_hint=True).high_impact(external=False) is False


def test_the_default_is_fail_closed_for_an_external_route():
    """A mounter that says NOTHING about an external route gets the strict
    answer. Resting on Phase 1's exposure filter instead would be the
    circumstantial protection DEC-13 rejects."""
    assert RouteImpact() == RouteImpact(capabilities=frozenset(), read_only_hint=False)
    assert RouteImpact().high_impact(external=True) is True


def test_the_capability_name_matches_the_closed_sdk_enum():
    """Anti-drift: the name is spelled here (stdlib-only module) and pinned
    there. A rename that missed one spelling would silently classify every web
    route as low-impact."""
    assert NETWORK_CAPABILITY in muthis_sdk.CAPABILITIES


# ─── Never a plugin's self-declaration ───────────────────────────────────────

def test_a_plugin_declaring_itself_read_only_cannot_lower_its_classification():
    """The gate-nullifying hole, driven directly: the plugin claims
    `read_only=True` and is mounted external WITHOUT a kernel-read hint. It
    stays high-impact, because its own claim is not an input."""
    router = ToolRouter()
    router.mount(_Plugin("act", read_only=True), namespace="ext",
                 provenance="mcp:ext", taint=True)
    assert _impact_of(router, namespaced_name("ext", "act")) is True


def test_a_plugin_declaring_itself_writable_cannot_raise_a_local_route():
    """The mirror: a local route stays low-impact however the plugin labels
    itself. The classification reads the MOUNT, not the descriptor."""
    router = ToolRouter()
    router.mount(_Plugin("local", read_only=False), provenance="core:test")
    assert _impact_of(router, "local") is False


def test_the_classification_module_never_reads_a_descriptors_read_only_field():
    """Structural twin of the two tests above (the test_pointer_look_only AST
    precedent — docstrings mention `read_only` on purpose, so a text scan would
    be wrong). The module's only fields are its own."""
    tree = ast.parse(HIGH_IMPACT_PY.read_text(encoding="utf-8"))
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "read_only" not in attributes
    assert "descriptor" not in attributes


def test_the_classification_module_imports_nothing_but_stdlib():
    """Importable in isolation (§17.4) and unbribable: it cannot consult a
    plugin, a manifest or the router even by accident."""
    tree = ast.parse(HIGH_IMPACT_PY.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            imported.add("<relative>")
    assert imported == {"__future__", "dataclasses"}, imported


# ─── The real mounts ─────────────────────────────────────────────────────────

def test_the_v1_four_are_not_high_impact():
    router = build_core_router(read_file=None)
    for descriptor in router.descriptors():
        assert _impact_of(router, descriptor.name) is False, descriptor.name


def test_a_network_less_sandbox_run_is_not_high_impact_under_active_taint():
    """THE DEC-15 refinement, on the REAL plugin mounted exactly as main.py
    mounts it. The taint is raised FIRST so the assertion is made in the state
    that matters; classification must not depend on it (the gate combines the
    two halves), and a regression here puts friction back on the flagship
    "proof of run" flow DEC-3-A protects."""
    router = build_core_router(read_file=None)
    router.mount(SandboxExecPlugin(), namespace="sandbox", provenance="sandbox_exec")
    router.session_taint.raise_taint("web:test")
    assert router.session_taint.tainted is True

    assert _impact_of(router, namespaced_name("sandbox", "run_code")) is False


def test_the_web_routes_t6_will_mount_are_high_impact():
    """Mounted as DEC-24/DEC-27 say T6 will mount them: `net.fetch` granted (the
    fetch power lives in the broker), results tainted."""
    router = ToolRouter()
    for tool_name in ("search", "fetch"):
        router.mount(_Plugin(tool_name), namespace="web", provenance="web:test",
                     taint=True, impact=RouteImpact(capabilities=NETWORK))
        assert _impact_of(router, namespaced_name("web", tool_name)) is True


def test_the_mcp_host_states_the_hint_it_read():
    """The host is where the annotation is READ (`policy.filter_tools` exposes a
    tool only when its catalog carried readOnlyHint=true), so the host is where
    it may be stated. Asserted by source scan, not by importing the composition
    path: dropping this line silently makes every Phase-1 MCP tool high-impact."""
    tree = ast.parse(HOST_PY.read_text(encoding="utf-8"))
    stated = [
        keyword for node in ast.walk(tree) if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "impact"
        and isinstance(keyword.value, ast.Call)
        and getattr(keyword.value.func, "id", "") == "RouteImpact"
        and any(inner.arg == "read_only_hint" and inner.value.value is True
                for inner in keyword.value.keywords)
    ]
    assert len(stated) == 1, "the MCP mount must state the readOnlyHint it read"


# ─── What the classification is FOR ──────────────────────────────────────────

def test_the_classification_is_now_consumed_by_the_gate():
    """The inertness mirror, inverted at the commit boundary it was written for:
    the very route that executed while no gate existed is now REFUSED under
    active taint. Classification alone changes nothing; joined to the session
    state at the router it is the whole enforcement. The two-turn flow itself is
    the subject of tests/test_confirm_gate.py."""
    router = ToolRouter()
    router.mount(_Plugin("act"), namespace="ext", provenance="mcp:ext",
                 taint=True, impact=RouteImpact(capabilities=NETWORK))
    router.session_taint.raise_taint("web:test")

    outcome = asyncio.run(router.service(namespaced_name("ext", "act"), {}))
    assert outcome.result.is_error is True
    assert outcome.provenance == "kernel:confirm"
    assert "نتيجة" not in outcome.result.text_ar   # the plugin never ran
