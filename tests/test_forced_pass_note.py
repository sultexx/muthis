# tests/test_forced_pass_note.py
"""
DEC-148 ⑤ — THE NOTE THE FORCED PASS READS, MADE TRUE FOR A KERNEL THAT SPEAKS.

THE COMPLAINT (Sultan, by ear, on `luna`): on the forced pass after a refusal the
model said it could not search — while it already held the results of the search
that had run a pass earlier (up to `MAX_RESULTS = 5`).

THE DIAGNOSIS, BY READING — the model's speech is never logged (DEC-142 ⑧), so this
is what the text handed that pass said, not a measurement. The old note gave the
pass ONE job, to relay the request, which the KERNEL had already spoken (DEC-138)
and which `luna` does not do (DEC-132 ③). It forbade every other job — «ردّك في
هذا الدور هو هذا الطلب لا غير» — told the model to say «إنك وقفت», and listed «بحث»
among the stopped capabilities. Nothing in it mentioned the results in hand. What
was left to say was the stop: DEC-132 ③'s «ما أقدر…» shape, which DEC-138 ⑤ had
recorded as a known cost of the forced pass.

WHAT EACH GUARD HOLDS — both notes, both bindings, through the REAL gate:
  * «the user hears nothing unless you speak» is GONE — false since DEC-138;
  * NO ORDER to relay the request the kernel spoke: every imperative to speak is
    one of the allowed clauses, and a negative control shows the check SEES the
    order it replaced;
  * ONE word, the kernel's — `test_confirm_word_set_and_retry.py`;
  * no tool can run in this reply, and the brake that makes that TRUE;
  * one true job: share what earlier results found, if anything, in one short
    sentence — without claiming it cannot search and without announcing a search,
    SCOPED TO THIS REPLY («فيه»), because the note stays in the history and C047
    must keep announcing the searches that ARE sent (DEC-145 ③; C047 itself is
    untouched, `test_persona_web_laws.py`).

THE KERNEL NEVER INTERPRETS A RESULT, AND HERE IT CANNOT: `confirm_note` is handed
NO RESULTS — its signature is pinned below, and the module is import-locked to
`{__future__, typing}` (`test_confirm_gate_notes.py`). Whether a result answers the
question is the MODEL's judgement; the note only makes the sharing conditional.

MEASURED BY EAR IN THE NEXT LIVE RUN. These guards prove the TEXT. What the model
does with it is not logged, so only Sultan can hear it.
"""

from __future__ import annotations

import inspect
import re

from muthis.kernel.highlight_gate import HighlightGate, loop_tool_choice
from muthis.trust.confirm_gate import ConfirmGate, confirm_note

SEARCH, FETCH = "web__search", "web__fetch"
CALLS = ((SEARCH, {"query": "أسعار الذهب"}), (FETCH, {"url": "https://a.test/x"}))

# The ONE sentence both notes carry, byte for byte: the reason, and the two things
# the reply must not claim — bound to THIS reply by «فيه».
NO_TOOL_THIS_REPLY = ("لا يمكن تشغيل أي أداة في هذا الرد، فلا تقل فيه إنك لا تستطيع "
                      "البحث ولا إنك ستبحث.")
SHARE_IF_ANY = "وإن كان فيما بين يديك من نتائج سابقة ما يجيب عن جزء من السؤال"
SILENCE_CLAIMS = ("فلن يسمع", "لن يسمع المستخدم شيئاً", "ينتهي الدور بلا جواب")

# Every imperative to SPEAK or ASK a note may give, as the clause it opens. Any
# other member of that family is an order to relay what the KERNEL already said.
SPEAK_ORDER = re.compile(r"(?<!\S)[وف]?(?:قل|اذكر|اطلب|بلّغ|بلغ|أخبر)\S*")
ALLOWED = ("فقل للمستخدم ما وجدته في جملة واحدة قصيرة",
           "قل للمستخدم إن ما قاله لم يُقرأ إذناً",
           "فقل له ما وجدته في جملة واحدة قصيرة")


def _notes() -> dict[str, str]:
    """A first refusal, and a retry after a heard non-approval, per binding."""
    notes = {}
    for tool, args in CALLS:
        gate = ConfirmGate()
        gate.new_turn()
        notes[f"{tool} first"] = gate.refusal_for(tool, args, high_impact=True, tainted=True)
        gate.new_turn()
        gate.observe("وش رايك في الجو اليوم")          # heard; neither answer
        notes[f"{tool} retry"] = gate.refusal_for(tool, args, high_impact=True, tainted=True)
    assert all(notes.values()), "the gate stopped refusing — the fixture is void"
    assert "لم يطابق" in notes[f"{SEARCH} retry"], "the retry form was never selected"
    return notes


def _relay_orders(note: str) -> list[str]:
    for clause in ALLOWED:
        note = note.replace(clause, "")
    return SPEAK_ORDER.findall(note)


def test_no_note_claims_the_user_hears_nothing_unless_the_model_speaks():
    """False since DEC-138: the kernel speaks the request at the refused pass, before
    this pass says a word (DEC-139 ④, DEC-145 ④)."""
    for name, note in _notes().items():
        for claim in SILENCE_CLAIMS:
            assert claim not in note, f"{name}: «{claim}» is back — the kernel already spoke"


def test_no_note_orders_the_request_repeated():
    for name, note in _notes().items():
        assert not _relay_orders(note), (
            f"{name}: an order to relay is back: {_relay_orders(note)} — the kernel "
            "spoke the request, and the model's copy is a duplicate at best")
        assert "لا تكرّر" in note, f"{name}: the note no longer says not to repeat it"


def test_the_relay_check_SEES_the_order_it_replaced():
    """THE NEGATIVE CONTROL: the pre-DEC-148 order, verbatim, is what the family
    check must catch — or a clean result above proves nothing."""
    old = ("الآن، وفي هذا الدور بالذات: قل له بصراحة إنك وقفت وإنك تطلب إذنه، "
           "واذكر اسم الأداة «web__search» ومعاملاتها كما هي (query=x)، واطلب منه أن يقول")
    assert _relay_orders(old) == ["قل", "واذكر", "واطلب"]
    assert _relay_orders("رسالة من النظام إلى المستخدم — بلّغها له الآن بصوتك") == ["بلّغها"]


def test_every_note_says_no_tool_can_run_in_THIS_reply():
    for name, note in _notes().items():
        assert NO_TOOL_THIS_REPLY in note, (
            f"{name}: the reason, or its scope to THIS reply, is gone — unscoped, the "
            "note would silence C047's announcement of a search that IS sent")


def test_the_claim_is_TRUE_the_pass_that_reads_the_note_cannot_call_a_tool():
    """A note must not state what the kernel does not enforce. The brake forces the
    pass after a refusal to text (DEC-131); this ties the sentence to it."""
    for tool, args in CALLS:
        gate = ConfirmGate()
        gate.new_turn()
        assert loop_tool_choice(HighlightGate(), gate) == "auto"   # control: nothing refused
        assert NO_TOOL_THIS_REPLY in gate.refusal_for(tool, args, high_impact=True, tainted=True)
        assert loop_tool_choice(HighlightGate(), gate) == "none", (
            f"{tool}: the note says no tool can run, and the pass that reads it is not forced")


def test_every_note_gives_the_pass_one_TRUE_job():
    """Share what earlier results found, if anything — conditional, one sentence."""
    for name, note in _notes().items():
        assert SHARE_IF_ANY in note, f"{name}: the pass has nothing true to do again"
        assert "ما وجدته في جملة واحدة قصيرة" in note, f"{name}: the share is unbounded"


def test_the_note_is_handed_NO_RESULTS():
    """THE KERNEL NEVER INTERPRETS A RESULT: the note is a pure function of the call
    and the gate's state, so what is shared can only be the MODEL's judgement."""
    assert list(inspect.signature(confirm_note).parameters) == [
        "tool", "args", "word", "missed", "scoped"], (
        "`confirm_note` grew a parameter — if a result can reach the note, the kernel "
        "can start choosing what the model says about it")
