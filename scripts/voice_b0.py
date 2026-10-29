"""
voice_b0.py — B0, the baseline (DEC-157 ②, DEC-158), run by Sultan himself:

    .venv\\Scripts\\python.exe scripts\\voice_b0.py
    .venv\\Scripts\\python.exe scripts\\voice_b0.py resummarise <results\\b0-folder>

He must be present: every scenario needs its screen arranged by hand, so this
cannot run unattended. For each scenario it names the screen, waits for Enter,
counts down while he brings that screen to the front, runs the repetitions, and
beeps twice when the scenario is done.

THE PLAN IS PRE-REGISTERED HERE, before any B0 data exists (DEC-158):
  * four scenarios — the harness's own phrases on its own fixture screens
    (`scripts/harness/prereg.json` S7, S3, S2 and S6, the last without its spoken
    file path: the path is on screen, and a dictated path is not reliable);
  * REPS = 6 each. Repetition 1 is COLD — reported on its own, never folded into a
    median — because both providers cache the request prefix (a Claude breakpoint,
    `cloud/cache_control.py`; luna's automatic cache, which reaches the image,
    `cloud/luna_agent.py:38-48`), and the first turn after a pause pays the write.
    Repetitions 2–6 give the median and the spread (min–max): five is the smallest
    count whose median survives two bad runs, and a single turn is not a baseline;
  * a repetition the driver FLAGS is listed; every flag but one keeps the WHOLE
    repetition out of every median (an error, a turn that did not end, a turn that
    never reached the reasoner, a budget refusal — and any flag not named here).

THE EXCLUSION RULES WERE CORRECTED AFTER B0's DATA EXISTED (DEC-159 ④), so the
pre-registered summary is never rewritten: `resummarise <folder>` writes
`summary-2.json` BESIDE `summary.json` and touches no record. Two defects: a turn
with no reasoner call was folded into the medians, and a confirmation excluded the
whole repetition although its refusal came after first_token and first_audio. Now
`confirm_in_turn` drops only the stages AFTER the first refusal, which names its
tool; a refusal with no time drops the whole repetition (fail closed).

EVERY REPETITION IS A CLEAN SESSION: each is its own child process, its own app,
its own SessionTaint (`composition.py:170`), so no taint from an earlier
repetition can make a search ask for approval. What a fresh process cannot
prevent is a high-impact call AFTER the turn's first result: that result taints
the session, so a second search or a fetch asks (`trust/confirm_gate.py:231`) —
B0 measured the fetch, in every search turn that reached the reasoner.

B0 STOPS, never continues, if the durable log changes, the probe refuses to start
(the real app came back), or the budget gate closes. Records go to
`~/Desktop/muthis_voice/results/b0-<UTC stamp>/`: one JSON per repetition plus
`summary.json`. Never inside the repository; never the transcript.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import statistics
import sys
import time
from dataclasses import asdict, dataclass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import voice_drive  # noqa: E402  (puts src/ on the path too)
from muthis import voice_probe  # noqa: E402  (loads nothing of the app on import)
from muthis.broker.search import TAVILY_COST_PER_QUERY_USD  # noqa: E402
from muthis.kernel.budget import Budget, DEFAULT_DAILY_LIMIT_USD  # noqa: E402

REPS = 6
COLD_REPS = 1
COUNTDOWN_S = 8
PAUSE_S = 3
# DEC-153 ②'s logged per-turn MEANS (DECISIONS.md:19698-19699): luna $0.4155 over
# 118 turns, Claude $0.6471 over 11. A projection, never a bound.
MEAN_TURN_USD = {"luna": 0.4155 / 118, "claude": 0.6471 / 11}
MAX_SEARCHES_PER_TURN = 3              # passes 1-3 only (highlight_gate.py:162)


@dataclass(frozen=True)
class Scenario:
    name: str
    clip: str
    phrase: str
    screen: str
    setup: str
    bring_back: str


DESKTOP = ("CAPTURE_GUIDE screen 1 (`desktop`): no window open, icons hidden, a plain "
           "background, Do not disturb on.")
PLAN = (
    Scenario("toolfree", "b0_toolfree", "كم يوم في السنة الكبيسة؟", "desktop", DESKTOP,
             "press Windows + D"),
    Scenario("search", "b0_search", "وش آخر إصدار من لغة بايثون؟", "desktop", DESKTOP,
             "press Windows + D"),
    Scenario("pointing", "b0_pointing", "وين زر الحفظ؟", "editor_save",
             "CAPTURE_GUIDE screen 2 (`editor_save`): Paint full screen, one line drawn, "
             "Alt + F4, and its save-changes question left OPEN with Save visible.",
             "press Alt + Tab once (back to Paint's question)"),
    Scenario("code", "b0_code", "اشرح لي هذا الكود", "editor_code",
             "CAPTURE_GUIDE screen 3 (`editor_code`): VS Code full screen on "
             "scripts\\harness\\fixtures\\explain_me.py, one tab, no side panels.",
             "press Alt + Tab once (back to VS Code)"),
)
STAGES = ("transcript", "frame_ready", "first_token", "draw", "first_audio", "first_pass_end", "end")
SPLITS = {  # name: (from, to) — a split survives only if BOTH ends do
    "capture": ("transcript", "frame_ready"),
    "reasoner_to_first_token": ("frame_ready", "first_token"),
    "buffering": ("first_token", "first_pass_end"),      # DEC-158's rule cost on a one-pass turn
    "voice_start": ("first_pass_end", "first_audio"),
    "draw_to_audio": ("draw", "first_audio"),
    "after_first_audio": ("first_audio", "end"),
    "gap_first_token_to_first_audio": ("first_token", "first_audio"),
}
PARTIAL_FLAGS = {"confirm_in_turn"}      # every other flag excludes the whole repetition


def _env_flags() -> dict:
    """Two NON-secret flags from `.env` — the only lines of it this reads."""
    wanted, found = ("MUTHIS_REASONER", "MUTHIS_DAILY_BUDGET_USD"), {}
    env_file = voice_drive.REPO / ".env"
    for line in env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []:
        key, _, value = line.partition("=")
        if key.strip() in wanted:
            found[key.strip()] = value.strip()
    return found


def preflight() -> dict:
    """Everything that would spoil B0 is checked BEFORE the first repetition."""
    problems, clips = [], {}
    for scenario in PLAN:
        path = voice_drive.CLIP_HOME / f"{scenario.clip}.wav"
        reason = voice_probe.clip_refusal(path)
        if reason:
            problems.append(f"{scenario.clip}: {reason} — record it: .venv\\Scripts\\python.exe "
                            f"scripts\\voice_drive.py record {scenario.clip}")
        clips[scenario.name] = path
    listing = voice_probe.process_listing()
    if listing is None or voice_probe.real_app_pids(listing, {os.getpid(), os.getppid()}):
        problems.append("the real app is running (or processes cannot be listed) — close it first")
    flags = _env_flags()
    reasoner = flags.get("MUTHIS_REASONER", "claude")
    limit = float(flags.get("MUTHIS_DAILY_BUDGET_USD", DEFAULT_DAILY_LIMIT_USD))
    spent = Budget(daily_limit_usd=limit, budget_file=voice_drive.REPO / "budget.json").spent_today_usd()
    turns = REPS * len(PLAN)
    projected = (turns * MEAN_TURN_USD.get(reasoner, MEAN_TURN_USD["claude"])
                 + REPS * MAX_SEARCHES_PER_TURN * TAVILY_COST_PER_QUERY_USD)
    if limit - spent < projected:
        problems.append(f"budget: ${limit - spent:.2f} left today, B0 projects ${projected:.2f} "
                        f"on {reasoner} — raise MUTHIS_DAILY_BUDGET_USD or run tomorrow")
    return {"problems": problems, "clips": clips, "reasoner": reasoner, "limit_usd": limit,
            "spent_today_usd": spent, "projected_usd": round(projected, 4), "turns": turns}


def _measures(record: dict) -> dict:
    timing = record["timing_ms_since_release"]
    driver = record["stages_driver_ms_since_release"]
    return {"transcript": driver["transcript"], "frame_ready": driver.get("frame_ready"),
            "first_token": timing.get("first_token"), "draw": timing.get("draw"),
            "first_audio": timing.get("first_audio"),
            "first_pass_end": (driver["pass_ends"] or [None])[0], "end": driver["end"]}


def usable(record: dict) -> dict | None:
    """The stages and splits a median may use, or None when a flag drops the whole
    repetition. After a confirm refusal only stages no later than the FIRST refusal
    survive; the clocks agree to within 1 ms (the timing lines arrive on time)."""
    flags = set(record["flags"])
    if flags - PARTIAL_FLAGS:
        return None
    stages = _measures(record)
    if flags:
        times = [r["ms_since_release"] for r in record.get("refusals") or [] if r["ms_since_release"] is not None]
        if not times:
            return None
        stages = {k: v if v is not None and v <= min(times) else None for k, v in stages.items()}
    splits = {name: stages[b] - stages[a] if stages[a] is not None and stages[b] is not None else None
              for name, (a, b) in SPLITS.items()}
    return {**stages, **splits}


def _stats(values: list) -> dict:
    values = [v for v in values if v is not None]
    return ({"n": len(values), "median": statistics.median(values), "min": min(values),
             "max": max(values)} if values else {"n": 0})


def _flagged(record: dict) -> dict:
    kept, measured = usable(record), _measures(record)
    return {"rep": record["rep"], "flags": record["flags"], "refused": record.get("refusals") or [],
            "excluded": "whole repetition" if kept is None
            else [s for s in STAGES if measured[s] is not None and kept[s] is None]}


def summarise(records: list[dict]) -> dict:
    """Per scenario: the cold repetition apart, the median and min–max of the rest
    with DEC-159's exclusions, flagged repetitions listed with what they lost, and
    the outcome classes per repetition (None where the record did not retain one)."""
    out = {}
    for scenario in PLAN:
        mine = sorted((r for r in records if r["scenario"] == scenario.name), key=lambda r: r["rep"])
        used = [u for r in mine if r["rep"] > COLD_REPS for u in [usable(r)] if u is not None]
        out[scenario.name] = {
            "cold": [{"rep": r["rep"], "flags": r["flags"], **(usable(r) or {"excluded": "whole repetition"})}
                     for r in mine if r["rep"] <= COLD_REPS],
            "stages_ms": {name: _stats([u[name] for u in used]) for name in (*STAGES, *SPLITS)},
            "flagged": [_flagged(r) for r in mine if r["flags"]],
            "transcription_per_rep": [r.get("transcription") for r in mine],
            "file_reads_per_rep": [r.get("file_reads") for r in mine],
            "spoken_chars_logged_per_rep": [r.get("spoken_chars_logged") for r in mine],
            "tools_per_pass_per_rep": [r.get("tools_per_pass") for r in mine],
            "searches_per_rep": [r["searches"] for r in mine],
        }
    return out


def resummarise(folder: pathlib.Path) -> pathlib.Path:
    """Re-summarise a finished B0 from its STORED records (DEC-159 ④): no turn is
    re-run, and neither a record nor the pre-registered summary.json is touched."""
    folder = voice_drive._outside_repo(folder)
    names = tuple(f"{s.name}-" for s in PLAN)
    records = [voice_drive.reclassify(json.loads(p.read_text(encoding="utf-8")))
               for p in sorted(folder.glob("*.json")) if p.name.startswith(names)]
    original = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    summary = {**original, "schema": "voice-b0/2", "resummarised_from": "summary.json",
               "records": len(records), "scenarios": summarise(records)}
    out = folder / "summary-2.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _beep() -> None:
    try:
        import winsound
        for _ in range(2):
            winsound.Beep(880, 250)
    except (ImportError, RuntimeError):
        print("\a\a")


def main(argv: list[str] | None = None) -> int:
    if argv and argv[0] == "resummarise" and len(argv) == 2:
        out = resummarise(pathlib.Path(argv[1]))
        for name, s in json.loads(out.read_text(encoding="utf-8"))["scenarios"].items():
            print(f"{name}: " + ", ".join(f"{k} {v['median']}" for k, v in s["stages_ms"].items() if v["n"]))
        print(f"written beside the original: {out}")
        return 0
    check = preflight()
    if check["problems"]:
        print("B0 cannot start:")
        for problem in check["problems"]:
            print(f"  - {problem}")
        return 2
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = voice_drive.CLIP_HOME / "results" / f"b0-{stamp}"
    folder = voice_drive._outside_repo(folder)       # checked BEFORE anything is created
    folder.mkdir(parents=True, exist_ok=True)
    print(f"B0: {len(PLAN)} scenarios x {REPS} repetitions = {check['turns']} turns on "
          f"{check['reasoner']}, projected ${check['projected_usd']:.2f} "
          f"(${check['limit_usd'] - check['spent_today_usd']:.2f} left today). About 10-15 minutes.")
    print("During a scenario touch nothing: the app answers aloud each time; two beeps end it.")
    input("Press Enter to begin. ")
    records: list[dict] = []
    for number, scenario in enumerate(PLAN, 1):
        print(f"\n=== {number} of {len(PLAN)}: {scenario.name} — say-clip {scenario.clip}.wav "
              f"«{scenario.phrase}»\nScreen: {scenario.setup}")
        input("Set that screen up, come back here, and press Enter. ")
        print(f"Now {scenario.bring_back}, park the mouse on an empty spot, and touch nothing.")
        for left in range(COUNTDOWN_S, 0, -1):
            print(f"  starting in {left} s", end="\r")
            time.sleep(1)
        for rep in range(1, REPS + 1):
            record = voice_drive.run_once(check["clips"][scenario.name], "B0",
                                          scenario=scenario.name, rep=rep, results_dir=folder)
            records.append(record)
            print(f"  {scenario.name} rep {rep}: {_measures(record)} flags={record['flags']}")
            stop = (not voice_drive.log_clean(record) and "the durable log CHANGED") or \
                   ("refused_to_start" in record["flags"] and "the probe refused to start") or \
                   ("budget_refused" in record["flags"] and "the budget gate closed")
            if stop:
                print(f"\nB0 STOPPED: {stop}. Records so far: {folder}")
                return 4
            time.sleep(PAUSE_S)
        _beep()
    summary = {"schema": "voice-b0/2", "created_utc": stamp, "reps": REPS, "cold_reps": COLD_REPS,
               "plan": [asdict(s) for s in PLAN], "preflight": {k: v for k, v in check.items()
                                                                if k not in ("clips", "problems")},
               "clips": {r["scenario"]: r["clip"] for r in records},
               "git_head": records[0]["git_head"], "config_lines": records[0]["config_lines"],
               "scenarios": summarise(records)}
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nB0 done. Tell Claude this folder: {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
