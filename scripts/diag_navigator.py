# scripts/diag_navigator.py
"""DIAG (V3 Phase 3 — T6 LIVE SOP) — the Navigator, the mode frame and evidence
pointing, driven live against the real model. NEVER run in CI.

**NOT ACCEPTANCE, AND THIS SCRIPT NEVER SAYS OTHERWISE.** Sultan runs the live
SOP on his own hardware and signs off PERSONALLY. Every run of this file — his or
an agent's — is DIAGNOSTIC, and the summary says so in its own output. A green
run is necessary, never sufficient.

────────────────────────────────────────────────────────────────────────────────
WHY THIS FILE IS SHORT, AND WHAT WAS DELIBERATELY LEFT OUT
────────────────────────────────────────────────────────────────────────────────
The project law (AGENTS.md, 2026-07-31): a diagnostic verifies ONLY what the
suite structurally CANNOT — live model behaviour, and the end-to-end path with
real objects. `diag_doc_rag.py` reached 2,297 lines and THREE of M3's four late
defects lived in its DETERMINISTIC half, the half pytest already owns. The
question when writing this was never "is it too long" but **"which of these
checks could pytest have run?"** — asked of every one, before a line was written:

  · **the mode indicator across turns** — `test_mode_indicator.py` already
    asserts survival across THREE turns, the restore AFTER the grab, the FORGET
    at mode end, and that `clear_caption` leaves it alone. NOT re-driven here.
    The live-only residue is the EYE: the real Tk widget on the real screen, and
    its ABSENCE from the frame actually sent to the provider — which is why this
    script SAVES that frame instead of asserting about it.
  · **the three exits** — `test_mode_exits.py` covers the exit word with
    near-miss negatives, idle expiry as a start-of-turn evaluation, and the
    directive↔approval-detector interaction in BOTH directions. The logic is not
    re-driven. What is live-only is the exit word arriving as a REAL STT
    TRANSCRIPT rather than a string a test typed — and that needs the microphone,
    so it is a MANUAL step printed at the end, not a scripted check.
  · **the pass economy** — `test_navigator_servicing.py` already asserts TWO
    passes for advance+point and THREE for advance alone. The shape is not
    re-driven; only the count a REAL model produces is, and only against the cap.

ONE CHECK WAS ADDED for being live-only with a failure class that has already
bitten: **catalog v6 accepted by the real API.** DEC-11 was a live 400 on a tool
name every offline test had passed. Eleven tools now, and only a real call proves
the catalog is accepted.

────────────────────────────────────────────────────────────────────────────────
DETERMINISTIC (driven and ASSERTED — these produce PASS / FAIL / SKIP)
────────────────────────────────────────────────────────────────────────────────
  A  catalog v6 is ACCEPTED by the real API — 11 tools, the DEC-11 failure class
  B  no LOOK-only violation is logged in any live turn
  C  no turn exceeds MAX_AGENTIC_ITERATIONS
  D  the mode indicator seam FIRES end-to-end on the real overlay, and the
     capture chokepoint restores it after a real screen grab (calls asserted;
     the pixels are Sultan's eye)
  E  each exit ENDS the mode on the real graph, through the real authority
  F  regression — the V1 pointing turn, `read_local_file`, `sandbox__run_code`,
     `web__search`, `docs__query`: each SERVICED live, or SKIPPED with a reason
  G  every independent turn started from a CLEAN session — plus the POSITIVE
     CONTROL that the isolation found state to clear (T7 run 1's leak; see
     `Session`)
  H  the run was not BUDGET-STARVED, because a starved run settles nothing

────────────────────────────────────────────────────────────────────────────────
OBSERVED (printed for Sultan; scored NEITHER pass NOR fail)
────────────────────────────────────────────────────────────────────────────────
  O-1  does the model reach for the Navigator verbs UNPROMPTED? — the question
       that decides whether a persona law is needed. Per the T4 ruling a persona
       law is written on an OBSERVED gap, never an expected one. INSTRUMENTED
       HERE, JUDGED BY SULTAN.
  O-2  step pacing and the spoken frame — does a five-step plan feel like
       GUIDANCE or like a list read aloud? Ear, not score.
  O-3  evidence pointing, all three paths — ① a screen claim, ② a DISPLAYED
       document, ③ an INDEXED-but-not-displayed one, whose honest refusal should
       redirect to the vision path.

Conflating these two halves is what produced M1's false negative and cost a full
run, so the registers are SEPARATE OBJECTS and an observation cannot reach the
verdict list even by accident.

────────────────────────────────────────────────────────────────────────────────
Needs in .env: ANTHROPIC_API_KEY, ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID (or
GEMINI_API_KEY for the TTS fallback). TAVILY_API_KEY and Docker are optional —
their regressions SKIP without them.

**COSTS ~15 REAL CLAUDE TURNS. SET `MUTHIS_DAILY_BUDGET_USD` BEFORE STARTING** —
T7's first run exhausted the budget partway and the OBSERVED phases, the half the
run exists for, came back empty. The budget is printed before anything is spent,
the observations now run BEFORE the regressions, and a starved turn is detected
from `TurnResult.budget_blocked` and announced rather than printed as data.

Run:  .venv\\Scripts\\python.exe scripts\\diag_navigator.py [--doc PATH --question "..."]
"""

import argparse
import asyncio
import logging
import pathlib
import sys
import tempfile
import time
from typing import Any, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()  # Law 5.1: .env before any muthis import that reads keys

from muthis.cloud.claude_agent import ClaudeAgent, LOOK_SYSTEM_PROMPT       # noqa: E402
from muthis.composition import (                                            # noqa: E402
    _build_broker_graph, _build_doc_rag, _build_orchestrator, _build_sandbox,
    mount_doc_rag, mount_navigator, mount_web_research,
)
from muthis.file_reader import FileReader                                   # noqa: E402
from muthis.kernel.budget import Budget                                     # noqa: E402
from muthis.kernel.mode_transition import (                                 # noqa: E402
    ENTER, EXPIRE, LEAVE, TransitionRequest,
)
from muthis.kernel.orchestrator import MAX_AGENTIC_ITERATIONS               # noqa: E402
from muthis.kernel.plan import Plan                                         # noqa: E402
from muthis.kernel.turn import TurnResult                                   # noqa: E402
from muthis.overlay import SidekickOverlay                                  # noqa: E402
from muthis.persona import resolve_system_prompt                            # noqa: E402
from muthis.vision.downscale import (                                       # noqa: E402
    DEFAULT_VISION_MAX_WIDTH, compute_scale_factors,
)
from muthis.vision.screen_capture import primary_monitor_size               # noqa: E402
from muthis_plugins.navigator import NavigatorPlugin                        # noqa: E402
from muthis_plugins.sandbox_exec import SandboxExecPlugin                   # noqa: E402

CATALOG_V6_TOOLS = 11
FRAME_DUMP = pathlib.Path("diag_navigator_sent_frame.png")

# The checks that cost a LIVE MODEL TURN, named in ONE place so the skip list and
# the run list can never drift apart. `--observations-only` skips exactly these:
# run 1 (2026-08-03) settled every one of them for ~$1.4, and re-buying a settled
# result with the budget that has to pay for the UNSETTLED half is the trade that
# left run 1 with no O-2 pacing and no O-3 at all.
#
# THE FREE DETERMINISTIC CHECKS STILL RUN — A0, D, E, B, C, G, H drive no model
# and cost nothing, and their failure would make the observations misleading
# rather than merely unconfirmed. Skipping them would buy nothing and lose signal.
PAID_CHECKS = (
    "A the real API accepted catalog v6 (the DEC-11 failure class)",
    "F1 V1 pointing (highlight_target)",
    "F2 read_local_file",
    "F3 sandbox__run_code",
    "F4 web__search",
    "F5 docs__query",
)
SETTLED_BY_RUN_1 = "settled by run 1 (2026-08-03) at ~$1.4 — NOT re-bought"

# The Arabic the model actually hears. O-1's question is the load-bearing one: it
# describes a MULTI-STEP TASK and never says "step", "plan" or "walk me through",
# because naming them would answer the question the observation exists to ask.
Q_UNPROMPTED = "كيف أغيّر خلفية سطح المكتب في ويندوز؟"
Q_WALKTHROUGH = "علّمني خطوة بخطوة كيف أسوّي نسخة احتياطية لملفاتي على ويندوز."
Q_ADVANCE = "التالي"
Q_SCREEN_EVIDENCE = "وش البرنامج المفتوح عندي الحين؟ وأشّر لي على الدليل على الشاشة."
Q_POINT = "يا مطحس، وين زر الإغلاق في هذه النافذة؟ أشّر عليه."
Q_RUN = "شغّل لي كود بايثون يطبع ناتج ٢ + ٢."
Q_SEARCH = "ابحث لي في الويب عن آخر إصدار مستقر من بايثون."


class Checks:
    """Ordered PASS / FAIL / SKIP register. True=PASS, False=FAIL, None=SKIP.

    An OBSERVATION never enters this register — that separation is the T6 ruling
    made structural rather than habitual."""

    def __init__(self) -> None:
        self.results: "dict[str, Optional[bool]]" = {}

    def record(self, name: str, ok: Optional[bool], why: str = "") -> None:
        self.results[name] = ok
        mark = {True: "PASS", False: "FAIL", None: "SKIP"}[ok]
        print(f"    [{mark}] {name}" + (f"  — {why}" if why else ""))

    def failed(self) -> "list[str]":
        return [n for n, ok in self.results.items() if ok is False]


class Observations:
    """The half this script MEASURES and does not judge. Its own object, so
    nothing here can leak into the summary as a verdict."""

    def __init__(self) -> None:
        self.items: "list[tuple[str, dict[str, Any]]]" = []

    def add(self, title: str, body: "dict[str, Any]") -> None:
        self.items.append((title, body))
        print(f"\n──── OBSERVATION — {title} ────")
        for key, value in body.items():
            print(f"    {key}: {value}")


class LogTap(logging.Handler):
    """Every record the process emits, so "no LOOK-only violation" is literal
    across the WHOLE run rather than scoped to one call."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: "list[str]" = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(f"{record.name}: {record.getMessage()}")
        except Exception:  # noqa: BLE001 — the tap must never break a run
            self.lines.append(f"{record.name}: <unformattable>")


class OverlayProbe:
    """The REAL overlay, with the two mode-indicator calls recorded.

    A PROXY rather than a fake: every other call goes straight through to the
    real Tk window, so what is driven is the production surface. It exists
    because the widget's own state lives on the Tk thread and is not readable
    from here — so the script asserts that the SEAM fired and leaves the pixels
    to Sultan's eye, which is the honest division."""

    def __init__(self, real: SidekickOverlay) -> None:
        self._real = real
        self.shown: "list[str]" = []
        self.restored = 0

    def show_mode_indicator(self, text: str) -> None:
        self.shown.append(text)
        self._real.show_mode_indicator(text)

    def restore_mode_indicator(self) -> None:
        self.restored += 1
        self._real.restore_mode_indicator()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class PassCounter:
    """The REAL agent, counting provider passes per turn — the one number only a
    live model can produce. Forwards everything else untouched."""

    def __init__(self, real: ClaudeAgent) -> None:
        self._real = real
        self.passes = 0
        self.max_seen = 0

    def new_turn(self) -> None:
        self.max_seen = max(self.max_seen, self.passes)
        self.passes = 0

    def run(self, *args: Any, **kwargs: Any) -> Any:
        self.passes += 1
        return self._real.run(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class Session:
    """The boundary between independent observations — and the LEAK IT MEASURES.

    T7's FIRST RUN found this harness answering the wrong question. F3 asked for
    ٢+٢ and the spoken reply was about the document on screen; O-2 asked about
    backups and the reply was «خلينا نكمّل خطوات تغيير الخلفية أولاً», continuing
    O-1's walkthrough. **Both checks PASSED**, because they assert the TOOL WAS
    CALLED — and it was. The reply was answering something else entirely.

    THE CAUSE: one Orchestrator across every phase. `history` accumulates by
    design, and a mode O-1 opened is still ACTIVE when O-2 starts, so its
    directive line rides the next turn. That is the Navigator working exactly as
    specified; what failed is the HARNESS, which never isolated its own
    experiment. An observation contaminated by its predecessor cannot answer the
    question it exists to ask — the same reason O-1's wording never names the
    verbs.

    **THE RESET ALONE WOULD NOT BE ENOUGH.** A silent reset that stopped being
    called would restore the defect with every check still green, which is the
    DEC-40 family one layer in. So this records what it FOUND to clear — the leak,
    measured, printed — and a check FAILS if it never found anything, because a
    reset with no work to do is not what is keeping the observations clean.

    WHAT IT CANNOT RESET, stated rather than hidden: `SessionTaint` has NO
    clearing method BY DESIGN (DEC-15 — a "clear the taint" verb would itself be
    a social-engineering channel), so a new PROCESS is its only reset. It does
    not distort these observations — the Navigator holds no capability, so no
    mode verb can ever be high-impact — but a future phase that turns on
    confirmation friction must start a new process, not call a method that
    deliberately does not exist. Sticky verbosity is the same shape; no phase
    here issues a verbosity command."""

    def __init__(self, orchestrator: Any) -> None:
        self._orch = orchestrator
        self.boundaries = 0
        self.carried: "list[str]" = []
        self.dirty_after: "list[str]" = []
        self.starved: "list[str]" = []

    def start(self, label: str) -> None:
        prelude = self._orch._prelude
        blocks, frame = len(self._orch.history), prelude.session_mode.frame
        if blocks or frame is not None:
            self.carried.append(
                f"{label} inherited {blocks} history block(s)"
                + (f" + the ACTIVE mode «{frame.name}»" if frame is not None else ""))
        # Ended through the REAL authority, never by writing the frame: the ONE
        # evaluation point stays the only writer even inside a diagnostic.
        prelude.authority.request(TransitionRequest(kind=LEAVE))
        self._orch.history.clear()
        self.boundaries += 1
        if self._orch.history or prelude.session_mode.frame is not None:
            self.dirty_after.append(label)


async def build_live_graph(budget: Budget, doc_plugin: Any):
    """The PRODUCTION graph, built by production's OWN helpers in production
    ORDER — so this script can never verify a composition it invented (DEC-40,
    and the self-built-graph default that had to be refused at T1, T3, T4 and
    T5). The only additions are two transparent proxies."""
    physical = primary_monitor_size()
    if physical is not None:
        sent_w, sent_h, _sx, _sy = compute_scale_factors(
            physical[0], physical[1], DEFAULT_VISION_MAX_WIDTH)
    else:
        sent_w, sent_h = DEFAULT_VISION_MAX_WIDTH, round(DEFAULT_VISION_MAX_WIDTH * 9 / 16)

    overlay = OverlayProbe(SidekickOverlay())
    router, _mcp, fetcher, web_plugin, search = _build_broker_graph(
        budget, overlay, FileReader())
    sandbox = _build_sandbox()
    router.mount(SandboxExecPlugin(), namespace="sandbox", provenance="sandbox_exec")
    mount_web_research(router, web_plugin, fetcher)
    mount_doc_rag(router, doc_plugin)
    mount_navigator(router, NavigatorPlugin())
    tools = [d.schema for d in router.descriptors()]
    print(f"    catalog: {[d['name'] for d in tools]}")

    agent = PassCounter(ClaudeAgent(
        system_prompt=resolve_system_prompt(LOOK_SYSTEM_PROMPT, sent_w, sent_h),
        tools=tools))
    await agent.warm_up_tls()
    orchestrator = _build_orchestrator(agent, budget, overlay, _no_mic, router, sandbox)
    orchestrator.add_interrupt_hook(sandbox.kill_active)
    return orchestrator, overlay, agent, fetcher, search, len(tools)


async def _no_mic() -> bytes:
    """The mic seam is never used: this script drives `run_turn(text)` directly,
    because the microphone path belongs to Sultan's own run of `main.py`."""
    return b""


async def drive(orchestrator, agent: PassCounter, session: Session, label: str,
                question: str, fresh: bool = True):
    """One live turn, printed. Returns the TurnResult and the pass count.

    **`fresh=True` IS THE DEFAULT, AND THAT DIRECTION IS THE FIX.** Independence
    is what an observation needs; continuity is the exception and has to be asked
    for at the call site, where a reader can see it. The walkthrough's «التالي»
    turns are the only callers that pass `fresh=False`, because a step that did
    not inherit its own plan would be measuring nothing.

    BUDGET STARVATION IS DETECTED, NOT INFERRED. `TurnResult.budget_blocked` is
    set by the Rule-10 gate before any provider call, so an exhausted run is a
    FACT the harness reads rather than a pattern it guesses from an empty reply.
    T7's first run printed four empty observations that looked like data."""
    if fresh:
        session.start(label)
    print(f"\n──────── {label} ────────\nQ: {question}")
    agent.new_turn()
    start = time.perf_counter()
    result = await orchestrator.run_turn(question)
    print(f"    tools={[c.name for c in result.tool_calls]}  passes={agent.passes}"
          f"  cost={result.cost_usd:.6f} USD  {(time.perf_counter() - start):.1f}s")
    print(f"    reply: {result.spoken_text.strip()[:400]}")
    if getattr(result, "budget_blocked", False):
        session.starved.append(label)
        print("    >>> BUDGET GATE CLOSED — NO provider call was made. This turn and"
              "\n    >>> every turn after it are EMPTY and SETTLE NOTHING. Raise"
              "\n    >>> MUTHIS_DAILY_BUDGET_USD and start the run again.")
    return result, agent.passes


async def check_indicator_and_exits(checks: Checks, orchestrator,
                                    overlay: OverlayProbe) -> None:
    """CHECKS D + E — the mode frame end-to-end on the REAL overlay.

    NOT the indicator's logic and NOT the exits' logic: both are pytest's, with
    fakes, on every commit. What is driven here is the wiring reaching a REAL Tk
    window without raising on its own thread — a failure a fake cannot have — and
    each exit ending the mode through the REAL authority the orchestrator built.

    The capture half drives the orchestrator's OWN `FrameCapture`, so the frame
    written to disk is the real hide→settle→grab→restore chokepoint's output —
    the one artefact that can show whether the indicator leaks into what the
    provider sees. The script does not judge that image; it saves it."""
    prelude = orchestrator._prelude          # the object PRODUCTION built, not one made here
    authority, mode = prelude.authority, prelude.session_mode
    plan = Plan.build("النسخ الاحتياطي", ("افتح الإعدادات", "اختر النسخ", "شغّل النسخة"))

    for name, end_the_mode in (
        ("E1 the deterministic exit WORD ends the mode",
         lambda: prelude.begin_turn("خلاص")),
        ("E2 model-signalled completion ends the mode",
         lambda: authority.request(TransitionRequest(kind=LEAVE))),
        ("E3 idle expiry ends the mode at the next turn",
         lambda: authority.request(TransitionRequest(kind=EXPIRE))),
    ):
        before = len(overlay.shown)
        authority.request(TransitionRequest(kind=ENTER, mode_name="النسخ الاحتياطي",
                                            plan=plan))
        entered = mode.frame is not None and len(overlay.shown) > before
        end_the_mode()
        checks.record(name, entered and mode.frame is None,
                      "" if entered else "the mode never entered, so the exit proved nothing")

    checks.record("D1 the indicator seam FIRES on the real overlay",
                  len(overlay.shown) >= 3)
    checks.record("D2 the mode END clears the indicator (empty text, not a stale chip)",
                  overlay.shown[-1] == "")

    # D3 — the capture chokepoint, driven for real with a mode ACTIVE.
    authority.request(TransitionRequest(kind=ENTER, mode_name="النسخ الاحتياطي", plan=plan))
    restored_before = overlay.restored
    frame = await orchestrator._frames.capture(TurnResult())
    checks.record("D3 the real capture chokepoint RESTORES the indicator after the grab",
                  overlay.restored > restored_before)
    if frame:
        FRAME_DUMP.write_bytes(frame)
        print(f"    sent frame written to {FRAME_DUMP} — SULTAN: the mode chip must "
              "NOT appear in it")
    authority.request(TransitionRequest(kind=LEAVE))


async def run_regressions(checks: Checks, orchestrator, agent: PassCounter,
                          session: Session, workdir: pathlib.Path,
                          doc_path: Optional[str],
                          question: Optional[str]) -> "list[int]":
    """CHECK F — every shipped capability still serviced, one live turn each.

    An unavailable dependency is a SKIP with its reason, never a FAIL: Docker,
    a search key and a document are environment facts, not regressions.

    The sample file lands in a TEMP directory, never the repo: a diagnostic that
    leaves artefacts in the working tree is one `git status` away from being
    committed by accident."""
    sample = workdir / "diag_sample.py"
    sample.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    passes: "list[int]" = []
    cases = [
        ("F1 V1 pointing (highlight_target)", Q_POINT, "highlight_target", True),
        ("F2 read_local_file", f"اقرأ لي الملف {sample} واشرح لي وش يسوي.",
         "read_local_file", True),
        ("F3 sandbox__run_code", Q_RUN, "sandbox__run_code", False),
        ("F4 web__search", Q_SEARCH, "web__search", False),
    ]
    if doc_path and question:
        cases.append(("F5 docs__query",
                      f"افتح المستند {doc_path} وجاوبني منه: {question}",
                      "docs__query", False))
    for name, prompt, tool, required in cases:
        # FRESH: each regression asks an unrelated question. T7's F3 asked for
        # ٢+٢ and answered about the document F2 had just read.
        result, count = await drive(orchestrator, agent, session, name, prompt)
        passes.append(count)
        called = any(c.name == tool for c in result.tool_calls)
        if called or required:
            checks.record(name, called and bool(result.spoken_text.strip()))
        else:
            checks.record(name, None, f"{tool} was not called — dependency or key absent")
    if not (doc_path and question):
        checks.record("F5 docs__query", None, "no --doc / --question supplied")
    return passes


async def observe(observations: Observations, orchestrator, agent: PassCounter,
                  session: Session, doc_path: Optional[str],
                  question: Optional[str], interactive: bool) -> "list[int]":
    """O-1 … O-3. NOTHING here returns a verdict, by construction: this function
    is handed the `Observations` register and never the `Checks` one.

    EVERY observation starts FRESH (see `Session`). The only exception is the
    walkthrough's advances, which must inherit the plan they are advancing and
    say so explicitly at their call site."""
    passes: "list[int]" = []
    result, count = await drive(orchestrator, agent, session,
                                "O-1 does the model reach for the verbs UNPROMPTED?",
                                Q_UNPROMPTED)
    passes.append(count)
    observations.add(
        "O-1 — UNPROMPTED Navigator reach (this decides the persona-law question)", {
            "the question named no step, plan or walkthrough": Q_UNPROMPTED,
            "tools the model called": [c.name for c in result.tool_calls],
            "did it call navigator__plan": any(
                c.name == "navigator__plan" for c in result.tool_calls),
            "reply": result.spoken_text.strip()[:600],
            "FOR SULTAN": "if it did NOT reach for the verbs, a persona law is a "
                          "RULING to request — never a patch to make quietly",
        })

    # FRESH: O-1 left an ACTIVE mode. T7's first run opened this walkthrough
    # inside it and the model answered «خلينا نكمّل خطوات تغيير الخلفية أولاً» —
    # correct behaviour for the Navigator, and a measurement of nothing.
    result, count = await drive(orchestrator, agent, session,
                                "O-2 step pacing — the walkthrough opens", Q_WALKTHROUGH)
    passes.append(count)
    turns = [result.spoken_text.strip()[:300]]
    for index in range(4):
        # fresh=False — THE ONE PLACE CONTINUITY IS CORRECT: an advance that did
        # not inherit its own plan would be advancing nothing.
        step, count = await drive(orchestrator, agent, session,
                                  f"O-2 step pacing — advance {index + 1}", Q_ADVANCE,
                                  fresh=False)
        passes.append(count)
        turns.append(step.spoken_text.strip()[:300])
    observations.add("O-2 — step pacing and the spoken frame (ear, not score)", {
        "the plan's opening": turns[0],
        "the advances": turns[1:],
        "FOR SULTAN": "does this feel like GUIDANCE, or like a list read aloud? "
                      "and did it call navigator__step 'done' at the end?",
    })

    result, count = await drive(orchestrator, agent, session,
                                "O-3 path ① — a claim about the SCREEN", Q_SCREEN_EVIDENCE)
    passes.append(count)
    observations.add("O-3 path ① — a SCREEN claim, evidence pointable", {
        "tools": [c.name for c in result.tool_calls],
        "pointed": any(c.name == "highlight_target" for c in result.tool_calls),
        "reply": result.spoken_text.strip()[:400],
    })

    if not (doc_path and question and interactive):
        observations.add("O-3 paths ② and ③ — SKIPPED", {
            "reason": "need --doc, --question and an interactive console",
        })
        return passes

    input("\n  >>> OPEN the document on screen now, then press Enter (path ②) ")
    result, count = await drive(orchestrator, agent, session,
                                "O-3 path ② — the DISPLAYED document",
                                f"افتح المستند {doc_path} وجاوبني منه: {question} — وورّني وين قالها.")
    passes.append(count)
    observations.add("O-3 path ② — a passage pointed at where the user can SEE it", {
        "tools": [c.name for c in result.tool_calls],
        "pointed": any(c.name == "highlight_target" for c in result.tool_calls),
        "reply": result.spoken_text.strip()[:400],
        "FOR SULTAN": "did the rectangle land on the passage it cited? this is the "
                      "prose-pointing question DEC-75 left open — D-1 measured UI "
                      "elements with visual boundaries, never continuous prose",
    })

    input("\n  >>> MINIMISE the document now, then press Enter (path ③) ")
    result, count = await drive(orchestrator, agent, session,
                                "O-3 path ③ — INDEXED, not displayed",
                                f"جاوبني من نفس المستند: {question} — وورّني وين قالها.")
    passes.append(count)
    observations.add("O-3 path ③ — the honest refusal that redirects to the vision path", {
        "tools": [c.name for c in result.tool_calls],
        "pointed anyway (it should NOT have)": any(
            c.name == "highlight_target" for c in result.tool_calls),
        "reply": result.spoken_text.strip()[:400],
        "FOR SULTAN": "did it name the page AND offer to point once the document is "
                      "on screen? a limit becoming a showcase, the DEC-47 pattern",
    })
    return passes


def summarise(checks: Checks, observations: Observations) -> int:
    print("\n" + "=" * 78)
    print("DIAGNOSTIC SUMMARY — THIS IS NOT AN ACCEPTANCE VERDICT")
    print("=" * 78)
    for name, ok in checks.results.items():
        print(f"  [{ {True: 'PASS', False: 'FAIL', None: 'SKIP'}[ok] }] {name}")
    # WHAT WAS SKIPPED, AND WHY, SAID PLAINLY. A summary that lists a skip as a
    # bare "SKIP" invites it to be read as "fine" — and a run whose coverage came
    # from a PREVIOUS run must say so, or the next reader will believe this one
    # proved more than it did.
    skipped = [n for n, ok in checks.results.items() if ok is None]
    if skipped:
        print(f"\n  SKIPPED — NOT RUN, NOT PROVEN BY THIS RUN ({len(skipped)}):")
        for name in skipped:
            note = SETTLED_BY_RUN_1 if name in PAID_CHECKS else "dependency absent"
            print(f"    · {name}\n        {note}")
        if any(n in PAID_CHECKS for n in skipped):
            print("    Coverage for the above comes from RUN 1, not from this run.")
    print(f"\n  observations recorded (NO verdict, Sultan judges): {len(observations.items)}")
    print("\n  MANUAL STEPS THIS SCRIPT CANNOT DRIVE — run `python -m muthis.main`:")
    print("    · hold F9 and SAY «خلاص» — the exit word must survive REAL STT,")
    print("      which is the only half of the exit that a typed string cannot prove")
    print("    · watch the mode chip: top-left, legible, surviving each turn, gone")
    print("      when the walkthrough ends — and ABSENT from the saved sent frame")
    print(f"      ({FRAME_DUMP} if a frame was captured)")
    print("    · listen for pacing: one step per breath, never a list read aloud")
    print("\n  T6 IS NEVER DECLARED PASSED BY AN AGENT. Sultan runs the live SOP on")
    print("  his own hardware and signs off PERSONALLY. This run is diagnostic only.")
    failed = checks.failed()
    if failed:
        print(f"\n  DETERMINISTIC FAILURES ({len(failed)}): {failed}")
    return 1 if failed else 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3 live SOP (diagnostic only)")
    parser.add_argument("--doc", help="a document of Sultan's own — never in the repo")
    parser.add_argument("--question", help="a question the document DOES answer")
    parser.add_argument(
        "--observations-only", action="store_true",
        help="skip the checks that cost a live model turn and were already "
             "settled by run 1, so the budget pays for the UNSETTLED half")
    args = parser.parse_args()

    tap = LogTap()
    logging.getLogger().addHandler(tap)
    logging.getLogger().setLevel(logging.INFO)
    checks, observations = Checks(), Observations()
    workdir = pathlib.Path(tempfile.mkdtemp(prefix="muthis-diag-nav-"))
    # The service is built and handed to the plugin by production's own helper;
    # the ROOT keeps it because it owns the teardown, and this script's teardown
    # is the process ending — the index is RAM-only and dies with it by design.
    _doc_service, doc_plugin = _build_doc_rag()
    budget = Budget()

    # THE BUDGET, STATED BEFORE ANYTHING IS SPENT. T7's first run exhausted it
    # partway through and printed four EMPTY observations that looked like data;
    # a full run is ~15 live turns and the decisive half is the last one.
    print(f"\n  budget today: {budget.spent_today_usd():.4f} spent / "
          f"{budget.daily_limit_usd:.2f} USD limit — "
          f"{budget.remaining_usd():.4f} remaining")
    print("  SULTAN: set MUTHIS_DAILY_BUDGET_USD high enough BEFORE starting. A run "
          "that starves\n  settles nothing, and the phases that settle the most run LAST.")

    print("\n════ building the PRODUCTION graph (production helpers, production order) ════")
    orchestrator, overlay, agent, fetcher, search, tool_count = \
        await build_live_graph(budget, doc_plugin)
    session = Session(orchestrator)
    # THE HARNESS'S OWN POSITIVE CONTROL, not a catalog test — `look_tools_v6.json`
    # is byte-pinned in pytest and needs no second guard. What this catches is a
    # mount MISSING FROM THIS SCRIPT, which would let every check below pass while
    # driving a catalog production never builds.
    checks.record(f"A0 the harness built the production catalog ({CATALOG_V6_TOOLS} tools)",
                  tool_count == CATALOG_V6_TOOLS, f"got {tool_count}")

    passes: "list[int]" = []
    try:
        if args.observations_only:
            # SKIPPED WITH A STATED REASON, never passed quietly: a skip that
            # reads as a pass is the failure this project keeps meeting from the
            # other side — a check reporting success having examined nothing.
            print("\n════ PAID DETERMINISTIC CHECKS — SKIPPED (--observations-only) ════")
            for name in PAID_CHECKS:
                checks.record(name, None, SETTLED_BY_RUN_1)
        else:
            first, count = await drive(orchestrator, agent, session,
                                       "A the catalog is ACCEPTED by the real API",
                                       Q_POINT)
            passes.append(count)
            checks.record("A the real API accepted catalog v6 (the DEC-11 failure class)",
                          bool(first.spoken_text.strip()) or bool(first.tool_calls))

        # The FREE deterministic checks run in BOTH modes — they drive no model.
        print("\n════ DETERMINISTIC — the mode frame end-to-end (free, always run) ════")
        await check_indicator_and_exits(checks, orchestrator, overlay)

        # OBSERVED RUNS BEFORE THE REGRESSIONS, and the order is a decision.
        # These three phases are what the run exists to settle and they are the
        # ones a budget ceiling truncates; the regressions confirm shipped
        # capabilities that pytest and four previous live SOPs already cover, so
        # they are the cheaper thing to lose. T7's first run lost the wrong half.
        print("\n════ OBSERVED — printed for Sultan, scored neither PASS nor FAIL ════")
        passes += await observe(observations, orchestrator, agent, session,
                                args.doc, args.question, sys.stdin.isatty())

        if not args.observations_only:
            print("\n════ DETERMINISTIC — regression across every shipped capability ════")
            passes += await run_regressions(checks, orchestrator, agent, session,
                                            workdir, args.doc, args.question)
    finally:
        await fetcher.aclose()
        await search.aclose()

    checks.record(f"C no turn exceeded MAX_AGENTIC_ITERATIONS={MAX_AGENTIC_ITERATIONS}",
                  all(p <= MAX_AGENTIC_ITERATIONS for p in passes),
                  f"pass counts: {passes}")
    checks.record("B no LOOK-only violation was logged in any live turn",
                  not any("LOOK-only violation" in line for line in tap.lines))
    # G1 / G2 — the T7 leak, closed and PROVEN CLOSED. G2 is the positive
    # control and it is the load-bearing one: a reset that never finds anything
    # to clear is not what is keeping the observations independent, and without
    # this the fix could rot into a no-op with every check still green.
    checks.record("G1 every independent turn started from a CLEAN session",
                  not session.dirty_after,
                  f"{session.boundaries} boundaries; still dirty: {session.dirty_after}")
    checks.record("G2 the isolation DID WORK (positive control — it found state to clear)",
                  bool(session.carried),
                  f"cleared at {len(session.carried)} of {session.boundaries} boundaries")
    for line in session.carried:
        print(f"      leak cleared — {line}")
    checks.record("H the run was NOT budget-starved (a starved run settles nothing)",
                  not session.starved, f"starved turns: {session.starved}")
    return summarise(checks, observations)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
