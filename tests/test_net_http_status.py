# tests/test_net_http_status.py
"""
DEC-149 ⑤, CLOSED — ONLY A 2xx IS THE PAGE.

THE DEFECT. The fetcher never tested `status`. A 403 block page came back
`ok=True`, reached the model under «نص الصفحة من <domain>:» as the site's
content, was CACHED for the session as a success — a re-fetch returned it without
a request, even after the site recovered — and put its domain on the badge as a
source read. Live at DEC-149 ③: `[fetch] alnassr.sa status=403 bytes=6064
chars=460`. The only sign that the text was a block page was its own wording.

THE THREE PROPERTIES, each driven through the REAL fetcher on a MockTransport (no
network), and each beside a CONTROL in the same harness proving the check can see
what it guards — an absence reported by an instrument that could never have seen
the thing is not evidence:
  * NEVER CONTENT — a non-success reaches the model as a failure STATING its
    status: at the fetcher, and on the production path (the real router, plugin
    and TurnPass), where what is asserted is what the model actually reads;
  * NEVER CACHED — so the site that recovers is read on the next fetch;
  * NEVER BADGED — nothing was read, so nothing is claimed as a source.
Mutation-verified: the status check removed (a 403 becomes content), the failure
cached, the failure badged — each RED.

THE NOTE carries the note law's three obligations (DEC-58, AGENTS.md): what
happened, whether a retry can help — TRUE to the status class — and the move the
model can make instead.

No test imports `muthis.main` (standing rule): live credentials.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
import pytest

from muthis.broker.net import FetchedDomains, HardenedFetcher
from muthis.broker.net.fetcher import EXTRACT_FAILED_AR, PDF_UNSUPPORTED_AR, USER_AGENT
from muthis.broker.net.http_status import (
    RETRY_FUTILE_AR, RETRY_LATER_AR, is_success, is_transient, status_note,
)
from muthis.cloud.protocol import ToolCall, TurnComplete, UserInput
from muthis.kernel.highlight_gate import HighlightGate
from muthis.kernel.tool_result_pairing import WEB_FETCH_TOOL
from muthis.kernel.tool_router import ToolRouter
from muthis.kernel.turn import TurnResult
from muthis.kernel.turn_pass import TurnPass
from muthis.trust.confirm_gate import ConfirmGate
from muthis.trust.high_impact import RouteImpact
from muthis_plugins.web_research.plugin import PAGE_HEADER_AR, WebResearchPlugin
from muthis_sdk import NetCapability, PluginContext

HOST = "site.example"
URL = f"https://{HOST}/article"
MAPPING = {HOST: ["93.184.216.34"], "cdn.example": ["93.184.216.35"]}
# What a block page says. Readable prose on purpose: the defect needed a page
# the extractor keeps, and the 200 control below proves this one is kept.
BLOCK_PAGE = "Access denied BLOCK-CANARY-4f1e: automated requests are not permitted here."

TERMINAL = (401, 403, 404, 410)
TRANSIENT = (408, 429, 500, 502, 503, 504)


def _page(status: int, text: str = BLOCK_PAGE) -> httpx.Response:
    return httpx.Response(status, text=f"<html><body><p>{text}</p></body></html>",
                          headers={"content-type": "text/html"})


def _fetcher(handler, collector=None) -> HardenedFetcher:
    return HardenedFetcher(
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), trust_env=False,
            follow_redirects=False, headers={"User-Agent": USER_AGENT}),
        resolver=lambda hostname, port: MAPPING[hostname],
        robots_enabled=False, domains=collector)


def _fetch_all(handler, urls, collector=None):
    """Fetch `urls` in order through ONE fetcher — one session cache."""
    async def go():
        fetcher = _fetcher(handler, collector)
        try:
            return [await fetcher.fetch_readable(u) for u in urls]
        finally:
            await fetcher.aclose()
    return asyncio.run(go())


# ─── NEVER CONTENT: a failure that states its status ─────────────────────────

@pytest.mark.parametrize("status", TERMINAL + TRANSIENT)
def test_a_non_success_page_is_a_failure_stating_its_status(status):
    (result,) = _fetch_all(lambda request: _page(status), [URL])
    assert result.ok is False, f"a {status} page came back as the page"
    assert result.text_ar == status_note(status)
    assert str(status) in result.text_ar, "the note does not state the status"
    assert result.content == "" and "BLOCK-CANARY" not in result.text_ar
    assert result.status == status and result.domain == HOST


def test_the_CONTROL_the_same_body_at_200_IS_the_page():
    """Without this, the canary's absence above could mean the extractor dropped
    it — and then the assertion would hold with or without the status check."""
    (result,) = _fetch_all(lambda request: _page(200), [URL])
    assert result.ok is True and "BLOCK-CANARY-4f1e" in result.content


def test_success_is_exactly_the_2xx_class():
    probes = (199, 200, 203, 299, 300, 304, 399, 400, 404, 500)
    assert [s for s in probes if is_success(s)] == [200, 203, 299]


@pytest.mark.parametrize("status,body,ctype,other_note", [
    (403, "%PDF-1.4", "application/pdf", PDF_UNSUPPORTED_AR),
    (404, '<html><body><div id="root"></div><script>render()</script></body></html>',
     "text/html", EXTRACT_FAILED_AR),
], ids=["403-pdf", "404-app-shell"])
def test_the_status_is_checked_before_the_content_type_and_the_extraction(
        status, body, ctype, other_note):
    """A 403 PDF is not "a PDF I cannot read yet", and a 404 app shell is not "a
    page with no readable text": either note would hide the status. The same body
    at 200 earns the other note — so the STATUS is what decided here."""
    def handler_at(code):
        return lambda request: httpx.Response(code, content=body.encode(),
                                              headers={"content-type": ctype})

    (at_200,) = _fetch_all(handler_at(200), [URL])
    (failed,) = _fetch_all(handler_at(status), [URL])
    assert at_200.text_ar == other_note          # the control: that branch is real
    assert failed.text_ar == status_note(status)


def test_the_failure_is_logged_as_domain_and_status_only(caplog):
    with caplog.at_level(logging.DEBUG, logger="muthis.broker.net"):
        _fetch_all(lambda request: _page(403), [URL])
    assert f"[fetch] {HOST} status=403 non-success" in caplog.text
    assert "BLOCK-CANARY" not in caplog.text      # DEC-20: never content


# ─── NEVER CACHED: the site that recovers is read ────────────────────────────

def test_a_non_success_is_never_cached_so_a_recovered_site_is_read():
    """The live shape inverted: the site answers 403, then recovers."""
    answers = iter((_page(403), _page(200, "The recovered article RECOVERED-CANARY text.")))
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return next(answers)

    first, second = _fetch_all(handler, [URL, URL])
    assert first.ok is False and first.status == 403
    assert len(calls) == 2, "the failure was served from the cache — no request made"
    assert second.ok is True and second.from_cache is False
    assert "RECOVERED-CANARY" in second.content


def test_a_repeated_failure_asks_the_site_every_time():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return _page(503)

    results = _fetch_all(handler, [URL, URL, URL])
    assert calls["n"] == 3
    assert all(r.ok is False and r.from_cache is False for r in results)


def test_the_CONTROL_a_success_IS_cached_in_this_harness():
    """The same harness sees a cache hit, so the two tests above cannot pass on
    a cache that never works."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return _page(200)

    _first, second = _fetch_all(handler, [URL, URL])
    assert calls["n"] == 1 and second.from_cache is True


# ─── NEVER BADGED: nothing was read ──────────────────────────────────────────

def test_a_non_success_is_never_recorded_on_the_badge():
    collector = FetchedDomains()
    _fetch_all(lambda request: _page(403), [URL], collector)
    assert collector.domains() == ()


def test_a_redirect_landing_on_a_non_success_records_nothing():
    """DEC-36 ③ records the FINAL host because content came from there; when the
    final host refuses, content came from nowhere."""
    def handler(request):
        if request.headers.get("host") == HOST:
            return httpx.Response(302, headers={"location": "https://cdn.example/x"})
        return _page(403)

    collector = FetchedDomains()
    (result,) = _fetch_all(handler, [URL], collector)
    assert result.ok is False and result.domain == "cdn.example"
    assert collector.domains() == ()


def test_the_CONTROL_a_success_IS_recorded_in_this_harness():
    collector = FetchedDomains()
    _fetch_all(lambda request: _page(200), [URL], collector)
    assert collector.domains() == (HOST,)


# ─── WHAT THE MODEL READS: the production path ───────────────────────────────

class _Overlay:
    def __init__(self) -> None:
        self.badges: list = []

    def show_domain_badge(self, domains) -> None:
        self.badges.append(tuple(domains))

    async def show(self, bbox, label_ar): ...
    async def hide(self): ...


class _Voice:
    async def ensure_open(self):
        return False

    async def speak_or_feed(self, text): ...


class _Budget:
    def record_turn(self, turn_complete): ...


class _Reasoner:
    """ONE pass: one `web__fetch` of URL, then complete."""

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        call = ToolCall(name=WEB_FETCH_TOOL, args={"url": URL}, tool_use_id="f1")
        yield call
        yield TurnComplete(
            input_tokens=1, output_tokens=1, cost_usd=0.0, stop_reason="tool_use",
            model="fake", assistant_content=[{"type": "tool_use", "id": "f1",
                                              "name": WEB_FETCH_TOOL, "input": call.args}])


def _model_reads(status: int):
    """One serviced `web__fetch` through the real router (wrap, taint, gate), the
    real plugin and the real fetcher: what the model reads, and what the badge
    drew."""
    collector = FetchedDomains()

    async def go():
        fetcher = _fetcher(lambda request: _page(status), collector)
        plugin = WebResearchPlugin()
        router = ToolRouter(confirm_gate=ConfirmGate(), turn_hooks=(plugin.new_turn,),
                            fetched_domains=collector.domains)
        router.mount(plugin, ctx=PluginContext(
                         net=NetCapability(fetch_readable=fetcher.fetch_readable)),
                     namespace="web", provenance="web_research", taint=True,
                     impact=RouteImpact(capabilities=frozenset({"net.fetch"})))
        overlay = _Overlay()
        turn_pass = TurnPass(reasoner=_Reasoner(), budget=_Budget(), overlay=overlay,
                             voice=object(), stream_tts=False, router=router)
        turn_pass.new_turn_voice()
        try:
            _complete, _refresh, serviced = await turn_pass.consume(
                UserInput(text="اقرأ لي الصفحة"), None, [], HighlightGate(),
                TurnResult(), _Voice())
        finally:
            await fetcher.aclose()
        return serviced.read_results[0][1], overlay.badges

    return asyncio.run(go())


def test_the_model_reads_the_status_note_never_the_block_page():
    read, badges = _model_reads(403)
    assert status_note(403) in read, "the model never read the status"
    assert PAGE_HEADER_AR not in read, "a 403 was presented as a page"
    assert "BLOCK-CANARY" not in read
    assert not any(badges), f"a refused fetch drew a source badge: {badges}"


def test_the_CONTROL_the_model_reads_a_200_as_the_page_and_the_badge_draws():
    read, badges = _model_reads(200)
    assert f"{PAGE_HEADER_AR} {HOST}:" in read and "BLOCK-CANARY-4f1e" in read
    assert badges and badges[-1] == (HOST,)


# ─── THE NOTE: the note law's three obligations ──────────────────────────────

@pytest.mark.parametrize("status", TERMINAL + TRANSIENT)
def test_the_note_says_what_happened(status):
    note = status_note(status)
    assert f"برمز الحالة {status}" in note          # the status, stated
    assert "وليس محتوى الصفحة" in note              # ...it is not the page
    assert "فما قرأت منها شي" in note               # ...and nothing was read


@pytest.mark.parametrize("status", TERMINAL)
def test_a_4xx_note_closes_the_attempt(status):
    """The site's answer to THIS link: the same link gets the same answer."""
    note = status_note(status)
    assert not is_transient(status)
    assert RETRY_FUTILE_AR in note and RETRY_LATER_AR not in note


@pytest.mark.parametrize("status", TRANSIENT)
def test_a_5xx_408_429_note_says_what_changes_and_not_within_this_reply(status):
    """Time can change it, a retry in the same reply cannot — "same answer every
    time" would be false here, and "retry" with no bound would invite the loop."""
    note = status_note(status)
    assert is_transient(status)
    assert RETRY_LATER_AR in note and RETRY_FUTILE_AR not in note


@pytest.mark.parametrize("status", TERMINAL + TRANSIENT)
def test_the_note_names_a_move_the_model_can_make_and_invites_no_retry(status):
    note = status_note(status)
    assert "بدل التكرار" in note and "خبّر المستخدم" in note
    assert "واذكر مصدره" in note                     # an answer from results in hand
    for invitation in ("جرّب مرة ثانية", "حاول مرة ثانية", "أعد المحاولة",
                       "أعد فتح", "افتحه مرة ثانية", "اطلبه مرة أخرى"):
        assert invitation not in note, f"the note invites a retry: {invitation!r}"
