# tests/test_kernel_spoken_request.py
"""
DEC-138: the KERNEL speaks the approval request, and it says the bytes it hashed.

WHAT THIS FILE IS GUARDING, in one sentence: under a kernel messenger the old
failure mode inverts. The risk was never "the description is wrong" — it was
"approve what you heard, execute what was hashed", and the two were rendered by
two different functions from the same dict, diverging on FOUR axes of which two
bite on values far under any bound.

THE STRUCTURAL HALF IS THE ONE THAT MATTERS. `speakable` is handed the canonical
STRING and never the argument dict, so it is unable to describe a payload the
fingerprint does not cover — an ABSENCE OF MEANS, not a check somebody can
delete. `test_speakable_CANNOT_BE_HANDED_the_argument_dict` is the test that
says so, and if the mutation it describes is ever easy to write, the structure
has stopped holding and these behavioural tests are worth much less.

THE NEGATIVE CONTROL IS NOT CEREMONY (DEC-115's shape: obligations PRESENT +
families of lie ABSENT + a NEGATIVE control + a MECHANISM check). Without
`test_a_call_that_is_NOT_refused_speaks_NOTHING`, a mutation that speaks on
every pass passes every other assertion here.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import pathlib

from muthis.kernel.pass_servicing import service_pass_calls
from muthis.kernel.tool_router import ToolRouter, namespaced_name
from muthis.cloud.protocol import ToolCall
from muthis.trust.call_binding import canonical_call
from muthis.trust.confirm_gate import ConfirmGate
from muthis.trust.confirm_gate_detector import APPROVAL_WORD_AR, APPROVAL_WORDS_AR
from muthis.trust.confirm_gate_notes import render_args
from muthis.trust.confirm_gate_speech import speakable, spoken_request, spoken_scope
from muthis.trust.high_impact import NETWORK_CAPABILITY, RouteImpact
from muthis_sdk import ToolDescriptor, ToolPlugin, ToolResult

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis"
SEARCH = namespaced_name("web", "search")
FETCH = namespaced_name("web", "fetch")
NETWORK = frozenset({NETWORK_CAPABILITY})

# Named here rather than read off the module: a guard that iterates its own
# subject's tuple deletes its expectation along with an entry, which is the
# self-referential failure DEC-28's logging guard was rewritten to avoid.
EVERY_ACCEPTED_WORD = ("أوافق", "موافق", "وافق", "اعتمد")


class _WebPlugin(ToolPlugin):
    def descriptors(self):
        return [ToolDescriptor(name=n, schema={"name": n, "description": "d",
                                               "input_schema": {}},
                               kernel_serviced=False)
                for n in ("search", "fetch")]

    async def execute(self, tool, args, ctx):
        return ToolResult(text_ar="نتائج البحث")


class _Result:
    """The three fields `log_pass` mutates, and the turn-level taint flag."""
    def __init__(self):
        self.passes_serviced = 0
        self.tool_calls = []
        self.tools_logged = 0
        self.taint = False


class _Voice:
    """Records what the kernel said, and HOW it said it."""
    def __init__(self):
        self.spoken = []

    async def speak_or_feed(self, text):
        self.spoken.append(text)


def _router(*, tainted: bool, high_impact: bool = True) -> ToolRouter:
    router = ToolRouter()
    router.mount(_WebPlugin(), namespace="web", provenance="web:test", taint=True,
                 impact=RouteImpact(capabilities=NETWORK) if high_impact
                 else RouteImpact(read_only_hint=True))
    if tainted:
        router.session_taint.raise_taint("web:test")
    return router


def _pass(router, call, voice):
    return asyncio.run(service_pass_calls(
        router=router, sandbox=None, result=_Result(), precondition=None,
        read=call, run=None, nav=None, prelude=None, turn_voice=voice))


def _call(name=SEARCH, **args):
    return ToolCall(name=name, args=args or {"query": "بايثون"}, tool_use_id="t1")


# ═══ R1 — THE SPOKEN BYTES ARE THE HASHED BYTES ═══════════════════════════════

def test_speakable_CANNOT_BE_HANDED_the_argument_dict():
    """THE STRUCTURAL PROPERTY, and the reason the behavioural tests below are
    not the whole guard. `speakable` takes ONE parameter and it is the canonical
    string; with no access to the dict it cannot describe a different payload."""
    params = list(inspect.signature(speakable).parameters)
    assert params == ["canonical"], (
        f"speakable's inputs changed to {params} — if the argument dict can reach "
        "it, divergence stops being an absence of means and becomes a check")
    assert "args" not in inspect.signature(spoken_request).parameters, (
        "spoken_request grew an `args` parameter — the same hole one level up")


FOUR_AXES = (
    ("bool", {"deep": True}),
    ("none", {"x": None}),
    ("nested", {"opts": {"a": 1}}),
    ("newline", {"code": "print(1)\nprint(2)"}),
)


def test_the_spoken_form_TRACKS_the_canonical_on_every_divergence_axis():
    """Four for four, and TWO of them on values far under any bound — which is
    the measured reason lifting a truncation bound would have fixed nothing."""
    for name, args in FOUR_AXES:
        canonical, _ = canonical_call(SEARCH, args)
        value = speakable(canonical).split("=", 1)[1]
        assert value in canonical, (
            f"{name}: the spoken value {value!r} is not present in the canonical "
            f"bytes {canonical!r} — the user would approve what was not hashed")


def test_the_MODEL_facing_renderer_still_diverges_and_that_is_the_control():
    """THE CONTROL. If `render_args` agreed with the canonical on these inputs,
    the test above would pass for a reason unrelated to this design and would go
    on passing after the property was removed."""
    diverged = 0
    for name, args in FOUR_AXES:
        canonical, _ = canonical_call(SEARCH, args)
        if render_args(args).split("=", 1)[1] not in canonical:
            diverged += 1
    assert diverged == len(FOUR_AXES), (
        f"only {diverged}/{len(FOUR_AXES)} axes diverge — the fixtures no longer "
        "exercise the defect this design exists to close")


def test_a_long_value_declares_THAT_it_was_cut_HOW_MUCH_and_WHICH_argument():
    """The declared prefix. An inaudible «…» is what the model-facing renderer
    does; a spoken cut must say so in words."""
    long_value = "https://example.com/" + "a" * 400
    canonical, _ = canonical_call(FETCH, {"url": long_value})
    out = speakable(canonical)
    assert len(out) < len(canonical), "nothing was cut — re-pick the fixture"
    assert "url" in out, "the cut did not name WHICH argument is partial"
    assert any(ch.isdigit() for ch in out.split("(")[-1]), (
        "the cut declared no character count — the user cannot judge what he missed")
    assert out.rstrip().endswith(")"), "the declaration is not the last thing said"


# ═══ R2 — AN APPROVAL IS UNTRANSFERABLE ═══════════════════════════════════════

def _refuse(gate, tool, args):
    return gate.refusal_for(tool, args, high_impact=True, tainted=True)


def _approved(tool, args):
    """A gate whose turn N refused (tool, args) and whose turn N+1 approved it."""
    gate = ConfirmGate()
    _refuse(gate, tool, dict(args))
    gate.new_turn()
    gate.observe(APPROVAL_WORDS_AR[0])
    return gate


def test_an_approval_releases_ONLY_what_it_was_given_for():
    """Both directions (DEC-51's rule): what an approval covers is released AND
    every near-miss is refused. One assertion alone is satisfiable by a mutation
    that hard-codes the other.

    FLIPPED IN PART BY DEC-143. For `web__search` the approval covers the TOOL for
    its turn, so a changed value or an extra argument IS released — the grant never
    reads arguments. ANOTHER TOOL is still refused: `web__fetch` after a search
    approval is the case that pins the SPLIT, and the design rests on it. A
    per-call tool keeps both directions exactly, and is asserted beside it."""
    query = {"query": "x"}
    assert _refuse(_approved(SEARCH, query), FETCH, dict(query)) is not None, (
        "another tool: a SEARCH grant released a FETCH — the split is gone (DEC-143)")
    for name, args in (("a changed value", {"query": "x "}),
                       ("an extra argument", {"query": "x", "max_results": 5}),
                       ("the approved call itself", dict(query))):
        assert _refuse(_approved(SEARCH, query), SEARCH, args) is None, (
            f"{name}: the search grant did not release it (DEC-143: tool x turn)")

    url = {"url": "https://a.test/"}
    for name, tool, args in (("another tool", SEARCH, {"query": "x"}),
                             ("a changed value", FETCH, {"url": "https://a.test/x"}),
                             ("an extra argument", FETCH, {"url": "https://a.test/", "depth": 1})):
        assert _refuse(_approved(FETCH, url), tool, args) is not None, (
            f"{name}: a FETCH approval travelled to a call the user never heard")
    assert _refuse(_approved(FETCH, url), FETCH, dict(url)) is None, (
        "the approved fetch was NOT released — the success path is broken")


def test_a_released_approval_leaves_nothing_to_say_and_ends_as_ruled():
    """A release leaves nothing to SAY, under either binding (DEC-138). FLIPPED IN
    PART BY DEC-143: a SEARCH approval serves its whole turn — the same search is
    released again — and ends at the next turn boundary; a FETCH approval is still
    spent on its one call."""
    gate = ConfirmGate()
    _refuse(gate, SEARCH, {"query": "x"})
    gate.new_turn()
    gate.observe(APPROVAL_WORDS_AR[0])
    assert _refuse(gate, SEARCH, {"query": "x"}) is None
    assert gate.take_spoken_request() is None, (
        "a released call left a spoken request behind — the user would hear a "
        "request for a call that already ran")
    assert _refuse(gate, SEARCH, {"query": "x"}) is None, "the search grant did not serve its turn"
    gate.new_turn()
    assert _refuse(gate, SEARCH, {"query": "x"}) is not None, "a search grant outlived its turn"

    gate = _approved(FETCH, {"url": "u"})
    assert _refuse(gate, FETCH, {"url": "u"}) is None
    assert gate.take_spoken_request() is None
    assert _refuse(gate, FETCH, {"url": "u"}) is not None, "the fetch approval was reusable"


# ═══ R3 — EVERY ACCEPTED WORD IS OFFERED ══════════════════════════════════════

def test_the_spoken_request_names_EVERY_accepted_word():
    """DEC-136 ruling 2 at the PER-CALL surface, which still names every word.
    DEC-147 ① reversed it for the search request alone — and corrected the
    mechanism this docstring once gave: naming one had refused nobody (DEC-135 ③).
    The words are named HERE independently of the module's tuple."""
    canonical, _ = canonical_call(SEARCH, {"query": "x"})
    said = spoken_request(SEARCH, canonical, APPROVAL_WORDS_AR)
    for word in EVERY_ACCEPTED_WORD:
        assert word in said, f"«{word}» is accepted by the detector but never offered"
    assert set(APPROVAL_WORDS_AR) == set(EVERY_ACCEPTED_WORD), (
        "the accepted set changed without this guard's expectation changing with it")


# ═══ R4 — ONE REQUEST PER REFUSAL ═════════════════════════════════════════════

def test_the_request_is_handed_over_ONCE_and_then_cleared():
    gate = ConfirmGate()
    _refuse(gate, SEARCH, {"query": "x"})
    assert gate.take_spoken_request(), "nothing was prepared to say"
    assert gate.take_spoken_request() is None, (
        "the request was handed over twice — the same approval would be asked "
        "for on every pass, which is DEC-131's loop on the other side of the mouth")


def test_several_refusals_in_one_pass_produce_ONE_request_for_the_LAST_call():
    """The S3 case: a pass carried the tool three times. Only the first is
    dispatched today, but the gate must not depend on that.

    RE-POINTED TO FETCH AT DEC-143. The rebind this pins is DEC-138's PER-CALL
    property — the spoken bytes follow the LAST refused call — and a search no
    longer speaks arguments at all: it speaks its SCOPE, identical for every
    search, and still exactly once."""
    gate = ConfirmGate()
    _refuse(gate, FETCH, {"url": "https://one.test/"})
    _refuse(gate, FETCH, {"url": "https://two.test/"})
    said = gate.take_spoken_request()
    assert said.count("url=") == 1, "more than one call was described in one breath"
    assert "two" in said and "one" not in said, (
        "the request describes a superseded call — the pending rebinds, so the "
        "spoken text must rebind with it")
    assert gate.take_spoken_request() is None

    gate = ConfirmGate()
    _refuse(gate, SEARCH, {"query": "one"})
    _refuse(gate, SEARCH, {"query": "two"})
    assert gate.take_spoken_request() == spoken_scope(SEARCH, APPROVAL_WORD_AR)  # DEC-147 ①
    assert gate.take_spoken_request() is None


# ═══ R5 / R6 — THE ROUTE, AND THE NEGATIVE CONTROL ════════════════════════════

def test_a_refused_call_is_SPOKEN_through_the_turns_voice():
    voice = _Voice()
    _pass(_router(tainted=True), _call(), voice)
    assert len(voice.spoken) == 1, f"expected one utterance, got {len(voice.spoken)}"
    assert SEARCH in voice.spoken[0]
    # DEC-147 ①: a search is asked for with ONE word; the per-call request still
    # offers every accepted word, and R3 pins that at its own surface. Matched as
    # «quoted» forms: «وافق» is a substring of the other two.
    offered = [word for word in EVERY_ACCEPTED_WORD if f"«{word}»" in voice.spoken[0]]
    assert offered == [APPROVAL_WORD_AR], f"the search request offered {offered}"


def test_the_utterance_never_takes_VoiceOut_speak_directly():
    """It must QUEUE BEHIND the pass's own ack rather than cut across live
    audio — `refuse_for_budget`'s `speak` parameter is the precedent."""
    text = (SRC / "kernel" / "pass_servicing.py").read_text(encoding="utf-8")
    assert "turn_voice.speak_or_feed(spoken)" in text
    assert ".speak(" not in text, (
        "pass_servicing reached VoiceOut.speak directly — that cuts across audio "
        "already playing")


def test_a_call_that_is_NOT_refused_speaks_NOTHING():
    """THE NEGATIVE CONTROL. Without it, a mutation that speaks on every pass
    passes every other assertion in this file."""
    clean = _Voice()
    _pass(_router(tainted=False), _call(), clean)
    assert clean.spoken == [], "a clean-session call spoke an approval request"

    contained = _Voice()
    _pass(_router(tainted=True, high_impact=False), _call(), contained)
    assert contained.spoken == [], (
        "a tainted but CONTAINED call spoke — the gate's second condition is gone")


def test_an_unwired_voice_is_inert_rather_than_a_crash():
    """`None` keeps the arm inert, the stub-first shape every seam here uses."""
    asyncio.run(service_pass_calls(
        router=_router(tainted=True), sandbox=None, result=_Result(),
        precondition=None, read=_call(), run=None, nav=None, prelude=None))


# ═══ R7 — THE PRODUCTION WIRING, ASSERTED STRUCTURALLY ════════════════════════

def test_the_PRODUCTION_call_site_actually_hands_the_voice_across():
    """DEC-40 is why this is asserted and not trusted: five of six mutations
    once survived because every test built its OWN router, so deleting the
    production mount call from `main.py` stayed GREEN. `turn_voice` defaults to
    None, and that default is FAIL-SILENT."""
    text = (SRC / "kernel" / "turn_pass.py").read_text(encoding="utf-8")
    assert "turn_voice=turn_voice)" in text, (
        "turn_pass.py no longer hands the voice into service_pass_calls, so the "
        "kernel's approval request is wired to nothing in production")
    assert text.count("service_pass_calls(") == 1, (
        "a second servicing call site appeared — the reason this cost one line "
        "was that there is exactly one")


def test_the_speech_module_holds_no_opinion_about_which_words_are_accepted():
    """`render_words` is IMPORTED, not copied, so a word cannot be ACCEPTED
    without being OFFERED (DEC-136 ruling 2) at this surface too."""
    text = (SRC / "trust" / "confirm_gate_speech.py").read_text(encoding="utf-8")
    body = text.split('"""', 2)[-1]
    assert "from .confirm_gate_notes import render_words" in text
    for forbidden in ("APPROVAL_WORDS_AR", "_APPROVALS", "detect_confirmation"):
        assert forbidden not in body, (
            f"{forbidden} reached the speech module — it acquired an opinion "
            "about which words are accepted")


def test_the_directive_the_MODEL_reads_still_names_the_tool_and_arguments():
    """DEC-138 ruling 3 kept this directive byte-identical while the weaker half was
    worked on (DEC-42); `claude` DOES relay, so deleting the order would break what
    works. DEC-143 ruling ③ then CHANGED it, WITH the grant and never before: one
    clause of the stop and, for a turn-granted tool, the scope sentence. What this
    still pins is the order to name the tool and the arguments."""
    from muthis.trust.confirm_gate_notes import CONFIRM_DIRECTIVE_AR
    assert "{args}" in CONFIRM_DIRECTIVE_AR and "{tool}" in CONFIRM_DIRECTIVE_AR
    gate = ConfirmGate()
    note = _refuse(gate, SEARCH, {"query": "x"})
    assert "query=x" in note, "the model-facing directive stopped naming the arguments"
