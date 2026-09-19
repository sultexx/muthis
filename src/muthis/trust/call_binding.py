# src/muthis/trust/call_binding.py
"""
THE BINDING — the canonical form of one tool call, and the fingerprint over it.

EXTRACTED FROM `confirm_gate.py` (DEC-138), and the reason is a SECOND CONSUMER
rather than a line count, which is the argument behind every extraction this
project has made. The canonicalisation is a MECHANISM, not a policy: the same
bytes whichever gate consumes them. It has two consumers now — the gate that
HASHES them to bind an approval, and the speech layer that SAYS them so the user
hears the call the hash covers — and a mechanism with two consumers belongs to
neither of them.

THE NAME IS CONSUMER-NEUTRAL ON PURPOSE. Its siblings are named for the gate
they serve (`confirm_gate_notes`, `confirm_gate_detector`, `confirm_gate_speech`)
because each is that gate's surface. This one is not a surface; naming it
`confirm_gate_binding` would tie a shared mechanism to one of its callers, which
is the thing the extraction exists to stop.

THE LINE-COUNT PRESSURE WAS REAL AND IS NOT THE JUSTIFICATION. `confirm_gate.py`
measured 314 with DEC-138 applied — a breach of the ≤300 LAW, not merely of its
pin — and three other relief options were measured and rejected: extracting
`_Pending` left 307 (still a breach), relocating the gate's one-shot accessor fit
on size but has no coherent home (the gate is the only place a refusal is known),
and shortening docstrings is what the law's second clause forbids. This one left
287. That it also relieves the ceiling is a consequence of its being the right
seam, not the argument for it.

PURE AND STATELESS, which is what makes it testable alone and guardable by HASH:
it holds no session, no pending, no policy and no opinion about whether anything
should be refused. It decides nothing. `tests/test_call_binding.py` pins the
moved function's output by SHA-256 over fixtures rather than by a green suite,
on DEC-108's method.

Pure stdlib, importable in isolation. Re-exported from `confirm_gate.py` so no
import site outside this package changed — the `confirm_gate_notes.py` (DEC-131)
and `confirm_gate_detector.py` (DEC-136) precedent.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def canonical_call(tool: str, args: Mapping[str, Any]) -> tuple[str, str]:
    """The CANONICAL BYTES and the fingerprint over them — ONE canonicalisation.

    `sort_keys` makes two equal argument dicts hash equal whatever order the
    stream produced them in; `default=str` keeps an exotic value from raising.
    A value that defeats even that falls back to `repr`, which is
    insertion-ordered — so the worst case is two equal calls hashing apart, i.e.
    a re-confirmation (friction), never two different calls hashing together.

    RETURNING THE CANONICAL STRING ADDS NOTHING TO WHAT ANY GATE HOLDS
    (DEC-138). It was always computed here and thrown away as a local; handing
    it back lets the SPOKEN request be derived from the bytes that were HASHED
    rather than rendered a second time from the dict. No caller stores more
    than it did before — there is no retention, because there is no gap
    between knowing and speaking. WHY a second
    rendering diverges anyway is `confirm_gate_speech.py`'s subject.

    THE HASH IS UNCHANGED BY THIS EXTENSION, and that is the point of its
    having landed in a separate commit: the preimage is still `tool` + newline
    + canonical, byte for byte, and `tests/test_call_binding.py` was written
    against the MOVE and passes here untouched."""
    try:
        canonical = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001 — a gate must never raise into a turn
        canonical = repr(args)
    return canonical, hashlib.sha256(
        f"{tool}\n{canonical}".encode("utf-8")).hexdigest()


def call_fingerprint(tool: str, args: Mapping[str, Any]) -> str:
    """The pin, unchanged: the fingerprint half of `canonical_call`. Kept at its
    own name because it IS the binding, and a caller wanting only the hash
    should not have to know a canonical form exists."""
    return canonical_call(tool, args)[1]


__all__ = ["call_fingerprint", "canonical_call"]
