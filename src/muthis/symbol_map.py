# src/muthis/symbol_map.py
"""
The SYMBOL MAP — names and line spans for a Python file, attached ON TRUNCATION
ONLY (DEC-113, Phase 4A).

WHAT IT IS FOR. `read_local_file` delivers ~242 effective lines where the
architecture permits 300 (DEC-112), so EIGHT OF THE TEN PINNED FILES cannot be
read whole: the tail is simply absent, and the delivered text says only THAT it
was cut, never WHAT was lost. Measured on that exact condition a map took the
model from 3/9 to 9/9 on structural questions and its grounding from 0/6 to 6/6.

AND IT IS ATTACHED NOWHERE ELSE, WHICH IS THE RULING. On WHOLE files the same
map TIED — four of five fixtures at 35/36 against 35/36 — and one fixture got
WORSE (3/3 → 2/3, a row's start read against the wrong row's end), because a
TABLE CAN BE MISREAD where raw text has no such failure mode. Attaching it always
would spend tokens to buy a tie and import a new way to be wrong. So this is a
TRUNCATION COMPENSATOR, not a retrieval index.

THAT RULING IS ENFORCED STRUCTURALLY, NOT BY A CHECK. The one caller builds this
inside the branch that has ALREADY decided to truncate; there is no
`if whole_file: skip` to delete, because no code path runs from a whole file to
here. A check can be removed by someone who thinks it redundant — a missing path
cannot.

NOT A PARSER. `ast` is stdlib and already ships. This module chooses WHAT to show
and REFUSES when it cannot parse.

IT REFUSES SILENTLY, AND THAT IS LOAD-BEARING. A file mid-edit is routinely
unparseable — an unclosed paren between keystrokes is the ordinary state of a
file someone is working in, which is exactly when they ask about it. A map is an
AID, so when the parse fails the reader must return precisely what it returns
today: never raise, never explain, just stop helping.

THE MAP IS APPENDED AFTER THE 16,000-CHAR CAP, SO THE PAYLOAD GROWS — it does not
displace code lines. That is a DECISION POINT, not a free lunch: it was measured
at 244 chars on `turn_pass.py`, and the model is charged for every one of them.
The trade is deliberate — those bytes buy the SHAPE OF WHAT IT CANNOT SEE, which
is the one thing the truncated text can never carry. `MAX_MAP_CHARS` bounds the
growth, because a reader that bounds its own size twice must not then append
something unbounded (a 2 MB file of one-line defs is inside `MAX_FILE_BYTES`).
"""

from __future__ import annotations

import ast
from typing import Optional

MAP_HEADER_AR = "خريطة رموز الملف كامل (الأسطر المذكورة تشمل ما لم يُعرض):"
MAP_CUT_AR = "  … (بقية الخريطة مقصوصة)"

# The appended map is payload GROWTH, so it carries its own ceiling.
MAX_MAP_CHARS = 4_000


def _rows(tree: ast.Module) -> tuple[list[str], list[str]]:
    """Top-level shape only: classes with their methods, functions, CONSTANTS.

    Deliberately NOT recursive past one level — the map exists to tell the model
    WHERE to ask next, and a nested closure is not a place it can ask for."""
    rows: list[str] = []
    consts: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            rows.append(f"  class    {node.name} {node.lineno}-{node.end_lineno or node.lineno}")
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    rows.append(f"    method {sub.name} {sub.lineno}-{sub.end_lineno or sub.lineno}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            rows.append(f"  def      {node.name} {node.lineno}-{node.end_lineno or node.lineno}")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(target, ast.Name) and target.id.isupper():
                consts.append(target.id)
    return rows, consts


def build_symbol_map(text: str) -> Optional[str]:
    """Names and line spans for the WHOLE file, or None when it cannot parse.

    None is also the answer for a file with no symbols at all: a header over an
    empty list is pure cost, and the reader must add nothing it cannot use."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return None
    rows, consts = _rows(tree)
    if not rows and not consts:
        return None
    if consts:
        rows.append(f"  constants: {', '.join(consts)}")
    body = "\n".join(rows)
    if len(body) > MAX_MAP_CHARS:
        body = body[:MAX_MAP_CHARS].rsplit("\n", 1)[0] + "\n" + MAP_CUT_AR
    return f"{MAP_HEADER_AR}\n{body}"


__all__ = ["build_symbol_map", "MAP_HEADER_AR", "MAP_CUT_AR", "MAX_MAP_CHARS"]
