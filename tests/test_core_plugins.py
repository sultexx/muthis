# tests/test_core_plugins.py
"""
The M4 dogfood proof — the four V1 tools as core plugins over muthis-sdk.

The load-bearing test is the SNAPSHOT: tests/snapshots/look_tools_v1.json was
generated from the v1.0.0 LOOK_ONLY_TOOLS BEFORE the re-founding; the
assembled catalog must reproduce it byte-for-byte in its canonical JSON
serialization. That equality IS the "zero behavioral change" clause for
everything the model sees.
"""

from __future__ import annotations

import ast
import asyncio
import json
import re
from pathlib import Path

import muthis_plugins
from muthis.cloud.tool_schemas import LOOK_ONLY_TOOLS
from muthis.kernel.core_router import build_core_router
from muthis.kernel.router_surfaces import MAX_TOOLS
from muthis.kernel.tool_result_pairing import WEB_FETCH_TOOL, WEB_SEARCH_TOOL
from muthis.kernel.turn import RUN_CODE_TOOL
from muthis_plugins.common import FILES_CAPABILITY_ABSENT_AR, KERNEL_SERVICED_AR
from muthis_plugins.file_read import FileReadPlugin
from muthis_plugins.look_pointer import LookPointerPlugin
from muthis_plugins.look_shapes import LookShapesPlugin
from muthis_plugins.screen_refresh import ScreenRefreshPlugin
from muthis_sdk import FilesCapability, PluginContext, load_manifest

SNAPSHOT = Path(__file__).parent / "snapshots" / "look_tools_v1.json"
V2_SNAPSHOT = Path(__file__).parent / "snapshots" / "look_tools_v2.json"
V3_SNAPSHOT = Path(__file__).parent / "snapshots" / "look_tools_v3.json"
PLUGINS_DIR = Path(muthis_plugins.__file__).parent


class _StubFetcher:
    """`ctx.net`'s embodiment, unused by the catalog — mounting only reads
    descriptors. No network, no key, and never `muthis.main`."""

    async def fetch_readable(self, url):  # pragma: no cover - never called here
        raise AssertionError("the catalog test must not fetch")


def _v3_router():
    """The v3 catalog built through the REAL production mounts, in production
    ORDER: core four → sandbox → web."""
    from muthis.composition import mount_web_research
    from muthis_plugins.sandbox_exec import SandboxExecPlugin
    from muthis_plugins.web_research.plugin import WebResearchPlugin

    router = build_core_router(read_file=None)
    router.mount(SandboxExecPlugin(), namespace="sandbox", provenance="sandbox_exec")
    mount_web_research(router, WebResearchPlugin(), _StubFetcher())
    return router

PLUGIN_SET = {
    "look_pointer": (LookPointerPlugin, "highlight_target", True),
    "look_shapes": (LookShapesPlugin, "draw_shapes", True),
    "screen_refresh": (ScreenRefreshPlugin, "request_screen_refresh", True),
    "file_read": (FileReadPlugin, "read_local_file", False),
}


# ─── The zero-behavior clause: the model-visible catalog is byte-identical ───

def test_catalog_matches_the_frozen_v1_snapshot_byte_for_byte():
    canonical = json.dumps(LOOK_ONLY_TOOLS, ensure_ascii=False, indent=2) + "\n"
    assert canonical.encode("utf-8") == SNAPSHOT.read_bytes(), (
        "LOOK_ONLY_TOOLS drifted from the v1.0.0 snapshot — a model-visible "
        "behavioral change; revert the schema edit or re-approve the snapshot"
    )


def test_v1_catalog_order_is_preserved():
    assert [t["name"] for t in LOOK_ONLY_TOOLS] == [
        "highlight_target", "draw_shapes", "request_screen_refresh", "read_local_file",
    ]


def test_v2_catalog_byte_pins_sandbox_run_code():
    """T5 — the FIRST model-visible change since Phase 1: sandbox.run_code joins
    the catalog. Byte-pinned to look_tools_v2.json; the V1 snapshot stays as the
    untouched historical anchor."""
    from muthis_plugins.sandbox_exec import SandboxExecPlugin
    router = build_core_router(read_file=None)
    router.mount(SandboxExecPlugin(), namespace="sandbox", provenance="sandbox_exec")
    catalog = [d.schema for d in router.descriptors()]
    canonical = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    assert canonical.encode("utf-8") == V2_SNAPSHOT.read_bytes(), (
        "the v2 catalog drifted from look_tools_v2.json — a model-visible change; "
        "revert the schema edit or re-approve the snapshot")
    assert [t["name"] for t in catalog] == [
        "highlight_target", "draw_shapes", "request_screen_refresh",
        "read_local_file", RUN_CODE_TOOL]
    # the sandbox descriptor is a DECLARATION (kernel-serviced, catalog-only)
    assert router.descriptors()[-1].kernel_serviced is True
    # the V1 snapshot is untouched (the historical anchor)
    assert (json.dumps(LOOK_ONLY_TOOLS, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8") == SNAPSHOT.read_bytes()


def test_v3_catalog_byte_pins_the_web_tools():
    """T6b — the THIRD model-visible change (V1 four → v2 sandbox → v3 web).
    Byte-pinned to look_tools_v3.json; V1 and v2 stay as historical anchors.

    Mounted through the REAL composition helper, not a hand-rolled copy: the
    snapshot must state what PRODUCTION shows the model, so a drift in the
    mount's namespace or schema fails here rather than at a live 400."""
    catalog = [d.schema for d in _v3_router().descriptors()]
    canonical = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    assert canonical.encode("utf-8") == V3_SNAPSHOT.read_bytes(), (
        "the v3 catalog drifted from look_tools_v3.json — a model-visible change; "
        "revert the schema edit or re-approve the snapshot")
    assert [t["name"] for t in catalog] == [
        "highlight_target", "draw_shapes", "request_screen_refresh",
        "read_local_file", RUN_CODE_TOOL, WEB_SEARCH_TOOL, WEB_FETCH_TOOL]
    # v3 is v2 with two tools APPENDED — the earlier anchors are untouched.
    v2 = json.loads(V2_SNAPSHOT.read_text(encoding="utf-8"))
    assert catalog[:len(v2)] == v2, "v3 must extend v2, never rewrite it"
    assert (json.dumps(LOOK_ONLY_TOOLS, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8") == SNAPSHOT.read_bytes()


def test_the_v3_catalog_holds_the_descriptor_cap():
    catalog = _v3_router().descriptors()
    assert len(catalog) == 7
    assert len(catalog) <= MAX_TOOLS, f"{len(catalog)} tools exceed the cap {MAX_TOOLS}"


def test_the_web_tools_are_router_serviced_not_kernel_serviced():
    """They are SERVICED through the router (DEC-39), unlike the sandbox
    declaration — so `kernel_serviced` must stay False or `service()` would
    refuse them defensively."""
    by_name = {d.schema["name"]: d for d in _v3_router().descriptors()}
    assert by_name[WEB_SEARCH_TOOL].kernel_serviced is False
    assert by_name[WEB_FETCH_TOOL].kernel_serviced is False
    assert by_name[RUN_CODE_TOOL].kernel_serviced is True


def test_every_model_visible_tool_name_matches_the_anthropic_pattern():
    """The lesson of the T6 live 400 (DEC-11): a dot-namespaced name broke the
    Anthropic tool-name pattern, and NOTHING in the suite caught it. Guard EVERY
    model-visible catalog name here — this must fail loudly if any future plugin
    (namespaced or bare) ships a name the API would reject.

    Runs over the FULL v3 catalog, not only v2: `web__search` / `web__fetch` are
    exactly the kind of namespaced name that produced the live 400."""
    api_name = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
    router = _v3_router()
    checked = {d.schema["name"] for d in router.descriptors()}
    assert {WEB_SEARCH_TOOL, WEB_FETCH_TOOL} <= checked, (
        "the name guard no longer covers the web tools")
    for descriptor in router.descriptors():
        name = descriptor.schema["name"]
        assert api_name.match(name), f"tool name {name!r} violates ^[a-zA-Z0-9_-]{{1,128}}$"
    for tool in LOOK_ONLY_TOOLS:  # the byte-pinned V1 four are valid too (bare names)
        assert api_name.match(tool["name"]), tool["name"]


def test_the_composition_root_actually_mounts_the_web_tools_after_the_sandbox():
    """AST over `main.py`, never an import (it runs `load_dotenv()` at module
    level and reads live credentials).

    Mutation found this missing: every catalog test above builds its OWN router,
    so PRODUCTION could stop mounting the web tools entirely — or mount them
    BEFORE the sandbox, silently reordering the byte-pinned catalog — and nothing
    would fail. Order matters: v3 must stay v2 with two tools APPENDED."""
    main_py = Path(__file__).resolve().parents[1] / "src" / "muthis" / "main.py"
    tree = ast.parse(main_py.read_text(encoding="utf-8"))

    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (getattr(node.func, "id", "") == "mount_web_research"
             or getattr(node.func, "attr", "") == "mount")
    ]
    kinds = [
        "web" if getattr(c.func, "id", "") == "mount_web_research" else "other"
        for c in sorted(calls, key=lambda c: c.lineno)
    ]
    assert "web" in kinds, "the composition root no longer mounts the web tools"
    sandbox_lines = [
        c.lineno for c in calls
        if any(getattr(a, "func", None) is not None
               and getattr(a.func, "id", "") == "SandboxExecPlugin" for a in c.args)
    ]
    web_lines = [c.lineno for c in calls if getattr(c.func, "id", "") == "mount_web_research"]
    assert sandbox_lines and web_lines
    assert min(web_lines) > max(sandbox_lines), (
        "the web mount must follow the sandbox mount — v3 is v2 plus two APPENDED")


def test_router_descriptors_are_the_same_schema_objects():
    router = build_core_router(read_file=None)
    descriptors = router.descriptors()
    assert [d.schema for d in descriptors] == LOOK_ONLY_TOOLS
    # Same OBJECTS, not copies — one source of truth, zero drift surface.
    for descriptor, schema in zip(descriptors, LOOK_ONLY_TOOLS):
        assert descriptor.schema is schema
    assert [d.kernel_serviced for d in descriptors] == [True, True, True, False]


# ─── Manifests: valid, capability-correct, consistent with the descriptors ───

def test_manifests_load_and_match_descriptors():
    expected_caps = {
        "look_pointer": ("annotate.overlay",),
        "look_shapes": ("annotate.overlay",),
        "screen_refresh": ("perceive.screen",),
        "file_read": ("perceive.files.read",),
    }
    for package, (plugin_cls, tool_name, _) in PLUGIN_SET.items():
        manifest = load_manifest(PLUGINS_DIR / package)
        assert manifest.name == package and manifest.kind == "native"
        assert manifest.capabilities_required == expected_caps[package]
        assert [t.name for t in manifest.tools] == [tool_name]
        assert manifest.tools[0].read_only is True
        (descriptor,) = plugin_cls().descriptors()
        assert descriptor.name == tool_name
        assert manifest.entry.endswith(plugin_cls.__name__)


# ─── Execution split (ruling C-1) ─────────────────────────────────────────────

def test_file_read_executes_through_the_granted_seam():
    async def fake_read(args):
        return f"سطر من {args['path']}"

    ctx = PluginContext(files=FilesCapability(read=fake_read))
    result = asyncio.run(FileReadPlugin().execute("read_local_file", {"path": "a.py"}, ctx))
    assert result.text_ar == "سطر من a.py" and result.is_error is False


def test_file_read_degrades_politely_without_the_capability():
    result = asyncio.run(FileReadPlugin().execute("read_local_file", {"path": "a.py"}, PluginContext()))
    assert result.text_ar == FILES_CAPABILITY_ABSENT_AR and result.is_error is True


def test_declaration_plugins_refuse_direct_execution():
    for plugin_cls, tool_name, kernel_serviced in PLUGIN_SET.values():
        if not kernel_serviced:
            continue
        result = asyncio.run(plugin_cls().execute(tool_name, {}, PluginContext()))
        assert result.text_ar == KERNEL_SERVICED_AR and result.is_error is True


# ─── Layering purity: plugins import muthis_sdk + stdlib ONLY ────────────────

def test_plugins_import_nothing_from_the_app():
    offending = []
    for source in PLUGINS_DIR.rglob("*.py"):
        for line_number, line in enumerate(
            source.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if re.match(r"\s*(from|import)\s+muthis(\.|\s|$)", line):
                offending.append(f"{source.relative_to(PLUGINS_DIR)}:{line_number}: {line.strip()}")
    assert not offending, f"muthis_plugins must not import the app: {offending}"
