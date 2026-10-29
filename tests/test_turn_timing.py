"""
test_turn_timing.py — DEC-157 ⑤'s three timing lines: emitted only under debug,
only once the voice instrument has started the clock, and never in the durable
log.

The lines are `[timing] first_token|draw|first_audio +N ms`. Each is proven to
FIRE through the real code path that carries it — a scripted turn through the
real Orchestrator for the first two, the real PCM player for the third — and to
stay SILENT in the two states normal operation is in: debug off, or debug on
with no instrument (nothing in the app starts the clock).
"""

from __future__ import annotations

import ast
import logging
import pathlib

import pytest

from muthis import logging_policy, turn_timing
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete
from muthis.kernel.budget import Budget
from muthis.kernel.orchestrator import Orchestrator
from muthis.kernel.turn import DownscaledImage
from muthis.tts_ws_player import PcmStreamPlayer

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


@pytest.fixture(autouse=True)
def _clean_clock(monkeypatch):
    monkeypatch.delenv(logging_policy.DEBUG_ENV, raising=False)
    turn_timing.reset()
    yield
    turn_timing.reset()


def _debug_on(monkeypatch):
    monkeypatch.setenv(logging_policy.DEBUG_ENV, "1")


def _timing_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "muthis.timing"]


# ─── The clock itself ──────────────────────────────────────────────────────────

def test_debug_OFF_the_clock_never_starts_and_nothing_is_emitted(caplog):
    caplog.set_level(logging.INFO, logger="muthis.timing")
    turn_timing.turn_started(now=100.0)
    assert turn_timing._turn_start is None, "the clock started outside debug"
    turn_timing.stage("first_token", now=100.5)
    assert _timing_lines(caplog) == []


def test_debug_switched_OFF_mid_turn_stops_the_lines(monkeypatch, caplog):
    """The SECOND gate, on its own: `stage()` re-reads the predicate, so a clock
    started under debug still emits nothing once debug is off."""
    _debug_on(monkeypatch)
    caplog.set_level(logging.INFO, logger="muthis.timing")
    turn_timing.turn_started(now=0.0)
    monkeypatch.delenv(logging_policy.DEBUG_ENV)
    turn_timing.stage("draw", now=1.0)
    assert _timing_lines(caplog) == []


def test_debug_ON_each_stage_is_emitted_ONCE_in_ms_since_the_start(monkeypatch, caplog):
    _debug_on(monkeypatch)
    caplog.set_level(logging.INFO, logger="muthis.timing")
    turn_timing.turn_started(now=100.0)
    turn_timing.stage("first_token", now=101.2345)
    turn_timing.stage("first_token", now=102.0)          # a later delta: no second line
    turn_timing.stage("draw", now=101.5)
    assert _timing_lines(caplog) == ["[timing] first_token +1234 ms", "[timing] draw +1500 ms"]


def test_a_new_turn_restarts_the_clock(monkeypatch, caplog):
    _debug_on(monkeypatch)
    caplog.set_level(logging.INFO, logger="muthis.timing")
    turn_timing.turn_started(now=0.0)
    turn_timing.stage("draw", now=1.0)
    turn_timing.turn_started(now=10.0)
    turn_timing.stage("draw", now=10.25)
    assert _timing_lines(caplog) == ["[timing] draw +1000 ms", "[timing] draw +250 ms"]


def test_debug_ON_without_the_instrument_nothing_is_emitted(monkeypatch, caplog):
    """Debug alone is not enough: only `turn_started()` starts the clock, and no
    module of the app calls it (proven by scan below)."""
    _debug_on(monkeypatch)
    caplog.set_level(logging.INFO, logger="muthis.timing")
    for name in turn_timing.STAGES:
        turn_timing.stage(name)
    assert _timing_lines(caplog) == []


def test_a_TurnComplete_is_not_a_first_token(monkeypatch, caplog):
    _debug_on(monkeypatch)
    caplog.set_level(logging.INFO, logger="muthis.timing")
    turn_timing.turn_started()
    turn_timing.model_event(TurnComplete(input_tokens=1, output_tokens=0, cost_usd=0.0,
                                         stop_reason="end_turn", model="m"))
    assert _timing_lines(caplog) == []
    turn_timing.model_event(TextDelta("أ"))
    assert [line.split(" +")[0] for line in _timing_lines(caplog)] == ["[timing] first_token"]


# ─── Never in the durable log ──────────────────────────────────────────────────

def test_the_lines_and_the_durable_log_read_ONE_predicate():
    """The state in which a timing line can exist is the state in which the file
    handler cannot be built — because both read the same function."""
    assert turn_timing.debug_content_enabled is logging_policy.debug_content_enabled
    tree = ast.parse((SRC / "turn_timing.py").read_text(encoding="utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "getenv" not in names and "environ" not in names, (
        "turn_timing reads the environment itself — a second debug predicate can drift")


def test_under_debug_the_durable_log_is_refused(tmp_path, monkeypatch, caplog):
    _debug_on(monkeypatch)
    assert logging_policy.attach_file_log(directory=tmp_path) is None
    turn_timing.turn_started()
    turn_timing.stage("draw")
    assert list(tmp_path.iterdir()) == [], "a file appeared where the durable log would be"


# ─── Each line fires through its REAL carrier ──────────────────────────────────

class _Reasoner:
    def __init__(self, scripts):
        self._scripts = list(scripts)

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        for event in self._scripts.pop(0):
            yield event


class _Overlay:
    def __init__(self):
        self.shows = []

    async def show(self, bbox, label_ar):
        self.shows.append(label_ar)

    async def hide(self):
        pass

    def set_state(self, state):
        pass

    def clear_status_light(self):
        pass


def _complete(stop_reason="end_turn", content=None):
    return TurnComplete(input_tokens=10, output_tokens=2, cost_usd=0.0001,
                        stop_reason=stop_reason, model="m",
                        assistant_content=content or [{"type": "text", "text": "هنا"}])


def _pointing_turn(tmp_path, overlay):
    call = ToolCall(name="highlight_target", tool_use_id="toolu_t1",
                    args={"x1": 10, "y1": 20, "x2": 30, "y2": 40, "label_ar": "زر"})
    scripts = [
        [TextDelta("لحظة"), call,
         _complete("tool_use", [{"type": "tool_use", "id": "toolu_t1",
                                 "name": call.name, "input": call.args}])],
        [TextDelta("هذا هو الزر."), _complete()],
    ]

    async def capture():
        return PNG

    async def downscale(screenshot):
        return DownscaledImage(PNG, 1280, 720, 1.0, 1.0)

    async def silent_tts(text):
        return None

    budget = Budget(daily_limit_usd=1.0, budget_file=tmp_path / "budget.json",
                    today_fn=lambda: "2026-10-29")
    return Orchestrator(reasoner=_Reasoner(scripts), budget=budget, tts=silent_tts,
                        overlay=overlay, screen_capture=capture, downscale=downscale)


@pytest.mark.asyncio
async def test_a_pointing_turn_emits_first_token_then_draw(tmp_path, monkeypatch, caplog):
    _debug_on(monkeypatch)
    caplog.set_level(logging.INFO, logger="muthis.timing")
    overlay = _Overlay()
    turn_timing.turn_started()
    await _pointing_turn(tmp_path, overlay).run_turn("وين الزر؟")
    assert overlay.shows == ["زر"], "the scripted draw never reached the overlay"
    assert [line.split(" +")[0] for line in _timing_lines(caplog)] == [
        "[timing] first_token", "[timing] draw"]


@pytest.mark.asyncio
async def test_the_same_turn_WITHOUT_the_clock_emits_nothing(tmp_path, monkeypatch, caplog):
    _debug_on(monkeypatch)
    caplog.set_level(logging.INFO, logger="muthis.timing")
    await _pointing_turn(tmp_path, _Overlay()).run_turn("وين الزر؟")
    assert _timing_lines(caplog) == []


class _FakeDevice:
    def __init__(self, rate, channels):
        self.written = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write(self, chunk):
        self.written.append(chunk)

    def stop(self):
        pass


@pytest.mark.asyncio
async def test_the_first_pcm_write_emits_first_audio_ONCE(monkeypatch, caplog):
    _debug_on(monkeypatch)
    caplog.set_level(logging.INFO, logger="muthis.timing")
    turn_timing.turn_started()
    player = PcmStreamPlayer(22050, stream_factory=_FakeDevice)
    player.start()
    player.feed(b"\x00\x01" * 64)
    player.feed(b"\x00\x01" * 64)
    await player.finish()
    assert [line.split(" +")[0] for line in _timing_lines(caplog)] == ["[timing] first_audio"]


# ─── The carriers stay wired, and nothing in the app starts the clock ──────────

def _calls(path: pathlib.Path, attr: str) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == attr
            and getattr(n.func.value, "id", "") == "turn_timing"]


def test_each_stage_has_exactly_one_carrier():
    assert len(_calls(SRC / "kernel" / "turn_pass.py", "model_event")) == 1
    stages = {}
    for path in sorted(SRC.rglob("*.py")):
        for call in _calls(path, "stage"):
            stages.setdefault(call.args[0].value, []).append(path.relative_to(SRC).as_posix())
    assert stages == {"draw": ["kernel/draw_dispatch.py"], "first_audio": ["tts_ws_player.py"]}


def test_only_the_instrument_starts_the_clock():
    starters = sorted(path.relative_to(SRC).as_posix() for path in SRC.rglob("*.py")
                      if _calls(path, "turn_started"))
    assert starters == [], (
        f"the clock is started inside the app: {starters} — only the voice "
        "instrument may start it")
