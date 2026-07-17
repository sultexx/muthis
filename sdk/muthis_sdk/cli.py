# sdk/muthis_sdk/cli.py
"""
The `muthis` developer CLI (console script installed by muthis-sdk).

Phase 0 ships exactly the roadmap §8.7 step-3 command:

    muthis plugin test <plugin-dir>

Exit code 0 = registry-admissible (no FAIL; SKIPs allowed and printed
honestly), 1 = at least one FAIL. Output is English (tooling surface);
Arabic appears only as quoted data.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from . import __version__
from .conformance import run_conformance

_STATUS_TAGS = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}


def _cmd_plugin_test(path: str) -> int:
    try:
        report = run_conformance(path)
    except NotADirectoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"muthis-sdk {__version__} — conformance kit")
    print(f"plugin under test: {report.plugin_dir}")
    print("-" * 64)
    for result in report.results:
        print(f"{_STATUS_TAGS[result.status]:6} {result.name:22} {result.detail}")
    print("-" * 64)
    failed = [r for r in report.results if r.status == "FAIL"]
    skipped = [r for r in report.results if r.status == "SKIP"]
    verdict = "ADMISSIBLE" if report.passed else "REJECTED"
    print(f"result: {verdict} — {len(report.results)} checks, "
          f"{len(failed)} failed, {len(skipped)} skipped")
    return 0 if report.passed else 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="muthis", description="Mut'his plugin developer tools (muthis-sdk)")
    parser.add_argument("--version", action="version",
                        version=f"muthis-sdk {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plugin_parser = subparsers.add_parser("plugin", help="plugin developer tools")
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_command", required=True)
    test_parser = plugin_sub.add_parser(
        "test", help="run the conformance kit against a plugin directory")
    test_parser.add_argument(
        "path", nargs="?", default=".",
        help="plugin directory containing muthis-plugin.toml (default: .)")

    args = parser.parse_args(argv)
    if args.command == "plugin" and args.plugin_command == "test":
        return _cmd_plugin_test(args.path)
    parser.error("unknown command")
    return 2  # unreachable; keeps type-checkers honest


if __name__ == "__main__":
    raise SystemExit(main())
