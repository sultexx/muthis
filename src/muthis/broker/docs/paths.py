# src/muthis/broker/docs/paths.py
"""
What the model SENT, turned into a path we can actually open — and what we had
to do to it.

THE DEFECT THIS CLOSES, from a live log: the model passed a PERCENT-ENCODED path
(`.../My%20Documents/book.pdf`). No such file exists, the extractor raised
`OSError`, and the model read a generic "something went wrong opening it" note
that named neither the cause nor the one action that fixes it. The path was
recoverable — `%20` is a space — and nothing tried.

THE RULE: **THE RAW PATH WINS WHENEVER IT EXISTS.** Decoding is a FALLBACK, never
a rewrite, because a real filename may legitimately contain a literal `%20` and
silently opening a different file would be the wrong-document failure this package
already refuses elsewhere (DEC-63 layer 3: guessing is only safe when guessing
wrong is observable — here it would not be).

So the order is: try what we were given; only if it does not exist AND it carries
a percent sequence, try the decoded form; if neither exists, report that it LOOKED
url-encoded so the note can say so. A decode that changes nothing is not reported
as a decode.

PRIVACY (DEC-61): this module logs LENGTHS and BOOLEANS — never a path, never a
filename, never a directory. A document path is the user's own file name and the
folder it lives in, which is exactly the datum DEC-61 removed from the logs.

Pure stdlib, importable in isolation, and it decides nothing about zones,
formats or notes — it answers ONE question and returns.
"""

from __future__ import annotations

import dataclasses
import logging
import pathlib
import re
import urllib.parse

logger = logging.getLogger("muthis.broker.docs")

# A percent sequence: `%` followed by two hex digits. Deliberately NOT a loose
# `%` test — a bare percent in a filename is ordinary and means nothing here.
_PERCENT_RE = re.compile(r"%[0-9A-Fa-f]{2}")


@dataclasses.dataclass(frozen=True)
class ResolvedPath:
    """The path to open, plus what the resolution had to notice."""

    path: pathlib.Path
    url_encoded: bool = False   # a percent sequence was present in what we were sent
    decoded: bool = False       # we actually swapped to the decoded form

    @property
    def exists(self) -> bool:
        return _exists(self.path)


def _exists(path: pathlib.Path) -> bool:
    """Never raises: a malformed path is simply not a file we can open."""
    try:
        return path.is_file()
    except OSError:
        return False


def resolve_document_path(raw: pathlib.Path) -> ResolvedPath:
    """Pick the path to actually open, preferring EXACTLY what we were given."""
    text = str(raw)
    if not _PERCENT_RE.search(text):
        return ResolvedPath(raw)

    decoded = pathlib.Path(urllib.parse.unquote(text))
    if decoded == raw:                       # nothing to gain
        return ResolvedPath(raw, url_encoded=True)
    if _exists(raw):                         # the raw path WINS when it is real
        return ResolvedPath(raw, url_encoded=True)
    if _exists(decoded):
        logger.info("[doc_rag] path looked URL-encoded and the decoded form "
                    "exists — opening that (raw_len=%d decoded_len=%d)",
                    len(text), len(str(decoded)))
        return ResolvedPath(decoded, url_encoded=True, decoded=True)
    # NEITHER exists. Hand back the raw form so the failure is reported against
    # what the model actually sent, with the flag the note needs.
    logger.info("[doc_rag] path looked URL-encoded and NEITHER form exists "
                "(raw_len=%d decoded_len=%d)", len(text), len(str(decoded)))
    return ResolvedPath(raw, url_encoded=True)


__all__ = ["ResolvedPath", "resolve_document_path"]
