# tests/test_net_robots.py
"""
RFC 9309 §2.3.1 — WHAT A ROBOTS.TXT FETCH MEANS, driven through the REAL fetcher.

THE DEFECT. `robots.py` said "a miss / unreachable / unparseable robots defaults
to ALLOW (the crawler standard)". For the case that matters the standard says the
opposite: a robots.txt that is UNREACHABLE — a 5xx or a network failure — means
the crawler MUST assume COMPLETE DISALLOW (§2.3.1.4). A comment asserted
compliance with the very rule the code violated, and no test pinned either.

WHAT EACH GUARD HOLDS, each beside a control in the same harness:
  * a 5xx robots.txt: the page is NEVER requested, and the model reads a note
    stating the status — even when the 5xx body itself says "Allow";
  * a network failure on robots.txt (connection, timeout, a name that does not
    resolve): the page is never requested, and the model reads the transport's
    own note — including the case where the page's own lookup would have worked;
  * an unreachable robots.txt is NEVER cached: the next fetch asks again;
  * a 4xx, and the redirect cap, stay "unavailable" (§2.3.1.3, §2.3.1.2): the URL
    is allowed — even when the 4xx body says "Disallow", because it is not rules;
  * a refusal of OUR OWN (the SSRF guard) still allows, so the page fetch meets
    the guard and the model reads the guard's note, never a robots one.

No test imports `muthis.main` (standing rule): live credentials.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
import pytest

from muthis.broker.net import HardenedFetcher
from muthis.broker.net.address_guard import BLOCKED_ADDRESS_AR, UNRESOLVABLE_AR
from muthis.broker.net.fetcher import ROBOTS_BLOCKED_AR, USER_AGENT
from muthis.broker.net.http_status import (
    RETRY_FUTILE_AR, RETRY_LATER_AR, robots_unreachable_note,
)
from muthis.broker.net.transport import NETWORK_ERROR_AR, TIMEOUT_AR

HOST = "r.example"
URL = f"https://{HOST}/page"
OTHER = f"https://{HOST}/other"
IP = ["93.184.216.34"]
PAGE = "The page body PAGE-CANARY-51c2 that robots decides about."
ALLOW_ALL = "User-agent: *\nAllow: /"
DISALLOW_ALL = "User-agent: *\nDisallow: /"


def _robots(status: int, rules: str) -> httpx.Response:
    return httpx.Response(status, text=rules, headers={"content-type": "text/plain"})


def _run(robots_answers, urls, *, resolver=None, robots_handler=None):
    """Fetch `urls` in order through ONE fetcher, robots ON. Each robots.txt
    request consumes the next of `robots_answers` — a Response is returned, an
    exception raised. Returns (results, every path the site was asked for)."""
    answers = iter(robots_answers)
    seen: list[str] = []

    def handler(request):
        seen.append(request.url.path)
        if robots_handler is not None and request.url.path != "/page":
            return robots_handler(request)
        if request.url.path == "/robots.txt":
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer
        return httpx.Response(200, text=f"<html><body><p>{PAGE}</p></body></html>",
                              headers={"content-type": "text/html"})

    async def go():
        fetcher = HardenedFetcher(
            client_factory=lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(handler), trust_env=False,
                follow_redirects=False, headers={"User-Agent": USER_AGENT}),
            resolver=resolver or (lambda hostname, port: IP),
            robots_enabled=True)
        try:
            return [await fetcher.fetch_readable(u) for u in urls]
        finally:
            await fetcher.aclose()

    return asyncio.run(go()), seen


# ─── §2.3.1.4 — a 5xx: COMPLETE DISALLOW ─────────────────────────────────────

@pytest.mark.parametrize("status", (500, 502, 503, 504))
def test_a_5xx_robots_txt_is_complete_disallow_and_the_page_is_never_requested(status):
    """The body ALLOWS everything — and is not rules, because a 5xx is not a 2xx."""
    (result,), seen = _run([_robots(status, ALLOW_ALL)], [URL])
    assert seen == ["/robots.txt"], f"the page was requested after a {status} robots.txt"
    assert result.ok is False
    assert result.text_ar == robots_unreachable_note(status)
    assert str(status) in result.text_ar and PAGE not in result.text_ar


def test_the_CONTROL_a_2xx_with_the_same_rules_allows():
    (result,), seen = _run([_robots(200, ALLOW_ALL)], [URL])
    assert seen == ["/robots.txt", "/page"]
    assert result.ok is True and "PAGE-CANARY-51c2" in result.content


# ─── §2.3.1.4 — a network failure: COMPLETE DISALLOW, the transport's own note ─

@pytest.mark.parametrize("failure,note", [
    (httpx.ConnectError("connection refused"), NETWORK_ERROR_AR),
    (httpx.ReadTimeout("too slow"), TIMEOUT_AR),
], ids=["connect-error", "read-timeout"])
def test_a_network_failure_on_robots_txt_is_complete_disallow(failure, note):
    (result,), seen = _run([failure], [URL])
    assert "/page" not in seen, "the page was requested with robots.txt unreachable"
    assert result.ok is False and result.text_ar == note


def test_a_robots_txt_name_that_fails_to_resolve_blocks_the_page_even_if_it_resolves_next():
    """The page's own lookup WOULD succeed — the resolver fails only once. The
    rules could not be read, so the page is not fetched, and the model reads the
    precise note (a typo'd domain still reads as one)."""
    calls = {"n": 0}

    def flaky(hostname, port):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("temporary DNS failure")
        return IP

    (result,), seen = _run([], [URL], resolver=flaky)
    assert calls["n"] == 1 and seen == [], "the page was resolved or requested"
    assert result.ok is False and result.text_ar == UNRESOLVABLE_AR


# ─── an outage is a state, not a rule: NEVER cached ──────────────────────────

def test_an_unreachable_robots_txt_is_never_cached_so_a_recovery_is_seen():
    (first, second), seen = _run([_robots(503, ALLOW_ALL), _robots(200, ALLOW_ALL)],
                                 [URL, URL])
    assert first.ok is False and first.text_ar == robots_unreachable_note(503)
    assert seen == ["/robots.txt", "/robots.txt", "/page"], "robots.txt was not asked again"
    assert second.ok is True and "PAGE-CANARY-51c2" in second.content


def test_the_CONTROL_readable_rules_ARE_cached_in_this_harness():
    """One robots.txt answer for two pages: a second request would exhaust it."""
    (first, second), seen = _run([_robots(200, ALLOW_ALL)], [URL, OTHER])
    assert first.ok and second.ok
    assert seen.count("/robots.txt") == 1


# ─── §2.3.1.3 / §2.3.1.2 — "unavailable": allowed ───────────────────────────

@pytest.mark.parametrize("status", (401, 403, 404, 410, 429))
def test_a_4xx_robots_txt_is_unavailable_and_allows(status):
    """The body DISALLOWS everything — and is not rules either. (The stdlib's own
    `read()` would refuse all on a 401/403; RFC 9309 says MAY access.)"""
    (result,), seen = _run([_robots(status, DISALLOW_ALL)], [URL])
    assert seen == ["/robots.txt", "/page"]
    assert result.ok is True and "PAGE-CANARY-51c2" in result.content


def test_the_CONTROL_a_2xx_disallow_IS_obeyed_with_its_own_note():
    (result,), seen = _run([_robots(200, DISALLOW_ALL)], [URL])
    assert seen == ["/robots.txt"]
    assert result.ok is False and result.text_ar == ROBOTS_BLOCKED_AR


def test_more_than_five_robots_redirects_is_unavailable_and_allows():
    def redirects(request):
        hop = 0 if request.url.path == "/robots.txt" else int(request.url.path[2:]) + 1
        return httpx.Response(301, headers={"location": f"/r{hop}"})

    (result,), seen = _run([], [URL], robots_handler=redirects)
    assert seen[:7] == ["/robots.txt", "/r0", "/r1", "/r2", "/r3", "/r4", "/page"]
    assert result.ok is True and "PAGE-CANARY-51c2" in result.content


# ─── a refusal of OUR OWN reads no rules — the guard keeps its own note ───────

def test_an_ssrf_refused_robots_txt_leaves_the_page_to_the_guard_and_its_note():
    (result,), seen = _run([], [URL], resolver=lambda hostname, port: ["127.0.0.1"])
    assert seen == [], "an internal address was contacted"
    assert result.ok is False and result.text_ar == BLOCKED_ADDRESS_AR


# ─── the note the model reads, and the log ───────────────────────────────────

@pytest.mark.parametrize("status", (500, 503))
def test_the_robots_note_carries_the_note_laws_three_obligations(status):
    note = robots_unreachable_note(status)
    assert f"برمز الحالة {status}" in note                     # what happened...
    assert "فما فتحت الصفحة ولا قرأت منها شي" in note         # ...and nothing was read
    assert RETRY_LATER_AR in note and RETRY_FUTILE_AR not in note  # time, not a retry now
    assert "بدل التكرار" in note and "خبّر المستخدم" in note  # a move the model can make
    for invitation in ("جرّب مرة ثانية", "حاول مرة ثانية", "أعد المحاولة", "أعد فتح"):
        assert invitation not in note


def test_the_refusal_reason_is_logged_and_the_disallow_line_is_unchanged(caplog):
    with caplog.at_level(logging.DEBUG, logger="muthis.broker.net"):
        _run([_robots(503, ALLOW_ALL)], [URL])
        _run([_robots(200, DISALLOW_ALL)], [URL])
    assert f"[fetch] {HOST} robots-unreachable" in caplog.text
    assert f"[fetch] {HOST} robots-disallowed" in caplog.text
    assert "PAGE-CANARY" not in caplog.text
