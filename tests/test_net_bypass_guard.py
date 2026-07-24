# tests/test_net_bypass_guard.py
"""
DEC-21-E — the trafilatura / urllib3 BYPASS guard. A STRUCTURAL boundary, not a
behavioural test.

trafilatura ships its OWN urllib3 and exposes network entry points
(fetch_url / fetch_response / buffered_downloads / ...). A single call to any of
them BYPASSES the entire DEC-17 hardened fetcher — no IP pinning, no SSRF
re-validation, no robots, no 2 MB / redirect caps, no clean logging, no total
budget. Per DEC-13, "it stays dormant because we only feed it HTML" is
CIRCUMSTANTIAL, not structural; this guard makes the bypass FORBIDDEN BY
CONSTRUCTION.

It is an ALLOW-LIST, not a deny-list — the closed-capability-enum shape (§1.1),
and the same reason DEC-17 rejected string matching for IP validation:
enumerating known-bad is fragile. A deny-list of today's network symbols would
pass a FUTURE trafilatura entry point (`fetch_v2`, anything) SILENTLY — green
while empty. So we PERMIT the one extraction symbol in the one module and forbid
everything else; an unknown future symbol is caught with zero maintenance.

THE INVARIANT (primary, allow-list):
  1. Across ALL of src/, `trafilatura` may be imported in EXACTLY ONE module —
     broker/net/extract.py — and used through ONLY the extraction symbol(s)
     genuinely required. Any other importing module, and any extra symbol, fails.
  2. Across ALL of src/, NO module imports `urllib3` directly. (trafilatura's own
     internal urllib3 use is the LIBRARY's internals — out of scope; this targets
     OUR source.)
The known network surface is asserted SEPARATELY (secondary/documentary) so the
test reads self-explanatory — but the allow-list above is what catches the
unknown future symbol.

AST scan (the test_pointer_look_only.py precedent), inspecting Import / ImportFrom
/ Attribute nodes only — so docstrings, comments, and this brief's own wording
never false-positive. httpx is out of scope entirely (the allow-list targets
trafilatura + urllib3), so the hardened fetcher's legitimate httpx use — and
T3b's provider client, also httpx — is never caught.

KNOWN LIMITS (recorded, both accepted — the same limits test_pointer_look_only.py
carries, and for the same reason):
  * A DYNAMIC import — importlib.import_module("trafilatura"), __import__, a
    getattr() on a string-built name — is invisible to a static AST scan and
    would not be caught.
  * The scan covers src/ ONLY; scripts/ (the live-SOP diag scripts) is not
    scanned.
Both are acceptable because the THREAT MODEL here is ACCIDENTAL bypass — a
developer reaching for the nearest function that fetches a URL — not an
adversarial insider deliberately hiding a dynamic import. A guard against that
adversary would have to be a runtime import hook, which buys nothing against a
contributor who can already edit the fetcher itself.

Run:  set PYTHONPATH=src && python -m pytest tests/test_net_bypass_guard.py -q
"""

from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

# The ONE module permitted to touch trafilatura, and the ONLY symbol it needs.
ALLOWED_MODULE = ("muthis", "broker", "net", "extract")  # src/muthis/broker/net/extract.py
ALLOWED_TRAFILATURA_SYMBOLS = frozenset({"extract"})

# SECONDARY / documentary: the network surface verified live in T3a (trafilatura
# 2.1.0 top level + `trafilatura.downloads`). The allow-list already forbids each
# of these AND any unknown sibling; naming them just makes the guard legible.
KNOWN_NETWORK_SYMBOLS = frozenset({
    "fetch_url", "fetch_response", "buffered_downloads",
    "buffered_response_downloads", "load_download_buffer", "downloads",
})


def _src_files():
    files = sorted(SRC.rglob("*.py"))
    assert files, f"no sources found under {SRC}"
    return files


def _rel_parts(path):
    return path.relative_to(SRC).with_suffix("").parts


def _trafilatura_use(tree):
    """(imported, symbols) for one module. `imported` is True if trafilatura is
    imported in ANY form — a bare `import trafilatura` is already a latent bypass
    even when unused. `symbols` is every trafilatura symbol REFERENCED:
      * each name in `from trafilatura[.sub] import A, B`      -> {A, B}
      * the submodule in `import trafilatura.sub` / `from trafilatura.sub ...` -> {sub}
      * each attribute `t.attr` on a name bound by `import trafilatura [as t]`  -> {attr}
    """
    imported = False
    module_names: set[str] = set()  # local names bound to the trafilatura package
    symbols: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] != "trafilatura":
                    continue
                imported = True
                module_names.add(alias.asname or "trafilatura")
                if len(parts) > 1:  # import trafilatura.downloads -> a submodule reference
                    symbols.add(parts[1])
        elif isinstance(node, ast.ImportFrom):
            if not node.module or node.module.split(".")[0] != "trafilatura":
                continue
            imported = True
            mod_parts = node.module.split(".")
            if len(mod_parts) > 1:  # from trafilatura.downloads import ...
                symbols.add(mod_parts[1])
            for alias in node.names:
                symbols.add(alias.name)
    for node in ast.walk(tree):  # attribute access on a bound module name
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in module_names:
                symbols.add(node.attr)
    return imported, symbols


def _imports_urllib3(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] == "urllib3" for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "urllib3":
                return True  # NB: stdlib `urllib` (urllib.parse/...) is a different root
    return False


def test_trafilatura_is_confined_to_extract_py_with_only_the_extract_symbol():
    """PRIMARY (allow-list): only extract.py may import trafilatura, and only via
    `extract`. Catches a bypass in a NEW module AND an unknown FUTURE symbol — the
    two failures a deny-list of today's network names would miss."""
    offenders = []
    for path in _src_files():
        imported, symbols = _trafilatura_use(ast.parse(path.read_text(encoding="utf-8")))
        if not imported and not symbols:
            continue
        parts = _rel_parts(path)
        if parts != ALLOWED_MODULE:
            offenders.append(f"{'/'.join(parts)} imports/uses trafilatura {sorted(symbols)}")
        elif not symbols <= ALLOWED_TRAFILATURA_SYMBOLS:
            extra = sorted(symbols - ALLOWED_TRAFILATURA_SYMBOLS)
            offenders.append(f"extract.py uses non-extraction trafilatura symbol(s): {extra}")
    assert not offenders, "hardened-fetcher bypass via trafilatura -> " + "; ".join(offenders)


def test_no_source_module_imports_urllib3_directly():
    """PRIMARY: our source never imports urllib3 (which would visit the internet
    off the pinned client). trafilatura's own internal urllib3 use is the library's
    internals, out of scope — this scans OUR modules only."""
    offenders = [
        "/".join(_rel_parts(p)) for p in _src_files()
        if _imports_urllib3(ast.parse(p.read_text(encoding="utf-8")))
    ]
    assert not offenders, f"direct urllib3 import (bypasses the pinned client): {offenders}"


def test_extract_py_touches_no_known_network_entry_point():
    """SECONDARY / documentary: the allow-list above already forbids these, but
    naming the KNOWN network surface pins what T3a verified live and keeps the
    guard self-explanatory."""
    extract_py = SRC.joinpath(*ALLOWED_MODULE).with_suffix(".py")
    _, symbols = _trafilatura_use(ast.parse(extract_py.read_text(encoding="utf-8")))
    hit = sorted(symbols & KNOWN_NETWORK_SYMBOLS)
    assert not hit, f"extract.py touches a known trafilatura network entry point: {hit}"
