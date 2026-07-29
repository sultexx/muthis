# tests/test_logging_privacy.py
"""
The composition root's logging PRIVACY policy (DEC-28, closing the 2026-07-25
LOGGING FINDING).

`httpx` logs the FULL request URL at INFO on every request, and `main.py` runs
the app at INFO — so before this policy a fetched page's query string, and a GET
search provider's QUERY (what the user asked while looking at their screen),
were written straight into the app log. That nullified DEC-17 ("content is NEVER
logged: domain + status + size"), DEC-20 (badge = DOMAIN only, precisely because
a URL can carry `?q=<the user's private query>`) and the first privacy law.

Two guards, both mutation-verified (DEC-12):
  1. the POLICY — after the composition root's logging setup, no third-party HTTP
     logger emits at INFO (while WARNING and above still surface);
  2. the BEHAVIOUR — a real fetch through the real `HardenedFetcher`, captured
     over EVERY logger at DEBUG (strictly more permissive than production), logs
     the DOMAIN and never the path or the query. The positive control (our own
     line IS present) keeps it from passing vacuously.

Run:  set PYTHONPATH=src && python -m pytest tests/test_logging_privacy.py -q
"""

from __future__ import annotations

import ast
import asyncio
import logging
import pathlib

import httpx
import pytest

from muthis.broker.net.fetcher import HardenedFetcher
from muthis.logging_policy import THIRD_PARTY_HTTP_LOGGERS, configure_logging

PRIVATE_QUERY = "what-is-my-private-question"
PAGE_PATH = "/page"
PAGE_URL = f"https://docs.example.com{PAGE_PATH}?q={PRIVATE_QUERY}"
PAGE_IP = "104.20.23.154"

# Named HERE, independently of the module's own tuple. Iterating that tuple would
# make the guard self-referential — deleting an entry would delete its
# expectation with it, and the test would stay green while the policy shrank
# (found by mutating the list, the same class of hole mutation caught in the
# search seam's key-leak check).
REQUIRED_SILENT_LOGGERS = frozenset({"httpx", "httpcore"})
CHECKED_LOGGERS = tuple(sorted(REQUIRED_SILENT_LOGGERS | set(THIRD_PARTY_HTTP_LOGGERS)))


@pytest.fixture(autouse=True)
def restore_logger_levels():
    """A test must not leave global logger levels changed for the rest of the
    session — the policy is production's to set, not this file's."""
    root = logging.getLogger()
    saved = [(root, root.level)] + [
        (logging.getLogger(name), logging.getLogger(name).level)
        for name in CHECKED_LOGGERS
    ]
    yield
    for logger, level in saved:
        logger.setLevel(level)


class _Capture(logging.Handler):
    """Captures EVERY record reaching the root, from any logger."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(f"{record.name}: {record.getMessage()}")


def _fetch_capturing_all_logs() -> tuple[object, list[str]]:
    """Run ONE real fetch through the real fetcher under the composition root's
    policy, capturing every emitted record. The root is opened to DEBUG — MORE
    permissive than production's INFO — so the policy, not the root level, is
    what silences the third-party line."""
    configure_logging()
    logging.getLogger().setLevel(logging.DEBUG)
    capture = _Capture()
    logging.getLogger().addHandler(capture)

    def handler(request):
        return httpx.Response(
            200,
            text="<html><body><p>hello</p></body></html>",
            headers={"content-type": "text/html"},
        )

    async def go():
        fetcher = HardenedFetcher(
            client_factory=lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                trust_env=False,
                follow_redirects=False,
            ),
            resolver=lambda hostname, port: [PAGE_IP],
            robots_enabled=False,
        )
        try:
            return await fetcher.fetch_readable(PAGE_URL)
        finally:
            await fetcher.aclose()

    try:
        return asyncio.run(go()), capture.messages
    finally:
        logging.getLogger().removeHandler(capture)


def test_the_policy_names_every_library_that_can_log_a_url():
    """The LIST is the policy, so shrinking it is a privacy change. Pinned by
    NAME here so removing an entry from `logging_policy.py` fails, instead of
    quietly removing its own expectation."""
    missing = sorted(REQUIRED_SILENT_LOGGERS - set(THIRD_PARTY_HTTP_LOGGERS))
    assert not missing, f"the logging policy no longer covers: {missing}"


def test_third_party_http_loggers_are_silenced_below_warning():
    """THE POLICY. The pre-assert pins the state this fix closed: inheriting the
    app's INFO root, these loggers WOULD emit their per-request URL line."""
    logging.getLogger().setLevel(logging.INFO)  # what the composition root sets
    for name in CHECKED_LOGGERS:
        logging.getLogger(name).setLevel(logging.NOTSET)  # inherit → the pre-fix state
        assert logging.getLogger(name).isEnabledFor(logging.INFO), name

    configure_logging()

    for name in CHECKED_LOGGERS:
        logger = logging.getLogger(name)
        assert not logger.isEnabledFor(logging.INFO), f"{name} still emits at INFO"
        # Silenced, not muted: a real transport error must still reach the log.
        assert logger.isEnabledFor(logging.WARNING), f"{name} lost its errors"


def test_the_composition_root_applies_the_policy_and_never_configures_logging_itself():
    """The policy is only worth what the ROOT actually calls. Reverting
    `main.py` to a bare `logging.basicConfig(...)` would leave every test above
    green while production leaked again — the precise silent revert this control
    exists to survive.

    A source scan (the `test_pointer_look_only.py` precedent) rather than an
    import: importing `muthis.main` runs `load_dotenv()` at module level, which
    would pull the developer's REAL keys — now including a live Tavily key —
    into the test process."""
    main_py = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis" / "main.py"
    tree = ast.parse(main_py.read_text(encoding="utf-8"))
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert "configure_logging" in called, "main.py no longer applies the logging policy"
    assert "basicConfig" not in called, (
        "main.py configures logging directly again — that bypasses the policy "
        "and reopens the URL leak (DEC-28)"
    )


def test_a_real_fetch_logs_the_domain_and_never_the_full_url():
    """THE BEHAVIOUR, end-to-end — the same measurement that PROVED the leak now
    proves the fix, over EVERY logger rather than only `muthis.*`."""
    result, messages = _fetch_capturing_all_logs()
    joined = "\n".join(messages)

    # POSITIVE CONTROL: the pipeline really ran and really logged (otherwise the
    # absence assertions below would pass on an empty log).
    assert result.ok is True
    assert any("muthis.broker.net" in m and "docs.example.com" in m for m in messages)
    assert "status=200" in joined

    # The leak, closed: no query, no path, no full URL — from ANY logger.
    assert PRIVATE_QUERY not in joined
    assert PAGE_PATH not in joined
    assert "HTTP Request" not in joined
    assert PAGE_IP not in joined  # the pinned IP rode the wire, never the log
