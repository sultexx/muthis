# sdk/muthis_sdk/manifest.py
"""
muthis-plugin.toml loader + validator (V2_ROADMAP.md §3.2).

Stdlib-only (tomllib, py>=3.11). Validation errors raise ManifestError with
English messages — the manifest is a developer surface (logs/tooling), not a
user surface; the ARABIC-description requirement is itself part of the contract
(Arabic is the reference language — V2_ROADMAP part 1 §3.7) and is checked here
as presence + non-emptiness (script-level linting is the conformance kit's job).

Capability names are validated against the CLOSED enum (types.CAPABILITIES):
an unknown capability — including any input.* — is rejected at LOAD time,
which is the golden rule §1.1 working before any broker exists.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .types import CAPABILITIES

MANIFEST_FILENAME = "muthis-plugin.toml"

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([abc-]|rc|\.|$)")
_KINDS = ("native", "mcp")


class ManifestError(ValueError):
    """A structurally invalid muthis-plugin.toml."""


@dataclass(frozen=True)
class ToolEntry:
    """One [tools.<name>] table."""

    name: str
    read_only: bool = True


@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str
    sdk: str
    kind: str
    description_ar: str
    description_en: str = ""
    entry: str = ""
    # kind=mcp only (roadmap §8.2): eager session at mount instead of the
    # lazy default (catalog fetched then the pipe closed until first need).
    warm: bool = False
    capabilities_required: tuple[str, ...] = ()
    capabilities_optional: tuple[str, ...] = ()
    tools: tuple[ToolEntry, ...] = field(default_factory=tuple)


def _require(table: dict[str, Any], key: str, section: str) -> Any:
    if key not in table:
        raise ManifestError(f"[{section}] is missing required key {key!r}")
    return table[key]


def _check_capabilities(names: list[Any], where: str) -> tuple[str, ...]:
    out: list[str] = []
    for name in names:
        if not isinstance(name, str) or name not in CAPABILITIES:
            # The closed-enum refusal: input.mouse etc. land here by design.
            raise ManifestError(
                f"unknown capability {name!r} in {where} — the enum is closed "
                f"(V2 golden rule): {sorted(CAPABILITIES)}"
            )
        out.append(name)
    return tuple(out)


def parse_manifest(data: dict[str, Any], *, source: str = MANIFEST_FILENAME) -> PluginManifest:
    """Validate an already-decoded TOML dict into a PluginManifest."""
    plugin = data.get("plugin")
    if not isinstance(plugin, dict):
        raise ManifestError(f"{source}: missing [plugin] table")

    name = _require(plugin, "name", "plugin")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ManifestError(f"plugin name {name!r} must match {_NAME_RE.pattern}")

    version = _require(plugin, "version", "plugin")
    if not isinstance(version, str) or not _VERSION_RE.match(version):
        raise ManifestError(f"plugin version {version!r} is not semver-like")

    sdk = _require(plugin, "sdk", "plugin")
    if not isinstance(sdk, str) or not sdk.strip():
        raise ManifestError("plugin sdk requirement must be a non-empty string")

    kind = _require(plugin, "kind", "plugin")
    if kind not in _KINDS:
        raise ManifestError(f"plugin kind {kind!r} must be one of {_KINDS}")

    entry = plugin.get("entry", "")
    if not isinstance(entry, str):
        raise ManifestError("plugin entry must be a string")

    warm = plugin.get("warm", False)
    if not isinstance(warm, bool):
        raise ManifestError("plugin warm must be a boolean")

    descriptions = data.get("descriptions")
    if not isinstance(descriptions, dict) or not str(descriptions.get("ar", "")).strip():
        # Arabic is the reference language (V2_ROADMAP part 1 §3.7) — a
        # manifest without an Arabic description is invalid, full stop.
        raise ManifestError(f"{source}: [descriptions] must carry a non-empty 'ar'")
    description_ar = str(descriptions["ar"]).strip()
    description_en = str(descriptions.get("en", "")).strip()

    caps = data.get("capabilities", {})
    if not isinstance(caps, dict):
        raise ManifestError("[capabilities] must be a table")
    required = _check_capabilities(list(caps.get("required", [])), "capabilities.required")
    optional = _check_capabilities(list(caps.get("optional", [])), "capabilities.optional")

    tools_table = data.get("tools", {})
    if not isinstance(tools_table, dict) or not tools_table:
        raise ManifestError(f"{source}: at least one [tools.<name>] table is required")
    tools: list[ToolEntry] = []
    for tool_name, entry_table in tools_table.items():
        if not _NAME_RE.match(tool_name):
            raise ManifestError(f"tool name {tool_name!r} must match {_NAME_RE.pattern}")
        if not isinstance(entry_table, dict):
            raise ManifestError(f"[tools.{tool_name}] must be a table")
        read_only = entry_table.get("read_only", True)
        if not isinstance(read_only, bool):
            raise ManifestError(f"[tools.{tool_name}] read_only must be a boolean")
        tools.append(ToolEntry(name=tool_name, read_only=read_only))

    return PluginManifest(
        name=name,
        version=version,
        sdk=sdk,
        kind=kind,
        description_ar=description_ar,
        description_en=description_en,
        entry=entry,
        warm=warm,
        capabilities_required=required,
        capabilities_optional=optional,
        tools=tuple(tools),
    )


def load_manifest(plugin_dir: str | Path) -> PluginManifest:
    """Load and validate <plugin_dir>/muthis-plugin.toml."""
    path = Path(plugin_dir) / MANIFEST_FILENAME
    if not path.is_file():
        raise ManifestError(f"no {MANIFEST_FILENAME} found in {plugin_dir}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"{path}: invalid TOML — {exc}") from exc
    return parse_manifest(data, source=str(path))
