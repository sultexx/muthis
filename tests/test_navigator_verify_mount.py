"""
test_navigator_verify_mount.py — catalog **v8**, the Navigator's third verb, and
the DEC-39 order it lands in (DEC-108 Gate 2A).

v8 EXTENDS. v5 and v7 each REVISED an existing tool and each had to invent a
blast-radius pin; this change appends one descriptor and leaves every earlier
schema byte-identical, so **the additive guard shape returns** — `v8[:len(v7)]
== v7`, the form v2, v3, v4 and v6 used.

AND IT RETURNS BECAUSE OF THE MOUNT, WHICH IS THE RULING THIS FILE EXISTS TO
PIN. The third verb belongs to the same NAMESPACE as the other two but arrives
through its OWN plugin, so `_v7_router()` — the object every v7-era pin builds —
is untouched and keeps producing eleven tools. A third descriptor on
`NavigatorPlugin` would have reddened those pins for a reason unrelated to what
they protect, and the tempting repair (re-basing them to compare snapshot file
against snapshot file) changes what they ASSERT. **The v7 helper is IMPORTED
here rather than copied**, so "v8 is v7 plus one mount" is a fact this file
demonstrates instead of a sentence it claims.

THE VERB IS NOT IN THE COMPOSITION ROOT YET, AND THAT IS ALSO PINNED. DEC-39's
ordering law — the servicing arm lands BEFORE the mount that makes a tool
reachable — is the one this project learned from a live failure. Gate 2A builds
the structure and joins `NAV_TOOLS`; Gate 2B wires the call site in
`pass_servicing.py` and only then does `main.py` mount it. The test at the
bottom of this file is what makes that a DECISION rather than an omission.
"""

from __future__ import annotations

import ast
import asyncio
import json
import pathlib
import re

import pytest

from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.composition import mount_navigator_verify
from muthis.kernel.budget import Budget
from muthis.kernel.deferral_notes import (
    NAV_PLAN_TOOL, NAV_STEP_TOOL, NAV_TOOLS, NAV_VERIFY_TOOL,
)
from muthis.kernel.highlight_gate import (
    HIGHLIGHT_ACK_TEXT_AR, SHAPES_ACK_TEXT_AR, loop_tool_choice,
)
from muthis.kernel.orchestrator import Orchestrator
from muthis.kernel.router_surfaces import MAX_TOOLS
from muthis.kernel.session_mode import SessionMode
from muthis.kernel.step_verification import OUTCOMES
from muthis.kernel.turn import DownscaledImage
from muthis.kernel.tool_router import ToolRouter
from muthis_plugins.navigator_verify import NavigatorVerifyPlugin
from test_navigator_mount import _v7_router          # the v7 object, not a copy

SNAPSHOTS = pathlib.Path(__file__).parent / "snapshots"
V7_SNAPSHOT = SNAPSHOTS / "look_tools_v7.json"
V8_SNAPSHOT = SNAPSHOTS / "look_tools_v8.json"
MAIN_PY = (pathlib.Path(__file__).resolve().parent.parent / "src" / "muthis"
           / "main.py")
PACKAGE = (pathlib.Path(__file__).resolve().parent.parent / "src"
           / "muthis_plugins" / "navigator_verify")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


def _v8_router() -> ToolRouter:
    """The v8 catalog: the REAL v7 router plus the ONE new mount, in production
    order. Built from `_v7_router()` itself so the extension is demonstrated
    rather than asserted."""
    router = _v7_router()
    mount_navigator_verify(router, NavigatorVerifyPlugin())
    return router


def _route(tool: str):
    return _v8_router()._routes[tool]                 # noqa: SLF001


def _catalog() -> "list[dict]":
    return [descriptor.schema for descriptor in _v8_router().descriptors()]


# ═══ CATALOG v8 — byte-pinned, and ADDITIVE ══════════════════════════════════

def test_v8_catalog_byte_pins_the_verify_verb():
    """The SEVENTH model-visible change (V1 four → v2 sandbox → v3 web → v4 docs
    → v5 revision → v6 navigator → v7 expected_result → v8 verify), built
    through the REAL mounts so the snapshot states what production will show the
    model rather than what a hand-rolled router would."""
    canonical = json.dumps(_catalog(), ensure_ascii=False, indent=2) + "\n"

    assert canonical.encode("utf-8") == V8_SNAPSHOT.read_bytes(), (
        "the v8 catalog drifted from look_tools_v8.json — a model-visible "
        "change; revert the schema edit or re-approve the snapshot")
    assert [tool["name"] for tool in _catalog()][-3:] == [
        NAV_PLAN_TOOL, NAV_STEP_TOOL, NAV_VERIFY_TOOL]
    assert len(_catalog()) == 12


def test_v8_EXTENDS_v7_and_the_ADDITIVE_guard_shape_RETURNS():
    """Two revisions in a row (v5, v7) each needed a blast-radius pin. This one
    appends, so the simple prefix rule is sufficient AGAIN — and sufficiency is
    the assertion: every earlier schema is byte-identical because nothing edited
    one, not because a changed-set check happened to come back empty."""
    catalog = _catalog()
    v7 = json.loads(V7_SNAPSHOT.read_text(encoding="utf-8"))

    assert catalog[:len(v7)] == v7, "v8 is not v7 with ONE tool APPENDED"
    assert len(catalog) == len(v7) + 1
    assert catalog[-1]["name"] == NAV_VERIFY_TOOL


def test_the_SEPARATE_MOUNT_leaves_the_v7_helper_producing_ELEVEN_TOOLS():
    """SULTAN'S RULING, PINNED AT THE ONE PLACE IT COULD SILENTLY STOP HOLDING.

    If the third verb were ever moved onto `NavigatorPlugin`, this fails FIRST
    and by name — before the two v7-era pins fail for a reason that would read
    like a snapshot needing re-approval. Each pin's object stays matched to its
    era: v7's tests v7's catalogue, v8's tests v8's, and no pin is weakened."""
    v7_catalog = [descriptor.schema for descriptor in _v7_router().descriptors()]

    assert len(v7_catalog) == 11, (
        "the v7 helper no longer builds v7 — the verify verb was added to the "
        "plugin the v7 pins mount, not to its own")
    assert v7_catalog == json.loads(V7_SNAPSHOT.read_text(encoding="utf-8"))
    assert NAV_VERIFY_TOOL not in [tool["name"] for tool in v7_catalog]


def test_twelve_tools_stay_well_inside_the_context_cap():
    """The cutoff and the admitted count, stated (the standing rule)."""
    assert len(_v8_router().descriptors()) == 12 < MAX_TOOLS


def test_the_tool_name_is_DERIVED_and_matches_the_anthropic_pattern():
    """DEC-11: the separator lives in ONE place and a dot fails the provider's
    pattern — caught live by a 400 once, guarded ever since. Run over the WHOLE
    v8 catalog, because a name that breaks the pattern costs the capability for
    the whole process, in silence."""
    pattern = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

    for tool in _catalog():
        assert pattern.match(tool["name"]), tool["name"]
    assert "__" in NAV_VERIFY_TOOL and "." not in NAV_VERIFY_TOOL
    for path in PACKAGE.glob("*.py"):
        assert "navigator__" not in path.read_text(encoding="utf-8"), (
            f"{path.name} spells the namespaced form — it must be DERIVED")


# ═══ THE FAIL-CLOSED CONTRACT, as the MODEL is offered it ════════════════════

def test_the_schema_enum_and_the_KERNEL_enumeration_cannot_drift():
    """THE GUARD THE LAYERING LAW MAKES NECESSARY. `muthis_plugins/` may import
    `muthis_sdk` and the stdlib ONLY, so the plugin cannot import
    `step_verification.OUTCOMES` and spells the three names a second time.

    The drift this catches is SILENT: an outcome the schema offers and the
    kernel does not recognise fails CLOSED, which turns every genuine advance
    into a retry with nothing anywhere reporting it."""
    verify = {tool["name"]: tool for tool in _catalog()}[NAV_VERIFY_TOOL]
    offered = verify["input_schema"]["properties"]["outcome"]["enum"]

    assert tuple(offered) == OUTCOMES, (
        f"the schema offers {offered} and the kernel knows {list(OUTCOMES)}")


def test_the_outcome_is_REQUIRED_and_the_evidence_is_conditional_in_PROSE():
    """`required` is a declaration to the provider and DEC-91 measured what a
    provider does with one it does not honour: nothing, in silence. So the
    OUTCOME is declared required and the EVIDENCE — required for exactly one of
    the three outcomes — is stated where the model actually reads it, and
    ENFORCED where it actually holds: the kernel, structurally."""
    verify = {tool["name"]: tool for tool in _catalog()}[NAV_VERIFY_TOOL]
    schema = verify["input_schema"]

    assert schema["required"] == ["outcome"]
    assert set(schema["properties"]) == {"outcome", "evidence"}
    assert "RESULT_PROVEN" in schema["properties"]["evidence"]["description"], (
        "the evidence field no longer tells the model when it is required")


# ═══ DEC-65's invariants, SPENT at the new mount ═════════════════════════════

def test_the_verify_verb_RAISES_NO_TAINT_and_HOLDS_NO_CAPABILITY():
    """A verb that only REPORTS grants less than the two that move a pointer:
    its arguments are the model's own words about a frame already in the
    context. And with nothing for `high_impact`'s capability arm to read, a
    spoken approval can never stand in front of a verification."""
    route = _route(NAV_VERIFY_TOOL)

    assert route.taint is False
    assert route.impact.capabilities == frozenset()
    assert route.impact.high_impact(external=route.taint) is False
    assert route.impact.high_impact(external=True) is False


def test_the_verb_is_KERNEL_SERVICED_so_the_router_never_executes_it():
    assert _route(NAV_VERIFY_TOOL).descriptor.kernel_serviced is True


def test_the_plugin_declares_a_schema_and_reaches_into_nothing():
    """One descriptor and no state — the `NavigatorPlugin` shape. `execute` is
    unreachable in production and refuses like every declaration plugin."""
    plugin = NavigatorVerifyPlugin()

    assert {d.name for d in plugin.descriptors()} == {"verify"}
    assert not [attribute for attribute in vars(plugin)], "the plugin grew state"
    source = (PACKAGE / "plugin.py").read_text(encoding="utf-8")
    for forbidden in ("SessionMode", "ModeAuthority", "Plan", "TransitionRequest",
                      "StepVerification", "verification_from"):
        assert forbidden not in source, f"the plugin reaches into the kernel: {forbidden}"


# ═══ NAV_TOOLS, and the FOUR NEGATIVES ═══════════════════════════════════════

def test_the_verb_joins_NAV_TOOLS_BEFORE_any_mount_makes_it_reachable():
    """DEC-39's ordering, one milestone later: the constant and the arms that
    read it land first. Both arms are reached through this ONE set, so joining
    it wires the detection AND the answer-by-name together."""
    assert NAV_VERIFY_TOOL in NAV_TOOLS
    assert NAV_TOOLS == {NAV_PLAN_TOOL, NAV_STEP_TOOL, NAV_VERIFY_TOOL}

    kernel = pathlib.Path(__file__).resolve().parent.parent / "src" / "muthis" / "kernel"
    for module in ("tool_result_pairing.py", "turn_pass.py"):
        assert "NAV_TOOLS" in (kernel / module).read_text(encoding="utf-8"), (
            f"the arm in {module} is gone")


class _VerifyReasoner:
    """Pass 1 emits ONE `navigator__verify` call; the continuation explains."""

    def __init__(self) -> None:
        self.calls: "list[tuple]" = []

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        self.calls.append((user_input.text, tool_choice))
        if len(self.calls) == 1:
            args = {"outcome": "RESULT_PROVEN", "evidence": "الملف ظاهر"}
            yield ToolCall(name=NAV_VERIFY_TOOL, args=args, tool_use_id="ver_1")
            yield TurnComplete(
                input_tokens=10, output_tokens=5, cost_usd=0.0001,
                stop_reason="tool_use", model="claude-sonnet-4-6",
                assistant_content=[{"type": "tool_use", "id": "ver_1",
                                    "name": NAV_VERIFY_TOOL, "input": args}])
        else:
            yield TextDelta("تمام.")
            yield TurnComplete(
                input_tokens=5, output_tokens=5, cost_usd=0.0001,
                stop_reason="end_turn", model="claude-sonnet-4-6",
                assistant_content=[{"type": "text", "text": "شرح"}])


class _Overlay:
    def __init__(self) -> None:
        self.shown: "list" = []

    async def show(self, bbox, label_ar=None):
        self.shown.append(bbox)

    async def hide(self):
        pass

    def set_state(self, state):
        pass

    def clear_status_light(self):
        pass


def _orchestrator(reasoner, tmp_path, mode):
    async def _capture():
        return PNG

    async def _downscale(raw):
        return DownscaledImage(sent_bytes=raw, sent_width=1280, sent_height=720,
                               scale_x=1.5, scale_y=1.5)

    return Orchestrator(
        reasoner=reasoner,
        budget=Budget(daily_limit_usd=1.0, budget_file=tmp_path / "b.json"),
        screen_capture=_capture, downscale=_downscale,
        overlay=_Overlay(), session_mode=mode)


def test_a_verify_call_gets_NO_POINTER_ACK_no_gate_flip_and_no_violation(
        tmp_path, caplog):
    """THE FOUR NEGATIVES, in one drive through the REAL orchestrator — the four
    faces of the SAME defect, an id nobody answered, and asserting one would
    leave the other three free. This is the test that would have caught the M2
    bug, written BEFORE the verb can be reached rather than after."""
    mode = SessionMode()
    orchestrator = _orchestrator(_VerifyReasoner(), tmp_path, mode)

    with caplog.at_level("ERROR"):
        asyncio.run(orchestrator.run_turn("تحقّق"))

    pairing = next(message for message in orchestrator.history
                   if message["role"] == "user"
                   and isinstance(message["content"], list)
                   and any(block.get("type") == "tool_result"
                           for block in message["content"]))
    answer = next(block for block in pairing["content"]
                  if block["tool_use_id"] == "ver_1")

    # (1) NOT the pointer ack — the draw branch never saw it.
    assert answer["content"] not in (HIGHLIGHT_ACK_TEXT_AR, SHAPES_ACK_TEXT_AR)
    # (2) the id WAS answered, by name, so nothing is left orphaned.
    assert answer["type"] == "tool_result" and answer["content"]
    # (3) the draw gate never flipped, so the loop was never terminated.
    assert orchestrator._highlight_gate.drawn is False
    assert loop_tool_choice(orchestrator._highlight_gate) == "auto"
    # (4) no LOOK-only violation was logged.
    assert "LOOK-only violation" not in caplog.text


def test_the_verb_moves_NOTHING_at_gate_2A_because_it_has_no_consumer_yet():
    """The honest state of this gate, asserted rather than described. The
    machine exists and the verb is answered; NOTHING reads the outcome, no state
    is kept and no step advances. Gate 2B is where that changes, and this test
    is what makes the change visible when it does."""
    mode = SessionMode()
    kernel = pathlib.Path(__file__).resolve().parent.parent / "src" / "muthis" / "kernel"
    servicing = (kernel / "pass_servicing.py").read_text(encoding="utf-8")

    assert mode.active is False
    assert "step_verification" not in servicing, (
        "the call site landed — that is Gate 2B, after Sultan's review")
    assert "VERIFYING" not in (kernel / "session_mode.py").read_text(encoding="utf-8")


# ═══ THE COMPOSITION ROOT — the DEC-39 order, pinned ═════════════════════════

def test_the_composition_root_has_NOT_mounted_the_verify_verb_yet():
    """DEC-39 AS A DELIBERATE ORDER RATHER THAN AN OMISSION — and it is the one
    ambiguity in Gate 2A's brief, resolved toward this project's own law.

    `deferral_notes.py` states it in the source: the constant and the arm that
    reads it "land BEFORE the mount that makes the tools reachable". A verb
    mounted now would be model-visible with no servicing arm behind it, and
    `service_navigator_call` would answer it as a malformed `step` — the exact
    class of half-wired surface DEC-39 was written from. Gate 2B adds ONE line
    to `main.py` and flips this test, which is where it belongs."""
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    mounted = {getattr(node.func, "id", "") for node in ast.walk(tree)
               if isinstance(node, ast.Call)}

    assert "mount_navigator" in mounted, "the navigator mount vanished"
    assert "mount_navigator_verify" not in mounted, (
        "the composition root mounted the verify verb — Gate 2A ships the "
        "structure only; the mount follows the call site (DEC-39)")


def test_the_mount_helper_EXISTS_and_is_the_one_line_gate_2B_will_add():
    """The helper is production code and is driven here, so Gate 2B's remaining
    work is a call rather than a design."""
    router = _v7_router()
    mount_navigator_verify(router, NavigatorVerifyPlugin())

    assert [d.name for d in router.descriptors()][-1] == NAV_VERIFY_TOOL


@pytest.mark.parametrize("path", sorted(PACKAGE.glob("*.py")))
def test_the_new_package_obeys_the_layering_law(path):
    """`muthis_plugins/` imports `muthis_sdk` and the stdlib ONLY — never
    `muthis.*`. Asserted per file here as well as by the tree-wide scan, because
    this package is the first one whose kernel twin holds the same three
    strings, and reaching for the import would look like deduplication."""
    for line in path.read_text(encoding="utf-8").splitlines():
        assert not re.match(r"\s*(from|import)\s+muthis(\.|\s|$)", line), (
            f"{path.name} imports the app: {line.strip()}")
