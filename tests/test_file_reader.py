"""
test_file_reader.py — v7 Phase 4: the read_local_file executor's safety gates
(NO network, NO real user files — everything under tmp_path).

Covers: numbered 1-based content + header; start_line/end_line ranges (and a
swapped range); missing-file / directory → the Arabic not-found note;
secret-bearing names refused by NAME (.env / .env.* / id_rsa* / *.pem /
credentials*); oversize refused; binary (NUL sniff) refused; char-cap
truncation cuts at a line boundary and appends the range hint; garbage args
never raise; file CONTENT never appears in logs (privacy law); and the
stubs.stub_read_file default answers the Arabic unavailable note.

Run:  set PYTHONPATH=src && python -m pytest tests/test_file_reader.py -q
"""

from __future__ import annotations

import hashlib
import inspect
import logging

import pytest

from muthis import file_reader as _fr
from muthis.file_reader import (
    DOCUMENT_FORMATS,
    FILE_BLOCKED_AR,
    FILE_IS_DOCUMENT_AR,
    FILE_NOT_FOUND_AR,
    FILE_NOT_TEXT_AR,
    FILE_READ_UNAVAILABLE_AR,
    FILE_TOO_LARGE_AR,
    FileReader,
    TRUNCATION_NOTE_AR,
)
from muthis.stubs import stub_read_file

CODE = "int led = 2;\nvoid setup() {\n  pinMode(led, OUTPUT);\n}\n"


@pytest.mark.asyncio
async def test_reads_numbered_content_with_header(tmp_path):
    target = tmp_path / "blink.ino"
    target.write_text(CODE, encoding="utf-8")

    out = await FileReader().read({"path": str(target)})

    assert "blink.ino" in out and "1-4 من 4" in out          # Arabic header
    assert "    1 | int led = 2;" in out                      # 1-based numbering
    assert "    3 |   pinMode(led, OUTPUT);" in out           # indentation kept


@pytest.mark.asyncio
async def test_line_range_and_swapped_range(tmp_path):
    target = tmp_path / "q.sql"
    target.write_text("\n".join(f"line{i}" for i in range(1, 11)), encoding="utf-8")
    reader = FileReader()

    ranged = await reader.read({"path": str(target), "start_line": 3, "end_line": 5})
    assert "3-5 من 10" in ranged
    assert "line3" in ranged and "line6" not in ranged and "line2" not in ranged

    swapped = await reader.read({"path": str(target), "start_line": 5, "end_line": 3})
    assert "3-5 من 10" in swapped                             # reversed range healed


@pytest.mark.asyncio
async def test_missing_file_and_directory_get_not_found_note(tmp_path):
    reader = FileReader()
    missing = await reader.read({"path": str(tmp_path / "ghost.py")})
    assert "ما لقيت الملف" in missing and "ghost.py" in missing
    directory = await reader.read({"path": str(tmp_path)})    # a dir is not a file
    assert "ما لقيت الملف" in directory


@pytest.mark.asyncio
@pytest.mark.parametrize("name", [
    ".env", ".env.production", "id_rsa", "id_ed25519.pub",
    "server.pem", "signing.key", "credentials.json",
])
async def test_secret_bearing_names_are_refused(tmp_path, name):
    target = tmp_path / name
    target.write_text("TOP_SECRET=1", encoding="utf-8")

    out = await FileReader().read({"path": str(target)})

    assert out == FILE_BLOCKED_AR
    assert "TOP_SECRET" not in out                            # content never leaks


@pytest.mark.asyncio
async def test_oversize_file_refused(tmp_path):
    target = tmp_path / "big.txt"
    target.write_text("x" * 100, encoding="utf-8")

    out = await FileReader(max_bytes=10).read({"path": str(target)})

    assert out == FILE_TOO_LARGE_AR


@pytest.mark.asyncio
async def test_binary_file_refused(tmp_path):
    target = tmp_path / "firmware.bin"
    target.write_bytes(b"MZ\x00\x01\x02\x00binary")

    out = await FileReader().read({"path": str(target)})

    assert out == FILE_NOT_TEXT_AR


@pytest.mark.asyncio
async def test_truncation_cuts_at_line_boundary_with_hint(tmp_path):
    target = tmp_path / "long.txt"
    target.write_text("\n".join(f"row {i:03}" for i in range(200)), encoding="utf-8")

    out = await FileReader(max_chars=300).read({"path": str(target)})

    assert TRUNCATION_NOTE_AR.strip() in out
    body = out.split(":\n", 1)[1]
    kept = body.split("\n(", 1)[0]                            # numbered part only
    assert all(line.lstrip()[0].isdigit() for line in kept.splitlines() if line)
    assert "row 199" not in out                               # tail really dropped


@pytest.mark.asyncio
async def test_garbage_args_never_raise(tmp_path):
    target = tmp_path / "ok.txt"
    target.write_text("a\nb\nc", encoding="utf-8")
    reader = FileReader()

    assert "ما لقيت الملف" in await reader.read({})           # no path at all
    assert "ما لقيت الملف" in await reader.read({"path": None})
    garbled = await reader.read(
        {"path": str(target), "start_line": "junk", "end_line": []})
    assert "1-3 من 3" in garbled                              # bad ints → whole file


@pytest.mark.asyncio
async def test_content_never_logged(tmp_path, caplog):
    target = tmp_path / "notes.txt"
    target.write_text("SENSITIVE_BODY_TOKEN once", encoding="utf-8")

    with caplog.at_level(logging.DEBUG):
        out = await FileReader().read({"path": str(target)})

    assert "SENSITIVE_BODY_TOKEN" in out                      # reaches the model
    assert "SENSITIVE_BODY_TOKEN" not in caplog.text          # never the logs


@pytest.mark.asyncio
async def test_the_PATH_is_never_logged_on_ANY_outcome(tmp_path, caplog):
    """I6, measured live 2026-07-31: a real corpus FILE NAME reached the logs
    while its CONTENT never did. This module's own recorded discipline said
    "path and outcome in English, NEVER content", and that clause was wrong
    about WHICH HALF is sensitive — the path carries the user's document name
    and the folder it lives in.

    EVERY outcome is driven, because the leak was in five refusal lines and one
    success line, not in any single one of them."""
    directory = tmp_path / "QDIRCANARYQ"
    directory.mkdir()
    readable = directory / "QREADCANARYQ.txt"
    readable.write_text("line one\nline two\n", encoding="utf-8")
    binary = directory / "QBINCANARYQ.pdf"
    binary.write_bytes(b"%PDF-1.7\x00 body")
    secret = directory / ".env"
    secret.write_text("KEY=value", encoding="utf-8")
    oversize = directory / "QBIGCANARYQ.txt"
    oversize.write_text("x" * 64, encoding="utf-8")
    missing = directory / "QGONECANARYQ.txt"

    with caplog.at_level(logging.DEBUG):
        assert "line one" in await FileReader().read({"path": str(readable)})
        await FileReader().read({"path": str(binary)})
        await FileReader().read({"path": str(secret)})
        await FileReader(max_bytes=8).read({"path": str(oversize)})
        await FileReader().read({"path": str(missing)})

    # ── THE PROPERTY: no name, no directory, no path — on any outcome ──
    for canary in ("QDIRCANARYQ", "QREADCANARYQ", "QBINCANARYQ",
                   "QBIGCANARYQ", "QGONECANARYQ", ".env"):
        assert canary not in caplog.text, f"{canary} reached the logs"
    assert str(tmp_path) not in caplog.text

    # ── THE CONTROL: without it every assertion above would pass on a module
    # that logged NOTHING AT ALL (the standing cutoff rule — a check that
    # examined nothing must never look like a check that passed). ──
    assert "[file_reader]" in caplog.text
    assert ".txt" in caplog.text and ".pdf" in caplog.text   # EXTENSION is kept
    assert "bytes=" in caplog.text                           # SIZE is kept


@pytest.mark.asyncio
async def test_an_OSError_never_carries_the_path_into_the_logs(tmp_path, caplog,
                                                               monkeypatch):
    """The SEVENTH site, found while fixing the six Sultan named: `OSError.__str__`
    embeds the offending path verbatim (`[Errno 2] ...: 'C:\\...'`), so logging the
    exception object re-opened the leak that the type name alone closes."""
    target = tmp_path / "QOSERRCANARYQ.txt"
    target.write_text("body", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError(2, "No such file or directory", str(target))

    monkeypatch.setattr(_fr.FileReader, "_read_blocking", boom)
    with caplog.at_level(logging.DEBUG):
        out = await FileReader().read({"path": str(target)})

    assert out == _fr.FILE_READ_ERROR_AR
    assert "QOSERRCANARYQ" not in caplog.text
    assert str(tmp_path) not in caplog.text
    # The TYPE is still reported — the control, without which this test would
    # pass on a module that logged nothing. errno 2 raises the CONCRETE
    # subclass, so the line names FileNotFoundError rather than OSError.
    assert "read failed (FileNotFoundError)" in caplog.text


@pytest.mark.asyncio
async def test_stub_read_file_answers_unavailable():
    assert await stub_read_file({"path": "C:/anything.py"}) == FILE_READ_UNAVAILABLE_AR


# ───────────── DEC-35: the refusal NAMES the format (T3, doc_rag) ─────────────
#
# Live evidence, 2026-07-25: a PDF was refused CORRECTLY — the binary NUL sniff
# fired exactly as designed and nothing leaked — but the note the model read
# reported a RETRYABLE reason. The model then did the rational thing and retried
# four different paths until MAX_AGENTIC_ITERATIONS stopped the turn: four
# provider calls, roughly $0.10, no answer for the user. Every guard behaved to
# spec; the SIGNAL lied about its reason. The fix is a MESSAGE, and the tests
# below also pin the neighbouring GUARDS as byte-identical, because "improving"
# a security gate while the file is open is what DEC-42's discipline forbids.

@pytest.mark.asyncio
async def test_a_pdf_refusal_NAMES_the_format_instead_of_a_generic_binary_note(tmp_path):
    target = tmp_path / "textbook.pdf"
    target.write_bytes(b"%PDF-1.7\x00\x00 stream junk")

    out = await FileReader().read({"path": str(target)})

    assert out == FILE_IS_DOCUMENT_AR.format(fmt="PDF")
    assert "PDF" in out
    assert out != FILE_NOT_TEXT_AR          # the note it REPLACED


@pytest.mark.asyncio
async def test_the_pdf_refusal_is_TERMINAL_and_is_NOT_the_not_found_note(tmp_path):
    """The two halves of DEC-35's defect, asserted as inequalities rather than as
    two independent content checks: the note must not be the not-found note (the
    wrong reason), and it must foreclose the retry (the wrong category)."""
    target = tmp_path / "textbook.pdf"
    target.write_bytes(b"%PDF-1.7\x00 junk")

    out = await FileReader().read({"path": str(target)})

    assert out != FILE_NOT_FOUND_AR.format(path=str(target))
    assert "لا تحاول" in out                 # do not retry — the terminal signal
    assert "على الشاشة" in out               # ...and the path forward (vision)


@pytest.mark.asyncio
async def test_a_DOCX_and_a_PDF_get_DIFFERENT_notes(tmp_path):
    """A mutation that named one format for every document would satisfy "the note
    mentions a format" twice over. The INEQUALITY is what closes that."""
    pdf = tmp_path / "a.pdf"
    docx = tmp_path / "b.docx"
    pdf.write_bytes(b"%PDF-1.7\x00 x")
    docx.write_bytes(b"PK\x03\x04\x00 x")

    pdf_note = await FileReader().read({"path": str(pdf)})
    docx_note = await FileReader().read({"path": str(docx)})

    assert pdf_note != docx_note
    assert "PDF" in pdf_note and "DOCX" in docx_note


@pytest.mark.asyncio
async def test_an_UNRECOGNISED_binary_keeps_the_generic_note(tmp_path):
    """No invented format names. Claiming a type we did not recognise would swap
    one inaccuracy for another, which is the whole defect being fixed."""
    target = tmp_path / "firmware.xyz"
    target.write_bytes(b"MZ\x00\x01 binary")

    assert await FileReader().read({"path": str(target)}) == FILE_NOT_TEXT_AR


def test_every_named_format_renders_a_note_that_actually_names_it():
    for suffix, name in DOCUMENT_FORMATS.items():
        note = _fr._binary_refusal(suffix)
        assert name in note, suffix
        assert note != FILE_NOT_TEXT_AR, suffix
    # A loop over an empty map would pass having examined nothing.
    assert len(DOCUMENT_FORMATS) >= 5


def test_the_format_lookup_is_case_insensitive():
    assert _fr._binary_refusal(".PDF") == _fr._binary_refusal(".pdf")


# ── THE GATES DID NOT MOVE. Pinned by sha256 over their own source ────────────
#
# DEC-35 states the requirement exactly: "The binary sniff and the secret-name
# guard do not move one line." A pinned hash is that sentence made mechanical —
# the GrantsStore precedent, where consent is pinned to manifest BYTES so any
# change invalidates it by construction rather than by review.
GATE_SOURCE_SHA256 = {
    "_blocked_name":
        "a204b5e6f5bd3061ddf84d545b765d037275ac39571a9b71f9141719dbd74d03",
    "_bare_name_violation":
        "4ad43cc6b1d3c724a2cb6d00da82083677537da35b27d7d9f9e9a8f08f230a2c",
    "stage_file_gate":
        "199ee14d9abfd851b0106cb3a61ed8e9803c9d5dcf5e2822d1855c4379f1224b",
}


@pytest.mark.parametrize("name,expected", sorted(GATE_SOURCE_SHA256.items()))
def test_the_security_gates_are_BYTE_IDENTICAL_through_the_dec35_message_fix(
        name, expected):
    """If you are reading this because it failed: the message layer is what DEC-35
    authorises changing. A gate change needs its own ruling, not a passing edit
    made while the file happened to be open — and then this pin is updated
    deliberately, in that ruling's commit."""
    source = inspect.getsource(getattr(_fr, name)).encode("utf-8")

    assert hashlib.sha256(source).hexdigest() == expected


def test_the_staging_gate_still_answers_the_GENERIC_binary_note():
    """`stage_file_gate` is DEC-13's security gate for model-staged sandbox files,
    and it was deliberately left alone: the DEC-42 discipline is that the stronger
    property stays byte-identical while the weaker one is fixed. A staged file has
    no filesystem path to take a suffix from, so a format name there would be a
    guess dressed as a fact."""
    assert _fr.stage_file_gate("blob.pdf", b"%PDF\x00") == FILE_NOT_TEXT_AR
