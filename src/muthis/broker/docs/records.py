# src/muthis/broker/docs/records.py
"""
What the two verbs RETURN — the frozen records, extracted from `service.py` under
the ≤300-line law (2026-07-31). A PURE MOVE, diff-proven byte-identical.

THE SEAM, and why it is this one. `service.py` owns two verbs, `open` and
`query`. These two dataclasses are what those verbs hand back: passive records
carrying zero behaviour beyond one derived property. That is precisely the
`MountedRoute` case (DEC-30) — "a passive record carrying zero behaviour, which
is why the dispatch file loses nothing by not holding it" — and it was chosen for
the same reason: under ceiling pressure the project reaches for an EXTRACTION,
and a move carries no risk of changing what it moves.

`Passage` in particular is a CROSS-BOUNDARY CONTRACT. The plugin may not import
it (a plugin imports `muthis_sdk` and stdlib only), so it duck-types the fields —
which makes the FIELDS the contract, as the class docstring says. A contract
record and the machinery that produces it are two responsibilities, and only one
of them belongs in the file holding the encoder lifetime and the registry.

RE-EXPORTED from `service.py`, so no importer changed: the dependency runs
service → records, so nothing cycles (the `router_surfaces.py` case, and NOT the
`core_router.py` one, where composition → registry forced importers to name the
new module directly).

A LEAF: imports `dataclasses` and `typing` and nothing else, in this package or
out of it. Importable in isolation.
"""

from __future__ import annotations

import dataclasses
from typing import Optional


@dataclasses.dataclass(frozen=True)
class Passage:
    """One retrieved chunk, with WHERE it came from and HOW well it matched.

    `parent` and `score` are here because the plugin needs both to apply DEC-46's
    two surviving delivery rules — dedupe by parent, deliver in relevance order —
    and it is duck-typed across the boundary, so the fields ARE the contract.

    `page` / `section` are the citation metadata DEC-46 distinguishes from a
    security boundary: they exist so a claim can be attributed to a location, and
    nothing downstream may read them as a trust signal."""

    text: str
    score: float
    parent: str
    page: Optional[int] = None
    section: str = ""


@dataclasses.dataclass(frozen=True)
class OpenedDocument:
    """What `open` produced: a zone, and either text, a doc_id, or a refusal."""

    zone: str
    note_ar: Optional[str] = None
    text: str = ""
    doc_id: str = ""
    pages: Optional[int] = None
    chunks: int = 0

    @property
    def ok(self) -> bool:
        return self.note_ar is None


__all__ = ["OpenedDocument", "Passage"]
