# tests/test_doc_mount.py
"""
The `doc_rag` MOUNT — catalog v4, and DEC-51's two flags in BOTH directions.

DEC-51 IS THE SHARPEST WIRING DETAIL OF THIS MILESTONE, and it is a COUPLING
rather than a pair of independent settings:

  * `taint=True` — every retrieved passage raises taint, in every zone and every
    format. Any document reaching this route is BY DEFINITION too large to have
    been inspected; the real line is not local-versus-external but whether the
    USER SAW IT.
  * `read_only_hint=True` — WITHOUT it, impact classification reads `taint` as the
    EXTERNALITY signal and the route gates ITSELF behind a two-turn spoken
    confirmation. Absurd for reading a local file, and DEC-32 predicted this exact
    case by name, asking to be re-read at this gate.

**SO BOTH DIRECTIONS ARE ASSERTED, because one alone is satisfiable by a mutation
that hard-codes the other.** "Taint is raised" passes if `high_impact` were
hard-wired False; "not high-impact" passes if taint were never raised. Only the
conjunction says what DEC-51 ruled.

AND THEY ARE ASSERTED AGAINST THE REAL MOUNT — `mount_doc_rag`, the function
`main.py` itself calls — plus an AST check that `main.py` still calls it. That
pairing is the M2 lesson: DEC-40 found five of six mutations surviving because
every test built its OWN router, so deleting the production mount call entirely
stayed green. A synthetic router proves nothing about production.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

from muthis.composition import mount_doc_rag, mount_web_research
from muthis.kernel.core_router import build_core_router
from muthis.kernel.router_surfaces import MAX_TOOLS
from muthis.kernel.tool_result_pairing import DOC_OPEN_TOOL, DOC_QUERY_TOOL
from muthis.kernel.tool_router import ToolRouter
from muthis.kernel.turn import RUN_CODE_TOOL, WEB_TOOLS
from muthis.trust.high_impact import NETWORK_CAPABILITY, RouteImpact
from muthis_plugins.doc_rag.plugin import DocRagPlugin
from muthis_plugins.sandbox_exec import SandboxExecPlugin
from muthis_plugins.web_research.plugin import WebResearchPlugin

ROOT = pathlib.Path(__file__).resolve().parents[1]
V3_SNAPSHOT = pathlib.Path(__file__).parent / "snapshots" / "look_tools_v3.json"
V4_SNAPSHOT = pathlib.Path(__file__).parent / "snapshots" / "look_tools_v4.json"
MAIN_PY = ROOT / "src" / "muthis" / "main.py"


class _StubFetcher:
    async def fetch_readable(self, url):  # pragma: no cover - never called here
        raise AssertionError("the catalog test must not fetch")


def _v4_router() -> ToolRouter:
    """The v4 catalog built through the REAL production mounts, in production
    ORDER: core four → sandbox → web → docs."""
    router = build_core_router(read_file=None)
    router.mount(SandboxExecPlugin(), namespace="sandbox", provenance="sandbox_exec")
    mount_web_research(router, WebResearchPlugin(), _StubFetcher())
    mount_doc_rag(router, DocRagPlugin())
    return router


def _route(tool: str):
    """The mounted route, read where its facts are STORED.

    Reaching one private field is the honest way to assert a fact whose whole
    value is that it does not depend on another fact (the `test_high_impact.py`
    precedent, same justification)."""
    return _v4_router()._routes[tool]                 # noqa: SLF001 — see above


# ═══ DEC-51 — BOTH DIRECTIONS, on the REAL mount ═════════════════════════════

def test_the_doc_route_RAISES_taint():
    """Direction 1. Alone, this would pass even if `high_impact` were hard-wired
    False — which is why the next test exists and why DEC-51 demands the pair."""
    for tool in (DOC_OPEN_TOOL, DOC_QUERY_TOOL):
        assert _route(tool).taint is True, f"{tool} does not raise taint (DEC-51)"


def test_the_doc_route_is_NOT_high_impact():
    """Direction 2. Alone, this would pass even if taint were never raised.

    Without the read-only hint the route would gate ITSELF: a two-turn spoken
    confirmation in front of reading a local file, which DEC-32 named as the
    absurdity to avoid."""
    for tool in (DOC_OPEN_TOOL, DOC_QUERY_TOOL):
        route = _route(tool)
        assert route.impact.high_impact(external=route.taint) is False, (
            f"{tool} gates itself behind spoken confirmation (DEC-51/DEC-32)")


def test_the_two_flags_are_a_COUPLING_and_the_conjunction_is_what_is_ruled():
    """The pair stated as ONE assertion, and the counterfactual driven directly:
    the SAME route without the hint IS high-impact. That is the arithmetic DEC-51
    recorded from P0b, re-derived here against the real mount rather than quoted."""
    route = _route(DOC_QUERY_TOOL)

    assert route.taint is True and route.impact.read_only_hint is True
    assert route.impact.high_impact(external=route.taint) is False
    # DROP THE HINT and the absurdity returns — proving the hint is load-bearing
    # and not decorative.
    assert RouteImpact().high_impact(external=route.taint) is True


def test_the_doc_route_holds_NO_capability_so_the_first_arm_cannot_fire_either():
    """Reading a local document sends nothing anywhere — the V1 `read_local_file`
    argument, unchanged. Asserted separately because `high_impact` has TWO arms and
    the capability arm ignores the hint entirely."""
    route = _route(DOC_OPEN_TOOL)

    assert NETWORK_CAPABILITY not in route.impact.capabilities
    assert route.impact.capabilities == frozenset()


def test_the_plugins_own_read_only_cannot_lower_the_kernels_classification():
    """A plugin does not get to grade itself (DEC-15/DEC-29). `read_only=True` sits
    on both descriptors; the classification comes from the MOUNT."""
    descriptors = {d.name: d for d in DocRagPlugin().descriptors()}

    assert all(d.read_only is True for d in descriptors.values())
    # ...and a route mounted WITHOUT the kernel's hint is high-impact regardless.
    router = build_core_router(read_file=None)
    router.mount(DocRagPlugin(), namespace="docs", provenance="doc_rag", taint=True)
    route = router._routes[DOC_OPEN_TOOL]             # noqa: SLF001
    assert route.impact.high_impact(external=route.taint) is True, (
        "a plugin's own read_only leaked into the kernel's classification")


# ═══ THE PRODUCTION CALL SITE — deletable invisibly without this ═════════════

def _main_tree() -> ast.Module:
    return ast.parse(MAIN_PY.read_text(encoding="utf-8"))


def test_the_composition_root_actually_mounts_doc_rag_after_the_web_tools():
    """AST over `main.py`, never an import (it runs `load_dotenv()` at module level
    and reads live credentials).

    DEC-40's lesson applied before it bites: every catalog test above builds its
    OWN router, so PRODUCTION could stop mounting the doc tools entirely — or mount
    them BEFORE the web tools, silently reordering the byte-pinned catalog — and
    nothing else would fail. Order matters: v4 must stay v3 with two APPENDED."""
    calls = [n for n in ast.walk(_main_tree()) if isinstance(n, ast.Call)]
    doc_lines = [c.lineno for c in calls if getattr(c.func, "id", "") == "mount_doc_rag"]
    web_lines = [c.lineno for c in calls
                 if getattr(c.func, "id", "") == "mount_web_research"]

    assert doc_lines, "the composition root no longer mounts the doc tools"
    assert web_lines, "the web mount vanished"
    assert min(doc_lines) > max(web_lines), (
        "the doc mount must FOLLOW the web mount — v4 is v3 plus two APPENDED")


def test_the_root_clears_the_document_index_at_shutdown():
    """The index is session-scoped and dies with the session (privacy law), so the
    ROOT that built the service owns its teardown. A missing `clear()` would leave
    the user's document in RAM for the process's remaining life — and nothing
    observable would differ, which is why this is asserted at the call site."""
    tree = _main_tree()
    cleared = [n for n in ast.walk(tree)
               if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "clear"
               and getattr(getattr(n.func, "value", None), "id", "") == "doc_service"]

    assert cleared, "main.py never clears the document service at shutdown"


# ═══ CATALOG v4 — byte-pinned, purely additive ═══════════════════════════════

def test_v4_catalog_byte_pins_the_doc_tools():
    """T4 — the FOURTH model-visible change (V1 four → v2 sandbox → v3 web → v4
    docs). Byte-pinned to look_tools_v4.json; v1/v2/v3 stay historical anchors.

    Mounted through the REAL composition helper, not a hand-rolled copy: the
    snapshot must state what PRODUCTION shows the model, so a drift in the mount's
    namespace or schema fails here rather than at a live 400."""
    catalog = [d.schema for d in _v4_router().descriptors()]
    canonical = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"

    assert canonical.encode("utf-8") == V4_SNAPSHOT.read_bytes(), (
        "the v4 catalog drifted from look_tools_v4.json — a model-visible change; "
        "revert the schema edit or re-approve the snapshot")
    assert [t["name"] for t in catalog] == [
        "highlight_target", "draw_shapes", "request_screen_refresh",
        "read_local_file", RUN_CODE_TOOL, "web__search", "web__fetch",
        DOC_OPEN_TOOL, DOC_QUERY_TOOL]


def test_v4_EXTENDS_v3_and_never_rewrites_it():
    catalog = [d.schema for d in _v4_router().descriptors()]
    v3 = json.loads(V3_SNAPSHOT.read_text(encoding="utf-8"))

    assert catalog[:len(v3)] == v3, "v4 must extend v3, never rewrite it"
    assert len(catalog) == len(v3) + 2


def test_the_v4_catalog_holds_the_descriptor_cap():
    """The cutoff and the admitted count, stated (the standing rule)."""
    catalog = _v4_router().descriptors()

    assert len(catalog) == 9, f"expected 9 descriptors, got {len(catalog)}"
    assert len(catalog) <= MAX_TOOLS, f"{len(catalog)} tools exceed the cap {MAX_TOOLS}"


def test_every_v4_tool_name_matches_the_anthropic_pattern():
    """DEC-11, the lesson of M1's live 400: a dot-namespaced name broke
    `^[a-zA-Z0-9_-]{1,128}$` and NOTHING in the suite caught it. Run over the FULL
    v4 catalog — `docs__open` / `docs__query` are exactly the namespaced shape that
    produced that failure."""
    api_name = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
    names = [d.schema["name"] for d in _v4_router().descriptors()]

    assert {DOC_OPEN_TOOL, DOC_QUERY_TOOL} <= set(names), (
        "the name guard no longer covers the doc tools")
    checked = 0
    for name in names:
        assert api_name.match(name), f"tool name {name!r} violates the API pattern"
        checked += 1
    assert checked == 9 and checked > 0     # a guard that checked nothing is not a guard


def test_the_separator_is_derived_from_ONE_place_not_spelled_in_the_plugin():
    """DEC-11 put the separator in `tool_router.namespaced_name` alone. The plugin
    declares BARE names; a package that spelled `docs__open` in CODE would be a
    second home for the fact that caused the live 400.

    AST over CODE literals and identifiers, not raw text — the
    `test_untrusted_wrap_guard.py` / `test_pointer_look_only.py` precedent. Comments
    and DOCSTRINGS must stay free to name the namespaced form, and every module in
    this package does name it while explaining why it does not spell it."""
    package = ROOT / "src" / "muthis_plugins" / "doc_rag"
    bare = {d.name for d in DocRagPlugin().descriptors()}

    assert bare == {"open", "query"}, "the plugin no longer declares BARE names"
    scanned = 0
    for path in sorted(package.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {ast.get_docstring(n, clean=False) for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                        ast.AsyncFunctionDef))}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in docstrings:
                    continue
                assert "docs__" not in node.value, f"{path.name}:{node.lineno}"
            if isinstance(node, ast.Name):
                assert "docs__" not in node.id, f"{path.name}:{node.lineno}"
        scanned += 1
    assert scanned >= 4, f"only {scanned} modules scanned"


def test_the_doc_tools_are_router_serviced_not_kernel_serviced():
    """They are SERVICED through the router (DEC-39), unlike the sandbox
    DECLARATION — so `kernel_serviced` must stay False or `service()` would refuse
    them defensively as a misroute."""
    by_name = {d.schema["name"]: d for d in _v4_router().descriptors()}

    assert by_name[DOC_OPEN_TOOL].kernel_serviced is False
    assert by_name[DOC_QUERY_TOOL].kernel_serviced is False
    assert by_name[RUN_CODE_TOOL].kernel_serviced is True


def test_the_earlier_anchors_are_untouched():
    """v1/v2/v3 remain HISTORICAL ANCHORS: a change to an older snapshot would
    rewrite what the model was shown in a shipped release."""
    for name, count in (("look_tools_v1.json", 4), ("look_tools_v2.json", 5),
                        ("look_tools_v3.json", 7)):
        anchor = json.loads(
            (pathlib.Path(__file__).parent / "snapshots" / name).read_text(
                encoding="utf-8"))
        assert len(anchor) == count, f"{name} changed — it is a historical anchor"
    assert set(WEB_TOOLS) & {t["name"] for t in json.loads(
        V3_SNAPSHOT.read_text(encoding="utf-8"))} == set(WEB_TOOLS)
