# tests/test_ack_scope.py
"""
The spoken ack is scoped to the ANSWER — DEC-83's measured gap, closed.

WHAT THIS GUARDS, stated as the ruling states it: **the code did not break. The
Navigator EXPOSED a directive-coverage gap that was previously closed by
COINCIDENCE** — DEC-13's posture one layer up, a property held by circumstance
rather than by construction.

The directive that forbids a repeated ack rides the DRAW pairing. Before Phase 3
the first pass of an answer ACKED AND DREW, so that directive arrived at once and
the only pass after it was the forced-text explain. The Navigator inserts an
ack-eligible pass BEFORE any draw (`test_advance_WITHOUT_pointing_leaves_the_gate
_unflipped` asserts `calls[1][1] == "auto"`), and every navigator and mode
directive was silent on acks. Live result: an ack per PASS inside one answer.

**THE LAW IS ASSERTED, NOT ITS WORDS.** A substring check on one constant is a
CUTOFF — the family M16 landed in at T5, where an assertion pinned a PREFIX of
the sentence it claimed to check and a mutation deleting the rest stayed green.
So the collection is SCANNED: every model-facing directive in the navigator and
mode surfaces is discovered from the source, and each must carry the scope. A
directive added later joins the set automatically and must satisfy it — which is
the difference between closing this gap and closing this instance of it.

**MULTI-PASS, NEVER SINGLE-PASS.** The behavioural test drives a REAL turn whose
pass 2 is still `auto`, because a single-pass assertion cannot see this defect at
all: the gap only exists between an ack-eligible pass and the draw that would
have silenced it.

Run:  set PYTHONDONTWRITEBYTECODE=1 && set PYTHONPATH=src && python -m pytest tests/test_ack_scope.py -q
"""

from __future__ import annotations

import ast
import asyncio
import pathlib

from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.kernel.ack_scope import ACK_SCOPE_AR
from muthis.kernel.budget import Budget
from muthis.kernel.deferral_notes import NAV_ONE_PER_PASS_AR, NAV_STEP_TOOL
from muthis.kernel.highlight_gate import (
    HIGHLIGHT_ACK_TEXT_AR, HIGHLIGHT_ALREADY_SHOWN_AR, SHAPES_ACK_TEXT_AR,
    SHAPES_ALREADY_SHOWN_AR,
)
from muthis.kernel.mode_surfaces import mode_directive_line
from muthis.kernel.navigator_service import (
    _FINISHED_AR, _MOVED_AR, _PLAN_STARTED_AR,
)
from muthis.kernel.orchestrator import Orchestrator
from muthis.kernel.plan import Plan
from muthis.kernel.session_mode import SessionMode
from muthis.kernel.mode_transition import ENTER, TransitionRequest
from muthis.kernel.untrusted_content import WRAP_CLOSE_AR, WRAP_OPEN_AR
from muthis.trust.confirm_gate import DIRECTIVE_MARKER_AR
from muthis.vision.downscale import DownscaledImage

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis"
KERNEL = SRC / "kernel"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8

# The surfaces the ruling names. `deferral_notes.py` is scanned for its NAV_*
# constants only — the doc and web deferral notes are OUTSIDE this ruling's
# scope and are recorded as an observation in DEC-84 rather than widened into
# silently.
NAVIGATOR_AND_MODE_SOURCES = ("navigator_service.py", "mode_surfaces.py")


def _directive_constants(module: str) -> "dict[str, str]":
    """Every module-level Arabic DIRECTIVE constant, read from the source.

    Discovered rather than listed: the family is identified by the marker the
    project already uses for it (`DIRECTIVE_MARKER_AR`, DEC-31's strip key), so
    a directive added in a later milestone is inside this law the moment it is
    written — not when someone remembers to add it here."""
    tree = ast.parse((KERNEL / module).read_text(encoding="utf-8"))
    found: "dict[str, str]" = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue                      # an f-string join — read below instead
        if isinstance(value, str) and DIRECTIVE_MARKER_AR in value:
            found[node.targets[0].id] = value          # type: ignore[attr-defined]
    return found


# ═══════════════════════════════════════════════════════════════════════════
# THE LAW — every directive that can precede another pass carries the scope
# ═══════════════════════════════════════════════════════════════════════════

# Built from the RENDERED surfaces, because several are f-string templates whose
# literal source is not the text the model reads.
def _rendered_directives() -> "dict[str, str]":
    return {
        "navigator plan started": _PLAN_STARTED_AR,
        "navigator step moved": _MOVED_AR.format(current=2, total=5),
        "navigator finished": _FINISHED_AR,
        "navigator one-per-pass": NAV_ONE_PER_PASS_AR,
        "mode frame line": mode_directive_line("وضع", 2, 5, "انقر"),
        "mode frame line (no plan)": mode_directive_line("وضع", 0, 0, None),
    }


def test_every_navigator_and_mode_directive_carries_the_ANSWER_scope():
    """THE LAW. Not "this constant contains this substring" — the whole
    collection, each member required to carry it, with the count reported.

    Before DEC-84 all six of these were SILENT on acks while all four draw
    directives carried the clause, and that asymmetry is the entire defect."""
    directives = _rendered_directives()
    assert len(directives) >= 6, (
        f"the collection has shrunk to {len(directives)} — a law that examines "
        "fewer surfaces than it claims is the cutoff defect this file exists to "
        "avoid")
    missing = [name for name, text in directives.items() if ACK_SCOPE_AR not in text]
    assert not missing, (
        f"{len(missing)} of {len(directives)} directives are SILENT on the ack "
        f"scope: {missing}. Each can be followed by another pass of the SAME "
        "answer, and a pass with no scope statement acks again (DEC-83).")


def test_the_draw_directives_still_carry_their_own_anti_ack_pressure():
    """The half that was ALREADY right, pinned so a later edit cannot 'unify'
    the wordings by deleting the one that was working. These carry their own
    stronger form — they NAME «أبشر» — and that is deliberate."""
    for name, text in (("highlight ack", HIGHLIGHT_ACK_TEXT_AR),
                       ("highlight already-shown", HIGHLIGHT_ALREADY_SHOWN_AR),
                       ("shapes ack", SHAPES_ACK_TEXT_AR),
                       ("shapes already-shown", SHAPES_ALREADY_SHOWN_AR)):
        assert "بدون أي مقدمة أو تأكيد" in text, f"{name} lost its anti-ack clause"


# A DISTINCTIVE CONTIGUOUS FRAGMENT of the clause. The whole sentence is never
# contiguous in any source file — it is written as implicit string concatenation,
# so a search for the rendered text finds NOTHING and would make the copy check
# below pass while examining nothing. That first draft of this guard did exactly
# that and this comment is why it does not any more.
_COPY_PROBE = "بلا كلمة تأكيد جديدة"


def test_the_scope_has_exactly_ONE_definition_site():
    """ONE COPY OF ONE FACT. Six directives read the sentence from `ack_scope`;
    a second literal copy anywhere in `src/` is how two wordings drift apart —
    the `NAMESPACE_SEP` discipline applied to a law rather than to a name."""
    assert _COPY_PROBE in ACK_SCOPE_AR, (
        "the probe no longer appears in the clause — it is aimed at nothing")
    holders = sorted(p.name for p in SRC.rglob("*.py")
                     if _COPY_PROBE in p.read_text(encoding="utf-8"))
    # The PERSONA's own file is a DELIBERATE EXCLUSION, and the reason is the
    # design rather than an inconvenience: DEC-20's pattern is LAYERED pressure —
    # the persona is layer ONE (a permanent law the model carries into every turn)
    # and these directives are layer TWO (the same law at the point of use). The
    # persona stating it in its own words is the layering working; a KERNEL
    # module restating it would be two copies of one fact.
    #
    # It is `persona_laws.py` and no longer `persona_rules.py` because the <=300
    # line law split the milestone laws out of that file (a MOVE ONLY — the
    # composed prompt is byte-identical across it). THIS GUARD FIRED ON THAT MOVE,
    # which is the behaviour wanted: the law's home is pinned, so relocating it is
    # a decision someone states here rather than a thing that happens quietly.
    assert holders == ["ack_scope.py", "persona_laws.py"], (
        f"the ack scope is written out in {holders} — outside the persona it "
        "must be defined once and imported, or the two wordings drift")


def test_ack_scope_has_no_means_to_become_anything_but_a_sentence():
    """Absence proven by lack of means (`session_mode.py`'s argument): the
    module imports NOTHING, so it cannot cycle and cannot grow a dependency that
    would make it logic instead of a law."""
    tree = ast.parse((KERNEL / "ack_scope.py").read_text(encoding="utf-8"))
    imports = [n for n in ast.walk(tree)
               if isinstance(n, (ast.Import, ast.ImportFrom))
               and getattr(n, "module", None) != "__future__"]
    assert not imports, "ack_scope.py has grown an import"


def test_the_clause_cannot_be_mistaken_for_the_untrusted_boundary():
    """DEC-14's rule, applied at T7's own request: **a law the model READS must
    never resemble the untrusted-content boundary it reads INSIDE.** Checked
    against the LIVE §3.2 constants rather than a copy of their wording, so a
    future rewording of the delimiters re-runs this comparison automatically."""
    open_words = set(WRAP_OPEN_AR.split()) - {"—", "{source}", "{nonce}"}
    close_words = set(WRAP_CLOSE_AR.split()) - {"—", "{nonce}"}
    shared = (open_words | close_words) & set(ACK_SCOPE_AR.split())
    assert not shared, (
        f"the ack-scope clause shares wording with the untrusted delimiters: "
        f"{sorted(shared)} — a rule the model reads must not look like the "
        "boundary it reads inside")


def test_the_scope_states_the_ANSWER_and_is_TOOL_AGNOSTIC():
    """The ruling's own formulation, and the half that stops the gap reopening.

    A clause written per TOOL FAMILY would have to be re-earned by every future
    capability that opens a new pass gap — which is exactly how this gap arrived.
    The scope names the ANSWER and explicitly covers whatever tools a pass calls,
    so a capability inherits it by existing."""
    assert "الإجابة" in ACK_SCOPE_AR, "the scope does not name the ANSWER"
    assert "مهما كانت الأدوات" in ACK_SCOPE_AR, (
        "the scope is not tool-agnostic — the next capability would re-open it")
    for family_word in ("المسار", "الرسم", "التأشير", "المستند"):
        assert f"بعد {family_word}" not in ACK_SCOPE_AR, (
            f"the scope is written per tool family ({family_word}) rather than "
            "per answer")


# ═══════════════════════════════════════════════════════════════════════════
# THE BEHAVIOURAL LAW — driven across a MULTI-PASS answer
# ═══════════════════════════════════════════════════════════════════════════

class _Overlay:
    def __init__(self):
        self.shown = []

    async def show(self, bbox, label_ar=None):
        self.shown.append(bbox)

    async def hide(self): ...
    def set_state(self, state): ...
    def clear_status_light(self): ...


class _AdvanceNoDraw:
    """Pass 1 advances the plan and draws NOTHING — the shape that leaves
    `tool_choice` on "auto" and opens the ack-eligible second pass."""

    def __init__(self):
        self.calls = []

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.calls.append((user_input.text, tool_choice, list(history)))
        if len(self.calls) == 1:
            args = {"action": "advance"}
            yield ToolCall(name=NAV_STEP_TOOL, args=args, tool_use_id="n1")
            yield TurnComplete(
                input_tokens=1, output_tokens=1, cost_usd=0.0,
                stop_reason="tool_use", model="fake",
                assistant_content=[{"type": "tool_use", "id": "n1",
                                    "name": NAV_STEP_TOOL, "input": args}])
        else:
            yield TextDelta("الخطوة الثانية: انقر على النظام.")
            yield TurnComplete(
                input_tokens=1, output_tokens=1, cost_usd=0.0,
                stop_reason="end_turn", model="fake",
                assistant_content=[{"type": "text", "text": "شرح"}])


def test_the_SECOND_pass_of_a_navigator_answer_receives_the_ack_scope(tmp_path):
    """THE DEFECT, ASSERTED WHERE IT LIVES — between the passes.

    Driven through the REAL Orchestrator, so what is checked is the history
    production actually builds. Pass 2 is still `auto` (T4 measured this and its
    test still asserts it), which is precisely why it can ack again — so the
    directive it receives must carry the scope. A single-pass test cannot see
    this: the gap exists only between an ack-eligible pass and the draw that
    would have silenced it."""
    async def _capture():
        return PNG

    async def _downscale(raw):
        return DownscaledImage(sent_bytes=raw, sent_width=1280, sent_height=720,
                               scale_x=1.5, scale_y=1.5)

    mode = SessionMode()
    reasoner = _AdvanceNoDraw()
    orchestrator = Orchestrator(
        reasoner=reasoner,
        budget=Budget(daily_limit_usd=1.0, budget_file=tmp_path / "b.json"),
        screen_capture=_capture, downscale=_downscale, overlay=_Overlay(),
        session_mode=mode)
    orchestrator._prelude.authority.request(TransitionRequest(
        kind=ENTER, mode_name="تغيير الخلفية",
        plan=Plan.build("تغيير الخلفية", [{"text": t, "expected_result": f"نتيجة {t}"}
                    for t in ("افتح الإعدادات", "انقر النظام", "احفظ")])))

    asyncio.run(orchestrator.run_turn("التالي"))

    assert len(reasoner.calls) >= 2, "the turn never reached a second pass"
    assert reasoner.calls[1][1] == "auto", (
        "pass 2 is no longer ack-eligible — if this changed, the premise of this "
        "test moved and the guard must be re-derived, not deleted")
    # What the model actually READ before pass 2: the history production built.
    second_pass_history = reasoner.calls[1][2]
    tool_results = [
        block.get("content", "")
        for message in second_pass_history if message.get("role") == "user"
        for block in message.get("content", [])
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert tool_results, "pass 2 saw no tool_result at all"
    assert any(ACK_SCOPE_AR in str(content) for content in tool_results), (
        "the navigator directive reaching pass 2 carries NO ack scope — this is "
        "DEC-83's gap exactly, and it is what produced «سم، شوف أول خطوة!"
        "أبشر، شوف شريط البحث!» live")


def test_the_mode_frame_line_the_turn_OPENS_with_also_carries_it(tmp_path):
    """The frame line rides the turn's FIRST user message and is therefore in
    context for every pass. It carries the scope in its POSITIVE form — where
    the ack belongs — never a prohibition: forbidding an ack there would kill the
    MANDATORY opening ack that masks the pass-2 round-trip (v7.1 Fix E)."""
    line = mode_directive_line("تغيير الخلفية", 1, 3, "افتح الإعدادات")
    assert ACK_SCOPE_AR in line
    assert "\n" not in line, "the frame line must stay ONE line (DEC-66)"
    assert "ممنوع" not in ACK_SCOPE_AR, (
        "the scope became a prohibition — on the opening frame line that would "
        "ban the mandatory first ack")
