"""
test_doc_id_roundtrip.py — the doc_id must survive a natural-language round-trip.

MEASURED LIVE (fourth SOP): `docs__query` never reached `DocumentService.query`'s
ranking. `self._registry.get(doc_id)` returned None, so the function returned
DOC_NOT_OPEN_AR before its own log line — which is why zero "query: candidates="
lines coexisted with "reopen: already open". The model paraphrased that note back
as «أداة فتح المستندات ما تشتغل صح», a phrase that occurs in that note and nowhere
else in the codebase.

ROOT CAUSE: `INDEXED_AR` presents the id INSIDE guillemets, so the live model must
extract and re-emit it. DEC-16's rule governs — a machine identifier must never
depend on the model's paraphrasing.
"""

from __future__ import annotations

import logging

import pytest

from muthis.broker.docs.index import IndexRegistry, SessionIndex
from muthis.broker.docs.service import DOC_NOT_OPEN_AR, _normalize_doc_id


class _Idx(SessionIndex):
    def __init__(self):
        pass


def _service_with(*doc_ids):
    from muthis.broker.docs.service import DocumentService
    import pathlib

    registry = IndexRegistry()
    for name in doc_ids:
        registry.put(name, _Idx())
    return DocumentService(model_dir=pathlib.Path("."), registry=registry)


@pytest.mark.parametrize("received", [
    "«lecture.pdf»", '"lecture.pdf"', " lecture.pdf ", "lecture.pdf",
    "“lecture.pdf”", "«lecture.pdf",
])
def test_every_wrapping_the_model_may_add_normalizes_to_the_registry_key(received):
    assert _normalize_doc_id(received) == "lecture.pdf"


def test_a_mangled_id_is_NOT_recovered_now_that_the_BINDING_replaces_it():
    """RE-AIMED at DEC-71, not deleted (DEC-63's own K2–K5 lesson).

    This used to assert that ONE open document RECOVERS a mangled id. That layer
    existed because the model carried the id; it is retired with the round-trip.
    The safety net now runs the other way: a residual caller supplying an id that
    does not match REFUSES — even with exactly one document open, where the old
    recovery would have masked it."""
    service = _service_with("lecture.pdf")

    _passages, note = service.query("سؤال؟", doc_id="something-the-model-invented")

    assert note == DOC_NOT_OPEN_AR, "an unmatched id was guessed at"


def test_a_mangled_id_is_NOT_guessed_when_two_documents_are_open():
    """DEC-63 layer 3, UNCHANGED and still the safety net: guessing would answer
    about the wrong document with no observable difference."""
    service = _service_with("a.pdf", "b.pdf")
    _passages, note = service.query("سؤال؟", doc_id="neither-of-them")
    assert note == DOC_NOT_OPEN_AR


def test_nothing_open_still_returns_the_honest_note():
    service = _service_with()
    _passages, note = service.query("سؤال؟", doc_id="anything")
    assert note == DOC_NOT_OPEN_AR


def test_a_query_with_NO_id_and_nothing_open_refuses_honestly():
    """The model's ONLY path since v5. Nothing bound, so nothing to answer from —
    and the note must send it to `open` rather than invite a retry."""
    service = _service_with()
    _passages, note = service.query("سؤال؟")
    assert note == DOC_NOT_OPEN_AR


def test_normalization_still_resolves_a_wrapped_id_on_the_RESIDUAL_path():
    """The normalization survives for callers that still pass an id (tests, the
    diag script). With TWO documents open there is no recovery to mask it, so a
    guillemet-wrapped id can only resolve THROUGH normalization — which is what
    keeps the mutation that deletes it RED."""
    service = _service_with("a.pdf", "b.pdf")
    passages, note = service.query("سؤال؟", doc_id="«a.pdf»")
    assert note != DOC_NOT_OPEN_AR, (
        "a wrapped id did not normalize; with two documents open nothing can "
        "mask it, so this is the normalization itself failing")
