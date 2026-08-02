# tests/test_doc_path_encoding.py
"""
A percent-encoded document path is retried DECODED, and the refusal names it.

**THE DEFECT, from a live log:** the model passed `.../My%20Documents/book.pdf`.
Nothing exists at that path, the extractor raised `OSError`, and the model read
the generic "something went wrong opening it" note — true, and useless, because
"check the path" does not tell a model that `%20` is a space. The path was
recoverable and nothing tried.

**THE RULE UNDER TEST: THE RAW PATH WINS WHENEVER IT EXISTS.** Decoding is a
FALLBACK, never a rewrite — a real filename may contain a literal `%20`, and
silently opening a different file is the wrong-document failure this package
refuses everywhere else. DEC-63 layer 3's principle: guessing is only safe when
guessing wrong is observable, and here it would not be.

**THE NOTE carries the standing three obligations** (AGENTS.md, ruled in DEC-58):
what happened (BOTH forms tried, nothing opened, no index), that repeating this
spelling is terminal, and the one action that fixes it.

**PRIVACY (DEC-61):** the resolver logs LENGTHS and BOOLEANS. A document path is
the user's own file name and the folder it lives in — the exact datum DEC-61
removed from the logs — so a canary check drives every branch and proves no path
text reaches any logger.
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from muthis.broker.docs import notes
from muthis.broker.docs.paths import ResolvedPath, resolve_document_path


# ───────────────────────── the resolver ─────────────────────────────────────

def test_a_plain_path_is_returned_untouched(tmp_path) -> None:
    real = tmp_path / "book.pdf"
    real.write_text("x", encoding="utf-8")

    out = resolve_document_path(real)

    assert out == ResolvedPath(real, url_encoded=False, decoded=False)


def test_a_percent_encoded_path_is_retried_decoded(tmp_path) -> None:
    """THE FIX. The decoded form exists, so it is opened and reported as decoded."""
    folder = tmp_path / "My Documents"
    folder.mkdir()
    real = folder / "book.pdf"
    real.write_text("x", encoding="utf-8")
    encoded = pathlib.Path(str(real).replace(" ", "%20"))
    assert not encoded.is_file(), "the encoded form must not exist for this test"

    out = resolve_document_path(encoded)

    assert out.path == real and out.decoded is True and out.url_encoded is True


def test_the_raw_path_WINS_when_it_actually_exists(tmp_path) -> None:
    """A real filename may contain a literal `%20`. Decoding it would open a
    DIFFERENT file with no observable difference — the failure this ordering
    exists to prevent, and the reason decoding is a fallback rather than a rule."""
    literal = tmp_path / "report%20final.pdf"
    literal.write_text("x", encoding="utf-8")
    decoy = tmp_path / "report final.pdf"
    decoy.write_text("DIFFERENT", encoding="utf-8")

    out = resolve_document_path(literal)

    assert out.path == literal and out.decoded is False
    assert out.url_encoded is True          # noticed, and deliberately not acted on


def test_neither_form_existing_reports_the_encoding_for_the_note(tmp_path) -> None:
    missing = tmp_path / "no%20such.pdf"

    out = resolve_document_path(missing)

    assert out.path == missing and out.decoded is False and out.url_encoded is True


def test_a_bare_percent_is_not_a_percent_sequence(tmp_path) -> None:
    """`%` followed by two HEX digits, never a loose `%`. A bare percent in a
    filename is ordinary and must not trigger a decode attempt."""
    out = resolve_document_path(tmp_path / "50% off.pdf")

    assert out.url_encoded is False and out.decoded is False


def test_the_resolver_never_raises_on_a_malformed_path() -> None:
    """A path that cannot even be stat'ed is simply not a file we can open."""
    out = resolve_document_path(pathlib.Path("\x00bad"))

    assert out.decoded is False


# ───────────────────────── the note ─────────────────────────────────────────

def test_the_two_refusals_are_different_notes() -> None:
    """DEC-35's rule: a refusal that misreports its reason turns a fixable
    condition into a blind retry. The INEQUALITY is asserted directly, because a
    mutation collapsing both onto one string satisfies each note's own check."""
    assert notes.read_failed(url_encoded=True) == notes.DOC_PATH_URL_ENCODED_AR
    assert notes.read_failed(url_encoded=False) == notes.DOC_READ_FAILED_AR
    assert notes.DOC_PATH_URL_ENCODED_AR != notes.DOC_READ_FAILED_AR


def test_the_encoded_note_carries_all_three_obligations() -> None:
    note = notes.DOC_PATH_URL_ENCODED_AR
    # (1) what happened: BOTH forms tried, nothing opened, nothing indexed
    assert "جرّبته كما وصلني" in note and "بعد فك" in note
    assert "ما فُتح شي في الحالتين" in note and "ما صارت فهرسة" in note
    # (2) TERMINAL for this spelling, with the reason
    assert "لا تعيد إرسال نفس المسار بنفس الصيغة" in note
    # (3) the valid NEXT STEP, named
    assert "كما يظهر له في مستكشف الملفات" in note


def test_the_encoded_note_names_the_cause_the_model_can_act_on() -> None:
    """"Check the path" does not tell a model that %20 is a space. Naming the
    encoding IS the actionable part, so it is asserted rather than assumed."""
    assert "ترميز الروابط" in notes.DOC_PATH_URL_ENCODED_AR
    assert "20%" in notes.DOC_PATH_URL_ENCODED_AR


def test_the_note_names_no_path(tmp_path) -> None:
    """The notes law: «المستند», never a filesystem path.

    Asserted on SEPARATORS only. A colon is ordinary Arabic punctuation here (both
    notes use one), and the encoded note carries exactly one `%` on purpose — it
    is teaching the model what a percent sequence looks like, which is the whole
    actionable content."""
    for note in (notes.DOC_PATH_URL_ENCODED_AR, notes.DOC_READ_FAILED_AR):
        assert "\\" not in note and "/" not in note
    assert notes.DOC_PATH_URL_ENCODED_AR.count("%") == 1


# ───────────────────────── the WIRING, end to end ───────────────────────────
#
# ADDED AFTER A SURVIVING MUTATION, not by review: removing `url_encoded` from
# `ingest`'s call to `_extract_blocks` changed nothing, because every test above
# drives `paths.py` and `notes.py` in ISOLATION. The resolver and the note were
# both guarded; the LINE THAT CONNECTS THEM was not. Same gap as DEC-69's M6, one
# module over — and the same lesson: a component test proves a component.
#
# These run the REAL `extract_blocks_async` against genuinely missing files, so
# the OSError is real and the whole chain is exercised with no fake in it.


@pytest.mark.asyncio
async def test_an_encoded_missing_path_reaches_the_ENCODED_note(tmp_path) -> None:
    from muthis.broker.docs.ingest import DocumentIngestor
    from muthis.broker.docs.zones import DocZone, ZonePolicy

    out = await DocumentIngestor(policy=ZonePolicy()).ingest(
        tmp_path / "My%20Documents" / "book.pdf")

    assert out.zone is DocZone.REFUSE and not out.ok
    assert out.note_ar == notes.DOC_PATH_URL_ENCODED_AR


@pytest.mark.asyncio
async def test_a_plain_missing_path_still_reaches_the_GENERIC_note(tmp_path) -> None:
    """The control. Without it, a mutation returning the encoded note
    unconditionally would satisfy the test above."""
    from muthis.broker.docs.ingest import DocumentIngestor
    from muthis.broker.docs.zones import DocZone, ZonePolicy

    out = await DocumentIngestor(policy=ZonePolicy()).ingest(
        tmp_path / "My Documents" / "book.pdf")

    assert out.zone is DocZone.REFUSE and not out.ok
    assert out.note_ar == notes.DOC_READ_FAILED_AR


@pytest.mark.asyncio
async def test_an_encoded_path_that_RESOLVES_is_actually_opened(tmp_path) -> None:
    """THE FIX, end to end: the decoded file exists, so ingestion reads IT rather
    than refusing. Proven by the outcome carrying that file's real content."""
    from muthis.broker.docs.ingest import DocumentIngestor
    from muthis.broker.docs.zones import DocZone, ZonePolicy

    folder = tmp_path / "My Documents"
    folder.mkdir()
    (folder / "notes.md").write_text("مرحبا بالعالم\n\nفقرة ثانية.", encoding="utf-8")
    encoded = pathlib.Path(str(folder / "notes.md").replace(" ", "%20"))

    out = await DocumentIngestor(policy=ZonePolicy()).ingest(encoded)

    assert out.zone is DocZone.INJECT and out.ok
    assert "مرحبا بالعالم" in out.text


# ───────────────────────── privacy (DEC-61) ─────────────────────────────────

def test_no_path_text_reaches_any_logger(tmp_path, caplog) -> None:
    """Driven over EVERY branch with a canary in both the file name AND the
    directory, with a positive control that the resolver logs at all — otherwise
    a module that logged nothing would pass this vacuously."""
    canary_dir = tmp_path / "CANARYDIR"
    canary_dir.mkdir()
    real = canary_dir / "CANARYFILE.pdf"
    real.write_text("x", encoding="utf-8")
    encoded = pathlib.Path(str(real).replace("CANARYDIR", "CANARY%44IR"))

    with caplog.at_level(logging.DEBUG):
        resolve_document_path(real)                       # plain
        resolve_document_path(encoded)                    # decoded-and-found
        resolve_document_path(canary_dir / "no%20such.pdf")  # neither exists

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "CANARYDIR" not in text and "CANARYFILE" not in text
    assert str(tmp_path) not in text
    # POSITIVE CONTROL: it did log, so the assertions above examined something.
    assert "URL-encoded" in text, "the resolver logged nothing — check is vacuous"
    assert "raw_len=" in text, "the log carries no shape — DEC-61's substitute"
