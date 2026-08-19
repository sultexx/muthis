"""
test_mode_indicator.py — DEC-65's kernel-drawn mode indicator (T3).

THE PROPERTY THAT NEEDS THE MOST CARE IS CROSS-TURN SURVIVAL, because it is
INVISIBLE TO ANY SINGLE-TURN TEST. The badge's per-turn lifetime is free precisely
because `clear_caption` fires at end of turn — so an indicator that inherited that
arrangement would look perfect for one turn and vanish on the next. Every survival
test below therefore runs THREE turns through the REAL `FrameCapture`, the REAL
`dispatch_command` and a REAL `ModeIndicator`, with the mode told to draw ONCE,
on turn one. Turns two and three are the assertion.

AND THE "NEVER MODEL-AUTHORED" CLAIM IS PROVEN TWICE OVER, as the acceptance
condition asks: by ATTRIBUTE SCAN (the composer reads four kernel attributes and
nothing else) and by SOURCE SCAN (the widget package names no model-facing
symbol, and the composition seam can hand the overlay nothing but the composer's
own output). A behavioural check alone would pass on a build that also had a
second, unguarded path to the same canvas.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib

import pytest

from muthis.kernel.frame_capture import FrameCapture
from muthis.kernel.highlight_gate import HighlightGate
from muthis.kernel.mode_surfaces import mode_indicator_text
from muthis.kernel.mode_transition import ENTER, ModeAuthority, TransitionRequest
from muthis.kernel.plan import Plan
from muthis.kernel.session_mode import SessionMode
from muthis.kernel.turn import TurnResult
from muthis.overlay.domain_badge import BOTTOM_MARGIN_PX, DOMAIN_BADGE_TAG, DomainBadge
from muthis.overlay.mode_indicator import (
    MODE_INDICATOR_TAG, TOP_MARGIN_PX, ModeIndicator,
)
from muthis.overlay.sidekick_window import SidekickOverlay
from muthis.overlay.style import OverlayStyle
from muthis.overlay.window_commands import dispatch_command
from muthis.overlay_autohide import AutoHideController

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
INDICATOR_PY = SRC / "muthis" / "overlay" / "mode_indicator.py"
SURFACES_PY = SRC / "muthis" / "kernel" / "mode_surfaces.py"
COMPOSITION_PY = SRC / "muthis" / "composition.py"
STEP_TEXTS = ("افتح الإعدادات", "اختر الشبكة", "احفظ")
# DEC-107: a step is a text AND the result the user will SEE. The indicator
# reads only the text, which is exactly why the result is given a DIFFERENT
# value here — an indicator that ever showed it would fail these assertions.
STEP_SPECS = tuple({"text": t, "expected_result": f"نتيجة {t}"} for t in STEP_TEXTS)


class _FakeCanvas:
    """Duck-typed canvas: records items per tag, so "is it drawn" is a fact."""

    def __init__(self) -> None:
        self.items: "dict[int, str]" = {}
        self.texts: "dict[int, str]" = {}
        self._next = 1

    def _add(self, tags: str, text: str = "") -> int:
        item = self._next
        self._next += 1
        self.items[item] = tags
        self.texts[item] = text
        return item

    def create_text(self, *_a, text="", tags="", **_kw) -> int:
        return self._add(tags, text)

    def create_polygon(self, *_a, tags="", **_kw) -> int:
        return self._add(tags)

    def bbox(self, _item):
        return (10, 10, 200, 40)

    def tag_lower(self, *_a) -> None:
        pass

    def delete(self, tag) -> None:
        for item in [i for i, t in self.items.items() if t == tag]:
            del self.items[item]
            self.texts.pop(item, None)

    # ─ the reading helpers the tests actually assert on ─
    def drawn(self, tag: str) -> "list[str]":
        return [self.texts[i] for i, t in self.items.items() if t == tag and self.texts[i]]

    def has(self, tag: str) -> bool:
        return any(t == tag for t in self.items.values())


class _Sent:
    sent_width, sent_height, scale_x, scale_y = 1280, 720, 1.5, 1.5
    sent_bytes = b"png"


class _NoAutoHide:
    def cancel(self) -> None:
        pass


class _DispatchOverlay:
    """An overlay that runs the REAL dispatcher against real widgets — so the
    hide / restore / clear_caption BRANCHES are the ones under test, not a fake
    of them."""

    def __init__(self, canvas) -> None:
        style = OverlayStyle()
        self.indicator = ModeIndicator(canvas, style=style)
        self.badge = DomainBadge(canvas, (1920, 1080), style=style)
        self.states: "list[str]" = []

    def _dispatch(self, command) -> None:
        dispatch_command(command, rect=_Noop(), pointer=_Noop(), animator=_Noop(),
                         badge=self.badge, mode=self.indicator)

    def show_mode_indicator(self, text: str) -> None:
        self._dispatch(("show_mode_indicator", text))

    def restore_mode_indicator(self) -> None:
        self._dispatch(("restore_mode_indicator",))

    def show_domain_badge(self, domains) -> None:
        self._dispatch(("show_domain_badge", tuple(domains)))

    def clear_caption(self) -> None:
        self._dispatch(("clear_caption",))

    async def hide(self) -> None:
        self._dispatch(("hide",))

    async def hide_for_capture(self) -> None:
        # Mirrors `SidekickOverlay.hide_for_capture` (DEC-104 ruling 1) — the
        # ONE hide that leaves the chip erased, because a grab follows it.
        # `FrameCapture` reaches this by getattr, exactly as production does.
        self._dispatch(("hide", False))

    def clear_status_light(self) -> None:
        self.states.append("cleared")

    def set_state(self, state: str) -> None:
        self.states.append(state)


class _Noop:
    def __getattr__(self, _name):
        return lambda *a, **k: None


def _graph():
    """The production shape: a mode whose on_change feeds the overlay, and the
    REAL capture chokepoint over it."""
    canvas = _FakeCanvas()
    overlay = _DispatchOverlay(canvas)
    mode = SessionMode(
        on_change=lambda m: overlay.show_mode_indicator(mode_indicator_text(m)))
    frames = FrameCapture(overlay=overlay, screen_capture=_capture,
                          downscale=_downscale, auto_hide=_NoAutoHide(), settle_s=0)
    return canvas, overlay, mode, ModeAuthority(mode=mode), frames


async def _capture():
    return b"raw"


async def _downscale(_raw):
    return _Sent()


def _turn(frames) -> None:
    """ONE turn's capture — hide (ghosting) → grab → relight → restore."""
    asyncio.run(frames.capture(TurnResult()))


# ─── Drawn from KERNEL state, never model input ─────────────────────────────

def test_the_composer_takes_exactly_one_argument_and_it_is_the_frame():
    """A caller cannot pass this function a claim — only the mode. "Never
    model-authored" is a property of the SIGNATURE, not of the call sites."""
    params = list(inspect.signature(mode_indicator_text).parameters)
    assert params == ["mode"], f"a second input appeared: {params}"


def test_the_composer_reads_four_kernel_attributes_and_nothing_else():
    """ATTRIBUTE SCAN. Anything else read off the frame — the plan's steps, a
    step's text — would be a new path onto a persistent user-facing surface."""
    tree = ast.parse(SURFACES_PY.read_text(encoding="utf-8"))
    func = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "mode_indicator_text")
    read = {n.attr for n in ast.walk(func)
            if isinstance(n, ast.Attribute) and getattr(n.value, "id", "") == "mode"}
    assert read == {"active", "name", "total_steps", "current_step"}, (
        f"the indicator's inputs changed: {sorted(read)}")


def test_no_model_authored_step_text_reaches_the_indicator():
    """The behavioural twin: the step TEXT belongs in the directive the model
    reads, never on the element the user watches."""
    mode = SessionMode()
    ModeAuthority(mode=mode).request(TransitionRequest(
        kind=ENTER, mode_name="navigator", plan=Plan.build("t", STEP_SPECS)))
    text = mode_indicator_text(mode)
    for step_text in STEP_TEXTS:
        assert step_text not in text, "model-authored text reached the indicator"
    assert "navigator" in text and "١" in text and "٣" in text


def test_the_widget_package_names_no_model_facing_symbol():
    """SOURCE SCAN, the second half the acceptance condition asks for. The
    widget must have no way to receive a tool result, a transcript or a
    reasoner event even if a future call site tried to hand it one."""
    names = {n.id for n in ast.walk(ast.parse(INDICATOR_PY.read_text(encoding="utf-8")))
             if isinstance(n, ast.Name)}
    for forbidden in ("ToolCall", "TurnComplete", "TextDelta", "assistant",
                      "transcript", "reasoner", "tool_result", "user_input"):
        assert forbidden not in names, f"mode_indicator.py names {forbidden}"


class _RecordingOverlay:
    """Records what the production seam actually sends it."""

    def __init__(self) -> None:
        self.shown: "list[str]" = []

    def show_mode_indicator(self, text: str) -> None:
        self.shown.append(text)


def test_the_REAL_composition_root_wires_the_seam_end_to_end():
    """ADDED AFTER A MUTATION SURVIVED, and the survivor is the family this
    project keeps meeting: every test above builds its OWN `on_change`, so
    deleting the production wiring entirely stayed GREEN. That is DEC-40's
    defect exactly — five of six mutations surviving because every test built
    its own router — and the answer is the same one T1 used: drive the REAL
    helper and assert the REAL overlay was reached."""
    from muthis import composition

    overlay = _RecordingOverlay()
    orchestrator = composition._build_orchestrator(
        object(), object(), overlay, object(), object(), object())

    mode = orchestrator._prelude.session_mode
    ModeAuthority(mode=mode).request(TransitionRequest(
        kind=ENTER, mode_name="navigator", plan=Plan.build("t", STEP_SPECS)))

    assert overlay.shown, "the composition root never wired the indicator seam"
    assert "navigator" in overlay.shown[-1] and "١" in overlay.shown[-1]


def test_the_root_seam_never_lets_a_failure_kill_a_turn():
    """`SessionMode` has no logger by design, so the guard belongs on the root's
    callable — the `turn_hooks` discipline: logged, never raised."""
    class _Exploding:
        def show_mode_indicator(self, _text):
            raise RuntimeError("overlay is gone")

    from muthis import composition

    mode = SessionMode(on_change=composition._mode_indicator_seam(_Exploding()))
    ModeAuthority(mode=mode).request(TransitionRequest(kind=ENTER, mode_name="x"))
    assert mode.active is True, "an indicator failure killed the transition"


def test_the_composition_seam_can_hand_the_overlay_nothing_but_the_composer():
    """The wiring half: the root's callable passes `show(...)` the result of
    `mode_indicator_text` and never a value of its own — so there is no second
    string that could reach this surface through the production path."""
    tree = ast.parse(COMPOSITION_PY.read_text(encoding="utf-8"))
    seam = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "_mode_indicator_seam")
    shows = [n for n in ast.walk(seam)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "show"]
    assert shows, "the seam no longer draws anything"
    for call in shows:
        assert (len(call.args) == 1
                and isinstance(call.args[0], ast.Call)
                and getattr(call.args[0].func, "id", "") == "mode_indicator_text"), (
            "the overlay is handed something other than the kernel's composed frame")


# ─── Inactive draws NOTHING ─────────────────────────────────────────────────

def test_an_inactive_mode_renders_no_text_and_no_chip():
    canvas, _overlay, mode, _authority, _frames = _graph()
    assert mode_indicator_text(mode) == ""
    assert not canvas.has(MODE_INDICATOR_TAG), "an empty chip was drawn"


def test_a_mode_without_a_plan_shows_its_name_and_no_step_numbers():
    mode = SessionMode()
    ModeAuthority(mode=mode).request(TransitionRequest(kind=ENTER, mode_name="review"))
    assert mode_indicator_text(mode) == "review"


def test_ending_the_mode_FORGETS_it_so_a_later_restore_cannot_resurrect_it():
    canvas, _overlay, mode, authority, frames = _graph()
    authority.request(TransitionRequest(kind=ENTER, mode_name="navigator",
                                        plan=Plan.build("t", STEP_SPECS)))
    _turn(frames)
    assert canvas.has(MODE_INDICATOR_TAG)

    authority.request(TransitionRequest(kind="leave"))
    _turn(frames)
    assert not canvas.has(MODE_INDICATOR_TAG), "an ended mode came back on restore"


# ─── SURVIVAL ACROSS TURNS — the property no single turn can show ───────────

def test_the_indicator_survives_THREE_turns_after_being_drawn_ONCE():
    """THE LOAD-BEARING TEST. The mode is told to draw on turn one only; turns
    two and three redraw it from the widget's own memory, through the REAL
    capture chokepoint. A build that inherited the badge's lifecycle passes turn
    one and fails here."""
    canvas, _overlay, _mode, authority, frames = _graph()
    authority.request(TransitionRequest(kind=ENTER, mode_name="navigator",
                                        plan=Plan.build("t", STEP_SPECS)))
    drawn_per_turn = []
    for _turn_index in range(3):
        _turn(frames)                              # hide → grab → relight → restore
        drawn_per_turn.append(canvas.drawn(MODE_INDICATOR_TAG))

    assert all(drawn_per_turn), f"the indicator died across turns: {drawn_per_turn}"
    assert len({tuple(d) for d in drawn_per_turn}) == 1, "the text changed by itself"


def test_the_capture_never_sees_the_indicator_and_the_restore_is_AFTER_the_grab():
    """GHOSTING, and the ordering that makes it true: at the moment pixels are
    grabbed the chip must be gone, and it must be back immediately after."""
    canvas, overlay, _mode, authority, _frames = _graph()
    authority.request(TransitionRequest(kind=ENTER, mode_name="navigator",
                                        plan=Plan.build("t", STEP_SPECS)))
    seen = {}

    async def _grab_and_look():
        seen["during"] = canvas.has(MODE_INDICATOR_TAG)
        return b"raw"

    frames = FrameCapture(overlay=overlay, screen_capture=_grab_and_look,
                          downscale=_downscale, auto_hide=_NoAutoHide(), settle_s=0)
    asyncio.run(frames.capture(TurnResult()))

    assert seen["during"] is False, "Claude would have seen our own indicator"
    assert canvas.has(MODE_INDICATOR_TAG), "the restore never happened"


def test_a_progress_change_mid_session_redraws_immediately():
    """The backstop must not lag the state it backs: a model claiming step 3
    while the chip reads ٢ is only 'visibly contradicted' if the chip is
    current. Every applied transition redraws, because the observer fires from
    the ONE mutation point."""
    canvas, _overlay, _mode, authority, frames = _graph()
    authority.request(TransitionRequest(kind=ENTER, mode_name="navigator",
                                        plan=Plan.build("t", STEP_SPECS)))
    _turn(frames)
    assert "١" in canvas.drawn(MODE_INDICATOR_TAG)[0]

    authority.request(TransitionRequest(kind="advance"))
    assert "٢" in canvas.drawn(MODE_INDICATOR_TAG)[0], "the chip lagged the frame"


def test_clear_caption_does_NOT_clear_the_indicator_but_DOES_clear_the_badge():
    """THE CARRIED WARNING, as one assertion with its own positive control. The
    badge's per-turn lifetime is free BECAUSE this fires at end of turn — which
    is exactly why the arrangement cannot transfer to a cross-turn element."""
    canvas, overlay, _mode, authority, _frames = _graph()
    authority.request(TransitionRequest(kind=ENTER, mode_name="navigator",
                                        plan=Plan.build("t", STEP_SPECS)))
    overlay.show_domain_badge(("example.com",))
    assert canvas.has(DOMAIN_BADGE_TAG) and canvas.has(MODE_INDICATOR_TAG)

    overlay.clear_caption()
    assert not canvas.has(DOMAIN_BADGE_TAG), "the badge no longer inherits it"
    assert canvas.has(MODE_INDICATOR_TAG), "the indicator was cleared at end of turn"


# ─── DEC-104 ruling 1 — THE HIDE THAT IS NOT A CAPTURE ──────────────────────
#
# The defect DEC-102 measured: `overlay_autohide.py` fires 7 s after speech end
# on EVERY drawing step of EVERY walkthrough, its hide reached
# `window_commands`' ghosting branch, and the only `restore_mode_indicator` in
# the tree sat in `FrameCapture.capture` — so the chip stayed dead until the
# next F9. The mode was alive in the kernel the whole time; its only on-screen
# evidence was not. Every test below drives the REAL controller, the REAL
# dispatcher and a REAL `ModeIndicator` — never a hand-written ("hide",).


def _auto_hide_fires(overlay) -> None:
    """Drive the REAL `AutoHideController` to completion on a zero-length timer,
    so the hide that reaches the dispatcher is the production one
    (`overlay_autohide.py`'s `_hide_after_timeout`), not a tuple we typed."""
    async def _drive() -> None:
        controller = AutoHideController(overlay, timeout_s=0)
        controller.schedule()
        await controller.task

    asyncio.run(_drive())


def test_the_chip_survives_the_AUTO_HIDE_and_is_still_there_NEXT_turn():
    """TEST 1 — THE DEFECT ITSELF, and it is invisible to any single-turn
    assertion. The auto-hide fires AFTER the turn's capture, so a test that
    stopped at the capture would find the chip present and pass while the
    product went blank a moment later; and the NEXT turn's capture restores it,
    so a test that only looked at end-of-turn-two would pass too. The
    discriminating observations are therefore both taken here — right after each
    auto-hide, and again at the top of the following turn (`carried_in`), which
    is the state the previous turn actually handed over. That is T3's lesson."""
    canvas, overlay, _mode, authority, frames = _graph()
    authority.request(TransitionRequest(kind=ENTER, mode_name="navigator",
                                        plan=Plan.build("t", STEP_SPECS)))
    carried_in, after_auto_hide = [], []
    for turn_index in range(3):
        if turn_index:                  # what the PREVIOUS turn left standing
            carried_in.append(canvas.drawn(MODE_INDICATOR_TAG))
        _turn(frames)                   # the turn's capture: hide → grab → restore
        _auto_hide_fires(overlay)       # 7 s after speech end, every drawing step
        after_auto_hide.append(canvas.drawn(MODE_INDICATOR_TAG))

    assert all(after_auto_hide), (
        f"the auto-hide erased the mode's evidence: {after_auto_hide}")
    assert all(carried_in), (
        f"the chip did not survive INTO the next turn: {carried_in}")
    assert len({tuple(d) for d in after_auto_hide}) == 1, "the text changed by itself"


def test_the_chip_is_ABSENT_from_every_frame_the_provider_is_SENT():
    """TEST 2 — THE GUARD AGAINST RESTORING TOO EARLY, and the reason the
    unified restore is safe. Capture hides DELIBERATELY: T6's
    `diag_navigator_sent_frame.png` shows the chip absent and Sultan verified it
    by eye, so a design that restored immediately in all three cases would break
    a proven invariant. The assertion is taken INSIDE the grab, off the same
    canvas the dispatcher draws on — the frame's own content, not the order of
    the source lines — and it is taken three times with the chip restored in
    between, so the restore is proven not to leak into ANY grab."""
    canvas, overlay, _mode, authority, _frames = _graph()
    authority.request(TransitionRequest(kind=ENTER, mode_name="navigator",
                                        plan=Plan.build("t", STEP_SPECS)))
    in_the_frame = []

    async def _grab_and_look():
        in_the_frame.append(canvas.drawn(MODE_INDICATOR_TAG))
        return b"raw"

    frames = FrameCapture(overlay=overlay, screen_capture=_grab_and_look,
                          downscale=_downscale, auto_hide=_NoAutoHide(), settle_s=0)
    for _turn_index in range(3):
        asyncio.run(frames.capture(TurnResult()))
        _auto_hide_fires(overlay)       # the chip is BACK between captures …

    assert in_the_frame == [[], [], []], (
        f"the provider was sent a frame containing our own chip: {in_the_frame}")
    assert canvas.drawn(MODE_INDICATOR_TAG), "… and standing again afterwards"


def test_an_ENDED_mode_is_not_resurrected_by_the_AUTO_HIDE_restore():
    """TEST 3 — the unified restore must be unable to bring back a mode that is
    OVER. It is, and not by asking anything: an ended mode has already been sent
    an EMPTY text, which FORGETS (DEC-104), so `restore()` draws nothing. The
    capture path already had this property; the auto-hide path is new and gets
    it for free — which is the point of unifying rather than re-implementing."""
    canvas, overlay, _mode, authority, frames = _graph()
    authority.request(TransitionRequest(kind=ENTER, mode_name="navigator",
                                        plan=Plan.build("t", STEP_SPECS)))
    _turn(frames)
    _auto_hide_fires(overlay)
    assert canvas.has(MODE_INDICATOR_TAG), "positive control: a LIVE mode is drawn"

    authority.request(TransitionRequest(kind="leave"))
    _auto_hide_fires(overlay)
    assert not canvas.has(MODE_INDICATOR_TAG), "the auto-hide resurrected an ended mode"
    _turn(frames)
    _auto_hide_fires(overlay)
    assert not canvas.has(MODE_INDICATOR_TAG), "… and it returned a turn later"


def test_barge_in_restores_a_LIVE_mode_and_draws_NOTHING_when_there_is_none():
    """TEST 4 — BOTH DIRECTIONS IN ONE DRIVE, through the REAL
    `Orchestrator.interrupt_turn` and the REAL composition wiring. F9 tears down
    the TURN, not the MODE (Sultan's ruling), so a live walkthrough keeps its
    chip; but a one-directional assertion would pass just as happily on a build
    that drew a chip which should not exist, so the no-mode case is asserted on
    either side of the live one. `interrupt_turn` costs `orchestrator.py` ZERO
    lines — it already calls `hide()`, and the duty now travels with it."""
    from muthis import composition

    canvas = _FakeCanvas()
    overlay = _DispatchOverlay(canvas)
    orchestrator = composition._build_orchestrator(
        object(), object(), overlay, object(), object(), object())
    authority = ModeAuthority(mode=orchestrator._prelude.session_mode)

    asyncio.run(orchestrator.interrupt_turn())
    assert not canvas.has(MODE_INDICATOR_TAG), "a barge-in drew a chip with no mode"

    authority.request(TransitionRequest(kind=ENTER, mode_name="navigator",
                                        plan=Plan.build("t", STEP_SPECS)))
    asyncio.run(orchestrator.interrupt_turn())
    assert canvas.drawn(MODE_INDICATOR_TAG), "the barge-in erased a live mode's evidence"

    authority.request(TransitionRequest(kind="leave"))
    asyncio.run(orchestrator.interrupt_turn())
    assert not canvas.has(MODE_INDICATOR_TAG), "the barge-in resurrected an ended mode"


class _QueueSpy:
    """`SidekickOverlay` minus Tk: only the queue hop is stubbed, so the command
    under test is the byte-for-byte one production enqueues."""

    def __init__(self) -> None:
        self.commands: "list[tuple]" = []

    def _enqueue(self, command: tuple) -> None:
        self.commands.append(command)


def test_the_real_overlays_two_hides_differ_ONLY_in_the_chip_coming_back():
    """THE SEAM'S FAIL-OPEN, CLOSED. `FrameCapture` reaches the capture hide by
    getattr — the idiom that file already uses for the restore — so an overlay
    LACKING the verb falls back to the restoring hide and would put the chip in
    a frame. There is exactly one production overlay, and this takes BOTH of its
    real hides (no Tk: only `_enqueue` is stubbed) and runs them through the
    REAL dispatcher against a REAL widget, so the verb's existence and the two
    hides' difference are one assertion instead of a source scan."""
    spy = _QueueSpy()
    asyncio.run(SidekickOverlay.hide_for_capture(spy))
    asyncio.run(SidekickOverlay.hide(spy))
    capture_hide, plain_hide = spy.commands

    canvas = _FakeCanvas()
    indicator = ModeIndicator(canvas, style=OverlayStyle())
    indicator.show("navigator ١/٣")

    dispatch_command(capture_hide, rect=_Noop(), pointer=_Noop(),
                     animator=_Noop(), mode=indicator)
    assert not canvas.has(MODE_INDICATOR_TAG), "the capture hide brought the chip back"

    dispatch_command(plain_hide, rect=_Noop(), pointer=_Noop(),
                     animator=_Noop(), mode=indicator)
    assert canvas.has(MODE_INDICATOR_TAG), "the plain hide did not restore the chip"


# ─── D-3: it disturbs nothing it is not allowed to disturb ──────────────────

def test_it_is_collision_free_by_construction_rather_than_by_an_offset():
    """Every other persistent element is anchored to the BOTTOM edge — the
    caption chip bottom-centre, the badge bottom-left, the status dot
    bottom-right by default — so a TOP anchor cannot collide however the caption
    wraps or the font changes."""
    assert TOP_MARGIN_PX > 0 and BOTTOM_MARGIN_PX > 0
    assert "bottom" in OverlayStyle().status_corner
    source = INDICATOR_PY.read_text(encoding="utf-8")
    assert 'anchor="nw"' in source, "the indicator stopped being top-anchored"
    assert MODE_INDICATOR_TAG != DOMAIN_BADGE_TAG


def test_it_consumes_none_of_the_captions_text_budget():
    """A separate, tag-scoped element on its own anchor: a long mode name can
    never eat a line of speech, because it never reaches the caption at all."""
    source = INDICATOR_PY.read_text(encoding="utf-8")
    assert "caption_bar" not in source and "wrap_caption" not in source
    canvas, overlay, _mode, _authority, _frames = _graph()
    overlay.show_mode_indicator("م" * 400)
    assert canvas.has(MODE_INDICATOR_TAG)
    assert not canvas.has("muthis-caption")


def test_it_never_consumes_the_per_turn_draw_gate():
    """The indicator is METADATA, not a visual intent — a step that points
    still gets its one pointing (DEC-67's per-turn resource is untouched)."""
    gate = HighlightGate()
    canvas, overlay, _mode, authority, frames = _graph()
    authority.request(TransitionRequest(kind=ENTER, mode_name="navigator",
                                        plan=Plan.build("t", STEP_SPECS)))
    _turn(frames)
    authority.request(TransitionRequest(kind="advance"))
    assert gate.drawn is False, "the indicator flipped the draw gate"

    source = INDICATOR_PY.read_text(encoding="utf-8")
    for forbidden in ("HighlightGate", "next_draw", "draw_dispatch", "PendingDraw",
                      "highlight_gate", "tool_choice"):
        assert forbidden not in source, f"mode_indicator.py names {forbidden}"


@pytest.mark.parametrize("path,symbol", [
    ("kernel/turn_pass.py", "mode_indicator"),
    ("turn_voice.py", "mode_indicator"),
    ("voice_out.py", "mode_indicator"),
    ("overlay/caption_bar.py", "mode_indicator"),
    ("kernel/draw_dispatch.py", "mode_indicator"),
    ("kernel/highlight_gate.py", "mode_indicator"),
])
def test_the_sacred_paths_do_not_know_the_indicator_exists(path, symbol):
    """Option-A sync, the turn voice, the caption chokepoint, caption pacing and
    the draw circuit are untouched — asserted as an ABSENCE of the symbol, so a
    future wiring into any of them fails here rather than in a live run."""
    assert symbol not in (SRC / "muthis" / path).read_text(encoding="utf-8")
