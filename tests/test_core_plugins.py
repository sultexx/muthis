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

import asyncio
import json
import re
from pathlib import Path

import muthis_plugins
from muthis.cloud.tool_schemas import LOOK_ONLY_TOOLS
from muthis.kernel.tool_router import build_core_router
from muthis.kernel.turn import RUN_CODE_TOOL
from muthis_plugins.common import FILES_CAPABILITY_ABSENT_AR, KERNEL_SERVICED_AR
from muthis_plugins.file_read import FileReadPlugin
from muthis_plugins.look_pointer import LookPointerPlugin
from muthis_plugins.look_shapes import LookShapesPlugin
from muthis_plugins.screen_refresh import ScreenRefreshPlugin
from muthis_sdk import FilesCapability, PluginContext, load_manifest

SNAPSHOT = Path(__file__).parent / "snapshots" / "look_tools_v1.json"
V2_SNAPSHOT = Path(__file__).parent / "snapshots" / "look_tools_v2.json"
PLUGINS_DIR = Path(muthis_plugins.__file__).parent

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


def test_every_model_visible_tool_name_matches_the_anthropic_pattern():
    """The lesson of the T6 live 400 (DEC-11): a dot-namespaced name broke the
    Anthropic tool-name pattern, and NOTHING in the suite caught it. Guard EVERY
    model-visible catalog name here — this must fail loudly if any future plugin
    (namespaced or bare) ships a name the API would reject."""
    api_name = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
    from muthis_plugins.sandbox_exec import SandboxExecPlugin
    router = build_core_router(read_file=None)
    router.mount(SandboxExecPlugin(), namespace="sandbox", provenance="sandbox_exec")
    for descriptor in router.descriptors():
        name = descriptor.schema["name"]
        assert api_name.match(name), f"tool name {name!r} violates ^[a-zA-Z0-9_-]{{1,128}}$"
    for tool in LOOK_ONLY_TOOLS:  # the byte-pinned V1 four are valid too (bare names)
        assert api_name.match(tool["name"]), tool["name"]


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
