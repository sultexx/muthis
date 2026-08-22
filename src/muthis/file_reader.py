# src/muthis/file_reader.py
"""
FileReader — the read_local_file LOOK-tier tool (v7 Phase 4, the Pedagogical
Analyzer).

Mut'his can now READ a local text file (code / SQL / config / notes) so his
explanation is grounded in the file's REAL content instead of squinting at
screenshot pixels. Reading is PASSIVE — it moves nothing, clicks nothing,
types nothing, writes nothing — so the LOOK-only action boundary (no
click/type/press/clipboard) is untouched; this is a perception tool like
request_screen_refresh, and like it, it never flips the draw gate.

SAFETY GATES (the model chooses the path, so the reader must be defensive):
  * SECRET-BEARING names are refused by NAME on the raw AND resolved path
    (symlink armor): .env / .env.* / key material (.pem/.key/.pfx/...) /
    id_rsa* / .netrc / credentials — their content must never enter the
    conversation (it would ride to the provider with the next request).
  * BINARY files are refused (NUL sniff in the head) — this is a TEXT reader.
  * SIZE is bounded twice: files over `max_bytes` are refused outright, and
    the returned text is capped at `max_chars` with an Arabic truncation note
    telling the model to request a line range instead.
  * A TRUNCATED PYTHON FILE also carries a SYMBOL MAP of what was cut (DEC-113
    — `symbol_map.py`). Truncation only: on a whole file the same map measured
    a TIE and one regression, so it is attached where it was measured to win
    and nowhere else. That is structural — the map is built inside the
    truncation branch, so no whole-file path reaches it.
  * NEVER raises — every failure returns a short Arabic tool_result note
    (the NO_SCREENSHOT_TOOL_RESULT_AR precedent); the turn always continues.

PRIVACY (Law: no content logging): logs carry the path and the outcome in
English only — never a byte of file content.

Content format: 1-based numbered lines ("   12 | ...") so the model can say
"السطر ١٢" and aim its whiteboard rectangles at the lines it is analyzing.

Pure stdlib (asyncio/logging/pathlib); importable in isolation. The blocking
I/O runs via asyncio.to_thread (the screen_capture convention). stubs.py owns
the logging stub default; main.py injects `FileReader().read`.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from .symbol_map import build_symbol_map

logger = logging.getLogger("muthis.file_reader")

# The tool name — the schema literal in cloud/tool_schemas.py must match.
READ_FILE_TOOL = "read_local_file"

# The orchestrator's injected seam shape (production: FileReader().read).
ReadFileFn = Callable[[dict[str, Any]], Awaitable[str]]

# Hard ceilings: a "teaching file" is small; anything bigger is refused (bytes)
# or truncated (returned chars ≈ a few thousand tokens, budget-friendly).
MAX_FILE_BYTES = 2_000_000
MAX_RETURN_CHARS = 16_000

# Secret-bearing names, matched case-insensitively on BOTH the raw and the
# RESOLVED path name (a symlink must not launder a blocked target).
BLOCKED_NAMES = frozenset({".env", ".netrc", ".npmrc", ".pypirc", ".git-credentials"})
BLOCKED_PREFIXES = (".env.", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", "credentials")
BLOCKED_SUFFIXES = frozenset({".pem", ".key", ".pfx", ".p12", ".der", ".kdbx", ".keystore"})

# ─── Model-facing Arabic tool_result surfaces (logs stay English) ─────────────
# EXTRACTED to `file_reader_notes.py` at DEC-113 (a MOVE ONLY, nothing reworded):
# the symbol map took this file 280 → 312 and the ≤300 law turned the arrival
# into an extraction. Re-exported below, so every existing import still resolves
# against `muthis.file_reader` and no call site changed.
from .file_reader_notes import (  # noqa: E402 — re-export, kept at its old home
    DOCUMENT_FORMATS, FILE_ALREADY_READ_AR, FILE_BLOCKED_AR, FILE_IS_DOCUMENT_AR,
    FILE_NAME_NOT_BARE_AR, FILE_NOT_FOUND_AR, FILE_NOT_TEXT_AR, FILE_READ_ERROR_AR,
    FILE_READ_UNAVAILABLE_AR, FILE_TOO_LARGE_AR, TRUNCATION_NOTE_AR,
)


def _blocked_name(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered in BLOCKED_NAMES
        or lowered.startswith(BLOCKED_PREFIXES)
        or Path(lowered).suffix in BLOCKED_SUFFIXES
    )


def _bare_name_violation(name: str) -> bool:
    """DEC-13: a STAGED sandbox file name must be BARE — the §2.1 schema declares
    files[].name as a plain file name with NO directory. A path separator (`/` or
    `\\`) or a `..` traversal reference is REFUSED outright (never normalized), so
    `/work` escape is closed BY CONSTRUCTION, not by an incidental write failure.
    A `..` in the MIDDLE of a bare name (e.g. `archive..bak`) is a legal file name,
    not a traversal segment, and is intentionally allowed (do not over-reject)."""
    return "/" in name or "\\" in name or name == ".."


def _binary_refusal(suffix: str) -> str:
    """DEC-35's MESSAGE fix, and ONLY a message fix.

    The binary GATE decided to refuse before this function is consulted; all this
    chooses is the sentence. A known document format gets a note that names it and
    closes the attempt; anything else keeps the generic binary note, because
    claiming a format we did not recognise would be a new inaccuracy in place of
    the old one.

    Deliberately NOT called from `stage_file_gate`: that is DEC-13's security gate
    for model-staged sandbox files, and this is the DEC-42 discipline — the
    stronger property stays byte-identical while the weaker one is fixed. A message
    defect is repaired inside the message layer; the guard beside it is not
    "improved" while the file happens to be open."""
    named = DOCUMENT_FORMATS.get(suffix.lower())
    return FILE_IS_DOCUMENT_AR.format(fmt=named) if named else FILE_NOT_TEXT_AR


def _log_shape(path: Path, size: Optional[int] = None) -> str:
    """ALL a log line may say about a file: its EXTENSION and its SIZE.

    NEVER the name, NEVER the directory, NEVER the path.

    THIS MODULE'S OWN RECORDED DISCIPLINE USED TO SAY "path and outcome in
    English, NEVER content", and the I6 breach proved that clause wrong about
    WHICH HALF IS SENSITIVE. The path carries the user's document name and the
    folder it lives in, so it is as private as the content — measured live, a
    real corpus file name reached the logs through these very lines while the
    content never did. `I5 passed while I6 failed` is that fact in one sentence.

    LOGS, NOT SPEECH. The Arabic note returned to the model still names the file,
    and `doc_rag` still uses the file's own name as a speakable `doc_id`. The
    distinction is not secrecy but PERMANENCE AND AUDIENCE: the user named the
    file and the user is listening, so saying it back is correct and useful — a
    log persists past the session, is read by other eyes, and travels in a bug
    report.

    The shape below is what `broker/net` already logs (domain + status + size)
    and what `doc_rag` already logs (`extract .pdf: blocks=…`): enough to debug a
    refusal, nothing that identifies the document."""
    suffix = path.suffix.lower() or "(no suffix)"
    return suffix if size is None else f"{suffix} bytes={size}"


def stage_file_gate(name: str, data: bytes) -> Optional[str]:
    """The gate for a model-STAGED sandbox file (sandbox_exec, T5 / DEC-13).
    STRICTER than FileReader.read(): read() resolves a real filesystem path, but a
    staged file has NO path — the schema declares files[].name as a BARE name. So
    this (1) REFUSES any name with a path separator or a `..` traversal reference
    OUTRIGHT (DEC-13 — enforce 'no directory' by construction; explicit refusal,
    never silent normalization; closes `/work` escape at the root), THEN (2)
    applies the SAME secret-name + binary refusals as read() to that bare name
    (§3.3). Returns None when the file may be staged, else the Arabic refusal."""
    if _bare_name_violation(name):
        return FILE_NAME_NOT_BARE_AR
    if _blocked_name(name):
        return FILE_BLOCKED_AR
    if b"\x00" in data[:4096]:
        return FILE_NOT_TEXT_AR
    return None


def _truncation_map(text: str, suffix: str) -> str:
    """The DEC-113 symbol map, and the ONLY site that attaches it.

    Reached from the truncation branch alone, which is what makes "a whole file
    gets no map" STRUCTURAL: there is no whole-file path into this function, so
    the ruling cannot be undone by deleting a check. Python only — the map is
    `ast`, and `ast` has nothing to say about SQL or a config file.

    Returns "" rather than raising or noting: an unparseable file (the ordinary
    state of one being edited) must leave the reader's output exactly as it
    stands today."""
    if suffix.lower() != ".py":
        return ""
    body = build_symbol_map(text)
    return f"\n{body}" if body else ""


def _int_arg(args: dict[str, Any], key: str) -> Optional[int]:
    """A best-effort int (the model occasionally sends "12"); None on garbage."""
    value = args.get(key)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class FileReader:
    """The read_local_file executor: safety gates → decode → numbered lines.
    One per process at the composition root; stateless between calls."""

    def __init__(self, *, max_bytes: int = MAX_FILE_BYTES,
                 max_chars: int = MAX_RETURN_CHARS) -> None:
        self._max_bytes = max_bytes
        self._max_chars = max_chars

    async def read(self, args: dict[str, Any]) -> str:
        """The ReadFileFn seam: tool args in, Arabic-noted content out. The
        blocking file I/O runs off-loop; NEVER raises (a failed read must
        degrade the pass, not kill the turn)."""
        try:
            return await asyncio.to_thread(self._read_blocking, args)
        except Exception as exc:  # noqa: BLE001 — the turn must survive any I/O surprise
            # The EXCEPTION TEXT is dropped, not shortened: OSError.__str__
            # embeds the offending path verbatim ("[Errno 2] ... : 'C:\\...'"),
            # so logging `exc` re-opens the leak the type name alone cannot.
            # `broker/net/fetcher.py` already logs exactly this shape.
            logger.warning("[file_reader] read failed (%s)", type(exc).__name__)
            return FILE_READ_ERROR_AR

    # ───────────────────────────── Internals ─────────────────────────────

    def _read_blocking(self, args: dict[str, Any]) -> str:
        raw = str(args.get("path") or "").strip().strip('"')
        if not raw:
            logger.info("[file_reader] refused: empty path")
            return FILE_NOT_FOUND_AR.format(path="")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if _blocked_name(path.name):
            logger.info("[file_reader] refused secret-bearing name: %s", _log_shape(path))
            return FILE_BLOCKED_AR
        if not path.is_file():
            logger.info("[file_reader] not found: %s", _log_shape(path))
            return FILE_NOT_FOUND_AR.format(path=raw)
        resolved = path.resolve()
        if _blocked_name(resolved.name):  # symlink armor: judge the real target
            logger.info("[file_reader] refused secret-bearing target: %s", _log_shape(resolved))
            return FILE_BLOCKED_AR
        if resolved.stat().st_size > self._max_bytes:
            # The cap is logged rather than the actual size, so the GATE line
            # above keeps its single stat() call and stays byte-identical.
            logger.info("[file_reader] refused oversize file: %s over %d bytes",
                        _log_shape(resolved), self._max_bytes)
            return FILE_TOO_LARGE_AR
        data = resolved.read_bytes()
        if b"\x00" in data[:4096]:
            logger.info("[file_reader] refused binary file: %s",
                        _log_shape(resolved, len(data)))
            return _binary_refusal(resolved.suffix)   # DEC-35: name the format
        text = data.decode("utf-8-sig", errors="replace")
        body, start, end, total = self._numbered_slice(text, args, resolved.suffix)
        logger.info("[file_reader] read %s lines %d-%d of %d",
                    _log_shape(resolved, len(data)), start, end, total)
        header = f"محتوى الملف {resolved.name} (الأسطر {start}-{end} من {total}):"
        return f"{header}\n{body}"

    def _numbered_slice(self, text: str, args: dict[str, Any],
                        suffix: str = "") -> tuple[str, int, int, int]:
        """1-based numbered lines for the requested range (whole file when no
        range), char-capped at a line boundary with the truncation note — and,
        on a truncated Python file ONLY, the symbol map for what was cut.

        THE MAP IS APPENDED AFTER THE CAP, SO THE PAYLOAD GROWS rather than the
        map displacing code lines. Deliberate (DEC-113): shrinking the delivered
        code to make room would pay for the map with the very thing the map
        exists to compensate for."""
        lines = text.splitlines() or [""]
        total = len(lines)
        start = _int_arg(args, "start_line") or 1
        end = _int_arg(args, "end_line") or total
        if end < start:
            start, end = end, start
        start = min(max(start, 1), total)
        end = min(max(end, 1), total)
        numbered = [f"{i:>5} | {line}" for i, line in enumerate(lines[start - 1:end], start)]
        body = "\n".join(numbered)
        if len(body) > self._max_chars:
            body = (body[:self._max_chars].rsplit("\n", 1)[0] + TRUNCATION_NOTE_AR
                    + _truncation_map(text, suffix))
        return body, start, end, total


__all__ = [
    "FileReader", "ReadFileFn", "READ_FILE_TOOL", "stage_file_gate",
    "MAX_FILE_BYTES", "MAX_RETURN_CHARS", "DOCUMENT_FORMATS",
    "FILE_NOT_FOUND_AR", "FILE_BLOCKED_AR", "FILE_TOO_LARGE_AR",
    "FILE_NOT_TEXT_AR", "FILE_IS_DOCUMENT_AR", "FILE_NAME_NOT_BARE_AR",
    "FILE_READ_ERROR_AR", "FILE_READ_UNAVAILABLE_AR",
    "FILE_ALREADY_READ_AR", "TRUNCATION_NOTE_AR",
]
