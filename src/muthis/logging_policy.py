# src/muthis/logging_policy.py
"""
The process-wide LOGGING POLICY — one definition, applied ONCE by the
composition root (`main.main()`), never by a component.

WHY THIS EXISTS (a deliberate privacy control — do NOT "clean it up"):
third-party HTTP libraries log the FULL request URL, and a URL carries private
content. Measured live on 2026-07-25, under this app's own `basicConfig(INFO)`:

    INFO httpx: HTTP Request: GET https://104.20.23.154/page?q=what+is+my+private+question
    INFO muthis.broker.net: [fetch] docs.example.com status=200 bytes=38 chars=5

Our line is exactly right; the line above it is a leak, and it nullifies three
signed rules at once — DEC-17 ("content is NEVER logged: domain + status + size,
English only"), DEC-20 (which restricts the on-screen domain badge to the DOMAIN
precisely because a URL can carry `?q=<the user's private query>`), and the
constitution's first privacy law (no transcripts / audio / screenshots by
default). It is the DEC-13 posture inverted: our guard is correct and a layer
beneath it silently undoes the property. Deleting the policy below silently
reopens all three.

SILENCE, NOT REDACTION (the ruling of 2026-07-25, DEC-28). A redaction filter
would put security-sensitive parsing INSIDE the logging path, where a single
defect leaks silently — the exact failure mode being eliminated. Silencing
PREVENTS the write by construction instead of sanitizing it afterwards. The
diagnostic loss is nil: the third-party line offers method + URL + status, while
our own line already carries domain + status + size, which is cleaner and more
useful; only the part that must never be written is lost. This covers the API
path too — a `POST https://api.anthropic.com/v1/messages` line has no diagnostic
value worth a privacy risk.

WHAT IS SILENCED, and why exactly these (verified against the installed
packages, not assumed):
  * `httpx` — THE leak. `logger.info('HTTP Request: %s %s "%s %d %s"', method,
    url, ...)` fires on EVERY request from one shared logger, so the same line
    covers the hardened fetcher, the search providers AND the Anthropic client.
  * `httpcore` — NOT today's leak: it emits at DEBUG only (everything routes
    through `_trace.py`'s `logger.debug`), so `basicConfig(INFO)` never shows it.
    It is silenced anyway because it carries the SAME content — its URL repr
    includes `target`, i.e. path + query — so a single `basicConfig(level=DEBUG)`
    would reopen the hole. Closing it by construction beats closing it by luck.
Deliberately NOT silenced (checked, and no full URL at INFO): `anthropic` (its
request logging is `log.debug`; its only INFO lines are token-compaction
messages on a path Mut'his does not use), `websockets` (INFO carries server
lifecycle and a reconnect-retry exception summary, never a URI), and `urllib3`
(no INFO call sites at all — and `src/` may not import it, per DEC-21-E).

A deliberate debugging session can still raise either logger AFTER startup; this
policy sets the floor at process entry, where a leak would otherwise be silent.

Pure stdlib, importable in isolation (the ≤300-line law) — deliberately NOT in
`main.py`, so a test can assert the policy without importing the composition
root, which calls `load_dotenv()` at import and would pull the developer's REAL
keys (now including a live Tavily key) into the test process. The policy is
DEFINED here and APPLIED at the root; nothing is scattered.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

logger = logging.getLogger("muthis.logging")

# English pipeline logs (the language-split law). Unchanged from the historical call.
LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"

# ─── THE DURABLE LOG, AND THE ONE COMBINATION IT REFUSES ─────────────────────
#
# WHY IT EXISTS. Every diagnosis this project has done reconstructed from ashes:
# `basicConfig` names no file, so the logs died with the terminal. The
# 2026-08-29 evaluation left three of four questions unanswerable for that one
# reason, and the sandbox incident had to be settled from DOCKER'S own daemon
# log because Mut'his had kept nothing of its own.
#
# THE REFUSAL, AND WHY IT IS THE WHOLE DESIGN. Until now the logs were
# EPHEMERAL, so DEC-61's PERMANENCE criterion was satisfied BY ACCIDENT rather
# than by design. Attaching a file handler re-classifies 248 existing call sites
# at once — from "whoever is watching the console" to "anyone with the disk, and
# whoever receives a bug report" — and none of them was written under that
# second regime. The one combination that must never exist is therefore
# MUTHIS_DEBUG=1 (which unseals the STT transcript and the submitted code) with
# a durable log: the project's most sensitive content, made permanent.
#
# IT FAILS CLOSED, AND IT IS STRUCTURAL RATHER THAN CHECKED. The alternative — a
# filter that strips debug content on its way to the file — depends on
# classification discipline across 248 unaudited sites, where one miss is a
# silent permanent leak. This instead makes the pair UNREPRESENTABLE: the handler
# is constructed at exactly ONE place in the tree, and that place is reachable
# only past the debug guard. There is no `if debug: skip` further down that
# someone could delete, because no code path runs from MUTHIS_DEBUG=1 to a
# handler at all — the `symbol_map` discipline, one domain over. A test asserts
# the "exactly one construction site" half, because that is what makes the
# property checkable in ONE place instead of 248.
DEBUG_ENV = "MUTHIS_DEBUG"

# Outside the repository ON PURPOSE: a log inside the tree is one `git add -A`
# from publication, and this file is the one artifact designed to outlive the
# session. `~/.muthis/` is already the user-data home (it holds `models`).
LOG_DIR = Path.home() / ".muthis" / "logs"
LOG_FILENAME = "muthis.log"
LOG_MAX_BYTES = 2 * 1024 * 1024      # 2 MB per file …
LOG_BACKUPS = 3                      # … × 3 backups — an ~8 MB ceiling, bounded
                                     # like every other growth surface here.

# The third-party HTTP loggers held at WARNING. See the module docstring for why
# each one is on (or off) this list — the list is the policy, so any change to it
# is a privacy decision, not a tidy-up.
THIRD_PARTY_HTTP_LOGGERS: tuple[str, ...] = ("httpx", "httpcore")


def silence_third_party_http_logs() -> None:
    """Raise every third-party HTTP logger to WARNING, so a request line — which
    carries the full URL — can never be written. Real errors still surface at
    WARNING and above; only the per-request URL line is prevented."""
    for name in THIRD_PARTY_HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def debug_content_enabled(debug: Optional[bool] = None) -> bool:
    """The ONE read of MUTHIS_DEBUG that the logging policy owns. `debug` is the
    test seam; production reads the environment, the `stt.py` shape."""
    return os.getenv(DEBUG_ENV) == "1" if debug is None else debug


def attach_file_log(level: int = logging.INFO, *,
                    debug: Optional[bool] = None,
                    directory: Optional[Path] = None) -> Optional[Path]:
    """Attach the rotating file log, or REFUSE and stay console-only.

    Returns the live log path, or None when it refused or could not write. The
    debug guard is the FIRST statement and returns before anything is built, so
    the handler below is unreachable with MUTHIS_DEBUG=1 — that is the property,
    not a check that happens to run first.

    IT DEGRADES THE DIAGNOSIS, NEVER THE APP. An unwritable directory (a locked
    profile, a full disk, a roaming home) leaves the console log exactly as it is
    today. Losing the durable log is a worse diagnosis; raising here would be a
    worse product, and Law 11 already settled which way that trades."""
    if debug_content_enabled(debug):
        logger.warning(
            "[logging] MUTHIS_DEBUG=1 — the durable log is REFUSED, console only. "
            "Debug logging unseals the transcript and submitted code; a file "
            "would make them permanent. Unset it to keep a session's log.")
        return None
    # THE ONLY FileHandler CONSTRUCTION IN THE TREE. Reachable only past the
    # guard above — see the module note on why this is structural.
    target = (directory if directory is not None else LOG_DIR)
    try:
        target.mkdir(parents=True, exist_ok=True)
        path = target / LOG_FILENAME
        handler = RotatingFileHandler(
            path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8")
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler.setLevel(level)
        logging.getLogger().addHandler(handler)
    except OSError:
        # The PATH is not logged (DEC-61) — the failure is, and the app runs on.
        logger.warning("[logging] durable log unavailable — console only")
        return None
    logger.info("[logging] durable log attached (%d KB x %d)",
                LOG_MAX_BYTES // 1024, LOG_BACKUPS)
    return path


def configure_logging(level: int = logging.INFO,
                      *, debug: Optional[bool] = None,
                      directory: Optional[Path] = None) -> Optional[Path]:
    """The composition root's ONE logging call: configure the app's own logs,
    apply the privacy policy above, then attach the durable log unless
    MUTHIS_DEBUG=1 refuses it. Transcript logging stays gated behind
    `MUTHIS_DEBUG` inside the components — never enabled here.

    ORDER IS LOAD-BEARING. `basicConfig` installs the console handler only when
    the root has NONE, so attaching the file first would silence the console for
    the whole run. And the third-party silencing applies to LOGGER levels, so it
    reaches the file handler too — a full request URL cannot be written to disk
    any more than it could be printed."""
    logging.basicConfig(level=level, format=LOG_FORMAT)
    silence_third_party_http_logs()
    return attach_file_log(level, debug=debug, directory=directory)


__all__ = [
    "LOG_FORMAT",
    "THIRD_PARTY_HTTP_LOGGERS",
    "silence_third_party_http_logs",
    "configure_logging",
    "attach_file_log",
    "debug_content_enabled",
    "DEBUG_ENV",
    "LOG_DIR",
    "LOG_FILENAME",
    "LOG_MAX_BYTES",
    "LOG_BACKUPS",
]
