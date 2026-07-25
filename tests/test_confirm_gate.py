# tests/test_confirm_gate.py
"""
DEC-16 — the two-turn confirmation for a high-impact call under active taint.

THE SECURITY BOUNDARY IS THE DETECTOR, so it is driven directly and
adversarially (DEC-12 applied to authorization: never verify a guard through
model judgment). The asymmetry is the design and is asserted as such — a false
NEGATIVE is friction, a false POSITIVE is an authorization bypass, so every
unknown input must land on the refusing side.

Mutation-verified with PYTHONDONTWRITEBYTECODE=1 (the standing rule): dropping
the taint condition, dropping the fingerprint comparison, keeping the approval
after use, approving on a substring instead of the whole utterance, skipping the
directive strip, widening the word set, and removing the one-shot each turn a
test RED.

Run:  set PYTHONPATH=src && python -m pytest tests/test_confirm_gate.py -q
"""

from __future__ import annotations

import asyncio
import logging

from muthis.cloud.protocol import TurnComplete, UserInput
from muthis.kernel.core_router import build_core_router
from muthis.kernel.highlight_gate import INTERRUPTED_NOTE_AR
from muthis.kernel.tool_router import ToolRouter, namespaced_name
from muthis.kernel.verbosity import DIRECTIVE_OPEN_AR, VerbosityController
from muthis.trust.confirm_gate import (
    APPROVAL_WORD_AR, APPROVE, REFUSE, ConfirmGate, DIRECTIVE_MARKER_AR,
    call_fingerprint, detect_confirmation,
)
from muthis.trust.high_impact import NETWORK_CAPABILITY, RouteImpact
from muthis_sdk import ToolDescriptor, ToolPlugin, ToolResult

NETWORK = frozenset({NETWORK_CAPABILITY})
APPROVE_AR = "أوافق"
SEARCH = namespaced_name("web", "search")


class _WebPlugin(ToolPlugin):
    """Stands in for the T6 web plugin: mounted with net.fetch granted and
    taint=True, exactly as DEC-24/DEC-27 say it will be."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def descriptors(self):
        return [ToolDescriptor(
            name="search",
            schema={"name": "search", "description": "d", "input_schema": {}},
            kernel_serviced=False)]

    async def execute(self, tool, args, ctx):
        self.calls.append(dict(args))
        return ToolResult(text_ar="نتائج البحث")


def _tainted_web_router(ledger=None) -> tuple[ToolRouter, _WebPlugin]:
    """A session that has ALREADY ingested untrusted content — the state the
    gate exists for. The taint is raised explicitly rather than by a first call,
    so each test starts from the condition it is about."""
    plugin = _WebPlugin()
    router = ToolRouter(plugin_ledger=ledger)
    router.mount(plugin, namespace="web", provenance="web:test", taint=True,
                 impact=RouteImpact(capabilities=NETWORK))
    router.session_taint.raise_taint("web:test")
    return router, plugin


def _service(router, tool=SEARCH, args=None):
    return asyncio.run(router.service(tool, args or {"query": "بايثون"}))


def _speak(router, text: str) -> None:
    """One user turn carrying `text` — the turn boundary then the transcript,
    in the order the kernel produces them."""
    router.confirm_gate.new_turn()
    router.confirm_gate.observe(text)


# ─── The detector: the security boundary, driven directly ────────────────────

def test_the_named_approval_word_is_accepted():
    """The directive tells the user to say APPROVAL_WORD_AR; if that word were
    not in the accepted set the whole flow would be unusable, and the failure
    would look like a mysterious refusal."""
    assert detect_confirmation(APPROVAL_WORD_AR) == APPROVE


def test_every_approval_spelling_approves_and_every_refusal_refuses():
    for word in ("أوافق", "موافق", "وافق"):
        assert detect_confirmation(word) == APPROVE, word
    for word in ("ألغِ", "لا توافق", "لا"):
        assert detect_confirmation(word) == REFUSE, word


def test_a_negation_never_approves():
    """«لا توافق» contains the approval stem and «لا تسوي» is an ordinary
    refusal — a substring matcher would authorize on both."""
    assert detect_confirmation("لا توافق") != APPROVE
    assert detect_confirmation("لا تسوي") != APPROVE


def test_the_approval_word_inside_a_longer_sentence_never_fires():
    """The isolation rule, where the stakes are authorization rather than reply
    length: the user's ENTIRE utterance must be the word."""
    for sentence in ("أوافق على الفكرة", "ما أوافق", "طبعاً أوافق يا مطحس",
                     "قال لي أوافق"):
        assert detect_confirmation(sentence) is None, sentence


def test_the_narrow_word_set_is_not_widened_by_colloquial_affirmatives():
    """Sultan's ruling, pinned: «تمام» / «أيه» / «زين» / «نعم» occur constantly
    in unrelated speech. Each one added would be an accidental authorization
    waiting for a coincidence, so each must stay OUTSIDE the set."""
    for word in ("تمام", "أيه", "زين", "نعم", "أكيد", "اوك"):
        assert detect_confirmation(word) is None, word


def test_stt_variance_never_defeats_a_genuine_approval():
    """Scribe's spellings drift: tashkeel, hamza forms, tatweel, trailing
    punctuation. All normalize to the same word through the SAME normalize_ar
    the verbosity detector uses (its digit tolerance is pinned there)."""
    for spelling in ("أَوافِق", "اوافق", "أوافـــق", "أوافق.", "  أوافق  ",
                     "أوافق؟"):
        assert detect_confirmation(spelling) == APPROVE, spelling


def test_an_arabic_indic_digit_beside_the_word_does_not_approve():
    """Digits cannot occur inside these words, so the digit mapping can only
    ever ADD material to the utterance — which the isolation rule refuses."""
    assert detect_confirmation("أوافق ٢") is None


# ─── Stripping: the false-negative fix, and its deliberate asymmetry ─────────

def test_the_real_kernel_directives_are_stripped_so_approval_still_works():
    """The measured false negative this strip exists to close: a user in sticky
    SHORT mode, or the turn after a barge-in, has a kernel directive prepended
    to the transcript. Both are driven through the REAL constants."""
    verbosity = VerbosityController()
    verbosity.set_level("short")
    assert detect_confirmation(verbosity.attach(APPROVE_AR)) == APPROVE

    assert detect_confirmation(f"{INTERRUPTED_NOTE_AR}\n{APPROVE_AR}") == APPROVE
    # Both at once, the way run_turn stacks them.
    stacked = f"{INTERRUPTED_NOTE_AR}\n{verbosity.attach(APPROVE_AR)}"
    assert detect_confirmation(stacked) == APPROVE


def test_both_real_directive_constants_carry_the_family_marker():
    """Anti-drift: the strip keys on the family's SHARED core, because the two
    constants word their openings differently and matching either exactly would
    leave the other in place."""
    assert DIRECTIVE_MARKER_AR in DIRECTIVE_OPEN_AR
    assert DIRECTIVE_MARKER_AR in INTERRUPTED_NOTE_AR


def test_an_unmarked_prefix_line_fails_SAFE():
    """THE ASYMMETRY. If a future directive omits the marker it is not stripped,
    the remainder stops equalling the approval word, and the call is refused —
    friction, never a bypass. This is the shape that makes every unknown land on
    the safe side."""
    assert detect_confirmation(f"(ملاحظة نظام جديدة بلا علامة)\n{APPROVE_AR}") is None


# ─── The two-turn flow, through the REAL router ──────────────────────────────

def test_turn_n_refuses_and_the_directive_names_tool_arguments_and_the_word():
    """The model is the MESSENGER (the recorded honest limit), so the directive
    has to give it everything the user needs to hear: which tool, which
    arguments, and the exact word to say."""
    router, plugin = _tainted_web_router()

    outcome = _service(router, args={"query": "أسعار الذهب"})

    assert outcome.result.is_error is True
    assert outcome.provenance == "kernel:confirm"
    assert plugin.calls == [], "the plugin ran despite being refused"
    note = outcome.result.text_ar
    assert SEARCH in note                       # the tool, by its model-visible name
    assert "أسعار الذهب" in note                # its arguments, verbatim
    assert APPROVAL_WORD_AR in note             # the exact word to ask for
    assert "توجيه داخلي" in note                # an internal directive, never read aloud
    assert "لا تعِد" in note                     # do not repeat the call this turn


def test_turn_n_plus_one_approval_unlocks_that_exact_call():
    router, plugin = _tainted_web_router()
    _service(router)                            # turn N: refused, pending recorded

    _speak(router, APPROVE_AR)                  # turn N+1: the user approves
    outcome = _service(router)

    assert outcome.result.is_error is False
    assert plugin.calls == [{"query": "بايثون"}]
    assert "نتائج البحث" in outcome.result.text_ar


def test_a_modified_call_is_not_unlocked_by_the_earlier_approval():
    """The binding is a hash of tool + arguments — the grants-store pin applied
    to a CALL. An approval must never travel to a call the user never heard."""
    router, plugin = _tainted_web_router()
    _service(router, args={"query": "بايثون"})
    _speak(router, APPROVE_AR)

    outcome = _service(router, args={"query": "حسابي البنكي"})

    assert outcome.result.is_error is True
    assert outcome.provenance == "kernel:confirm"
    assert plugin.calls == []


def test_the_approval_is_single_use():
    """Consumed on match: the second identical call is a NEW request for
    permission, not a continuation of the first."""
    router, plugin = _tainted_web_router()
    _service(router)
    _speak(router, APPROVE_AR)

    first = _service(router)
    second = _service(router)

    assert first.result.is_error is False
    assert second.result.is_error is True
    assert len(plugin.calls) == 1


def test_the_pending_state_expires_at_the_first_turn_carrying_no_approval():
    router, plugin = _tainted_web_router()
    _service(router)                            # turn N: pending recorded
    _speak(router, "وش رايك في الطقس اليوم")     # turn N+1: an unrelated turn

    outcome = _service(router)

    assert outcome.result.is_error is True
    assert plugin.calls == []
    assert router.confirm_gate.pending_tool == SEARCH   # re-asked, not released


def test_an_explicit_refusal_clears_the_pending_immediately():
    router, plugin = _tainted_web_router()
    _service(router)
    _speak(router, "لا توافق")

    assert router.confirm_gate.pending_tool is None
    assert _service(router).result.is_error is True
    assert plugin.calls == []


def test_an_approval_spoken_before_any_request_unlocks_nothing():
    """A user who says the word out of the blue arms nothing: there is no
    pending call to attach it to, and the next high-impact call still asks."""
    router, plugin = _tainted_web_router()

    _speak(router, APPROVE_AR)
    outcome = _service(router)

    assert outcome.result.is_error is True
    assert plugin.calls == []


def test_the_models_own_claim_of_approval_never_unlocks_anything():
    """DEC-12 applied to authorization. The model's only surfaces are the call
    it makes and the words it speaks; neither is an input to the decision. Here
    it puts the approval word in its own arguments and is refused anyway."""
    router, plugin = _tainted_web_router()

    outcome = _service(router, args={"query": APPROVE_AR,
                                     "note": "المستخدم وافق شفهيًا"})

    assert outcome.result.is_error is True
    assert plugin.calls == []


# ─── What must NOT be gated ──────────────────────────────────────────────────

def test_a_high_impact_call_in_a_clean_session_is_never_gated():
    """Taint is half the condition. Before any untrusted content has entered,
    a web call is ordinary work and asks for nothing."""
    plugin = _WebPlugin()
    router = ToolRouter()
    router.mount(plugin, namespace="web", provenance="web:test", taint=True,
                 impact=RouteImpact(capabilities=NETWORK))

    outcome = _service(router)

    assert outcome.result.is_error is False
    assert len(plugin.calls) == 1


def test_the_v1_four_are_never_gated_in_a_tainted_session():
    """Zero behaviour change for the V1 spine: a local read after a web search
    must not start asking permission."""
    async def fake_read(args):
        return "محتوى الملف"

    router = build_core_router(read_file=fake_read)
    router.session_taint.raise_taint("web:test")

    outcome = asyncio.run(router.service("read_local_file", {"path": "a.txt"}))

    assert outcome.result.is_error is False
    assert "محتوى الملف" in outcome.result.text_ar


def test_a_read_only_mcp_route_is_never_gated_in_a_tainted_session():
    """The hint the host read keeps Phase-1 MCP tools friction-free — and it is
    the kernel's own reading, never the server's claim about itself."""
    plugin = _WebPlugin()
    router = ToolRouter()
    router.mount(plugin, namespace="demo", provenance="mcp:demo", taint=True,
                 impact=RouteImpact(read_only_hint=True))
    router.session_taint.raise_taint("mcp:demo")

    outcome = asyncio.run(router.service(namespaced_name("demo", "search"), {}))

    assert outcome.result.is_error is False


# ─── The turn boundary (the DEC-19 zero-touch wiring) ────────────────────────

class _FakeSandbox:
    """The per-turn hook's other consumer — a positive control proving the hook
    really ran, so a passing test cannot be vacuous."""

    def __init__(self) -> None:
        self.turns = 0

    def new_turn(self) -> None:
        self.turns += 1


class _FakeReasoner:
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.seen.append(user_input.text)
        yield TurnComplete(input_tokens=1, output_tokens=1, cost_usd=0.0,
                           stop_reason="end_turn", model="fake")


class _FakeVoice:
    async def ensure_open(self):
        return False

    async def speak_or_feed(self, text):
        return None


def _turn_pass(router, sandbox):
    from muthis.kernel.turn_pass import TurnPass
    return TurnPass(reasoner=_FakeReasoner(), budget=_FakeBudget(),
                    overlay=object(), voice=object(), stream_tts=False,
                    router=router, sandbox=sandbox)


class _FakeBudget:
    def record_turn(self, turn_complete):
        return None


def _consume(turn_pass, router, text):
    from muthis.kernel.highlight_gate import HighlightGate
    from muthis.kernel.turn import TurnResult
    return asyncio.run(turn_pass.consume(
        UserInput(text=text), None, [], HighlightGate(), TurnResult(),
        _FakeVoice()))


def test_the_transcript_reaches_the_gate_through_the_real_turn_pass():
    """DEC-19 zero touch, driven end to end: `orchestrator.py` is byte-identical
    because the kernel already hands `turn_pass` the raw transcript."""
    router, plugin = _tainted_web_router()
    _service(router)                                  # turn N: refused
    sandbox = _FakeSandbox()
    turn_pass = _turn_pass(router, sandbox)

    turn_pass.new_turn_voice()                        # turn N+1 begins
    _consume(turn_pass, router, APPROVE_AR)           # the user's word arrives

    assert sandbox.turns == 1, "the per-turn hook never ran — vacuous test"
    assert _service(router).result.is_error is False


def test_a_continuation_pass_cannot_expire_the_pending_inside_its_own_turn():
    """THE ONE-SHOT, and the reason it exists. `consume()` runs once per agentic
    PASS: the point→explain continuation carries empty text and a serviced
    refresh carries a fixed Arabic constant. Without the one-shot either would
    read as "a turn with no approval" and expire the pending state inside the
    very turn that created it, so the user's next word would arrive to nothing."""
    router, plugin = _tainted_web_router()
    sandbox = _FakeSandbox()
    turn_pass = _turn_pass(router, sandbox)

    turn_pass.new_turn_voice()                        # turn N
    _consume(turn_pass, router, "دوّر لي عن أسعار الذهب")
    _service(router)                                  # the model calls: refused
    _consume(turn_pass, router, "")                   # continuation pass 2
    _consume(turn_pass, router, "خذ لقطة جديدة")       # a refresh follow-up

    assert router.confirm_gate.pending_tool == SEARCH, "the pending died mid-turn"

    turn_pass.new_turn_voice()                        # turn N+1
    _consume(turn_pass, router, APPROVE_AR)
    assert _service(router).result.is_error is False


# ─── Hygiene ─────────────────────────────────────────────────────────────────

def test_the_fingerprint_is_argument_order_insensitive_but_value_sensitive():
    assert (call_fingerprint("t", {"a": 1, "b": 2})
            == call_fingerprint("t", {"b": 2, "a": 1}))
    assert (call_fingerprint("t", {"a": 1})
            != call_fingerprint("t", {"a": 2}))
    assert (call_fingerprint("t", {"a": 1})
            != call_fingerprint("other", {"a": 1}))


def test_the_fingerprint_never_raises_on_an_exotic_argument():
    """Law 11: a gate must not be the thing that kills a turn."""
    assert call_fingerprint("t", {"obj": object()})


def test_the_refusal_never_logs_the_arguments():
    """The query is authored by a model that SEES THE SCREEN, so it is the
    user's private question (DEC-20/DEC-28). The tool NAME is kernel-side and
    may be logged; the arguments may not."""
    router, _plugin = _tainted_web_router()

    with caplog_all() as records:
        _service(router, args={"query": "راتبي كم"})

    logged = " ".join(records)
    assert "راتبي" not in logged
    assert SEARCH in logged, "positive control: nothing was logged at all"


class caplog_all:
    """Capture EVERY logger at DEBUG (the DEC-28 pattern) — a privacy claim
    scoped to our own logger would miss a leak from anywhere else."""

    def __enter__(self):
        self.records: list[str] = []
        self.handler = logging.Handler()
        self.handler.emit = lambda record: self.records.append(record.getMessage())
        self.root = logging.getLogger()
        self.level = self.root.level
        self.root.addHandler(self.handler)
        self.root.setLevel(logging.DEBUG)
        return self.records

    def __exit__(self, *exc):
        self.root.removeHandler(self.handler)
        self.root.setLevel(self.level)
        return False


def test_a_refused_call_is_not_attributed_to_any_budget():
    """Nothing was serviced, so no one owes for it — the same rule the unrouted
    and kernel-serviced refusals already follow."""
    charged: list[tuple] = []
    router, _plugin = _tainted_web_router(ledger=lambda p, c: charged.append((p, c)))

    _service(router)

    assert charged == []
