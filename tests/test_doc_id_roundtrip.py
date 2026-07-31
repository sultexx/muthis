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


def test_a_mangled_id_is_RECOVERED_when_exactly_one_document_is_open(caplog):
    """The shape that failed live: the id does not match, one document is open,
    so the answer must still be served — and the recovery must be VISIBLE."""
    service = _service_with("lecture.pdf")
    with caplog.at_level(logging.WARNING, logger="muthis.broker.docs.service"):
        _passages, note = service.query("something-the-model-invented", "سؤال؟")
    assert note != DOC_NOT_OPEN_AR, "the single open document was not recovered"
    assert "RECOVERED MISMATCH" in caplog.text, "the recovery was silent"
    # DEC-61: a doc_id IS the file's own name, so the VALUES never reach the log.
    assert "lecture.pdf" not in caplog.text
    assert "something-the-model-invented" not in caplog.text


def test_a_mangled_id_is_NOT_guessed_when_two_documents_are_open():
    """Here the ambiguity is REAL: guessing would answer questions about the
    wrong document with no observable difference (the DEC-47 argument)."""
    service = _service_with("a.pdf", "b.pdf")
    _passages, note = service.query("neither-of-them", "سؤال؟")
    assert note == DOC_NOT_OPEN_AR


def test_nothing_open_still_returns_the_honest_note():
    service = _service_with()
    _passages, note = service.query("anything", "سؤال؟")
    assert note == DOC_NOT_OPEN_AR


def test_normalization_alone_resolves_a_wrapped_id_when_recovery_CANNOT_help():
    """THE DISCRIMINATING TEST, added because a mutation survived without it.

    Removing the normalization survived the tests above: with ONE document open
    the single-doc recovery caught every mangled id, so normalization was never
    the thing under test. Two documents open disables recovery (the ambiguity is
    real), so a guillemet-wrapped id can ONLY resolve through normalization —
    and the mutation now goes RED. The M15 rule, applied: an unobservable
    property is a fact about the test, not a licence to leave it unguarded."""
    service = _service_with("a.pdf", "b.pdf")
    passages, note = service.query("«a.pdf»", "سؤال؟")
    assert note != DOC_NOT_OPEN_AR, (
        "a wrapped id did not normalize; with two documents open the recovery "
        "cannot mask it, so this is the normalization itself failing")
