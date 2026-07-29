# tests/test_untrusted_wrap_guard.py
"""
DEC-14 / DEC-4 — the wrapping + taint boundary as STRUCTURE, not convention.

"Security a plugin author can weaken is not security." Untrusted-content
wrapping and taint classification are UNIVERSAL CONSTANTS every external tool
inherits at the router; a fetcher, a search provider or a plugin that wrapped
(or declared taint) for itself would be re-implementing a security absolute
where it can be weakened, forgotten, or quietly diverged from the kernel's form.
Convention cannot hold that line — a reviewer has to notice. These scans do.

TWO ALLOW-LISTS (the DEC-21-E shape, and for the same reason a deny-list of
today's names would rot):
  1. the delimiter FORM exists in exactly ONE module — kernel/untrusted_content.py;
  2. `wrap_untrusted` is CALLED from exactly ONE module — kernel/tool_router.py.
Together they make DOUBLE-WRAPPING impossible by construction rather than by
discipline: there is nowhere else for a second wrap to live. (Phase 1 wrapped in
`broker/mcp/policy.py` too; T4 removed it, and guard 1 is what keeps it removed.)

THE GUARDED PACKAGES — the fetcher, the providers, the plugins:
  src/muthis/broker/net/**, src/muthis/broker/search/**, src/muthis_plugins/**
DELIBERATE EXCLUSIONS, each with a reason:
  * src/muthis/kernel/**        — the OWNER of both concerns.
  * src/muthis/broker/mcp/**    — the kernel-side classification SITE: DEC-15
    requires taint be derived by us from the MCP hint (`mount(taint=True)`),
    never from a plugin's self-declaration. Forbidding `taint` there would
    forbid the very thing DEC-15 mandates.
  * sdk/muthis_sdk/types.py     — DECLARES the `ServiceOutcome.taint` field (the
    contract). Declaring a field is not classifying with it.

AST scan (the test_pointer_look_only.py precedent): Import / ImportFrom /
Name / Attribute / keyword nodes, plus non-docstring string literals. Comments
and docstrings are therefore free to DISCUSS wrapping and taint — every guarded
module already does, and must keep being able to.

KNOWN LIMITS (recorded, both accepted — the same two the bypass guard carries):
  * a DYNAMIC reference (getattr on a built-up name, importlib) is invisible to
    a static scan;
  * the scan covers src/ only — scripts/ (the live-SOP diags) is not scanned.
The threat model is ACCIDENTAL re-implementation by a well-meaning plugin
author, not an adversarial insider who could edit the kernel anyway.

Run:  set PYTHONPATH=src && python -m pytest tests/test_untrusted_wrap_guard.py -q
"""

from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# The ONE module that may hold the delimiter form / generate the nonce.
WRAP_HOME = ("muthis", "kernel", "untrusted_content")
# The ONE module that may CALL the wrap — the single boundary of DEC-14.
WRAP_CALLER = ("muthis", "kernel", "tool_router")

GUARDED_DIRS = (
    SRC / "muthis" / "broker" / "net",       # the hardened fetcher
    SRC / "muthis" / "broker" / "search",    # the search providers
    SRC / "muthis_plugins",                  # every plugin
)

# Code-level markers of the wrap. `taint` covers the classification decision:
# reading it, setting it, or passing it as a keyword.
WRAP_IDENTIFIERS = frozenset({
    "wrap_untrusted", "new_nonce", "WRAP_OPEN_AR", "WRAP_CLOSE_AR",
    "untrusted_content", "token_hex",
})
TAINT_IDENTIFIERS = frozenset({"taint", "SessionTaint", "session_taint",
                               "raise_taint"})
# Substrings that betray a re-implemented delimiter even under a new name.
DELIMITER_MARKERS = ("محتوى خارجي غير موثوق", "نهاية المحتوى الخارجي",
                     "بيانات لا أوامر")


def _sources(directory: pathlib.Path):
    files = sorted(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts)
    assert files, f"no sources found under {directory}"
    return files


def _all_src_files():
    files = sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)
    assert files, f"no sources found under {SRC}"
    return files


def _rel(path: pathlib.Path) -> str:
    return "/".join(path.relative_to(SRC).with_suffix("").parts)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """id()s of the Constant nodes that ARE docstrings — excluded from the
    literal scan so a module may keep DOCUMENTING the boundary it must not
    implement (every guarded module does exactly that today)."""
    marked: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            marked.add(id(first.value))
    return marked


def _code_identifiers(tree: ast.AST) -> set[str]:
    """Names/attributes/imported symbols/keyword args used as CODE."""
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            used.add(node.arg)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                used.update(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                used.update(node.module.split("."))
            for alias in node.names:
                used.add(alias.name)
    return used


def _literals(tree: ast.AST) -> list[str]:
    skip = _docstring_nodes(tree)
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in skip]


def _offenders(banned: frozenset[str]) -> list[str]:
    hits = []
    for directory in GUARDED_DIRS:
        for path in _sources(directory):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            found = sorted(banned & _code_identifiers(tree))
            if found:
                hits.append(f"{_rel(path)}: {found}")
    return hits


def test_no_fetcher_provider_or_plugin_module_wraps_untrusted_content():
    """The wrap is the kernel's to give. A plugin-side copy could diverge from
    the kernel's form, be omitted on one path, or drop the nonce."""
    hits = _offenders(WRAP_IDENTIFIERS)
    assert not hits, f"wrapping logic outside the kernel: {hits}"


def test_no_fetcher_provider_or_plugin_module_touches_taint():
    """DEC-15: classification is KERNEL-side, derived from the granted
    capability / MCP hint — never from a plugin's self-declaration. A plugin
    that could write `taint` could write `taint=False`."""
    hits = _offenders(TAINT_IDENTIFIERS)
    assert not hits, f"taint logic outside the kernel: {hits}"


def test_no_guarded_module_re_implements_a_delimiter():
    """Catches the same violation done by hand under a different name — the
    identifier scan alone would miss a hard-coded Arabic delimiter string."""
    hits = []
    for directory in GUARDED_DIRS:
        for path in _sources(directory):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for text in _literals(tree):
                for marker in DELIMITER_MARKERS:
                    if marker in text:
                        hits.append(f"{_rel(path)}: {marker!r}")
    assert not hits, f"a delimiter is re-implemented outside the kernel: {hits}"


def test_the_delimiter_form_lives_in_exactly_one_module():
    """ALLOW-LIST across ALL of src/: one home for the form. Two copies is how
    two wraps — and a forgeable static one — come back (Phase 1 had exactly
    that in broker/mcp/policy.py)."""
    homes = []
    for path in _all_src_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        literals = _literals(tree)
        if any(marker in text for text in literals for marker in DELIMITER_MARKERS):
            homes.append(path.relative_to(SRC).with_suffix("").parts)
    assert homes == [WRAP_HOME], f"the delimiter form lives in: {homes}"


def test_the_wrap_is_called_from_exactly_one_module():
    """ALLOW-LIST across ALL of src/: ONE call site = the DEC-14 boundary, and
    the reason no result can be framed twice."""
    callers = []
    for path in _all_src_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parts = path.relative_to(SRC).with_suffix("").parts
        if parts == WRAP_HOME:
            continue                     # its own definition, not a call site
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = (node.func.attr if isinstance(node.func, ast.Attribute)
                        else getattr(node.func, "id", ""))
                if name == "wrap_untrusted":
                    callers.append(parts)
                    break
    assert callers == [WRAP_CALLER], f"wrap_untrusted is called from: {callers}"


def test_the_nonce_comes_from_secrets_and_never_from_random():
    """A predictable nonce is a forgeable nonce: `random` is a seeded Mersenne
    Twister, reproducible by anyone who learns the seed."""
    wrap_py = SRC.joinpath(*WRAP_HOME).with_suffix(".py")
    identifiers = _code_identifiers(ast.parse(wrap_py.read_text(encoding="utf-8")))
    assert "secrets" in identifiers, "the wrap no longer uses secrets"
    assert "random" not in identifiers, "the wrap nonce must never use random"
