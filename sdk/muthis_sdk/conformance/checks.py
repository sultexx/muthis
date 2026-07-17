# sdk/muthis_sdk/conformance/checks.py
"""
The individual conformance checks. Each takes what it needs and returns a
(status, detail) tuple — statuses are "PASS" / "FAIL" / "SKIP". English
output (developer tooling surface); Arabic appears only as quoted DATA.
"""

from __future__ import annotations

import importlib
import re
import time
from typing import Any, Optional

from ..context import FilesCapability, PluginContext
from ..manifest import PluginManifest
from ..plugin import ToolPlugin
from ..types import ToolDescriptor, ToolResult

_ARABIC_RE = re.compile(r"[؀-ۿ]")
_MIN_AR_DESCRIPTION = 10          # chars — a real sentence, not a placeholder
LATENCY_WARN_MS = 1000.0          # golden-run per-call soft budget (Phase 0: warn)


def check_entry_class(manifest: PluginManifest) -> tuple[str, str, Optional[ToolPlugin]]:
    """Import manifest.entry ("module:Class") and instantiate it."""
    if manifest.kind != "native":
        return "SKIP", ("kind=mcp: the runtime suite covers out-of-proc serving; "
                        "kit-driven child spawning arrives in Phase 2"), None
    if ":" not in manifest.entry:
        return "FAIL", f"entry {manifest.entry!r} is not 'module:Class'", None
    module_name, _, class_name = manifest.entry.partition(":")
    try:
        module = importlib.import_module(module_name)
        plugin_cls = getattr(module, class_name)
    except Exception as exc:  # noqa: BLE001 — report, never crash the kit
        return "FAIL", f"cannot import {manifest.entry!r}: {exc}", None
    if not (isinstance(plugin_cls, type) and issubclass(plugin_cls, ToolPlugin)):
        return "FAIL", f"{class_name} is not a ToolPlugin subclass", None
    try:
        return "PASS", f"{manifest.entry} instantiates", plugin_cls()
    except Exception as exc:  # noqa: BLE001
        return "FAIL", f"{class_name}() raised at construction: {exc}", None


def check_descriptors(plugin: ToolPlugin) -> tuple[str, str, list[ToolDescriptor]]:
    """descriptors(): non-empty, typed, unique, deterministic."""
    try:
        first, second = plugin.descriptors(), plugin.descriptors()
    except Exception as exc:  # noqa: BLE001
        return "FAIL", f"descriptors() raised: {exc}", []
    if not first or not all(isinstance(d, ToolDescriptor) for d in first):
        return "FAIL", "descriptors() must return a non-empty list[ToolDescriptor]", []
    names = [d.name for d in first]
    if len(set(names)) != len(names):
        return "FAIL", f"duplicate tool names: {names}", []
    if names != [d.name for d in second]:
        return "FAIL", "descriptors() is not deterministic across calls", []
    return "PASS", f"{len(first)} descriptor(s): {', '.join(names)}", first


def check_manifest_consistency(
    manifest: PluginManifest, descriptors: list[ToolDescriptor]
) -> tuple[str, str]:
    declared = {t.name for t in manifest.tools}
    offered = {d.name for d in descriptors}
    if declared != offered:
        return "FAIL", f"manifest tools {sorted(declared)} != descriptors {sorted(offered)}"
    return "PASS", "manifest [tools.*] matches the offered descriptors"


def check_schema_structure(descriptors: list[ToolDescriptor]) -> tuple[str, str]:
    """The model-visible dict: name/description/input_schema shaped correctly."""
    for d in descriptors:
        s = d.schema
        if s.get("name") != d.name:
            return "FAIL", f"{d.name}: schema['name'] is {s.get('name')!r}"
        if not isinstance(s.get("description"), str) or not s["description"].strip():
            return "FAIL", f"{d.name}: schema description missing/empty"
        input_schema = s.get("input_schema")
        if not isinstance(input_schema, dict) or input_schema.get("type") != "object":
            return "FAIL", f"{d.name}: input_schema must be an object schema"
        properties = input_schema.get("properties", {})
        if not isinstance(properties, dict):
            return "FAIL", f"{d.name}: input_schema.properties must be a dict"
        required = input_schema.get("required", [])
        missing = [k for k in required if k not in properties]
        if missing:
            return "FAIL", f"{d.name}: required keys absent from properties: {missing}"
    return "PASS", "every schema is a well-formed model-visible tool dict"


def check_arabic_description(manifest: PluginManifest) -> tuple[str, str]:
    """Arabic is the reference language (§3.7): real Arabic, real sentence."""
    text = manifest.description_ar
    if not _ARABIC_RE.search(text):
        return "FAIL", "descriptions.ar carries no Arabic script"
    if len(text) < _MIN_AR_DESCRIPTION:
        return "FAIL", f"descriptions.ar too short ({len(text)} chars) — write a real sentence"
    return "PASS", f"Arabic description healthy: «{text[:40]}…»" if len(text) > 40 else f"Arabic description healthy: «{text}»"


async def golden_run(
    plugin: ToolPlugin, descriptors: list[ToolDescriptor]
) -> tuple[str, str]:
    """The fake-kernel golden run: execute() every declared tool against a
    stub context. The contract under test: returns ToolResult, NEVER raises,
    and answers inside the (Phase-0 warn-only) latency budget."""

    async def _fake_read(args: dict[str, Any]) -> str:
        return "سطر تجريبي من نواة العدّة المزيفة"

    ctx = PluginContext(files=FilesCapability(read=_fake_read))
    notes: list[str] = []
    for d in descriptors:
        started = time.perf_counter()
        try:
            result = await plugin.execute(d.name, {}, ctx)
        except Exception as exc:  # noqa: BLE001 — a raising plugin FAILS the kit
            return "FAIL", f"{d.name}: execute() raised ({exc!r}) — plugins must return, never raise"
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if not isinstance(result, ToolResult):
            return "FAIL", f"{d.name}: execute() returned {type(result).__name__}, not ToolResult"
        if not isinstance(result.text_ar, str) or not result.text_ar.strip():
            return "FAIL", f"{d.name}: ToolResult.text_ar is empty"
        slow = " (over soft budget!)" if elapsed_ms > LATENCY_WARN_MS else ""
        notes.append(f"{d.name} {elapsed_ms:.0f}ms{slow}")
    return "PASS", "golden run clean: " + "; ".join(notes)


async def permission_checks(
    plugin: ToolPlugin, descriptors: list[ToolDescriptor], manifest: PluginManifest
) -> tuple[str, str]:
    """The Phase-1 permission-violation suite (the M1-4 activation of the
    Phase-0 SKIP marker). Two refusal contracts, both MUST hold:

    1. STARVED CONTEXT — execute() against a bare PluginContext (every
       capability absent, exactly what the broker hands an ungranted
       plugin) must DEGRADE to a ToolResult, never raise: a plugin that
       crashes when denied is a plugin that cannot be safely refused.
    2. UNDECLARED USE — execute() against an INSTRUMENTED context (every
       seam present, each access recorded) must touch only capabilities
       the manifest declares (required or optional): silent capability
       use is a permission violation even when the seam happens to exist.
    """
    from ..context import FilesCapability, ScreenCapability

    declared = set(manifest.capabilities_required) | set(manifest.capabilities_optional)

    # 1) The starved run — the broker's denial posture.
    for d in descriptors:
        try:
            result = await plugin.execute(d.name, {}, PluginContext())
        except Exception as exc:  # noqa: BLE001
            return "FAIL", (f"{d.name}: raised on a capability-starved context "
                            f"({exc!r}) — denial must degrade, never crash")
        if not isinstance(result, ToolResult):
            return "FAIL", f"{d.name}: starved run returned {type(result).__name__}"

    # 2) The instrumented run — silent capability use is a violation.
    accessed: set[str] = set()

    async def _spy_read(args: dict[str, Any]) -> str:
        accessed.add("perceive.files.read")
        return "سطر تجريبي"

    async def _spy_capture() -> Optional[bytes]:
        accessed.add("perceive.screen")
        return b"\x89PNG"

    spy_ctx = PluginContext(files=FilesCapability(read=_spy_read),
                            screen=ScreenCapability(capture=_spy_capture))
    for d in descriptors:
        try:
            await plugin.execute(d.name, {}, spy_ctx)
        except Exception as exc:  # noqa: BLE001
            return "FAIL", f"{d.name}: raised on the instrumented context ({exc!r})"
    undeclared = accessed - declared
    if undeclared:
        return "FAIL", (f"capabilities used but not declared in the manifest: "
                        f"{sorted(undeclared)}")
    note = f"used={sorted(accessed)}" if accessed else "no capability touched"
    return "PASS", f"starved-context denial degrades politely; {note}, all declared"
