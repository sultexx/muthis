"""
runner.py — one configuration through the pre-registered scenarios, on a FRESH
real graph per run, with every record written to the harness home OUTSIDE the
repository (`~/Desktop/muthis_harness`).

The reasoner is whatever the configuration names, behind `RecordingReasoner`:
a scripted policy for the self-test, or a live agent. A LIVE agent is built only
through `live_reasoner`, which takes the API key as an argument — the key is
read at ONE site (`cli.py`, from `.env` by `dotenv_values`), never placed in
`os.environ`, never printed. `store=False` is the agent's own and untouched.

Scoring is separate: `signals_for` (signals per run, the exclusions) and
`calibrate` (the A-against-A′ pair: its pooled spread and allowance). The
pairwise gates — which word rules and which thresholds may count — are computed
by the caller from BOTH configurations (`gates`).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import pathlib
import runpy
from typing import Any, Callable, Iterator, Optional

from muthis.logging_policy import silence_third_party_http_logs

from harness import graph as graph_mod
from harness.config import (Configuration, apply_notes, canonical_catalogue, compose_persona,
                            fingerprint, sha, texts_for, verify_declared)
from harness.prereg import Prereg, Scenario, fixture_paths, source_identical, source_text_in
from harness.record import (MemoryLogHandler, RecordingOverlay, RecordingReasoner,
                            RecordingVoice, RunRecorder)
from harness.score import aggregate, padding_bounds
from harness.signals import extract

HOME = pathlib.Path.home() / "Desktop" / "muthis_harness"
SIGNAL_CONSTANTS = ("muthis.kernel.verification_notes.VERIFY_FALLBACK_AR",
                    "muthis_plugins.sandbox_exec.runner.DOCKER_UNAVAILABLE_AR")


def truths(prereg: Prereg) -> dict[str, str]:
    """Computed from the fixture, never typed: f(37) by running the fixture here."""
    f = runpy.run_path(fixture_paths()["recur"])["f"]
    return {"recurrence_f37": str(f(37)), "leap_days": str(prereg.scenarios["S7"].truth)}


def fingerprint_constants(prereg: Prereg, configs: list[Configuration]) -> list[str]:
    names = {f"{r.source.module}.{r.source.name}" for r in prereg.rules.values()
             if r.source.kind == "constant"}
    names |= set(SIGNAL_CONSTANTS)
    for cfg in configs:
        names |= set(cfg.notes)
    return sorted(names)


def catalogue_now() -> list:
    """The catalogue a fresh graph hands the model — taken from a real router."""
    budget = graph_mod.harness_budget(HOME / "preflight", 0.01)
    return graph_mod.build_router(runner="docker", budget=budget).catalogue


def prepare(cfg: Configuration, prereg: Prereg, constants: list[str],
            catalogue: list) -> dict[str, Any]:
    """The configuration as this process will SEND it: persona, texts, the
    fingerprint, and every mismatch with what it declared."""
    persona = compose_persona(cfg, prereg.sent_image)
    with apply_notes(cfg):
        texts = texts_for(persona, constants)
        errors = verify_declared(cfg, persona, catalogue, texts, prereg.sent_image)
    return {"persona": persona, "texts": texts, "errors": errors,
            "fingerprint": fingerprint(cfg, persona, catalogue, texts)}


@contextlib.contextmanager
def effort(cfg: Configuration) -> Iterator[None]:
    """Luna's effort is a module global read at call time (`REASONING_EFFORT`)."""
    if cfg.reasoner != "luna":
        yield
        return
    from muthis.cloud import luna_agent
    saved = luna_agent.REASONING_EFFORT
    luna_agent.REASONING_EFFORT = cfg.effort
    try:
        yield
    finally:
        luna_agent.REASONING_EFFORT = saved


def live_reasoner(cfg: Configuration, persona: str, catalogue: list, api_key: str) -> Any:
    if cfg.reasoner == "luna":
        from muthis.cloud.luna_agent import LunaAgent
        return LunaAgent(api_key=api_key, model=cfg.model, max_tokens=cfg.max_tokens,
                         system_prompt=persona, tools=catalogue)
    if cfg.reasoner == "claude":
        from muthis.cloud.claude_agent import ClaudeAgent
        return ClaudeAgent(api_key=api_key, model=cfg.model, max_tokens=cfg.max_tokens,
                           system_prompt=persona, tools=catalogue)
    raise ValueError(f"not a live reasoner: {cfg.reasoner!r}")


async def run_one(cfg: Configuration, scenario: Scenario, rep: int, persona: str,
                  png: bytes, make_inner: Callable[[list, Scenario], Any],
                  budget_limit: float) -> dict[str, Any]:
    recorder = RunRecorder(config=cfg.label, scenario=scenario.id, rep=rep, model=cfg.model)
    overlay, voice = RecordingOverlay(recorder), RecordingVoice(recorder)
    budget = graph_mod.harness_budget(HOME / "budget", budget_limit)
    g = graph_mod.build_router(runner=scenario.runner, budget=budget)
    if sha(canonical_catalogue(g.catalogue)) != cfg.catalogue_sha256:
        raise RuntimeError(f"{cfg.label}: this run's catalogue is not the declared one")
    inner = make_inner(g.catalogue, scenario)
    reasoner = RecordingReasoner(inner, recorder)
    orchestrator = graph_mod.build_orchestrator(g, reasoner=reasoner, overlay=overlay,
                                                voice=voice, png=png)
    kernel_log = logging.getLogger("muthis")
    handler, saved_level = MemoryLogHandler(recorder), kernel_log.level
    kernel_log.addHandler(handler)
    kernel_log.setLevel(logging.INFO)
    try:
        for index, text in enumerate(scenario.turn_texts()):
            recorder.begin_turn(text)
            if hasattr(inner, "begin_turn"):
                inner.begin_turn(index)
            recorder.end_turn(await orchestrator.run_turn(text))
    finally:
        kernel_log.removeHandler(handler)
        kernel_log.setLevel(saved_level)
        await g.aclose()
        await reasoner.aclose()
    recorder.data["catalogue_tools"] = [t["name"] for t in g.catalogue]
    return recorder.data


def run_configuration(cfg: Configuration, prereg: Prereg, scenario_ids: list[str],
                      reps: int, screens: dict[str, bytes],
                      make_inner: Callable[[list, Scenario], Any], budget_limit: float,
                      out: Optional[pathlib.Path] = None) -> dict[str, list[dict]]:
    """R runs of each scenario. Each run is its own event loop and its own graph."""
    silence_third_party_http_logs()
    persona = compose_persona(cfg, prereg.sent_image)
    runs: dict[str, list[dict]] = {}
    with apply_notes(cfg), effort(cfg):
        for sid in scenario_ids:
            scenario = prereg.scenarios[sid]
            for rep in range(reps):
                data = asyncio.run(run_one(cfg, scenario, rep, persona, screens[scenario.screen],
                                           make_inner, budget_limit))
                data["prereg_sha256"] = prereg.sha256
                runs.setdefault(sid, []).append(data)
                if out is not None:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    with out.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(data, ensure_ascii=False) + "\n")
    return runs


def exclusion(run: dict) -> Optional[str]:
    """Why a run is NOT model behaviour, or None. "echo": a pass reported another
    id than the configured one (`record.py`: the agent's own id, not a provider
    echo); "budget": the harness ceiling refused a turn; "timeout": the session
    bound truncated one. Each is counted and reported, never silently dropped."""
    passes = [p for t in run["turns"] for p in t["passes"]]
    if not passes or not all(p["usage"] and p["usage"]["model_echo"] == run["configured_model"]
                             for p in passes):
        return "echo"
    if any(t.get("result", {}).get("budget_blocked") for t in run["turns"]):
        return "budget"
    if any(t.get("result", {}).get("timed_out") for t in run["turns"]):
        return "timeout"
    return None


def gates(prereg: Prereg, texts_a: dict, texts_b: dict) -> tuple[dict, dict]:
    """Which word rules and thresholds may count in THIS comparison."""
    enabled = {rid: source_identical(r.source, texts_a, texts_b)
               for rid, r in prereg.rules.items()}
    thresholds_on = {tid: source_identical(t.source, texts_a, texts_b)
                     for tid, t in prereg.thresholds.items()}
    return enabled, thresholds_on


def signals_for(runs: dict[str, list[dict]], prereg: Prereg, texts: dict, enabled: dict,
                thresholds_on: dict) -> tuple[dict, dict, dict]:
    """(signals per scenario, the runs kept, the exclusions by reason). `texts`
    is THIS configuration's, so each reads its own delivered constants."""
    ctx = {"rules": prereg.rules, "enabled": enabled, "thresholds": prereg.thresholds,
           "thresholds_on": thresholds_on, "truths": truths(prereg),
           "constants": {k: v for k, v in texts.items() if k != "persona"}}
    sigs: dict[str, list[dict]] = {}
    kept: dict[str, list[dict]] = {}
    excluded: dict[str, dict[str, int]] = {}
    for sid, rows in runs.items():
        reasons = [exclusion(r) for r in rows]
        good = [r for r, why in zip(rows, reasons) if why is None]
        excluded[sid] = {why: reasons.count(why) for why in set(reasons) if why}
        kept[sid] = good
        sigs[sid] = [extract(r, prereg.scenarios[sid], ctx) for r in good]
    return sigs, kept, excluded


def calibrate(pair: list[tuple[str, dict, dict]], prereg: Prereg) -> tuple[list[dict], dict]:
    """The A-against-A′ pair: its pooled S2 spread, both arms aggregated against
    it, and the allowance (the larger arm's padding-flag count) that later
    comparisons are held to. `pair`: (label, sigs, kept runs) per arm."""
    bounds = padding_bounds([s for _, sigs, _ in pair for s in sigs.get("S2", [])])
    aggs = [aggregate(label, sigs, kept, prereg, {**bounds, "allowance": None})
            for label, sigs, kept in pair]
    allowance = max(a["scenarios"].get("S2", {}).get("padding_suspect", 0) for a in aggs)
    return aggs, {**bounds, "allowance": allowance}


def cost(runs: dict[str, list[dict]]) -> float:
    return round(sum((p["usage"] or {}).get("cost_usd") or 0.0
                     for rows in runs.values() for r in rows
                     for t in r["turns"] for p in t["passes"]), 6)


__all__ = ["HOME", "calibrate", "catalogue_now", "cost", "effort", "exclusion",
           "fingerprint_constants", "gates", "live_reasoner", "prepare", "run_configuration",
           "run_one", "signals_for", "source_text_in", "truths"]
