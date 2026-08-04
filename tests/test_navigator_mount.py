"""
test_navigator_mount.py — catalog v6 and the Navigator's KERNEL-STATED facts (T4).

EVERY CATALOG ASSERTION HERE RUNS THROUGH THE REAL PRODUCTION MOUNTS, never a
hand-rolled router. That is DEC-40's lesson, and this milestone earned it twice
more: five of six mutations survived M2 because every test built its own router,
and at T3 the composition-root wiring could be deleted entirely while every test
stayed green. **A synthetic router proves nothing about production**, so the
guard that would have caught it is written first here rather than after.

v6 EXTENDS, unlike v5. DEC-71 removed a field and forced the additive guard to
change shape into a blast-radius pin; T4 appends two tools and leaves every
earlier schema byte-identical, so the additive relation returns — asserted
against v5 directly, with the v5/v4 anchors untouched in their own file.
"""

from __future__ import annotations

import ast
import json
import pathlib

import pytest

from muthis.composition import mount_doc_rag, mount_navigator, mount_web_research
from muthis.kernel.core_router import build_core_router
from muthis.kernel.deferral_notes import NAV_PLAN_TOOL, NAV_STEP_TOOL
from muthis.kernel.router_surfaces import MAX_TOOLS
from muthis.kernel.tool_router import ToolRouter
from muthis_plugins.doc_rag.plugin import DocRagPlugin
from muthis_plugins.navigator import NavigatorPlugin
from muthis_plugins.sandbox_exec import SandboxExecPlugin
from muthis_plugins.web_research.plugin import WebResearchPlugin

SNAPSHOTS = pathlib.Path(__file__).parent / "snapshots"
V5_SNAPSHOT = SNAPSHOTS / "look_tools_v5.json"
V6_SNAPSHOT = SNAPSHOTS / "look_tools_v6.json"
MAIN_PY = (pathlib.Path(__file__).resolve().parent.parent / "src" / "muthis"
           / "main.py")


class _StubFetcher:
    async def fetch_readable(self, url):  # pragma: no cover — never called
        raise AssertionError("the catalog test must not fetch")


def _v6_router() -> ToolRouter:
    """The v6 catalog, built through the REAL production mounts in production
    ORDER: core four → sandbox → web → docs → navigator."""
    router = build_core_router(read_file=None)
    router.mount(SandboxExecPlugin(), namespace="sandbox", provenance="sandbox_exec")
    mount_web_research(router, WebResearchPlugin(), _StubFetcher())
    mount_doc_rag(router, DocRagPlugin())
    mount_navigator(router, NavigatorPlugin())
    return router


def _route(tool: str):
    """The mounted route, read where its facts are STORED (the
    `test_doc_mount.py` precedent, same justification)."""
    return _v6_router()._routes[tool]                 # noqa: SLF001


def _main_tree() -> ast.Module:
    return ast.parse(MAIN_PY.read_text(encoding="utf-8"))


# ═══ DEC-65's invariant, SPENT at the mount ══════════════════════════════════

@pytest.mark.parametrize("tool", [NAV_PLAN_TOOL, NAV_STEP_TOOL])
def test_a_mode_verb_RAISES_NO_TAINT(tool):
    """A mode ingests NOTHING: its arguments are the model's own words, already
    in the context. `doc_rag` needed `taint=True` because a document is by
    definition too large to have been inspected — there is no analogous quantity
    here. This is the opposite flag to DEC-51's, for the opposite reason."""
    assert _route(tool).taint is False


@pytest.mark.parametrize("tool", [NAV_PLAN_TOOL, NAV_STEP_TOOL])
def test_a_mode_verb_HOLDS_NO_CAPABILITY_and_is_never_high_impact(tool):
    """DEC-65's hard invariant, driven rather than asserted in prose — and with
    the taint ALREADY RAISED, which is the state a confirmation would fire in.
    A spoken approval in front of «next step» would make a walkthrough
    unusable, and it is the capability arm that would demand one."""
    route = _route(tool)
    assert route.impact.capabilities == frozenset()
    assert route.impact.high_impact(external=route.taint) is False
    assert route.impact.high_impact(external=True) is False, (
        "the kernel's read-only hint no longer protects the mode verbs")


@pytest.mark.parametrize("tool", [NAV_PLAN_TOOL, NAV_STEP_TOOL])
def test_the_verbs_are_KERNEL_SERVICED_so_the_router_never_executes_them(tool):
    """The state they change is the KERNEL'S. A plugin holding it would make
    "step 3 of 5" a plugin's CLAIM — exactly what DEC-65 removed."""
    assert _route(tool).descriptor.kernel_serviced is True


def test_the_plugin_declares_a_schema_and_holds_no_state():
    """It contributes two descriptors and nothing else: no mode, no plan, no
    transition and no note. `execute` is unreachable in production."""
    plugin = NavigatorPlugin()
    assert {d.name for d in plugin.descriptors()} == {"plan", "step"}
    assert not [a for a in vars(plugin)], "the plugin grew state"
    source = (pathlib.Path(__file__).resolve().parent.parent / "src"
              / "muthis_plugins" / "navigator" / "plugin.py").read_text(encoding="utf-8")
    for forbidden in ("SessionMode", "ModeAuthority", "Plan", "TransitionRequest"):
        assert forbidden not in source, f"the plugin reaches into the kernel: {forbidden}"


# ═══ CATALOG v6 — byte-pinned, and purely ADDITIVE ═══════════════════════════

def test_v6_catalog_byte_pins_the_navigator_tools():
    """The FIFTH model-visible change (V1 four → v2 sandbox → v3 web → v4 docs →
    v5 revision → v6 navigator), built through the REAL mounts so the snapshot
    states what PRODUCTION shows the model."""
    catalog = [d.schema for d in _v6_router().descriptors()]
    canonical = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"

    assert canonical.encode("utf-8") == V6_SNAPSHOT.read_bytes(), (
        "the v6 catalog drifted from look_tools_v6.json — a model-visible "
        "change; revert the schema edit or re-approve the snapshot")
    assert [t["name"] for t in catalog][-2:] == [NAV_PLAN_TOOL, NAV_STEP_TOOL]
    assert len(catalog) == 11


def test_v6_EXTENDS_v5_leaving_every_earlier_schema_byte_identical():
    """The additive relation RETURNS after v5's revision. A schema edit that
    reached `highlight_target`, `web__fetch` or `docs__query` fails here — the
    blast-radius property DEC-71 had to invent, now expressible again as the
    simpler prefix rule."""
    v5 = json.loads(V5_SNAPSHOT.read_text(encoding="utf-8"))
    v6 = json.loads(V6_SNAPSHOT.read_text(encoding="utf-8"))

    assert v6[:len(v5)] == v5, "v6 is not v5 with two tools APPENDED"
    assert len(v6) == len(v5) + 2


def test_the_tool_names_are_derived_and_match_the_anthropic_pattern():
    """DEC-11: the separator lives in ONE place and a dot fails the provider's
    pattern — caught live by a 400 once, guarded ever since."""
    import re

    pattern = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
    for name in (NAV_PLAN_TOOL, NAV_STEP_TOOL):
        assert pattern.match(name), name
        assert "__" in name and "." not in name
    package = (pathlib.Path(__file__).resolve().parent.parent / "src"
               / "muthis_plugins" / "navigator")
    for path in package.glob("*.py"):
        assert "navigator__" not in path.read_text(encoding="utf-8"), (
            f"{path.name} spells the namespaced form — it must be DERIVED")


def test_eleven_tools_stay_well_inside_the_context_cap():
    assert len([d for d in _v6_router().descriptors()]) == 11 < MAX_TOOLS


# ═══ THE PRODUCTION ROOT — driven, not assumed ═══════════════════════════════

def test_the_composition_root_mounts_the_navigator_AFTER_the_doc_tools():
    """AST over `main.py`, never an import (`load_dotenv()` at module level
    would pull live credentials into the test process).

    ORDER IS THE ASSERTION: v6 must stay v5 with two APPENDED, so a mount that
    ran before the doc tools would silently reorder the byte-pinned catalog."""
    calls = [n for n in ast.walk(_main_tree()) if isinstance(n, ast.Call)]
    nav_lines = [c.lineno for c in calls
                 if getattr(c.func, "id", "") == "mount_navigator"]
    doc_lines = [c.lineno for c in calls
                 if getattr(c.func, "id", "") == "mount_doc_rag"]

    assert nav_lines, "the composition root no longer mounts the navigator"
    assert doc_lines, "the doc mount vanished"
    assert min(nav_lines) > max(doc_lines), (
        "the navigator mount must FOLLOW the doc mount — v6 is v5 plus two")


def test_the_root_builds_a_REAL_plugin_and_hands_it_to_the_mount():
    """The T3 lesson, applied here rather than after a survivor: a root that
    mounted `None`, or built the plugin and never passed it, would satisfy a
    laxer check while wiring nothing."""
    calls = [n for n in ast.walk(_main_tree()) if isinstance(n, ast.Call)]
    mounts = [c for c in calls if getattr(c.func, "id", "") == "mount_navigator"]

    assert mounts, "the navigator mount vanished"
    for call in mounts:
        assert len(call.args) == 2, "mount_navigator's call shape changed"
        assert getattr(call.args[1].func, "id", "") == "NavigatorPlugin", (
            "the root hands the mount something other than a real NavigatorPlugin")


def test_the_servicing_landed_BEFORE_the_mount_is_still_true_in_the_source():
    """DEC-39 as a standing property rather than a one-off ordering: the two
    verbs must be answered BY NAME in the pairing builder. If that arm were
    ever removed while the mount stayed, every navigator call would take the
    POINTER ack and hard-terminate the turn."""
    pairing = (pathlib.Path(__file__).resolve().parent.parent / "src" / "muthis"
               / "kernel" / "tool_result_pairing.py").read_text(encoding="utf-8")
    turn_pass = (pathlib.Path(__file__).resolve().parent.parent / "src" / "muthis"
                 / "kernel" / "turn_pass.py").read_text(encoding="utf-8")
    assert "NAV_TOOLS" in pairing, "the answer-by-name arm is gone"
    assert "NAV_TOOLS" in turn_pass, "the servicing detection arm is gone"
