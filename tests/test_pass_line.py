# tests/test_pass_line.py
"""DEC-111 ② — the PER-PASS TOOL LINE, open for a week and blocking a cap ruling twice.

WHAT IT HAD TO OVERCOME. DEC-117 measured four sites and rejected all of them:
`pass_servicing.py` (its option B) was recorded "blind to the draw, the refresh
and `tool_choice`", the only site seeing everything was `turn_pass.py` (pinned),
and the pass ORDINAL "exists only in `orchestrator.py`" — whose option D
"BREACHES the ≤300 law by 2".

WHAT CHANGED IS A MEASUREMENT, NOT A RULING. The blindness was a property of the
SERVICED PARAMETERS, not of `result`, which `consume()` appends EVERY accepted
call to — draw, refresh, router-serviced, nav and run. So the ordinal and the
whole tool list are both reachable from the unpinned site, and no pin moves.

THE TESTS THAT MATTER ARE THE TWO DEC-117 SAID WERE IMPOSSIBLE: the draw is
visible, and the ordinal is real. Each carries the control that would fail on a
line that merely looks right.
"""

from __future__ import annotations

import asyncio
import logging

from muthis.cloud.protocol import ToolCall
from muthis.kernel.pass_servicing import log_pass, service_pass_calls
from muthis.kernel.turn import TurnResult


def _call(name, **args):
    return ToolCall(name=name, args=args or {"q": "x"}, tool_use_id="id-" + name)


def _drive(caplog, passes):
    """Run `log_pass` once per element, appending that pass's calls first —
    the order `consume()` uses (drain, then service)."""
    caplog.set_level(logging.INFO, logger="muthis.orchestrator")
    result = TurnResult()
    for calls in passes:
        result.tool_calls.extend(calls)
        log_pass(result)
    return caplog.text, result


# ─────────────────────────── the ordinal is real ────────────────────────────

def test_the_ordinal_counts_passes_not_tools(caplog):
    text, _ = _drive(caplog, [
        [_call("highlight_target"), _call("read_local_file")],   # two tools, ONE pass
        [_call("navigator__verify")],
    ])
    assert "[pass] #1" in text
    assert "[pass] #2" in text
    assert "[pass] #3" not in text, "the ordinal counted tools instead of passes"


def test_a_pass_that_asked_for_nothing_still_gets_a_line(caplog):
    """A silent pass is a datum — it is what a turn spending its cap on nothing
    looks like — so it must not be the one case that vanishes."""
    text, _ = _drive(caplog, [[]])
    assert "[pass] #1 tools=-" in text


# ─── the two DEC-117 recorded as unreachable from this site ─────────────────

def test_the_DRAW_is_visible(caplog):
    """DEC-117's option B was rejected as "blind to the draw". This is the
    assertion that claim is no longer true — and the draw is the call DEC-111's
    whole mechanism turns on, since `gate.drawn` decides the next tool_choice."""
    text, _ = _drive(caplog, [[_call("highlight_target")]])
    assert "highlight_target" in text


def test_the_REFRESH_is_visible(caplog):
    text, _ = _drive(caplog, [[_call("request_screen_refresh")]])
    assert "request_screen_refresh" in text


def test_each_pass_reports_only_its_OWN_tools(caplog):
    """The watermark, which is what makes the line per-PASS rather than
    per-TURN. Without it pass 2 re-reports pass 1 and the table is useless for
    the question it exists to answer — WHEN a call happened."""
    text, _ = _drive(caplog, [
        [_call("highlight_target")],
        [_call("navigator__verify")],
    ])
    first, second = [ln for ln in text.splitlines() if "[pass] #" in ln][:2]
    assert "highlight_target" in first and "navigator__verify" not in first
    assert "navigator__verify" in second and "highlight_target" not in second


def test_the_watermark_advances_to_the_end_of_the_list(caplog):
    _, result = _drive(caplog, [[_call("a"), _call("b")], [_call("c")]])
    assert result.tools_logged == len(result.tool_calls) == 3
    assert result.passes_serviced == 2


# ───────────────────── names only — never arguments (DEC-61) ────────────────

def test_no_tool_ARGUMENT_ever_reaches_the_line(caplog):
    """A tool NAME is a control-flow fact; a tool ARGUMENT is user content — a
    path, a query, a program. The line carries the first and never the second."""
    text, _ = _drive(caplog, [[
        _call("read_local_file", path=r"C:\Users\sultb\Desktop\private\thesis.md"),
        _call("sandbox__run_code", code="SECRET = 'hunter2'"),
    ]])
    assert "read_local_file" in text and "sandbox__run_code" in text   # control
    assert "thesis.md" not in text
    assert "hunter2" not in text
    assert "Desktop" not in text


def test_the_tool_use_id_is_not_logged_either(caplog):
    text, _ = _drive(caplog, [[_call("highlight_target")]])
    assert "id-highlight_target" not in text


# ────────────────── it is wired into the real servicing call ────────────────

def test_service_pass_calls_emits_the_line(caplog):
    """The MECHANISM check: the line must be written by the production path, not
    merely by a helper the production path could have forgotten to call."""
    caplog.set_level(logging.INFO, logger="muthis.orchestrator")
    result = TurnResult()
    result.tool_calls.append(_call("highlight_target"))
    asyncio.run(service_pass_calls(
        router=None, sandbox=None, result=result,
        precondition=None, read=None, run=None, nav=None, prelude=None))
    assert "[pass] #1" in caplog.text
    assert "highlight_target" in caplog.text
