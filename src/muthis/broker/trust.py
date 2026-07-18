# src/muthis/broker/trust.py
"""
The Phase-1 consent flow (decision Q-1.3): pure module execution, no GUI —

    python -m muthis.broker.trust <plugin-dir> [--yes] [--grants-file PATH]
    python -m muthis.broker.trust --revoke <name> [--grants-file PATH]

Shows the manifest identity (name/version/kind), its Arabic description
(quoted data), the manifest sha256 pin, and the REQUESTED capabilities,
then asks for an explicit y/N before writing the grant. `--yes` is for
scripted/diag use. English tooling surface; exit 0 granted / 1 refused
or invalid / 2 usage. The polished install/consent UI is Phase 4.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from muthis_sdk import ManifestError, load_manifest

from .grants import GrantsStore, manifest_sha256


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m muthis.broker.trust",
        description="Grant (or revoke) a plugin's capability consent — hash-pinned.")
    parser.add_argument("plugin_dir", nargs="?",
                        help="directory containing muthis-plugin.toml")
    parser.add_argument("--yes", action="store_true",
                        help="grant without the interactive prompt")
    parser.add_argument("--revoke", metavar="NAME",
                        help="revoke an existing grant by plugin name")
    parser.add_argument("--grants-file", default=None,
                        help="override the grants.json location (tests/diags)")
    args = parser.parse_args(argv)

    store = GrantsStore(grants_file=args.grants_file)

    if args.revoke:
        if store.revoke(args.revoke):
            print(f"revoked: {args.revoke}")
            return 0
        print(f"no grant found for: {args.revoke}", file=sys.stderr)
        return 1

    if not args.plugin_dir:
        parser.error("plugin_dir is required unless --revoke is used")
    plugin_dir = Path(args.plugin_dir)
    try:
        manifest = load_manifest(plugin_dir)
    except ManifestError as exc:
        print(f"invalid manifest: {exc}", file=sys.stderr)
        return 1
    digest = manifest_sha256(plugin_dir)
    if digest is None:
        print("cannot read/hash the manifest file", file=sys.stderr)
        return 1

    requested = sorted(set(manifest.capabilities_required)
                       | set(manifest.capabilities_optional))
    print(f"plugin   : {manifest.name} {manifest.version} (kind={manifest.kind})")
    print(f"about    : «{manifest.description_ar}»")
    print(f"manifest : sha256 {digest}")
    print(f"requests : {requested if requested else '(no capabilities)'}")
    print("NOTE: the grant dies automatically if the manifest changes (re-consent).")

    if not args.yes:
        answer = input("grant these capabilities? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("refused — nothing written.")
            return 1

    if not store.grant(manifest, plugin_dir):
        print("grant refused (see log).", file=sys.stderr)
        return 1
    print(f"granted — recorded in {store.grants_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
