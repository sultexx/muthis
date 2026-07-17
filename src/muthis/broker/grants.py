# src/muthis/broker/grants.py
"""
GrantsStore — the consent ledger (roadmap §3.3: install-time consent +
privilege diff on update + hash pinning).

A grant records: the plugin name, the sha256 of its muthis-plugin.toml
BYTES, and the capability set the user approved. Lookup requires BOTH the
name and the CURRENT manifest hash — a changed manifest (new version, new
capabilities, anything) silently invalidates the grant, forcing re-consent
through the trust flow. That is the whole update-diff rule, enforced by
construction rather than by comparison UI.

File discipline mirrors kernel/budget.py exactly: grants.json in the
process cwd (gitignored), atomic tmp+replace saves, corrupt/missing file
degrades to "no grants" with an English warning — the app never crashes
over a consent ledger, it just refuses politely until re-trusted.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from muthis_sdk import CAPABILITIES, PluginManifest

logger = logging.getLogger("muthis.broker.grants")

DEFAULT_GRANTS_FILENAME = "grants.json"
MANIFEST_FILENAME = "muthis-plugin.toml"


def manifest_sha256(plugin_dir: str | Path) -> Optional[str]:
    """The pin: sha256 over the manifest FILE BYTES (not a parse — byte
    identity is the tamper/update detector). None when unreadable."""
    path = Path(plugin_dir) / MANIFEST_FILENAME
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as e:
        logger.warning("[grants] cannot hash %s: %s", path, e)
        return None


class GrantsStore:
    """One per app. Synchronous, never raises on IO (budget.py contract)."""

    def __init__(self, grants_file: Optional[os.PathLike | str] = None) -> None:
        self.grants_file = (
            Path(grants_file) if grants_file is not None
            else Path.cwd() / DEFAULT_GRANTS_FILENAME
        )
        self._records: dict[str, dict[str, Any]] = self._load()

    # ─────────────────────────── Public API ───────────────────────────

    def grant(self, manifest: PluginManifest, plugin_dir: str | Path) -> bool:
        """Record consent for the manifest AS IT IS ON DISK right now.
        Unknown capabilities can't get here (manifest load already refused
        them — the closed enum), but re-check defensively: consent must
        never outrun the constitution."""
        requested = set(manifest.capabilities_required) | set(manifest.capabilities_optional)
        illegal = requested - CAPABILITIES
        if illegal:
            logger.error("[grants] refusing grant for %s — capabilities outside "
                         "the closed enum: %s", manifest.name, sorted(illegal))
            return False
        digest = manifest_sha256(plugin_dir)
        if digest is None:
            return False
        self._records[manifest.name] = {
            "manifest_sha256": digest,
            "capabilities": sorted(requested),
            "granted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._save()
        logger.info("[grants] granted %s (%s): %s",
                    manifest.name, digest[:12], sorted(requested))
        return True

    def revoke(self, name: str) -> bool:
        if name not in self._records:
            return False
        del self._records[name]
        self._save()
        logger.info("[grants] revoked %s", name)
        return True

    def granted_capabilities(
        self, name: str, current_manifest_sha256: Optional[str]
    ) -> Optional[frozenset[str]]:
        """The consented capability set — or None when there is no grant OR
        the manifest hash changed since consent (the update-diff rule)."""
        record = self._records.get(name)
        if record is None or current_manifest_sha256 is None:
            return None
        if record.get("manifest_sha256") != current_manifest_sha256:
            logger.warning(
                "[grants] %s manifest changed since consent — grant invalidated, "
                "re-run: python -m muthis.broker.trust", name)
            return None
        return frozenset(record.get("capabilities", []))

    # ───────────────────────── Persistence ─────────────────────────

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            raw = self.grants_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as e:
            logger.warning("[grants] cannot read %s: %s — treating as empty",
                           self.grants_file, e)
            return {}
        try:
            data = json.loads(raw)
            records = data.get("plugins") if isinstance(data, dict) else None
            if not isinstance(records, dict):
                raise ValueError("grants root must be {'plugins': {...}}")
            return {k: v for k, v in records.items() if isinstance(v, dict)}
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("[grants] corrupt grants file %s (%s) — no plugin is "
                           "trusted until re-granted", self.grants_file, e)
            return {}

    def _save(self) -> None:
        tmp = self.grants_file.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps({"plugins": self._records}, indent=2,
                                      sort_keys=True, ensure_ascii=False),
                           encoding="utf-8")
            os.replace(tmp, self.grants_file)
        except OSError as e:
            logger.warning("[grants] failed to persist %s: %s", self.grants_file, e)


__all__ = ["DEFAULT_GRANTS_FILENAME", "GrantsStore", "manifest_sha256"]
