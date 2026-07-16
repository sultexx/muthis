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

import logging

import pytest

from muthis.file_reader import (
    FILE_BLOCKED_AR,
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
async def test_stub_read_file_answers_unavailable():
    assert await stub_read_file({"path": "C:/anything.py"}) == FILE_READ_UNAVAILABLE_AR
