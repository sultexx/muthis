# tests/test_doc_delivery.py
"""
Delivery, the plugin surface, and the broker service (V2 Phase 2 M3, T4).

DEC-50 retired DEC-46's fusion machinery in full but named TWO clauses that
SURVIVE, "because they are properties of small-to-big and the delivery cap, NOT of
fusion". Both are tested here, and the ORDER OF OPERATIONS between them is the part
worth defending:

  · **sort by relevance FIRST, then dedupe by parent, then fill the cap.** Deduping
    before sorting would keep an ARBITRARY child of each parent rather than its
    BEST child — and every "we deduped" and "we sorted" assertion would still pass.
    Capping before deduping would let one well-matching section spend the whole
    budget before a second source is ever considered.

That interaction is why the tests below assert POSITIONS and CONTENT rather than
counts: a count-only check cannot tell a correct pipeline from one whose stages run
in the wrong order.

No model, no ONNX session, no corpus. The encoder and the index are faked; what is
under test is OUR delivery contract.
"""

from __future__ import annotations

import asyncio
import pathlib

import numpy as np
import pytest

from muthis.broker.docs import notes
from muthis.broker.docs.blocks import Block, Chunk
from muthis.broker.docs.encoder import EncoderUnavailable
from muthis.broker.docs.index import IndexRegistry, SessionIndex
from muthis.broker.docs.service import (
    CANDIDATES, DOC_NOT_OPEN_AR, DocumentService, EMPTY_QUESTION_AR, Passage,
)
from muthis_plugins.doc_rag.delivery import (
    MAX_PASSAGE_CHARS, MIN_PASSAGE_CHARS, NOTHING_FOUND_AR, render, select,
)
from muthis_plugins.doc_rag.plugin import (
    DocRagPlugin, EMPTY_DOC_ID_AR, EMPTY_PATH_AR, FULL_HEADER_AR, NO_SERVICE_AR,
    UNKNOWN_TOOL_AR,
)
from muthis_sdk import PluginContext


def _p(text, score, parent, page=None, section=""):
    return Passage(text=text, score=score, parent=parent, page=page, section=section)


# ═══ DEC-46 clause (a): parent dedupe + relevance order + the cap ════════════

def test_siblings_of_one_parent_are_COLLAPSED_to_the_best_one():
    """Small-to-big means several children of one parent rank together — a
    well-matching section produces many well-matching chunks. Without parent-level
    dedupe ONE section consumes the entire budget and the second-best source never
    appears at all."""
    passages = [_p("الأفضل من ١٤", 0.9, "p14", page=14),
                _p("أضعف من ١٤", 0.7, "p14", page=14),
                _p("من ٢١", 0.6, "p21", page=21)]

    chosen, report = select(passages)

    assert [c.parent for c in chosen] == ["p14", "p21"]
    assert chosen[0].text == "الأفضل من ١٤", "the WEAKER sibling survived"
    assert report["parents_collapsed"] == 1


def test_delivery_is_in_RELEVANCE_order_not_arrival_order():
    """The cap may truncate, so whatever is dropped must be the LEAST relevant
    thing rather than the last to arrive. Ordering by document position would make
    truncation arbitrary — the passage that answers the question could be dropped
    for sitting on a later page."""
    passages = [_p("ثالث", 0.3, "p3"), _p("أول", 0.95, "p1"), _p("ثاني", 0.6, "p2")]

    chosen, _report = select(passages)

    assert [c.text for c in chosen] == ["أول", "ثاني", "ثالث"]


def test_the_sort_happens_BEFORE_the_dedupe_so_the_BEST_child_survives():
    """THE ORDER-OF-OPERATIONS TEST. Deduping first would keep whichever child
    arrived first — here the weak one — while "we deduped" and "we sorted" both
    still passed. Built so the arrival order and the score order DISAGREE."""
    passages = [_p("ضعيف", 0.10, "p7", page=7),      # arrives first, worst score
                _p("قوي", 0.99, "p7", page=7)]        # arrives last, best score

    chosen, report = select(passages)

    assert len(chosen) == 1 and report["parents_collapsed"] == 1
    assert chosen[0].score == pytest.approx(0.99), "dedupe ran before the sort"


def test_the_total_cap_bounds_the_delivered_text():
    passages = [_p("x" * 6_000, 0.9 - i / 100, f"p{i}") for i in range(10)]

    chosen, report = select(passages)

    assert report["chars"] <= MAX_PASSAGE_CHARS
    assert sum(len(c.text) for c in chosen) <= MAX_PASSAGE_CHARS
    assert len(chosen) < len(passages), "the cap admitted everything"


def test_the_cap_keeps_the_MOST_relevant_when_it_truncates():
    passages = [_p("y" * 9_000, 0.99, "p1"), _p("z" * 9_000, 0.10, "p2")]

    chosen, _report = select(passages)

    assert len(chosen) == 1 and chosen[0].score == pytest.approx(0.99)


def test_a_shorter_passage_can_still_fit_after_a_long_one_is_skipped():
    """The cap SKIPS rather than STOPS while useful room remains — dropping every
    later passage because one long one did not fit would throw away relevance the
    budget could still afford."""
    passages = [_p("a" * 15_000, 0.9, "p1"), _p("b" * 9_000, 0.8, "p2"),
                _p("c" * 500, 0.7, "p3")]

    chosen, _report = select(passages)

    assert [c.parent for c in chosen] == ["p1", "p3"]


def test_the_report_states_its_cutoff_and_its_admitted_count():
    """The standing rule from the P0 gate: every check with a cutoff reports which
    cutoff it used and how many cases it admitted, because a filter inside a stage
    can silently exclude the stage's own subject."""
    chosen, report = select([_p("نص", 0.5, "p1")])

    assert report == {"candidates": 1, "admitted": 1, "parents_collapsed": 0,
                      "chars": len("نص"), "cap": MAX_PASSAGE_CHARS}
    assert report["admitted"] == len(chosen)


def test_no_candidates_admits_zero_and_says_so_honestly():
    chosen, report = select([])

    assert chosen == [] and report["admitted"] == 0
    assert render(chosen) == NOTHING_FOUND_AR
    # The note tells the model to SAY SO rather than infer — the persona law's
    # deterministic companion (DEC-49 ruling 3 retired the entry floor, so nothing
    # else stands between a topically-adjacent passage and a confident answer).
    assert "ما يجاوب" in NOTHING_FOUND_AR


def test_the_minimum_slot_stops_the_scan_when_no_room_is_left():
    passages = [_p("q" * (MAX_PASSAGE_CHARS - 50), 0.9, "p1"),
                _p("r" * 500, 0.8, "p2")]

    chosen, report = select(passages)

    assert len(chosen) == 1
    assert MAX_PASSAGE_CHARS - report["chars"] < MIN_PASSAGE_CHARS


# ═══ Rendering: citation metadata, never a security boundary ══════════════════

def test_each_passage_is_labelled_with_its_PAGE_when_the_format_has_pages():
    out = render([_p("متن", 0.9, "p212", page=212)])

    assert "[صفحة 212]" in out and "متن" in out


def test_a_pageless_format_is_labelled_by_SECTION_not_by_a_fake_page():
    out = render([_p("متن", 0.9, "s2.3", section="2.3")])

    assert "[قسم 2.3]" in out and "صفحة" not in out


def test_a_passage_with_no_position_says_so_rather_than_inventing_one():
    assert "بدون موضع" in render([_p("متن", 0.9, "s")])


def test_passages_are_NUMBERED_so_the_model_can_refer_to_one_while_speaking():
    out = render([_p("أ", 0.9, "p1", page=1), _p("ب", 0.8, "p2", page=2)])

    assert "[1]" in out and "[2]" in out


def test_the_renderer_adds_NO_wrapper_and_NO_nonce():
    """DEC-46 × DEC-14: ONE wrapper, ONE nonce, applied by the ROUTER for the whole
    result. The location labels here are CITATION METADATA and carry no security
    meaning — nothing downstream may read them as a trust boundary."""
    from muthis.kernel.untrusted_content import WRAP_CLOSE_AR, WRAP_OPEN_AR

    out = render([_p("متن", 0.9, "p1", page=1)])

    assert WRAP_OPEN_AR.split("{", 1)[0] not in out
    assert WRAP_CLOSE_AR.split("{", 1)[0] not in out


# ═══ The plugin surface ══════════════════════════════════════════════════════

class _Opened:
    def __init__(self, **kw):
        self.zone = kw.get("zone", "index")
        self.note_ar = kw.get("note_ar")
        self.text = kw.get("text", "")
        self.doc_id = kw.get("doc_id", "")
        self.pages = kw.get("pages")
        self.chunks = kw.get("chunks", 0)

    @property
    def ok(self):
        return self.note_ar is None


class _Service:
    def __init__(self, opened=None, passages=None, note=None, boom=False):
        self._opened, self._passages, self._note = opened, passages or [], note
        self._boom = boom

    async def open(self, path):
        if self._boom:
            raise OSError("disk gone")
        return self._opened

    def query(self, doc_id, question):
        return ([], self._note) if self._note else (self._passages, None)


def _run(plugin, tool, args):
    return asyncio.run(plugin.execute(tool, args, PluginContext()))


def test_zone_1_hands_over_the_full_text_and_says_not_to_query_it():
    plugin = DocRagPlugin(service=_Service(_Opened(zone="inject", text="النص كامل")))

    out = _run(plugin, "open", {"path": "C:/x/a.md"})

    assert out.is_error is False
    assert "النص كامل" in out.text_ar and FULL_HEADER_AR.split("(", 1)[0] in out.text_ar
    assert "ما تحتاج" in out.text_ar     # do not call query — it would cost a pass


def test_zone_2_returns_the_doc_id_the_model_must_pass_back():
    plugin = DocRagPlugin(service=_Service(
        _Opened(zone="index", doc_id="lecture.pdf", pages=228, chunks=267)))

    out = _run(plugin, "open", {"path": "C:/x/lecture.pdf"})

    assert "lecture.pdf" in out.text_ar and "267" in out.text_ar
    assert "228 صفحة" in out.text_ar


def test_a_pageless_document_gets_no_invented_page_count():
    plugin = DocRagPlugin(service=_Service(
        _Opened(doc_id="notes.md", pages=None, chunks=12)))

    out = _run(plugin, "open", {"path": "C:/x/notes.md"})

    assert "صفحة" not in out.text_ar and "notes.md" in out.text_ar


def test_a_refusal_is_passed_through_UNEDITED():
    """DEC-35's rule at the plugin boundary: the broker's own wording is the
    accurate one, and re-wording a TERMINAL refusal into a generic failure is what
    makes a model retry. The `web_research` precedent — a mutation that re-words
    the fetcher's note goes RED."""
    exact = "هذا ملف PDF ممسوح ضوئيًا — لا تحاول تقرأه مرة أخرى."
    plugin = DocRagPlugin(service=_Service(_Opened(zone="refuse", note_ar=exact)))

    out = _run(plugin, "open", {"path": "C:/x/scan.pdf"})

    assert out.text_ar == exact and out.is_error is True


def test_the_plugin_never_raises_when_the_service_explodes():
    plugin = DocRagPlugin(service=_Service(boom=True))

    out = _run(plugin, "open", {"path": "C:/x/a.pdf"})

    assert out.is_error is True and out.text_ar


@pytest.mark.parametrize("tool,args,expected", [
    ("open", {}, EMPTY_PATH_AR),
    ("open", {"path": "   "}, EMPTY_PATH_AR),
    ("query", {}, EMPTY_DOC_ID_AR),
    ("query", {"doc_id": ""}, EMPTY_DOC_ID_AR),
    ("nonsense", {}, UNKNOWN_TOOL_AR),
])
def test_bad_arguments_become_arabic_notes_never_exceptions(tool, args, expected):
    plugin = DocRagPlugin(service=_Service(_Opened()))

    assert _run(plugin, tool, args).text_ar == expected


def test_no_service_configured_is_an_ordinary_note_not_a_missing_tool():
    """The DEC-18 posture: the TOOL exists on every machine, so a missing model or
    an unreadable cache is an Arabic note rather than a structural difference in the
    catalog the model sees."""
    plugin = DocRagPlugin(service=None)

    assert _run(plugin, "open", {"path": "x"}).text_ar == NO_SERVICE_AR
    assert _run(plugin, "query", {"doc_id": "x"}).text_ar == NO_SERVICE_AR


def test_the_plugin_applies_the_delivery_rules_it_owns():
    plugin = DocRagPlugin(service=_Service(passages=[
        _p("الأفضل", 0.9, "p1", page=1), _p("شقيق أضعف", 0.5, "p1", page=1),
        _p("مصدر ثانٍ", 0.7, "p2", page=2)]))

    out = _run(plugin, "query", {"doc_id": "d", "question": "س"})

    assert "شقيق أضعف" not in out.text_ar, "the plugin did not dedupe by parent"
    assert out.text_ar.index("الأفضل") < out.text_ar.index("مصدر ثانٍ")


def test_a_service_note_is_surfaced_as_an_error_note():
    plugin = DocRagPlugin(service=_Service(note=DOC_NOT_OPEN_AR))

    out = _run(plugin, "query", {"doc_id": "ghost", "question": "س"})

    assert out.text_ar == DOC_NOT_OPEN_AR and out.is_error is True


# ═══ The broker service ══════════════════════════════════════════════════════

class _FakeEncoder:
    def load(self): ...

    def count_tokens(self, text):
        return max(1, len(text.split()))

    def encode_passages(self, texts):
        return np.ones((len(texts), 4), dtype=np.float32) / 2.0

    def encode_queries(self, texts):
        return np.ones((1, 4), dtype=np.float32) / 2.0


def _service(**kw) -> DocumentService:
    return DocumentService(model_dir=pathlib.Path("."), encoder=_FakeEncoder(), **kw)


def _index(n=3) -> SessionIndex:
    chunks = [Chunk(text=f"مقطع {i}", n_tokens=2,
                    blocks=(Block(text=f"مقطع {i}", page=i + 1),)) for i in range(n)]
    return SessionIndex(chunks, np.ones((n, 4), dtype=np.float32) / 2.0)


def test_querying_an_unopened_document_gets_its_OWN_note_not_not_found():
    """DEC-35 one layer up: "not found" would make the model retry the QUERY when
    what it needs is to OPEN the document first."""
    passages, note = _service().query("ghost.pdf", "س")

    assert passages == [] and note == DOC_NOT_OPEN_AR


def test_an_empty_question_is_refused_before_the_encoder_is_touched():
    class _Boom:
        def encode_queries(self, texts):
            raise AssertionError("the encoder ran on an empty question")

    service = DocumentService(model_dir=pathlib.Path("."), encoder=_Boom())
    passages, note = service.query("d", "   ")

    assert passages == [] and note == EMPTY_QUESTION_AR


def test_an_unavailable_encoder_becomes_a_note_not_an_exception():
    class _Dead:
        def encode_queries(self, texts):
            raise EncoderUnavailable("no onnxruntime")

    registry = IndexRegistry()
    registry.put("d", _index())
    service = DocumentService(model_dir=pathlib.Path("."), registry=registry,
                              encoder=_Dead())

    passages, note = service.query("d", "س")

    assert passages == [] and note == notes.DOC_ENCODER_UNAVAILABLE_AR


def test_query_returns_ranked_passages_carrying_their_position():
    registry = IndexRegistry()
    registry.put("d", _index())
    service = _service(registry=registry)

    passages, note = service.query("d", "س")

    assert note is None and len(passages) == 3
    assert all(p.parent and p.page for p in passages)
    assert passages == sorted(passages, key=lambda p: -p.score)


def test_the_candidate_cutoff_is_generous_enough_for_dedupe_to_collapse_into():
    """CANDIDATES must exceed the delivery shape P0 measured (8-17 parents), or the
    cap stops being the binding constraint and this number silently becomes it."""
    assert CANDIDATES >= 20


def test_clear_drops_every_open_document():
    registry = IndexRegistry()
    registry.put("d", _index())
    service = _service(registry=registry)

    assert service.open_documents == 1
    service.clear()
    assert service.open_documents == 0
