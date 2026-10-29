# src/muthis/instructions/render.py
"""
render.py — the registry's renderer. PURE: the registry and the sent-image size
in, the prompt out. It reads one data file and logs nothing.

THE CUT IS DEC-139's. Every heading and every bullet line of today's prompt is
ONE entry, 106 in all, and each entry's `after` holds the exact bytes up to the
next one: a newline, a blank line, the triple newline before the navigator
laws, and the EMPTY separator that today joins the last navigator bullet to the
code laws' heading (`persona_laws_navigator.py` ends without a newline). Every
byte of the prompt is therefore an entry's text or a separator, so a later
merge or deletion is one row.

ONE ENTRY IS A TEMPLATE. C011 carries the sent-image size, which the
composition root computes once per session (`persona.py:140-149`); it is the
only entry whose rendered length depends on the screen.
"""

from __future__ import annotations

import json
import pathlib

REGISTRY = pathlib.Path(__file__).with_name("registry.json")
MANIFEST = pathlib.Path(__file__).with_name("manifest.json")


def load(path: pathlib.Path = REGISTRY) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def entry_text(entry: dict, width: int, height: int) -> str:
    text = entry["text"]
    if entry.get("template"):
        text = text.replace("{width}", str(width)).replace("{height}", str(height))
    return text


def render(registry: dict, width: int, height: int) -> str:
    return "".join(entry_text(e, width, height) + e["after"] for e in registry["entries"])


def slots(registry: dict, width: int, height: int) -> dict[str, tuple[int, int]]:
    """Each entry's (start, end) in `render(registry, width, height)`: where
    a guard reads its own text, by slot and never by a fixed offset."""
    spans, at = {}, 0
    for entry in registry["entries"]:
        end = at + len(entry_text(entry, width, height))
        spans[entry["id"]] = (at, end)
        at = end + len(entry["after"])
    return spans
