# tests/test_domain_badge_draw.py
"""
The badge is DRAWN by the kernel, from the broker's real record (DEC-20/DEC-36).

The previous commit made the collector turn-scoped; it was still invisible. This
one closes DEC-20's third layer: `TurnPass` reads the record through the router's
blind `fetched_domains` seam and calls `overlay.show_domain_badge` at the END of
each pass.

WHAT THESE TESTS ARE FOR, precisely. After this milestone's fourth guard hole —
a check that asserted a PARAMETER EXISTED while production could have wired it to
None — the assertions here are about what production WIRES:

  * the drawn domains must come from the LIVE collector, so recording a domain
    and re-running a pass changes what is drawn (a constant provider fails);
  * the badge must never carry a URL, into the overlay or into any log;
  * an EMPTY record must draw NOTHING — no empty chip;
  * the draw must not disturb the Option-A sync point (draw → speak) or the
    caption, which is asserted by ORDER, not by inspection.

No test here imports `muthis.main`; the composition root is scanned by AST.
"""

from __future__ import annotations

import ast
import asyncio
import pathlib

from muthis.broker.net import FetchedDomains
from muthis.cloud.protocol import TextDelta, ToolCall, TurnComplete, UserInput
from muthis.kernel.highlight_gate import HighlightGate
from muthis.kernel.tool_router import ToolRouter
from muthis.kernel.turn import TurnResult
from muthis.kernel.turn_pass import TurnPass
from muthis.overlay.domain_badge import format_badge

COMPOSITION_PY = (
    pathlib.Path(__file__).resolve().parents[1] / "src" / "muthis" / "composition.py"
)

PRIVATE_URL = "https://docs.python.org/3/search.html?q=my+private+question"


class _Overlay:
    """Records the ORDER of everything the pass does to the screen, so the
    badge's position relative to the Option-A sync point is asserted rather
    than assumed."""

    def __init__(self) -> None:
        self.events: list = []

    def show_domain_badge(self, domains) -> None:
        self.events.append(("badge", tuple(domains)))

    async def show(self, bbox, label_ar):
        self.events.append(("draw", bbox))

    async def draw_shapes(self, shapes):
        self.events.append(("draw_shapes", shapes))

    def dim_screen(self):
        self.events.append(("dim",))

    async def hide(self):
        self.events.append(("hide",))


class _Voice:
    def __init__(self, overlay: _Overlay) -> None:
        self._overlay = overlay

    async def ensure_open(self):
        return False

    async def speak_or_feed(self, text):
        self._overlay.events.append(("speak", text))

    async def end_stream(self):
        self._overlay.events.append(("speak_stream_end",))


class _Reasoner:
    def __init__(self, events=()):
        self._events = events

    async def run(self, user_input, screenshot, history, tool_choice="auto"):
        for event in self._events:
            yield event
        yield TurnComplete(input_tokens=1, output_tokens=1, cost_usd=0.0,
                           stop_reason="end_turn", model="fake")


class _Budget:
    def record_turn(self, turn_complete):
        return None


def _pass(collector: FetchedDomains, overlay: _Overlay, reasoner=None):
    router = ToolRouter(fetched_domains=collector.domains)
    return TurnPass(reasoner=reasoner or _Reasoner(), budget=_Budget(),
                    overlay=overlay, voice=object(), stream_tts=False,
                    router=router)


def _run(turn_pass, overlay, text="اشرح لي"):
    return asyncio.run(turn_pass.consume(
        UserInput(text=text), None, [], HighlightGate(), TurnResult(),
        _Voice(overlay)))


# ─── The drawn fact comes from the LIVE collector ────────────────────────────


def test_the_badge_is_drawn_from_the_live_collector_not_a_snapshot():
    """A constant provider passes a "does the parameter exist" check and fails
    this one: the SAME router must draw different domains once the FETCHER has
    recorded one."""
    collector, overlay = FetchedDomains(), _Overlay()
    turn_pass = _pass(collector, overlay)

    _run(turn_pass, overlay)
    assert ("badge", ()) in overlay.events, "the badge was never drawn"

    collector.record("docs.python.org")          # what the fetcher does
    _run(turn_pass, overlay)

    assert overlay.events[-1] == ("badge", ("docs.python.org",))


def test_an_empty_record_draws_nothing_rather_than_an_empty_chip():
    """The KNOWN LIMIT, asserted as behaviour: a snippet-only turn shows no
    badge. "Nothing fetched" must look like nothing, not like a source."""
    collector, overlay = FetchedDomains(), _Overlay()
    _run(_pass(collector, overlay), overlay)

    (drawn,) = [e for e in overlay.events if e[0] == "badge"]
    assert drawn[1] == ()
    assert format_badge(drawn[1]) == ""


def test_an_overlay_without_a_badge_surface_never_crashes_the_turn():
    """Duck-typed like every other optional overlay surface (the voice_out
    caption seam, draw_dispatch's dim/shapes). A StubOverlay simply has no
    badge — metadata must never take down a turn."""
    class _Bare:
        async def show(self, bbox, label_ar): ...
        async def hide(self): ...

    collector = FetchedDomains()
    collector.record("example.com")
    turn_pass = TurnPass(reasoner=_Reasoner(), budget=_Budget(), overlay=_Bare(),
                         voice=object(), stream_tts=False,
                         router=ToolRouter(fetched_domains=collector.domains))

    complete, _refresh, _read, _run_result = asyncio.run(turn_pass.consume(
        UserInput(text="اشرح"), None, [], HighlightGate(), TurnResult(),
        _Voice(_Overlay())))

    assert complete is not None, "a missing badge surface killed the pass"


def test_a_router_with_no_web_wired_still_draws_an_empty_badge_and_never_raises():
    """The default provider answers () — a V1-only composition must not crash."""
    overlay = _Overlay()
    turn_pass = TurnPass(reasoner=_Reasoner(), budget=_Budget(), overlay=overlay,
                         voice=object(), stream_tts=False, router=ToolRouter())
    _run(turn_pass, overlay)
    assert ("badge", ()) in overlay.events


# ─── DOMAIN ONLY — never a URL, on screen or in a log ────────────────────────


def test_the_badge_never_receives_a_url_and_never_logs_one(caplog):
    """DEC-20/DEC-28: a URL can carry `?q=<the user's private question>`. The
    collector stores hostnames, so this holds BY TYPE — and the draw path must
    not reintroduce one through a log line."""
    collector, overlay = FetchedDomains(), _Overlay()
    collector.record("docs.python.org")          # a domain, never the URL
    turn_pass = _pass(collector, overlay)

    with caplog.at_level("DEBUG"):
        _run(turn_pass, overlay)

    drawn = [e for e in overlay.events if e[0] == "badge"][-1][1]
    assert drawn == ("docs.python.org",)
    for value in drawn:
        assert "?" not in value and "/" not in value

    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "my+private+question" not in logged
    assert PRIVATE_URL not in logged
    assert "docs.python.org" not in logged, "the draw path logged a domain"


# ─── The Option-A sync point is untouched ────────────────────────────────────


def test_the_badge_is_drawn_after_the_draw_then_speak_sync_point():
    """The badge is METADATA, not speech. It must never enter draw→speak: the
    ORDER is asserted, so a future edit that moves the call before the sync
    point fails here rather than in a live run."""
    collector, overlay = FetchedDomains(), _Overlay()
    collector.record("example.com")
    reasoner = _Reasoner((
        TextDelta("شرح"),
        ToolCall(name="highlight_target",
                 args={"x1": 10, "y1": 10, "x2": 40, "y2": 40, "label_ar": "هنا"},
                 tool_use_id="h1"),
    ))
    turn_pass = _pass(collector, overlay, reasoner)

    _run(turn_pass, overlay)

    kinds = [e[0] for e in overlay.events]
    assert kinds.index("draw") < kinds.index("speak"), "Option-A sync broke"
    assert kinds.index("speak") < kinds.index("badge"), "the badge entered draw→speak"
    assert kinds[-1] == "badge", "the badge must be the LAST thing the pass does"


# ─── The composition root, by SOURCE SCAN (never an import) ──────────────────


def test_the_composition_root_wires_the_real_collector_as_the_badge_source():
    """The VALUE, not the keyword — the lesson of this milestone's fourth guard
    hole. `fetched_domains=tuple` or `=None` would keep the argument present
    while the badge silently never showed a source."""
    tree = ast.parse(COMPOSITION_PY.read_text(encoding="utf-8"))
    wired = [
        kw for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", "") == "build_core_router"
        for kw in node.keywords if kw.arg == "fetched_domains"
    ]
    assert wired, "the composition root no longer wires the badge's source"
    (value,) = wired
    assert isinstance(value.value, ast.Attribute), (
        "the badge source must be the collector's own reader, not a constant")
    assert value.value.attr == "domains"
    assert getattr(value.value.value, "id", "") == "fetched_domains", (
        "the badge must read the SAME collector the fetcher records into")
