# tests/test_tool_router.py
"""
kernel.tool_router — the V2 Phase-0 dispatch registry.

Covers the contract the approved plan pinned: read_local_file servicing is
byte-identical to the V1 seam (test_read_file_tool.py remains the untouched
oracle for the pipeline side); the router NEVER raises into a turn; core
plugins keep bare V1 names while namespaced plugins are fenced; the draw
path is refused defensively (kernel-serviced); the catalog is capped.
"""

from __future__ import annotations

import asyncio

import pytest

from muthis.file_reader import FILE_READ_UNAVAILABLE_AR
from muthis.kernel.tool_router import (
    KERNEL_SERVICED_NOTE_AR,
    MAX_TOOLS,
    PLUGIN_FAILED_NOTE_AR,
    UNROUTED_TOOL_NOTE_AR,
    ToolRouter,
    build_core_router,
)
from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin, ToolResult


class _FakePlugin(ToolPlugin):
    def __init__(self, *names, kernel_serviced=False, raises=False):
        self._names = names or ("echo",)
        self._kernel_serviced = kernel_serviced
        self._raises = raises
        self.calls = []

    def descriptors(self):
        return [
            ToolDescriptor(
                name=n, schema={"name": n, "description": "d", "input_schema": {}},
                kernel_serviced=self._kernel_serviced,
            )
            for n in self._names
        ]

    async def execute(self, tool, args, ctx):
        if self._raises:
            raise RuntimeError("contract breach")
        self.calls.append((tool, args))
        return ToolResult(text_ar=f"نفّذت {tool}")


# ─── build_core_router: the read path, byte-identical to the V1 seam ─────────

def test_core_router_services_read_via_the_seam():
    async def fake_read(args):
        return f"محتوى {args['path']}"

    router = build_core_router(read_file=fake_read)
    outcome = asyncio.run(router.service("read_local_file", {"path": "x.py"}))
    assert outcome.result.text_ar == "محتوى x.py"
    assert outcome.result.is_error is False
    assert outcome.provenance == "core:file_read"
    assert outcome.taint is False and outcome.cost_usd is None  # Phase-1 fields inert


def test_core_router_none_seam_degrades_to_v1_unavailable_note():
    router = build_core_router(read_file=None)
    outcome = asyncio.run(router.service("read_local_file", {"path": "x.py"}))
    assert outcome.result.text_ar == FILE_READ_UNAVAILABLE_AR  # the EXACT V1 string
    assert outcome.result.is_error is True


# ─── The never-raise wall ─────────────────────────────────────────────────────

def test_unrouted_tool_is_an_arabic_note_never_a_raise():
    outcome = asyncio.run(ToolRouter().service("no_such_tool", {}))
    assert outcome.result.text_ar == UNROUTED_TOOL_NOTE_AR
    assert outcome.result.is_error is True


def test_kernel_serviced_tool_is_refused_defensively():
    router = ToolRouter()
    router.mount(_FakePlugin("highlight_target", kernel_serviced=True),
                 provenance="core:look_pointer")
    outcome = asyncio.run(router.service("highlight_target", {}))
    assert outcome.result.text_ar == KERNEL_SERVICED_NOTE_AR
    assert outcome.result.is_error is True


def test_raising_plugin_is_walled_off(caplog):
    router = ToolRouter()
    router.mount(_FakePlugin("boom", raises=True))
    with caplog.at_level("ERROR"):
        outcome = asyncio.run(router.service("boom", {}))
    assert outcome.result.text_ar == PLUGIN_FAILED_NOTE_AR
    assert outcome.result.is_error is True
    assert any("contract breach" in r.message for r in caplog.records)


# ─── Namespacing (core exemption) + collisions + the cap ─────────────────────

def test_core_mount_keeps_bare_v1_names():
    router = ToolRouter()
    router.mount(_FakePlugin("read_local_file"), namespace=None)
    assert [d.name for d in router.descriptors()] == ["read_local_file"]


def test_namespaced_mount_fences_name_and_schema():
    router = ToolRouter()
    plugin = _FakePlugin("search_web")
    router.mount(plugin, namespace="web")
    (descriptor,) = router.descriptors()
    assert descriptor.name == "web.search_web"
    assert descriptor.schema["name"] == "web.search_web"
    outcome = asyncio.run(router.service("web.search_web", {"q": "x"}))
    assert outcome.result.text_ar == "نفّذت search_web"  # plugin sees its BARE name
    assert plugin.calls == [("search_web", {"q": "x"})]


def test_mount_collision_raises_at_composition_time():
    router = ToolRouter()
    router.mount(_FakePlugin("echo"))
    with pytest.raises(ValueError, match="collision"):
        router.mount(_FakePlugin("echo"))


def test_catalog_is_capped(caplog):
    router = ToolRouter()
    names = tuple(f"tool_{i:02d}" for i in range(MAX_TOOLS + 3))
    router.mount(_FakePlugin(*names))
    with caplog.at_level("WARNING"):
        merged = router.descriptors()
    assert len(merged) == MAX_TOOLS
    assert any("cap" in r.message for r in caplog.records)
