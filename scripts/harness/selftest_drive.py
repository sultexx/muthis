"""
selftest_drive.py — the scripted policies driven through the REAL graph, and
the check that every pre-registered cheat is CAUGHT while the honest policy
triggers nothing (split from `selftest.py` under the ≤300-line law).

The honest configuration runs TWICE per scenario and its two repetitions stand
in for the A-against-A′ calibration pair: their pooled S2 spread and their
padding-flag allowance are what every cheat is scored against. Scripted runs
are identical, so that spread is a single point — the tightest bound the
padding companion can ever have. A live pair varies across its eighty runs and
its bound is correspondingly looser.
"""

from __future__ import annotations

from typing import Any

from harness.canned import placeholder_png
from harness.config import (Configuration, comparison_type, production_catalogue_sha,
                            production_persona, sha)
from harness.policies import CHEATS, ScriptedReasoner
from harness.runner import (HOME, calibrate, fingerprint_constants, gates, prepare,
                            run_configuration, signals_for)
from harness.score import SILENCE_SATISFIES, aggregate, detections
from harness.signals import extract

SCREENS = ("desktop", "editor_save", "editor_code", "notepad_text")


class Results:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []
        self.report: dict[str, Any] = {}

    def check(self, name: str, ok: bool, detail: Any = "") -> bool:
        self.rows.append((name, bool(ok), str(detail)))
        return bool(ok)

    @property
    def failed(self) -> list[tuple[str, bool, str]]:
        return [r for r in self.rows if not r[1]]


def scripted(policy: str, *, persona: str = "production", persona_sha: str = "",
             baseline: bool = False, model: str = "") -> Configuration:
    return Configuration(label=policy, reasoner="scripted", model=model or f"scripted:{policy}",
                         cost_model="none", persona=persona, persona_sha256=persona_sha,
                         catalogue_sha256=production_catalogue_sha(), baseline=baseline,
                         policy=policy)


def _by_rep(sigs: dict, kept: dict, rep: int) -> tuple[dict, dict]:
    return ({sid: [s for s, r in zip(rows, kept[sid]) if r["rep"] == rep]
             for sid, rows in sigs.items()},
            {sid: [r for r in rows if r["rep"] == rep] for sid, rows in kept.items()})


def _strip(sig: dict) -> dict:
    return {k: v for k, v in sig.items() if k != "blind"}


def cheats(res: Results, prereg, catalogue: list) -> dict[str, Any]:
    screens = {name: placeholder_png(1920, 1080) for name in SCREENS}
    persona = production_persona(prereg.sent_image)
    sids = list(prereg.scenarios)
    constants = fingerprint_constants(prereg, [])
    honest_cfg = scripted("honest", persona_sha=sha(persona), baseline=True)
    prep_h = prepare(honest_cfg, prereg, constants, catalogue)
    res.check("honest configuration passes its declaration", prep_h["errors"] == [],
              prep_h["errors"])
    enabled, on = gates(prereg, prep_h["texts"], prep_h["texts"])

    def drive(cfg: Configuration, reps: int = 1) -> dict:
        return run_configuration(cfg, prereg, sids, reps, screens,
                                 lambda cat, sc: ScriptedReasoner(cfg.policy, sc.id), 0.5,
                                 out=HOME / "selftest" / "runs" / f"{cfg.label}.jsonl")

    sigs_h, kept_h, excl = signals_for(drive(honest_cfg, reps=2), prereg, prep_h["texts"],
                                       enabled, on)
    res.check("honest: no run excluded (echo, budget, timeout)", not any(excl.values()), excl)
    res.check("fresh graph per run: two honest runs give identical signals",
              all(_strip(sigs_h[s][0]) == _strip(sigs_h[s][1]) for s in sids))
    pair, calib = calibrate([("honest", *_by_rep(sigs_h, kept_h, 0)),
                             ("honest′", *_by_rep(sigs_h, kept_h, 1))], prereg)
    res.check("the calibration pair marks S2 'calibration', never UNRELIABLE",
              all(a["reliability"]["S2_explain"] == "calibration" for a in pair),
              [a["reliability"] for a in pair])
    agg_h = aggregate("honest", sigs_h, kept_h, prereg, calib)
    found_h = detections(agg_h)
    every_tag = {t for c in prereg.cheats.values() for t in c.get("caught_by", [])
                 if ":" in t and not t.startswith(("comparison:", "rule_"))}
    res.check("honest triggers NONE of the cheat tags", not (found_h & every_tag),
              sorted(found_h & every_tag))
    res.check("honest scores as pre-registered",
              set(prereg.cheats["honest"]["scores_as"]) <= found_h,
              sorted(set(prereg.cheats["honest"]["scores_as"]) - found_h))
    res.check("honest: every reliability mark 'ok'",
              all(v == "ok" for v in agg_h["reliability"].values()), agg_h["reliability"])
    report: dict[str, Any] = {"calibration": calib,
                              "honest": {"found": sorted(found_h), "signals": sigs_h}}
    for name in CHEATS:
        if name == "reword":
            continue
        cfg = scripted(name, persona_sha=sha(persona))
        sigs, kept, _ = signals_for(drive(cfg), prereg, prep_h["texts"], enabled, on)
        agg = aggregate(cfg.label, sigs, kept, prereg, calib)
        found = detections(agg)
        spec = prereg.cheats[name]
        missing = set(spec["caught_by"]) - found
        res.check(f"cheat '{name}' CAUGHT by {spec['caught_by']}", not missing, sorted(missing))
        res.check(f"cheat '{name}' scores as {spec['scores_as']}",
                  set(spec["scores_as"]) <= found, sorted(set(spec["scores_as"]) - found))
        report[name] = {"found": sorted(found),
                        "extra": sorted((found & every_tag) - set(spec["caught_by"])),
                        "reliability": agg["reliability"], "mute": agg["mute"]}
        if name == "mute":
            res.check(f"mute marks every side silence satisfies UNRELIABLE {sorted(SILENCE_SATISFIES)}",
                      all(agg["reliability"][m] == "UNRELIABLE" for m in SILENCE_SATISFIES),
                      agg["reliability"])
        if name.startswith("padding"):
            res.check(f"'{name}' marks the S2 explain rate UNRELIABLE (flags > allowance "
                      f"{calib['allowance']})", agg["reliability"]["S2_explain"] == "UNRELIABLE",
                      agg["reliability"])
    report["reword"] = reword(res, prereg, catalogue, drive, constants, prep_h, calib)
    return report


def reword(res: Results, prereg, catalogue, drive, constants, prep_h, calib) -> dict:
    reworded = HOME / "selftest" / "persona_reword.txt"
    cfg = scripted("reword", persona=str(reworded),
                   persona_sha=sha(reworded.read_text(encoding="utf-8")))
    prep_r = prepare(cfg, prereg, constants, catalogue)
    res.check("reword configuration passes its OWN declaration", prep_r["errors"] == [],
              prep_r["errors"])
    kind = comparison_type(prep_h["fingerprint"], prep_r["fingerprint"])
    enabled, on = gates(prereg, prep_h["texts"], prep_r["texts"])
    runs = drive(cfg)
    sigs, kept, _ = signals_for(runs, prereg, prep_r["texts"], enabled, on)
    found = detections(aggregate(cfg.label, sigs, kept, prereg, calib))
    found |= {f"comparison:{kind}"}
    found |= {f"rule_disabled:{r}" for r, v in enabled.items() if not v}
    found |= {f"rule_enabled:{r}" for r, v in enabled.items() if v}
    spec = prereg.cheats["reword"]
    missing = set(spec["caught_by"]) - found
    res.check(f"cheat 'reword' CAUGHT by {spec['caught_by']}", not missing, sorted(missing))
    res.check(f"reword control holds: {spec['control']}", set(spec["control"]) <= found,
              sorted(set(spec["control"]) - found))
    ungated = {rid: True for rid in prereg.rules}
    ctx = {"rules": prereg.rules, "enabled": ungated, "thresholds": prereg.thresholds,
           "thresholds_on": on, "truths": {"recurrence_f37": "", "leap_days": "366"},
           "constants": {k: v for k, v in prep_r["texts"].items() if k != "persona"}}
    s4 = extract(runs["S4"][0], prereg.scenarios["S4"], ctx)
    res.check("WITHOUT the gate, the old matcher misjudges the reworded announce "
              "(S4a=False on a text that announces)", s4["S4a"] is False
              and "أبحث لك عن" in s4["forced_text"], s4["forced_text"])
    return {"comparison": kind, "disabled": sorted(r for r, v in enabled.items() if not v),
            "found": sorted(found)}


__all__ = ["Results", "SCREENS", "cheats", "scripted"]
