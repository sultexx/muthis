# tests/test_doc_servicing.py
"""
`docs__open` / `docs__query` are SERVICED through the router — DEC-39's REQUIREMENT.

WHY THIS FILE LANDS BEFORE THE CATALOG. DEC-39 does not merely recommend servicing
first; it records the order as a REQUIREMENT, because M2 nearly shipped the
opposite. A mounted-but-unserviced tool falls to `consume()`'s LOOK-only `else`:
it never reaches `router.service()`, so the DEC-14 wrap, the DEC-15 taint raise and
the DEC-16 confirm gate are ALL bypassed — and then `build_tool_result_message`
answers its id from the DRAW fallback with `HIGHLIGHT_ACK_TEXT_AR`, which also
flips `gate.drawn`, forces `tool_choice="none"` and HARD-TERMINATES the agentic
loop. The model would be told a rectangle is on screen in reply to a request to
read a book.

So the four NEGATIVE assertions come first and are the point of the file: no
pointer ack, no draw-gate flip, no loop termination, no LOOK-only violation. A test
that would have caught the bug is worth more than one that confirms the fix.

The positive half then proves the boundaries are genuinely ON the path — routing
through `router.service()` is the entire reason the branch exists — and DEC-51's
two flags are asserted in BOTH directions against the REAL mount that `main.py`
performs, never a synthetic one (see `test_doc_mount.py`).

No model, no ONNX session, no corpus: the document service is faked, because what
is under test is the KERNEL'S dispatch, not retrieval quality.
"""

from __future__ import annotations

import asyncio

from muthis.cloud.protocol import ToolCall, TurnComplete, UserInput
from muthis.kernel.highlight_gate import (
    HIGHLIGHT_ACK_TEXT_AR, HIGHLIGHT_ALREADY_SHOWN_AR, HighlightGate,
    loop_tool_choice,
)
from muthis.kernel.tool_result_pairing import (
    DOC_ONE_PER_PASS_AR, DOC_OPEN_TOOL, DOC_QUERY_TOOL, DOC_TOOLS,
    build_tool_result_message,
)
from muthis.kernel.tool_router import ToolRouter
from muthis.kernel.turn import TurnResult
from muthis.kernel.turn_pass import TurnPass
from muthis.kernel.untrusted_content import WRAP_CLOSE_AR, WRAP_OPEN_AR
from muthis.trust.confirm_gate import ConfirmGate
from muthis.kernel.session_taint import SessionTaint
from muthis.trust.high_impact import RouteImpact
from muthis_plugins.doc_rag.plugin import DocRagPlugin
from muthis_sdk import PluginContext

OPEN_ARGS = {"path": "C:/Users/sultan/Documents/lecture.pdf"}
QUERY_ARGS = {"doc_id": "lecture.pdf", "question": "ما هو الحد الأقصى للجهد؟"}

# A distinctive marker so a test can prove the DOCUMENT's own text reached the
# model, rather than some note that merely looked successful.
PASSAGE_MARKER = "الحد الأقصى للجهد ٥ فولت"


# ─── The real graph, minus the parser and the encoder ────────────────────────

class _Passage:
    def __init__(self, text, score, parent, page=None, section=""):
        self.text, self.score, self.parent = text, score, parent
        self.page, self.section = page, section


class _Opened:
    def __init__(self, *, zone="index", note_ar=None, text="", doc_id="",
                 pages=None, chunks=0):
        self.zone, self.note_ar, self.text = zone, note_ar, text
        self.doc_id, self.pages, self.chunks = doc_id, pages, chunks

    @property
    def ok(self):
        return self.note_ar is None


class _Service:
    """Stands in for the broker's DocumentService. Records what it was asked."""

    def __init__(self, *, opened=None, passages=None, note=None):
        self._opened = opened or _Opened(doc_id="lecture.pdf", pages=228, chunks=267)
        self._passages = passages if passages is not None else [
            _Passage(PASSAGE_MARKER, 0.81, "p14", page=14)]
        self._note = note
        self.opened: list[str] = []
        self.queried: list[tuple[str, object]] = []

    async def open(self, path):
        self.opened.append(path)
        return self._opened

    def query(self, doc_id, question):
        self.queried.append((doc_id, question))
        return ([], self._note) if self._note else (self._passages, None)


class _Overlay:
    async def show(self, bbox, label_ar): ...
    async def hide(self): ...
    def show_domain_badge(self, domains): ...


class _Voice:
    async def ensure_open(self):
        return False

    async def speak_or_feed(self, text): ...


class _Budget:
    def record_turn(self, turn_complete): ...


class _Reasoner:
    def __init__(self, calls=()):
        self._calls = calls

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        for call in self._calls:
            yield call
        yield TurnComplete(
            input_tokens=1, output_tokens=1, cost_usd=0.0, stop_reason="tool_use",
            model="fake",
            assistant_content=[
                {"type": "tool_use", "id": c.tool_use_id, "name": c.name,
                 "input": c.args} for c in self._calls])


def _graph(service=None, *, taint=None):
    """The mount as production performs it: taint=True TOGETHER WITH the
    read-only hint (DEC-51). `test_doc_mount.py` asserts this against the REAL
    `main.py` wiring; here it is the fixture the dispatch tests need."""
    plugin = DocRagPlugin(service=service or _Service())
    router = ToolRouter(confirm_gate=ConfirmGate(),
                        session_taint=taint or SessionTaint())
    router.mount(plugin, ctx=PluginContext(), namespace="docs",
                 provenance="doc_rag", taint=True,
                 impact=RouteImpact(read_only_hint=True))
    return router, plugin


def _consume(router, calls, gate=None):
    turn_pass = TurnPass(reasoner=_Reasoner(calls), budget=_Budget(),
                         overlay=_Overlay(), voice=object(), stream_tts=False,
                         router=router)
    turn_pass.new_turn_voice()
    gate = gate if gate is not None else HighlightGate()
    result = TurnResult()
    complete, _refresh, routed, run = asyncio.run(turn_pass.consume(
        UserInput(text="اشرح لي المستند"), None, [], gate, result, _Voice()))
    return complete, routed, gate


def _open_call(tool_use_id="d1", args=None):
    return ToolCall(name=DOC_OPEN_TOOL, args=args or OPEN_ARGS,
                    tool_use_id=tool_use_id)


def _query_call(tool_use_id="d2", args=None):
    return ToolCall(name=DOC_QUERY_TOOL, args=args or QUERY_ARGS,
                    tool_use_id=tool_use_id)


# ═══ THE FOUR NEGATIVES — what M2's bug would have looked like here ══════════


def test_a_doc_call_never_receives_the_pointer_ack():
    router, _plugin = _graph()
    complete, routed, _gate = _consume(router, [_query_call()])

    pairing = build_tool_result_message(
        complete.assistant_content, None, None, HighlightGate(), routed, None)
    (block,) = pairing["content"]

    assert block["content"] not in (HIGHLIGHT_ACK_TEXT_AR, HIGHLIGHT_ALREADY_SHOWN_AR)
    assert PASSAGE_MARKER in block["content"], "the passage never reached the model"


def test_a_doc_call_never_flips_the_draw_gate_or_terminates_the_loop():
    """`gate.drawn` forces tool_choice="none", the agentic loop's HARD terminator.
    A document read that flipped it would end the turn the moment the model tried
    to open a book — before it could explain a single line of it."""
    router, _plugin = _graph()
    complete, routed, gate = _consume(router, [_open_call()])
    build_tool_result_message(complete.assistant_content, None, None, gate,
                              routed, None)

    assert gate.drawn is False, "a doc call flipped the unified draw gate"
    assert loop_tool_choice(gate) == "auto", "the agentic loop was terminated"


def test_a_doc_call_is_not_refused_as_a_look_only_violation(caplog):
    router, _plugin = _graph()
    with caplog.at_level("ERROR"):
        _complete, routed, _gate = _consume(router, [_open_call()])

    assert routed, "the doc call was never serviced"
    assert not any("LOOK-only violation" in r.getMessage() for r in caplog.records)


def test_both_doc_tools_are_serviced_not_just_the_one_that_was_wired_first():
    """Driven per TOOL, because servicing is registered per NAME. `open` working
    proves nothing about `query`, and the M2 lesson is that the untested half is
    where the fallthrough hides."""
    admitted = 0
    for call in (_open_call(), _query_call()):
        router, _plugin = _graph()
        _complete, routed, gate = _consume(router, [call])
        assert routed, f"{call.name} was never serviced"
        assert gate.drawn is False, f"{call.name} flipped the draw gate"
        admitted += 1

    assert admitted == len(DOC_TOOLS) == 2      # cutoff: both tools, none skipped


# ═══ THE POSITIVE HALF — the boundaries are genuinely on the path ════════════


def test_the_result_is_WRAPPED_by_the_router_with_exactly_one_nonce():
    """DEC-46's intersection with DEC-14: ONE wrapper, ONE nonce, for the WHOLE
    result — because it is ONE tool result. A per-passage wrap would multiply
    nonces inside one result and teach the model the delimiters are ordinary
    formatting that repeats, which is the erosion the nonce exists to prevent."""
    router, _plugin = _graph(_Service(passages=[
        _Passage("مقطع أول", 0.9, "p1", page=1),
        _Passage("مقطع ثاني", 0.8, "p2", page=2),
        _Passage("مقطع ثالث", 0.7, "p3", page=3)]))

    outcome = asyncio.run(router.service(DOC_QUERY_TOOL, QUERY_ARGS))

    assert outcome.result.text_ar.count(WRAP_OPEN_AR.split("{", 1)[0]) == 1
    assert outcome.result.text_ar.count(WRAP_CLOSE_AR.split("{", 1)[0]) == 1
    # ...and all three passages are inside that ONE wrapper.
    for body in ("مقطع أول", "مقطع ثاني", "مقطع ثالث"):
        assert body in outcome.result.text_ar


def test_servicing_a_doc_call_RAISES_the_session_taint():
    """DEC-51: every retrieved passage raises taint, in every zone and every
    format. Any document reaching this plugin is BY DEFINITION too large to have
    been inspected — the injection threshold alone exceeds a hundred pages."""
    taint = SessionTaint()
    router, _plugin = _graph(taint=taint)

    assert taint.tainted is False
    asyncio.run(router.service(DOC_QUERY_TOOL, QUERY_ARGS))

    assert taint.tainted is True


def test_open_and_query_in_ONE_message_are_BOTH_serviced_and_the_query_answers():
    """DEC-35 one level up: telling the model "I serve one WEB request per step"
    after it asked for a DOCUMENT sends it looking for a web call it never made.

    T6 BLOCKING FIX: the deferral note now also reports the STATE ACHIEVED. This
    shape — `docs__open` + `docs__query` in ONE assistant message — is the exact
    live failure: the old note said only "ask again next step", so the model
    re-issued its whole plan (open first) and paid a FULL re-ingestion per retry.
    The note must therefore say the open SUCCEEDED and that re-opening is
    pointless, or the retry loop returns."""
    from muthis.kernel.tool_result_pairing import (
        DOC_ONE_PER_PASS_AR, DOC_OPENED_ASK_NEXT_AR, WEB_ONE_PER_PASS_AR)

    router, _plugin = _graph()
    complete, routed, _gate = _consume(
        router, [_open_call("d1"), _query_call("d2")])
    pairing = build_tool_result_message(
        complete.assistant_content, None, None, HighlightGate(), routed, None)

    # THE RULED CHANGE (Option 3): `docs__open` is a PRECONDITION — it returns a
    # confirmation, never content — so it does not consume the pass's slot. BOTH
    # calls are serviced, the precondition FIRST because the query depends on the
    # index the open builds.
    assert [call.tool_use_id for call, _ in routed] == ["d1", "d2"]

    by_id = {b["tool_use_id"]: b["content"] for b in pairing["content"]}
    # Option B: EVERY tool_use is answered, or the NEXT turn 400s on an orphan.
    assert len(by_id) == 2
    # The query returns REAL PASSAGES, not a deferral note. This is the shape
    # that failed LIVE three times: the loop's root cause is now removed rather
    # than bounded by a better note, so the note is never reached at all.
    assert PASSAGE_MARKER in by_id["d2"]
    assert DOC_OPENED_ASK_NEXT_AR not in by_id.values()
    assert DOC_ONE_PER_PASS_AR not in by_id.values()
    assert WEB_ONE_PER_PASS_AR not in by_id.values()
    # The note itself is UNCHANGED and still carries the three obligations of the
    # standing note law — it now fires only for a genuinely unserviced id (see
    # the two-query test below), which is what the invariant always meant.
    assert "فُتح المستند بنجاح" in DOC_OPENED_ASK_NEXT_AR
    assert "لا تفتحه مرة أخرى" in DOC_OPENED_ASK_NEXT_AR
    assert "الخطوة التالية" in DOC_OPENED_ASK_NEXT_AR


def test_a_second_QUERY_in_one_pass_never_claims_a_document_was_opened():
    """The other half of the same law. When the serviced call was a QUERY, no
    open happened — and a note claiming one would be a fresh instance of the
    defect the fix above closes, in the opposite direction."""
    router, _plugin = _graph()
    complete, routed, _gate = _consume(
        router, [_query_call("q1"), _query_call("q2")])
    pairing = build_tool_result_message(
        complete.assistant_content, None, None, HighlightGate(), routed, None)

    contents = [b["content"] for b in pairing["content"]]
    assert DOC_ONE_PER_PASS_AR in contents
    assert "فُتح المستند بنجاح" not in "".join(contents)


def test_the_first_doc_call_of_the_pass_is_the_serviced_one():
    router, _plugin = _graph()
    complete, routed, _gate = _consume(
        router, [_open_call("d1"), _query_call("d2")])

    assert routed[0][0].tool_use_id == "d1"
    assert len(complete.assistant_content) == 2


def test_a_refused_document_still_pairs_and_still_never_touches_the_draw_gate():
    """A refusal is the COMMON case for a huge document, so it must survive the
    same path: the model reads the broker's own Arabic note and the turn continues."""
    router, _plugin = _graph(_Service(opened=_Opened(
        zone="refuse", note_ar="المستند أكبر من طاقتي على الفهرسة")))

    complete, routed, gate = _consume(router, [_open_call()])
    pairing = build_tool_result_message(complete.assistant_content, None, None,
                                        gate, routed, None)

    assert gate.drawn is False and loop_tool_choice(gate) == "auto"
    assert "أكبر من طاقتي" in pairing["content"][0]["content"]
