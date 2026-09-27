"""
cli.py — the harness's commands.

  selftest   the harness tested before it measures anything (no provider, no key)
  preflight  two configurations: declarations, fingerprints, the DERIVED
             comparison type, which word rules and thresholds may count
  run        ONE configuration, LIVE. Refuses unless every gate below holds.
  score      two configurations' recorded runs → counts, Fisher, the blind queue

THE LIVE GATES (`run`): an explicit `--live`; a clean preflight; every screen the
scenarios use present, hashed as the manifest records and marked reviewed, and
SENT at the pre-registered size; Docker answering; an explicit budget; the key
present. The key is read HERE and nowhere else, from `.env` by `dotenv_values`
— never `load_dotenv`, never into `os.environ`, never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys
from typing import Optional

from harness import prodlog
from harness.config import Configuration, comparison_type
from harness.prereg import HERE, load, missing_in_production
from harness.record import MemoryLogHandler
from harness.runner import (HOME, calibrate, catalogue_now, cost, fingerprint_constants, gates,
                            live_reasoner, prepare, run_configuration, signals_for)
from harness.score import aggregate, blind_queue, compare, detections

REPO = HERE.parents[1]
MANIFEST = HERE / "fixtures" / "screens" / "MANIFEST.json"
KEY_NAMES = {"luna": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY"}   # as selection.py


def _selftest(_args: argparse.Namespace) -> int:
    from harness import selftest
    res = selftest.main()
    for name, ok, detail in res.rows:
        line = f"{'PASS' if ok else 'FAIL'}  {name}"
        print(line if ok or not detail else f"{line}\n        {detail[:300]}")
    out = HOME / "selftest" / "report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"rows": res.rows, "report": res.report}, ensure_ascii=False,
                              indent=1, default=str), encoding="utf-8")
    print(f"\n{len(res.rows) - len(res.failed)} of {len(res.rows)} checks pass; report: {out}")
    return 0 if not res.failed else 1


def _prepared(paths: list[str]):
    prereg = load()
    configs = [Configuration.from_json(pathlib.Path(p)) for p in paths]
    catalogue = catalogue_now()
    constants = fingerprint_constants(prereg, configs)
    return prereg, configs, [prepare(c, prereg, constants, catalogue) for c in configs]


def _preflight(args: argparse.Namespace) -> int:
    prereg, configs, preps = _prepared([args.a, args.b])
    bad = 0
    for cfg, prep in zip(configs, preps):
        print(f"{cfg.label}: {'declaration OK' if not prep['errors'] else prep['errors']}")
        bad += len(prep["errors"])
    stale = missing_in_production(prereg, preps[0]["texts"] if configs[0].baseline else
                                  preps[1]["texts"])
    print(f"sources missing in production: {stale or 'none'}")
    kind = comparison_type(preps[0]["fingerprint"], preps[1]["fingerprint"])
    enabled, on = gates(prereg, preps[0]["texts"], preps[1]["texts"])
    print(f"comparison type (derived): {kind}")
    print(f"word rules that count: {sorted(r for r, v in enabled.items() if v)}")
    print(f"word rules DISABLED → blind read: {sorted(r for r, v in enabled.items() if not v)}")
    print(f"thresholds DISABLED → blind read: {sorted(t for t, v in on.items() if not v)}")
    return 1 if bad or stale else 0


def screens_for_live(prereg, scenario_ids: list[str], manifest_path: pathlib.Path = MANIFEST
                     ) -> tuple[dict[str, bytes], list[str]]:
    """The reviewed screens, or every reason one cannot be used."""
    from muthis.vision.downscale import downscale_to_max_width
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["screens"]
    screens, problems = {}, []
    for name in sorted({prereg.scenarios[s].screen for s in scenario_ids}):
        entry = manifest.get(name) or {}
        path = manifest_path.parent / entry.get("file", f"{name}.png")
        if not path.exists():
            problems.append(f"{name}: no file {path.name}")
            continue
        png = path.read_bytes()
        digest = hashlib.sha256(png).hexdigest()
        if not entry.get("reviewed") or entry.get("sha256") != digest:
            problems.append(f"{name}: not marked reviewed for sha256 {digest[:12]}")
            continue
        sent = asyncio.run(downscale_to_max_width(png))
        size = (sent.sent_width, sent.sent_height)          # (0, 0) on a Pillow failure
        if size != tuple(prereg.sent_image):
            problems.append(f"{name}: sent at {size}, pre-registered {prereg.sent_image}")
            continue
        screens[name] = png
    return screens, problems


def _docker_up() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except Exception:  # noqa: BLE001 — a missing binary is a refusal, not a crash
        return False


def _api_key(reasoner: str) -> Optional[str]:
    """THE ONE READ SITE for a key."""
    from dotenv import dotenv_values
    value = dotenv_values(REPO / ".env").get(KEY_NAMES.get(reasoner, ""), "") or ""
    return value.strip() or None


def _run(args: argparse.Namespace) -> int:
    prereg, (cfg,), (prep,) = _prepared([args.config])
    sids = args.scenarios.split(",") if args.scenarios else list(prereg.scenarios)
    refusals = [] if args.live else ["--live was not given"]
    refusals += prep["errors"]
    screens, problems = screens_for_live(prereg, sids)
    refusals += problems
    if not _docker_up():
        refusals.append("docker info failed")
    if args.budget_usd is None:
        refusals.append("--budget-usd is required")
    key = _api_key(cfg.reasoner) if not refusals else None
    if not refusals and key is None:
        refusals.append(f"{KEY_NAMES.get(cfg.reasoner, cfg.reasoner)} is empty in .env")
    if refusals:
        print("REFUSED:\n  " + "\n  ".join(refusals))
        return 2
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = HOME / "runs" / cfg.label / f"{stamp}.jsonl"
    reps = args.reps or prereg.runs_per_configuration
    with prodlog.Guard(extra_allowed=(MemoryLogHandler,)):
        runs = run_configuration(
            cfg, prereg, sids, reps, screens,
            lambda catalogue, sc: live_reasoner(cfg, prep["persona"], catalogue, key),
            args.budget_usd, out=out)
    print(f"{sum(map(len, runs.values()))} runs → {out}; spent ${cost(runs):.4f}")
    return 0


def _load_runs(path: pathlib.Path) -> dict[str, list[dict]]:
    runs: dict[str, list[dict]] = {}
    files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    for file in files:
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                runs.setdefault(row["scenario"], []).append(row)
    return runs


def _score(args: argparse.Namespace) -> int:
    prereg, configs, preps = _prepared([args.a, args.b])
    kind = comparison_type(preps[0]["fingerprint"], preps[1]["fingerprint"])
    enabled, on = gates(prereg, preps[0]["texts"], preps[1]["texts"])
    runs = [_load_runs(pathlib.Path(p)) for p in (args.a_runs, args.b_runs)]
    wrong = [r["rep"] for rs in runs for rows in rs.values() for r in rows
             if r.get("prereg_sha256") != prereg.sha256]
    if wrong:
        print(f"REFUSED: {len(wrong)} runs were recorded under another pre-registration")
        return 2
    arms = [signals_for(runs[i], prereg, preps[i]["texts"], enabled, on) for i in (0, 1)]
    out = HOME / "scores" / f"{configs[0].label}_vs_{configs[1].label}"
    out.mkdir(parents=True, exist_ok=True)
    if args.calibration:
        calib = json.loads(pathlib.Path(args.calibration).read_text(encoding="utf-8"))
        if calib.get("prereg_sha256") != prereg.sha256:
            print("REFUSED: the calibration was made under another pre-registration")
            return 2
        aggs = [aggregate(configs[i].label, arms[i][0], arms[i][1], prereg, calib)
                for i in (0, 1)]
    elif kind == "identical":
        aggs, calib = calibrate([(configs[i].label, arms[i][0], arms[i][1]) for i in (0, 1)],
                                prereg)
        (out / "calibration.json").write_text(json.dumps(
            {**calib, "pair": [c.label for c in configs], "prereg_sha256": prereg.sha256}),
            encoding="utf-8")
    else:
        print(f"REFUSED: a {kind} comparison is scored against an A-against-A′ calibration "
              "(--calibration <scores/…/calibration.json>)")
        return 2
    queue, key = blind_queue(aggs, seed=args.seed)
    (out / "blind_queue.json").write_text(json.dumps(queue, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    (out / "blind_KEY_open_after_reading.json").write_text(json.dumps(key), encoding="utf-8")
    table = {"comparison": kind, "calibration": calib, "excluded": [arms[0][2], arms[1][2]],
             "reliability": [aggs[0]["reliability"], aggs[1]["reliability"]],
             "mute": [aggs[0]["mute"], aggs[1]["mute"]], "rows": compare(aggs[0], aggs[1]),
             "detections": [sorted(detections(aggs[0])), sorted(detections(aggs[1]))],
             "cost_usd": [cost(runs[0]), cost(runs[1])], "blind_passages": len(queue)}
    (out / "table.json").write_text(json.dumps(table, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    print(f"{kind} comparison; {len(queue)} passages to read blind; results in {out}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="harness")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest").set_defaults(func=_selftest)
    p = sub.add_parser("preflight")
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.set_defaults(func=_preflight)
    r = sub.add_parser("run")
    r.add_argument("--config", required=True)
    r.add_argument("--live", action="store_true")
    r.add_argument("--reps", type=int, default=None)
    r.add_argument("--scenarios", default="")
    r.add_argument("--budget-usd", type=float, default=None)
    r.set_defaults(func=_run)
    s = sub.add_parser("score")
    for flag in ("--a", "--b", "--a-runs", "--b-runs"):
        s.add_argument(flag, required=True)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--calibration", default="")
    s.set_defaults(func=_score)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
