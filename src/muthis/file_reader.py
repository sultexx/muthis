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

FILE_NOT_FOUND_AR = "ما لقيت الملف «{path}». تأكد من المسار الكامل واطلب القراءة من جديد."
FILE_BLOCKED_AR = "هذا الملف من ملفات الأسرار (مفاتيح/بيانات اعتماد) وقراءته ممنوعة حمايةً للمستخدم."
FILE_TOO_LARGE_AR = "الملف أكبر من الحد المسموح للقراءة. اطلب من المستخدم يفتح الجزء المطلوب أو حدّد ملفاً أصغر."
FILE_NOT_TEXT_AR = "هذا ملف ثنائي (غير نصّي) وما أقدر أقرأه كنص."
# DEC-35, closed by the doc_rag milestone: the binary refusal NAMES THE FORMAT.
# Live evidence (2026-07-25): a PDF was refused correctly and nothing leaked, but
# the note the model read reported a RETRYABLE reason — so the model did the
# rational thing and retried four different paths until the agentic cap stopped the
# turn. Four provider calls, ~$0.10, no answer. A refusal that misreports its
# REASON turns a TERMINAL condition into a retryable one, and the agentic loop
# exists precisely to retry, so the cost compounds. Naming the format ends the
# attempt at the FIRST call, and the note routes to the vision path — the DEC-17
# robots-refusal pattern, where a block becomes a showcase.
DOCUMENT_FORMATS = {
    ".pdf": "PDF", ".docx": "DOCX", ".doc": "DOC", ".epub": "EPUB",
    ".odt": "ODT", ".rtf": "RTF", ".xlsx": "XLSX", ".xls": "XLS",
    ".pptx": "PPTX", ".ppt": "PPT", ".djvu": "DjVu",
}
FILE_IS_DOCUMENT_AR = (
    "هذا ملف {fmt}، وأداة قراءة النص عندي تقرأ الملفات النصية فقط فما تنفع معه. "
    "ما فيه مسار ثاني يقرأه كنص، فلا تحاول بمسار أو صيغة ثانية. افتح الملف على "
    "الشاشة وأنا أشرح لك منه وأشير على المكان اللي تسأل عنه."
)
# Staging-only (sandbox files[], DEC-13): the name must be BARE — no directory.
FILE_NAME_NOT_BARE_AR = "اسم الملف لازم يكون بدون مسار أو مجلّد — مرّر اسم ملف بسيط فقط."
FILE_READ_ERROR_AR = "صار خطأ أثناء قراءة الملف، جرّب مرة ثانية أو تأكد من الصلاحيات."
FILE_READ_UNAVAILABLE_AR = "قراءة الملفات غير متاحة في هذا الوضع."
# A second read_local_file in the SAME pass — the same internal-directive
# family as the draw acks: answer from what you already have, explain now.
FILE_ALREADY_READ_AR = (
    "(توجيه داخلي من النظام — هذا النص ليس من المستخدم ولا يراه ولا يُقرأ "
    "بصوت عالٍ): قرأت ملفاً في هذه الجولة قبل قليل. لا تكرر القراءة — استخدم "
    "المحتوى اللي عندك وكمّل الشرح الآن."
)
TRUNCATION_NOTE_AR = (
    "\n(القراءة مقصوصة عند الحد الأقصى — اطلب read_local_file مرة ثانية مع "
    "start_line و end_line للجزء اللي يهمّك.)"
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
            logger.warning("[file_reader] read failed (%s: %s)", type(exc).__name__, exc)
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
            logger.info("[file_reader] refused secret-bearing name: %s", path)
            return FILE_BLOCKED_AR
        if not path.is_file():
            logger.info("[file_reader] not found: %s", path)
            return FILE_NOT_FOUND_AR.format(path=raw)
        resolved = path.resolve()
        if _blocked_name(resolved.name):  # symlink armor: judge the real target
            logger.info("[file_reader] refused secret-bearing target: %s", resolved)
            return FILE_BLOCKED_AR
        if resolved.stat().st_size > self._max_bytes:
            logger.info("[file_reader] refused oversize file: %s", resolved)
            return FILE_TOO_LARGE_AR
        data = resolved.read_bytes()
        if b"\x00" in data[:4096]:
            logger.info("[file_reader] refused binary file: %s", resolved)
            return _binary_refusal(resolved.suffix)   # DEC-35: name the format
        text = data.decode("utf-8-sig", errors="replace")
        body, start, end, total = self._numbered_slice(text, args)
        logger.info("[file_reader] read %s lines %d-%d of %d", resolved, start, end, total)
        header = f"محتوى الملف {resolved.name} (الأسطر {start}-{end} من {total}):"
        return f"{header}\n{body}"

    def _numbered_slice(self, text: str, args: dict[str, Any]) -> tuple[str, int, int, int]:
        """1-based numbered lines for the requested range (whole file when no
        range), char-capped at a line boundary with the truncation note."""
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
            body = body[:self._max_chars].rsplit("\n", 1)[0] + TRUNCATION_NOTE_AR
        return body, start, end, total


__all__ = [
    "FileReader", "ReadFileFn", "READ_FILE_TOOL", "stage_file_gate",
    "MAX_FILE_BYTES", "MAX_RETURN_CHARS", "DOCUMENT_FORMATS",
    "FILE_NOT_FOUND_AR", "FILE_BLOCKED_AR", "FILE_TOO_LARGE_AR",
    "FILE_NOT_TEXT_AR", "FILE_IS_DOCUMENT_AR", "FILE_NAME_NOT_BARE_AR",
    "FILE_READ_ERROR_AR", "FILE_READ_UNAVAILABLE_AR",
    "FILE_ALREADY_READ_AR", "TRUNCATION_NOTE_AR",
]
