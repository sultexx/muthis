# tests/test_doc_ingest.py
"""
The three-zone ingestion router (V2 Phase 2 M3, T3 — DEC-47, DEC-35, DEC-49).

THE TWO CLAIMS THIS FILE EXISTS TO MAKE UNFALSIFIABLE-BY-ACCIDENT:

  1. **A ZONE-1 DOCUMENT NEVER TOUCHES THE ENCODER**, and a ZONE-3 DOCUMENT NEVER
     ENCODES. Not "does not need to" — cannot. The encoder arrives as a FACTORY,
     and the tests below hand over a factory that RAISES if it is ever called, so
     the assertion is not "we observed no call" but "a call would have failed the
     test loudly". An AST check then pins the single reference site, because the
     way this property dies is a future edit hoisting the factory above the branch
     for convenience — a change that keeps every behavioural test green.

  2. **A SCANNED PDF AND AN UNSUPPORTED FORMAT GET DIFFERENT NOTES** (DEC-35).
     Asserting each note's content separately is not enough: a mutation collapsing
     both onto one string satisfies two independent "the note mentions the format"
     assertions. So the INEQUALITY of the two notes is asserted directly — the same
     asymmetry lesson the T2 prefix tests produced.

The encoder is faked throughout. No model is downloaded, no ONNX session is built,
and no vector arithmetic is checked here — T2 owns that. What is under test is the
ROUTING and the REFUSALS.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import textwrap

import numpy as np
import pytest

from muthis.broker.docs import notes
from muthis.broker.docs.blocks import Block, ExtractReport
from muthis.broker.docs.chunking import ChunkWindowExceeded
from muthis.broker.docs.encoder import EncoderUnavailable
from muthis.broker.docs.extract import NoTextLayer, UnsupportedDocument
from muthis.broker.docs.ingest import DocumentIngestor, IngestOutcome
from muthis.broker.docs.zones import DocZone, ZonePolicy


# ---------------------------------------------------------------------------
# Seams
# ---------------------------------------------------------------------------

class _ExplodingEncoder:
    """Every entry point fails. Reaching ANY of them fails the test by name."""

    def load(self):
        raise AssertionError("load(): a bypassed zone constructed the encoder")

    def count_tokens(self, text):
        raise AssertionError("count_tokens(): a bypassed zone chunked the document")

    def encode_passages(self, texts):
        raise AssertionError("encode_passages(): a bypassed zone ENCODED")


def _exploding_factory():
    raise AssertionError("the encoder FACTORY was called on a bypassed zone")


class _SpyEncoder:
    """Works, and records which stages ran — for the zone-2 positive control.

    `dense=True` makes its tokenizer count one token per CHARACTER, which is far
    above the estimator's 0.358 ceiling. That is not a contrived number: it is the
    UNDER-ESTIMATION the second gate exists to catch, and the only way to reach
    that gate in a test is to be a document the first gate under-counted."""

    def __init__(self, *, dense: bool = False):
        self.calls: list[str] = []
        self._dense = dense

    def load(self):
        self.calls.append("load")

    def count_tokens(self, text):
        return len(text) if self._dense else max(1, len(text.split()))

    def encode_passages(self, texts):
        self.calls.append(f"encode:{len(texts)}")
        return np.ones((len(texts), 4), dtype=np.float32) / 2.0


def _blocks(chars: int, *, per_block: int = 500) -> list[Block]:
    """Arabic-shaped filler of a known character count, positioned like a PDF."""
    word = "كلمة "
    body = (word * (per_block // len(word) + 1))[:per_block]
    count = max(1, chars // per_block)
    return [Block(text=body, page=1 + i // 4, para=i % 4) for i in range(count)]


def _extractor(blocks: list[Block], *, raises: Exception | None = None):
    async def extract(path):
        if raises is not None:
            raise raises
        return blocks, ExtractReport(source=path.suffix, blocks=len(blocks),
                                     pages_total=None, pages_with_text=None,
                                     chars=sum(len(b.text) for b in blocks))
    return extract


def _ingestor(blocks=None, *, factory=_exploding_factory, raises=None,
              policy=None) -> DocumentIngestor:
    # `blocks is None`, NOT `blocks or ...`: an EMPTY list is a real case here (the
    # zero-admitted refusal), and a falsy check silently replaced it with a healthy
    # document — the test then asserted against the opposite of its own subject and
    # passed for the wrong reason. Same family as a length floor that filters out
    # the only case a check exists to examine.
    if blocks is None:
        blocks = _blocks(2_000)
    return DocumentIngestor(policy=policy or ZonePolicy(),
                            encoder_factory=factory,
                            extract=_extractor(blocks, raises=raises))


DOC = pathlib.Path("teaching/notes.md")
PDF = pathlib.Path("teaching/book.pdf")


# ---------------------------------------------------------------------------
# ZONE 1 — built and tested FIRST (DEC-47's ordering), and it encodes NOTHING
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zone_1_returns_the_WHOLE_document_and_no_index():
    blocks = _blocks(2_000)

    out = await _ingestor(blocks).ingest(DOC)

    assert out.zone is DocZone.INJECT and out.ok
    assert out.index is None                      # nothing was indexed
    assert out.chunks is None                     # nothing was chunked
    # every block's text is present: full injection means FULL
    for block in blocks:
        assert block.text.strip() in out.text


@pytest.mark.asyncio
async def test_zone_1_NEVER_CONSTRUCTS_THE_ENCODER():
    """THE structural claim. The factory raises, so reaching it is a failure with
    a name rather than a silent extra call nobody counted."""
    out = await _ingestor(_blocks(2_000), factory=_exploding_factory).ingest(DOC)

    assert out.zone is DocZone.INJECT and out.ok


@pytest.mark.asyncio
async def test_zone_1_does_not_reach_the_encoder_even_if_one_is_HANDED_OVER():
    """The complementary case: a factory that succeeds but returns an object whose
    every method explodes. This distinguishes "the factory was not called" from
    "the encoder was not used" — a mutation could restore one without the other."""
    out = await _ingestor(_blocks(2_000),
                          factory=lambda: _ExplodingEncoder()).ingest(DOC)

    assert out.zone is DocZone.INJECT and out.ok


@pytest.mark.asyncio
async def test_a_document_AT_the_injection_limit_is_still_injected():
    # 50_000 tokens at the ceiling ratio = 139_664 chars; sized just under.
    chars = int(50_000 / 0.358) - 1_000

    out = await _ingestor(_blocks(chars)).ingest(DOC)

    assert out.zone is DocZone.INJECT
    assert out.decision.tokens <= out.decision.inject_limit


@pytest.mark.asyncio
async def test_zone_1_marks_POSITIONS_so_the_injected_copy_can_be_cited():
    """DEC-45 captures page and section precisely so a location can be named. A
    228-page document injected as one unmarked blob is a document the model cannot
    cite, which would waste the field at the exact moment it is free."""
    out = await _ingestor(_blocks(4_000)).ingest(DOC)      # 8 blocks -> 2 pages

    # PAGE 1 INCLUDED. The first page was the one an earlier draft left unlabelled,
    # because "the position changed" read as false when there was no previous block.
    assert "[صفحة 1]" in out.text and "[صفحة 2]" in out.text


@pytest.mark.asyncio
async def test_markdown_sections_are_marked_when_there_are_no_pages():
    blocks = [Block(text="أول", page=None, para=0, section="1"),
              Block(text="ثاني", page=None, para=1, section="2.3")]

    out = await _ingestor(blocks).ingest(DOC)

    assert "[قسم 2.3]" in out.text


# ---------------------------------------------------------------------------
# ZONE 3 — refused BEFORE encoding, both gates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zone_3_refuses_with_ZERO_encoding_and_zero_chunking():
    out = await _ingestor(_blocks(3_000_000)).ingest(DOC)

    assert out.zone is DocZone.REFUSE and not out.ok
    assert out.index is None and out.chunks is None
    assert out.decision.admitted == 0


@pytest.mark.asyncio
async def test_the_zone_3_refusal_OFFERS_THREE_PATHS():
    """The robots-refusal pattern: a block becomes a showcase. The third offer is
    not a consolation — it routes the user into the LOOK-only vision path, the one
    capability no document-chat tool has."""
    out = await _ingestor(_blocks(3_000_000)).ingest(DOC)

    assert "قسم محدد" in out.note_ar          # ask about a specific section
    assert "قسّم الملف" in out.note_ar        # split the file
    assert "على الشاشة" in out.note_ar        # open it on screen and point


@pytest.mark.asyncio
async def test_the_zone_3_refusal_STATES_the_size_and_the_limit():
    out = await _ingestor(_blocks(3_000_000)).ingest(DOC)

    assert str(out.decision.tokens) in out.note_ar
    assert str(out.decision.max_tokens) in out.note_ar


@pytest.mark.asyncio
async def test_the_SECOND_gate_refuses_an_under_estimated_document_before_encoding():
    """The estimate is an upper bound, not a proof. If a document slips through the
    first gate, the true chunk count catches it — and `encode_passages` is never
    reached, which is what "before the budget is spent" has to mean."""
    spy = _SpyEncoder(dense=True)
    # A budget that pays for 2 chunks. 2_000 chars ESTIMATE to 716 tokens, which is
    # inside this policy's 760-token maximum — so gate 1 admits the document. Its
    # dense tokenizer then yields far more than 2 chunks, and gate 2 refuses it.
    tiny = ZonePolicy(inject_limit=10, budget_seconds=2 * 30.2 / 1000.0)
    assert tiny.max_chunks == 2 and tiny.max_tokens == 760

    out = await _ingestor(_blocks(2_000), factory=lambda: spy,
                          policy=tiny).ingest(DOC)

    assert out.zone is DocZone.REFUSE and not out.ok
    assert "encode:" not in " ".join(spy.calls)     # tokenized, never encoded
    assert out.decision.exact is True               # counted, not estimated
    assert out.decision.tokens > 760, "gate 1 under-counted; gate 2 caught it"


# ---------------------------------------------------------------------------
# ZONE 2 — the positive control, so the bypass tests are not vacuous
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zone_2_chunks_encodes_and_builds_an_index():
    spy = _SpyEncoder()
    chars = int(50_000 / 0.358) + 20_000        # just past the injection limit

    out = await _ingestor(_blocks(chars), factory=lambda: spy).ingest(DOC)

    assert out.zone is DocZone.INDEX and out.ok
    assert out.index is not None and len(out.index) > 0
    assert out.chunks.chunks == len(out.index)
    assert "load" in spy.calls and any(c.startswith("encode:") for c in spy.calls)
    assert out.text == ""                        # zone 2 injects nothing


@pytest.mark.asyncio
async def test_zone_2_with_no_encoder_configured_degrades_LOUDLY_not_silently(caplog):
    chars = int(50_000 / 0.358) + 20_000

    with caplog.at_level("ERROR", logger="muthis.broker.docs"):
        out = await _ingestor(_blocks(chars), factory=None).ingest(DOC)

    assert not out.ok and out.note_ar == notes.DOC_ENCODER_UNAVAILABLE_AR
    assert "no encoder configured" in caplog.text


@pytest.mark.asyncio
async def test_an_unloadable_encoder_becomes_an_arabic_note_not_an_exception():
    class Dead:
        def load(self):
            raise EncoderUnavailable("no onnxruntime")

    chars = int(50_000 / 0.358) + 20_000
    out = await _ingestor(_blocks(chars), factory=lambda: Dead()).ingest(DOC)

    assert not out.ok and out.note_ar == notes.DOC_ENCODER_UNAVAILABLE_AR


@pytest.mark.asyncio
async def test_a_chunker_that_cannot_split_REFUSES_rather_than_indexing_a_partial():
    """DEC-53 ruled the SPLITTER gets fixed when this fires, never the guard —
    and DEC-47 rejected partial ingestion, because the disclosure fires once at
    ingestion while the wrong answer arrives later with nothing connecting them."""
    class Weird:
        def load(self):
            pass

        def count_tokens(self, text):
            raise ChunkWindowExceeded(9_000, 400)

    chars = int(50_000 / 0.358) + 20_000
    out = await _ingestor(_blocks(chars), factory=lambda: Weird()).ingest(DOC)

    assert not out.ok and out.note_ar == notes.DOC_CHUNK_FAILED_AR
    assert out.index is None


# ---------------------------------------------------------------------------
# DEC-35 — the two refusals that must DIFFER
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_SCANNED_pdf_and_an_UNSUPPORTED_format_get_DIFFERENT_notes():
    """The inequality is the assertion. Two separate "it names the format" checks
    would both pass on a mutation that returned one note for both conditions —
    which is exactly the retryable/terminal confusion DEC-35 recorded."""
    scanned = await _ingestor(raises=NoTextLayer("no text layer on 40 pages")
                              ).ingest(PDF)
    unsupported = await _ingestor().ingest(pathlib.Path("thesis.docx"))

    assert scanned.note_ar != unsupported.note_ar
    assert not scanned.ok and not unsupported.ok


@pytest.mark.asyncio
async def test_the_scanned_note_is_TERMINAL_and_forecloses_a_retry():
    """DEC-35's live cost was four provider calls and ~$0.10 because a terminal
    condition read as retryable. A competent agent retries a retryable note; the
    only defence is a note that says the attempt is over."""
    out = await _ingestor(raises=NoTextLayer("scanned")).ingest(PDF)

    assert out.note_ar == notes.PDF_SCANNED_AR
    assert "PDF" in out.note_ar                     # names the format
    assert "لا تحاول" in out.note_ar                # do not try again
    assert "على الشاشة" in out.note_ar              # ...and here is what to do


@pytest.mark.asyncio
async def test_the_unsupported_note_NAMES_the_format_and_offers_conversion():
    out = await _ingestor().ingest(pathlib.Path("book.epub"))

    assert ".epub" in out.note_ar
    assert "حوّل الملف" in out.note_ar               # a converted copy works
    assert "لا تحاول" not in out.note_ar             # NOT terminal — the difference


@pytest.mark.asyncio
async def test_an_unsupported_format_opens_NO_FILE_at_all():
    """The cheapest refusal first: the suffix is knowable from the name, so a
    .docx never reaches the extractor and a missing file never even matters."""
    async def must_not_run(path):
        raise AssertionError("the extractor ran on an unsupported format")

    ingestor = DocumentIngestor(policy=ZonePolicy(), extract=must_not_run,
                                encoder_factory=_exploding_factory)

    assert not (await ingestor.ingest(pathlib.Path("x.docx"))).ok


@pytest.mark.asyncio
async def test_a_suffixless_file_is_described_as_such_rather_than_as_empty_quotes():
    out = await _ingestor().ingest(pathlib.Path("README"))

    assert "بدون امتداد" in out.note_ar


@pytest.mark.asyncio
async def test_an_extraction_that_admits_ZERO_blocks_is_a_FAILURE_not_a_pass(caplog):
    with caplog.at_level("INFO", logger="muthis.broker.docs"):
        out = await _ingestor([]).ingest(DOC)

    assert not out.ok and out.note_ar == notes.DOC_EMPTY_AR
    assert "ZERO" in caplog.text


@pytest.mark.asyncio
async def test_an_io_error_becomes_a_note_and_never_escapes():
    out = await _ingestor(raises=PermissionError("locked")).ingest(DOC)

    assert not out.ok and out.note_ar == notes.DOC_READ_FAILED_AR


@pytest.mark.asyncio
async def test_every_refusal_note_offers_at_least_one_path_forward():
    """The robots-refusal pattern applied uniformly: a refusal with no offer is
    a dead end, and a dead end invites the retry loop DEC-35 measured."""
    for name, note in vars(notes).items():
        if name.endswith("_AR") and isinstance(note, str):
            assert "على الشاشة" in note or "اسألني" in note or "حوّل" in note, name


# ---------------------------------------------------------------------------
# THE PLUGIN CANNOT CHOOSE ITS ZONE
# ---------------------------------------------------------------------------

def test_the_ingest_seam_takes_a_PATH_and_nothing_else():
    """DEC-18's signature-scan discipline, applied to the zone instead of the
    search destination. A plugin that could name its zone could ask for FULL
    INJECTION of a hostile 200-page document — a plugin declaring how much of the
    user's context it is entitled to spend, which is the DEC-15/29/34 family of
    self-assertions this project refuses on principle."""
    parameters = list(inspect.signature(DocumentIngestor.ingest).parameters)

    assert parameters == ["self", "path"]


def test_no_INGESTOR_method_accepts_a_zone_or_a_limit():
    """The scan, not one hand-checked function: a second entry point added later
    with a `zone=` or `limit=` parameter would reopen the hole silently.

    Scoped to `DocumentIngestor`, deliberately. `IngestOutcome` DOES take a zone —
    it is the broker REPORTING which path it chose, which is the opposite direction
    of travel. A plugin fabricating an outcome fools only itself; a plugin passing a
    zone INTO the ingestor would move the broker's hand."""
    forbidden = {"zone", "limit", "inject", "max_tokens", "budget", "policy_override",
                 "force", "full", "inject_limit", "estimate"}
    source = pathlib.Path("src/muthis/broker/docs/ingest.py").read_text(encoding="utf-8")
    ingestor = next(n for n in ast.walk(ast.parse(source))
                    if isinstance(n, ast.ClassDef) and n.name == "DocumentIngestor")

    checked = 0
    for node in ast.walk(ingestor):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            checked += 1
            names = ({a.arg for a in node.args.args}
                     | {a.arg for a in node.args.kwonlyargs})
            assert not names & forbidden, f"{node.name} accepts {names & forbidden}"

    # A scan that examined nothing is not a scan (the standing cutoff rule).
    assert checked >= 4, f"only {checked} methods scanned"


def test_the_encoder_factory_is_referenced_on_EXACTLY_ONE_line():
    """THE MUTATION THIS EXISTS FOR: hoisting the factory above the zone branch.
    Every behavioural test stays green — zone 1 still returns the right text — and
    the bypass silently becomes a promise instead of a property. Counting the
    reference sites is what notices."""
    source = pathlib.Path("src/muthis/broker/docs/ingest.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    sites = [node for node in ast.walk(tree)
             if isinstance(node, ast.Attribute) and node.attr == "_encoder_factory"
             and not isinstance(getattr(node, "ctx", None), ast.Store)]
    holders = {f.name for f in ast.walk(tree)
               if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
               and any(isinstance(n, ast.Attribute) and n.attr == "_encoder_factory"
                       and not isinstance(n.ctx, ast.Store) for n in ast.walk(f))}

    # Two reads: the `is None` guard and the call, both inside `_index`.
    assert len(sites) == 2, [ast.dump(s) for s in sites]
    assert holders == {"_index"}, holders


def test_ingest_never_raises_for_any_of_the_refusal_conditions():
    """A refusal that arrives as an exception ends the turn instead of continuing
    it, and the caller then owns a decision that belongs here (the FileReader
    precedent, and the Law-11 wall between the broker and the kernel)."""
    # Parsed, not grepped: the docstring says "Never raises", so a substring check
    # finds its own documentation and asserts nothing about the code.
    tree = ast.parse(textwrap.dedent(inspect.getsource(DocumentIngestor.ingest)))

    assert not [n for n in ast.walk(tree) if isinstance(n, ast.Raise)]


def test_the_outcome_carries_a_note_XOR_a_result():
    injected = IngestOutcome(DocZone.INJECT, text="نص")
    refused = IngestOutcome(DocZone.REFUSE, note_ar="لا")

    assert injected.ok and not refused.ok
