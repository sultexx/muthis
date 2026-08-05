# src/muthis/cloud/tool_envelope.py
"""
tool_envelope.py — the tool-catalogue ENVELOPE translation, and the reason it is
a module with a structural guard rather than four lines inside a wrapper.

ONE CONCERN: re-shaping the byte-pinned catalogue's OUTER envelope for a vendor
that spells it differently. The CONTENT — name, description, JSON Schema — is
carried byte-identical. Nothing here reads, rewrites, validates or repairs a
schema, and nothing here is allowed to learn what a tool DOES.

MEASURED, NEVER GUESSED (DEC-88 ①, live 2026-08-05). The real eleven-tool
catalogue sent unmodified is REJECTED — `Missing required parameter:
'tools[0].type'`. The mechanical rename below is accepted whole, and `__` in a
tool name is legal there, so DEC-11's specific defect does not recur.

WHY THIS FILE EXISTS AT ALL, AND IT IS THE SHARPEST FINDING OF THE PROBE.
DEC-11 was a LOUD failure: one dotted tool name returned a live 400 that every
offline test had passed, and the turn STOPPED. **This provider inverts the
direction.** Each of these was measured and each was ACCEPTED with no error:

  · `input_schema` present and `parameters` MISSING — the realistic half-port,
    where someone adds `type` and forgets the rename. The model is then handed a
    tool with NO DECLARED PARAMETERS and nothing says so.
  · `parameters` AND `input_schema` both present — accepted.
  · an outright nonsense key — accepted and ignored.
  · `strict` omitted although the SDK types it Required — accepted.

A capability is lost for the whole process, in silence, with a green suite and a
model that simply never calls the tool correctly again. **A silent failure is
worse than a loud one** — the recurring argument of DEC-11 (a loud 400), DEC-60
(a ledger that lies) and DEC-89 ruling 4 (a confidently misplaced box).

So the envelope is ASSERTED STRUCTURALLY (`tests/test_tool_envelope.py`) instead
of trusted: the key set is compared EXACTLY, so a dropped rename, a leftover
`input_schema`, a stray key and a missing `strict` are all the same kind of
failure — the only shape that catches a half-port, because the API reports none
of them. `VENDOR_ENVELOPE_KEYS` is that contract, declared once HERE and
imported by the guard; a test that re-typed the key set would be checking its
own copy rather than this module.

THE ACCESSES BELOW ARE SUBSCRIPTS, NOT `.get()`, ON PURPOSE. A descriptor that
reaches here without `name`, `description` or `input_schema` is a broken mount,
and a `KeyError` at composition time is the LOUD failure this vendor will not
give us. Defaulting the missing field would re-create the exact silence the
module exists to close.
"""

from __future__ import annotations

from typing import Any

# The EXACT key set of a translated descriptor — exhaustive, because the guard
# compares `set(translated) == VENDOR_ENVELOPE_KEYS` and a MISSING key must fail
# the same way an EXTRA one does. That symmetry is what catches the half-port,
# which simultaneously drops `parameters` and keeps `input_schema`.
VENDOR_ENVELOPE_KEYS = frozenset({"type", "name", "strict", "description", "parameters"})

# The vendor's only tool kind we ever declare. LOOK-only is unaffected by this
# constant: what a tool may DO is decided by the catalogue and the router, never
# by an envelope field.
VENDOR_TOOL_TYPE = "function"

# `strict` is sent FALSE, and that is a decision rather than an SDK default.
# Strict mode makes the VENDOR the authority on which JSON Schema dialect our
# tools may use — but the eleven schemas are BYTE-PINNED
# (`tests/snapshots/look_tools_v6.json`) and are the same objects Anthropic
# receives. The catalogue is pinned first and translated second, never the
# reverse; turning this on would invert that order and make a pinned artifact
# answerable to a vendor's validator.
VENDOR_STRICT = False


def to_vendor_envelope(tool: dict[str, Any]) -> dict[str, Any]:
    """ONE pinned descriptor → ONE vendor descriptor. Envelope only.

    THE RENAME IS THE WHOLE TRANSLATION: `input_schema` → `parameters`, plus
    `type` and `strict`. Name and description are carried through untouched, so
    whatever the API says about this catalogue is a statement about OUR
    catalogue and not about the transform.

    The schema is carried BY REFERENCE — never copied and never edited. It is
    one of the byte-pinned dicts `router.descriptors()` hands back by identity
    (asserted in DEC-59 Q3), and `cache_control.py` keeps its copy discipline
    precisely because writing into one mutates the model-visible catalogue for
    the entire process. Nothing here writes, so nothing here copies; the guard
    asserts the source dict is unchanged after a translation.
    """
    return {
        "type": VENDOR_TOOL_TYPE,
        "name": tool["name"],
        "strict": VENDOR_STRICT,
        "description": tool["description"],
        "parameters": tool["input_schema"],
    }


def to_vendor_catalogue(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The whole catalogue, IN ORDER — the order is itself pinned (v6 is v4 with
    two tools appended), so preserving it keeps the snapshot meaningful."""
    return [to_vendor_envelope(tool) for tool in tools]


__all__ = [
    "VENDOR_ENVELOPE_KEYS", "VENDOR_TOOL_TYPE", "VENDOR_STRICT",
    "to_vendor_envelope", "to_vendor_catalogue",
]
