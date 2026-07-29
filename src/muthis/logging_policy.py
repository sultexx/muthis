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

Pure stdlib, importable in isolation (§17.4) — deliberately NOT in `main.py`, so
a test can assert the policy without importing the composition root, which calls
`load_dotenv()` at import and would pull the developer's REAL keys (now including
a live Tavily key) into the test process. The policy is DEFINED here and APPLIED
at the root; nothing is scattered.
"""

from __future__ import annotations

import logging

# English pipeline logs (the language-split law). Unchanged from the historical call.
LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"

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


def configure_logging(level: int = logging.INFO) -> None:
    """The composition root's ONE logging call: configure the app's own logs,
    then apply the privacy policy above. Transcript logging stays gated behind
    `MUTHIS_DEBUG` inside the components — never enabled here."""
    logging.basicConfig(level=level, format=LOG_FORMAT)
    silence_third_party_http_logs()


__all__ = [
    "LOG_FORMAT",
    "THIRD_PARTY_HTTP_LOGGERS",
    "silence_third_party_http_logs",
    "configure_logging",
]
