# src/muthis/broker/broker.py
"""
Broker — turns a plugin's GRANT into a capability-gated PluginContext
(roadmap §3.3: "external plugin code never holds an OS handle — it asks
the kernel").

The rule table for each capability seam:
  granted + kernel seam wired  → the capability object rides the context
  granted but seam not wired   → absent (the plugin degrades politely)
  not granted / grant invalid  → absent + an English log line
The plugin-facing surface is ALWAYS the same PluginContext type — denial
is an absent attribute, never a different API, so a plugin written against
the SDK contract cannot tell a missing grant from a missing feature and
must handle both with the same polite Arabic note.

The four CORE native plugins do NOT pass through here: they are the
kernel's own signed tools, wired directly in build_core_router. The broker
gates EXTERNAL plugins (MCP, Phase-1+) exclusively.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from muthis_sdk import (
    FilesCapability,
    NetCapability,
    PluginContext,
    PluginManifest,
    ScreenCapability,
)

from ..file_reader import ReadFileFn
from .grants import GrantsStore, manifest_sha256

logger = logging.getLogger("muthis.broker")

# The Arabic surface an ungranted profile/bridge request receives (M1-6
# services it; defined HERE because refusal wording is the broker's ruling).
CAPABILITY_NOT_GRANTED_AR = "هذه المقدرة غير ممنوحة لهذه الإضافة."


class Broker:
    """One per app, composed at the root with the kernel's OWN gated seams.
    Stateless per call; owns no lifecycle (Law 11 — it only answers)."""

    def __init__(
        self,
        *,
        grants: GrantsStore,
        read_file: Optional[ReadFileFn] = None,
        capture=None,  # async () -> Optional[bytes]; the kernel capture line
        net_fetch=None,  # async (url: str) -> FetchResult; HardenedFetcher's ONE verb
    ) -> None:
        self._grants = grants
        self._read_file = read_file
        self._capture = capture
        self._net_fetch = net_fetch

    def has_grant(self, manifest: PluginManifest, plugin_dir: str | Path) -> bool:
        """True iff a HASH-CURRENT consent record exists — distinct from
        granted() == frozenset(), which a zero-capability plugin also gets."""
        current = manifest_sha256(plugin_dir)
        return self._grants.granted_capabilities(manifest.name, current) is not None

    def granted(self, manifest: PluginManifest, plugin_dir: str | Path) -> frozenset[str]:
        """The plugin's LIVE capability set: consented AND hash-current."""
        current = manifest_sha256(plugin_dir)
        granted = self._grants.granted_capabilities(manifest.name, current)
        if granted is None:
            logger.warning("[broker] %s has no valid grant — all capabilities "
                           "denied (trust flow: python -m muthis.broker.trust %s)",
                           manifest.name, plugin_dir)
            return frozenset()
        return granted

    def context_for(self, manifest: PluginManifest, plugin_dir: str | Path) -> PluginContext:
        """Build the gated context — the ONLY door to kernel capabilities."""
        granted = self.granted(manifest, plugin_dir)
        files = None
        if "perceive.files.read" in granted and self._read_file is not None:
            # The seam IS FileReader().read — every secret-name/binary/size
            # gate fires inside the kernel; nothing is re-implemented here.
            files = FilesCapability(read=self._read_file)
        screen = None
        if "perceive.screen" in granted and self._capture is not None:
            screen = ScreenCapability(capture=self._capture)
        net = None
        if "net.fetch" in granted and self._net_fetch is not None:
            # The seam IS HardenedFetcher.fetch_readable — every DEC-17 defense
            # (resolve-once IP pinning, per-hop re-validation, robots, the
            # size/type caps, the DEC-22 total budget) fires inside the broker;
            # the plugin gets readable content, never a socket, and nothing here
            # is re-implemented (the FilesCapability discipline, applied to net).
            net = NetCapability(fetch_readable=self._net_fetch)
        denied = granted - {
            c for c, wired in (
                ("perceive.files.read", files is not None),
                ("perceive.screen", screen is not None),
                ("net.fetch", net is not None),
            ) if wired
        } - {"annotate.overlay", "speak.caption", "sandbox.execute",
             "cache.session"}
        if denied:
            logger.info("[broker] %s granted-but-unwired capabilities: %s "
                        "(their seams arrive in later phases)",
                        manifest.name, sorted(denied))
        # DEC-24(b): `net.fetch` LEFT the granted-but-unwired subtraction set
        # with this commit. While it sat there, a plugin GRANTED net.fetch and
        # one DENIED it saw the same absent seam and the same silence — the
        # undefined THIRD state M1-4 forbids ("denial = an ABSENT seam, never a
        # different API" presumes the grant, when wired, PRODUCES the seam). The
        # contract is now binary: granted+wired → present, denied → absent; and
        # a root that forgot to build the fetcher is no longer swallowed — it
        # surfaces on the granted-but-unwired line above.
        return PluginContext(files=files, screen=screen, net=net)


__all__ = ["Broker", "CAPABILITY_NOT_GRANTED_AR"]
