# tests/test_doc_binding.py
"""
DEC-71 — the broker binds the query; the model carries NO document identifier.

**WHY THE IDENTIFIER LEFT.** Three live truncations in one session
(`received len=16, key len=23, differ_only_by_wrapping=False`), and the diagnosis
ruled out every mechanical cause: no `maxLength` in the schema, no truncation in
the open note, and **no rule-shaped mangling produces 16 from 23** — drop `.pdf`
gives 19, an NFC fold gives 23, first-word gives 4. So the model was not
TRANSFORMING the id, it was RECONSTRUCTING it, and normalizing a fourth shape
could never work because there is no fourth shape, there is a paraphrase.

**WHY (A) AND NOT A SHORTER STRING.** An opaque handle or an ordinal SHRINKS the
round-trip; a reconstructing model is not bounded by making the string shorter,
and both keep the silent wrong-document failure. Removing the field removes the
trip. The identifier is a fact the BROKER owns — routing it through the model is
the pattern this project has rejected repeatedly (DEC-29 `is_error`, DEC-34 a
plugin-set cost, DEC-36 the badge's provenance).

**WHAT SURVIVES:** DEC-63 layer 3. A residual caller that still passes an id and
misses REFUSES rather than guessing, because guessing answers about the wrong
document with no observable difference. Layer 2 — the single-document recovery —
is retired: it was a safety net UNDER the round-trip, and the binding replaces it.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from muthis.broker.docs.blocks import Block, Chunk
from muthis.broker.docs.index import IndexRegistry, SessionIndex
from muthis.broker.docs.service import (
    DOC_ALREADY_IN_FULL_AR, DOC_NOT_OPEN_AR, DocumentService,
)


class _Encoder:
    def load(self): pass
    def count_tokens(self, text): return max(1, len(text.split()))
    def encode_passages(self, texts): return np.ones((len(texts), 4), np.float32) / 2
    def encode_queries(self, texts): return np.ones((len(texts), 4), np.float32) / 2


def _index(n: int = 3) -> SessionIndex:
    chunks = [Chunk(text=f"مقطع {i}", n_tokens=3,
                    blocks=(Block(text=f"مقطع {i}", page=i + 1, para=0),))
              for i in range(n)]
    return SessionIndex(chunks, np.ones((n, 4), np.float32) / 2)


def _service(*registered: str) -> DocumentService:
    registry = IndexRegistry()
    for name in registered:
        registry.put(name, _index())
    return DocumentService(model_dir=pathlib.Path("."), registry=registry,
                           encoder=_Encoder())


# EVERY binding test below drives the REAL `DocumentService.open`.
#
# ADDED AFTER THREE SURVIVING MUTATIONS, and the mechanism was my own helper: it
# set `service._bound` DIRECTLY instead of opening anything, so deleting the
# binding line in `open`, deleting the switch, and deleting the zone-1 clear all
# changed NOTHING. The tests proved `_bind` and never touched the code that FEEDS
# it. Third sighting in this session of one family — a component test proves a
# component (DEC-40, DEC-69's M6, TASK 2's M6).


def _write(tmp: pathlib.Path, name: str, marker: str, *, big: bool) -> pathlib.Path:
    """A real .md on disk. `big` pushes it past the injection limit into zone 2;
    `marker` is what tells us WHICH document answered."""
    para = f"{marker} " * 20
    # MEASURED, not guessed: zone 2 starts at 139,665 chars (inject_limit 50,000
    # tokens / 0.358 tok-per-char). 1200 reps = 122,400 lands in zone ONE, which
    # is how the first draft of this file silently tested the wrong zone.
    body = (para + "\n\n") * (1600 if big else 2)      # 163,200 chars
    path = tmp / name
    path.write_text(body, encoding="utf-8")
    return path


# ───────────────────────── the binding ──────────────────────────────────────

@pytest.mark.asyncio
async def test_a_query_with_no_id_answers_from_the_document_just_opened(tmp_path) -> None:
    """The model's ONLY path since v5, driven through the REAL open."""
    service = _service()
    opened = await service.open(_write(tmp_path, "lecture.md", "ألفا", big=True))
    assert opened.zone == "index" and opened.ok, "the fixture did not reach zone 2"

    passages, note = service.query("ما هذا؟")

    assert note is None and passages
    assert all("ألفا" in p.text for p in passages)


@pytest.mark.asyncio
async def test_opening_a_SECOND_document_SWITCHES_which_one_answers(tmp_path) -> None:
    """`open` IS the select verb — it carries a PATH the user supplied rather than
    an id we minted, so there is nothing for the model to paraphrase. Asserted on
    the CONTENT that comes back, not on private state."""
    service = _service()
    await service.open(_write(tmp_path, "first.md", "ألفا", big=True))
    await service.open(_write(tmp_path, "second.md", "بيتا", big=True))

    passages, note = service.query("ما هذا؟")

    assert note is None and passages
    assert all("بيتا" in p.text for p in passages), (
        "the query answered from the FIRST document — opening the second did not "
        "switch the binding")


def test_nothing_open_refuses_and_sends_the_model_to_open() -> None:
    passages, note = _service().query("ما هذا؟")

    assert passages == [] and note == DOC_NOT_OPEN_AR


@pytest.mark.asyncio
async def test_TWO_documents_open_is_no_longer_ambiguous(tmp_path) -> None:
    """THE DEFECT'S ORIGINAL BLAST RADIUS, closed. Under the round-trip a
    truncated id with two documents open FAILED every query (measured). With the
    binding there is no ambiguity to resolve: the last open wins, by construction."""
    service = _service()
    await service.open(_write(tmp_path, "other.md", "ألفا", big=True))
    await service.open(_write(tmp_path, "wanted.md", "بيتا", big=True))

    passages, note = service.query("ما هذا؟")

    assert note is None and all("بيتا" in p.text for p in passages)


@pytest.mark.asyncio
async def test_RE_opening_the_same_document_keeps_it_selected(tmp_path) -> None:
    """DEC-58 made re-open idempotent at essentially zero cost, and DEC-71 makes
    it the switch-back verb: re-opening the first document selects it again."""
    service = _service()
    first = _write(tmp_path, "first.md", "ألفا", big=True)
    await service.open(first)
    await service.open(_write(tmp_path, "second.md", "بيتا", big=True))
    await service.open(first)

    passages, note = service.query("ما هذا؟")

    assert note is None and all("ألفا" in p.text for p in passages)


# ───────────────────────── the zone-1 interaction ───────────────────────────

@pytest.mark.asyncio
async def test_opening_an_INJECTED_document_stops_the_query_answering_from_an_older_one(
        tmp_path) -> None:
    """THE SUB-DECISION, resolved in the direction the ruling requires and driven
    through the REAL open. A zone-1 document is handed over whole and registers no
    index. Leaving the previous binding would let the next query answer from an
    EARLIER document while the user is looking at this one — the wrong-document
    failure with no observable difference, which is what DEC-71 exists to remove."""
    service = _service()
    await service.open(_write(tmp_path, "big.md", "ألفا", big=True))
    small = await service.open(_write(tmp_path, "small.md", "بيتا", big=False))
    assert small.zone == "inject" and small.ok, "the fixture did not reach zone 1"

    passages, note = service.query("ما هذا؟")

    assert passages == [] and note == DOC_ALREADY_IN_FULL_AR
    assert note != DOC_NOT_OPEN_AR, "a category error must not read as a failure"


def test_the_injected_note_carries_the_three_obligations() -> None:
    note = DOC_ALREADY_IN_FULL_AR
    assert "وصلك كاملاً بنصّه" in note                    # what IS the case
    assert "ولا صار خطأ ولا ناقص شي" in note              # nothing failed
    assert "ولا تعيد فتحه" in note                        # terminal for re-open
    assert "جاوب من النص اللي بين يديك" in note           # the valid next step


# ───────────────────────── DEC-63 layer 3 survives ──────────────────────────

def test_a_residual_id_that_matches_still_works() -> None:
    service = _service("kept.pdf")

    passages, note = service.query("ما هذا؟", doc_id="kept.pdf")

    assert note is None and len(passages) == 3


@pytest.mark.asyncio
async def test_a_residual_id_that_MISSES_refuses_and_never_falls_back_to_the_binding(
        tmp_path) -> None:
    """The safety net, and the direction matters: an explicit id that misses must
    NOT be quietly replaced by the bound document. That would be the guess DEC-63
    layer 3 forbids, reintroduced through the back door. Driven with a document
    genuinely open, so the fallback it must not take is actually available."""
    service = _service()
    await service.open(_write(tmp_path, "bound.md", "ألفا", big=True))

    passages, note = service.query("ما هذا؟", doc_id="something-else.pdf")

    assert passages == [] and note == DOC_NOT_OPEN_AR


def test_a_wrapped_residual_id_still_normalizes() -> None:
    service = _service("a.pdf")

    passages, note = service.query("ما هذا؟", doc_id="«a.pdf»")

    assert note is None and passages


# ───────────────────────── the production graph ─────────────────────────────

def test_the_REAL_composition_helper_builds_the_document_service() -> None:
    """ADDED AFTER A REAL BREAKAGE, not by review. Removing the TASK-1 observer
    parameter from `DocumentService` left `composition.py` still PASSING it — a
    `TypeError` on every production start — and the whole suite stayed GREEN,
    because every test builds its own service.

    That is DEC-40's defect exactly: *a test that builds its own graph proves
    nothing about production.* This drives the REAL helper. It imports
    `composition`, never `muthis.main` (the standing rule: importing main executes
    `load_dotenv()` and pulls real credentials into the test process)."""
    from muthis.composition import _build_doc_rag

    service, plugin = _build_doc_rag()

    assert isinstance(service, DocumentService)
    assert plugin.descriptors()[0].name == "open"
    # the binding starts empty: nothing is open until something is opened
    passages, note = service.query("ما هذا؟")
    assert passages == [] and note == DOC_NOT_OPEN_AR
