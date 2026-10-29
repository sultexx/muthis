"""
test_voice_b0.py — B0's guided command and the driver's per-run record (DEC-157 ②,
DEC-158), proven without a microphone, a provider or a child process.

What is pinned: every repetition is its OWN child process (a clean session); the
transcript's text never reaches a record; the stages are measured from the F9
release; the plan is the harness's own pre-registered phrases and screens; the
cold repetition and every flagged repetition stay out of the medians; and B0 STOPS
on a durable-log change instead of continuing.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import wave

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SECRET_WORDS = "كلمة_سرية_في_النص"


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


drive = _load("voice_drive")
b0 = _load("voice_b0")

CHILD = [
    (100, "INFO muthis.cloud: [cloud] reasoner=luna model=gpt-5.6-luna"),
    (110, "INFO muthis.broker.search: [search] provider=tavily (auto)"),
    (1000, "INFO muthis.voice_probe: [probe] F9 released after 2.10 s — scheduling the turn"),
    (2300, f"INFO stt: [STT] transcript: '{SECRET_WORDS} [timing] [pass]'"),
    (3100, "INFO muthis.timing: [timing] first_token +2050 ms"),
    (4200, "INFO budget: [budget] recorded 0.003 USD — today 0.003 / 2.00 USD"),
    (4300, "INFO muthis.orchestrator: [pass] #1 tools=web__search"),
    (4400, "INFO muthis.trust.confirm_gate: [confirm-gate] high-impact web__search refused — awaiting spoken approval"),
    (5100, "INFO muthis.timing: [timing] first_audio +4080 ms"),
    (6000, "INFO muthis.orchestrator: [pass] #2 tools=-"),
    (9000, "INFO muthis.main: [main] turn ended — state reset; F9 ready"),
]


# ─── The driver's record ──────────────────────────────────────────────────────

def test_the_stages_are_measured_from_the_release():
    s = drive.summarise(CHILD)
    assert s["release_at_driver_ms"] == 1000
    assert s["stages_driver_ms_since_release"] == {"transcript": 1300, "pass_ends": [3200], "end": 8000}
    assert s["timing_ms_since_release"] == {"first_token": 2050, "first_audio": 4080}
    assert s["gap_first_token_to_first_audio_ms"] == 2030
    assert s["tools_per_pass"] == [["web__search"], []] and s["searches"] == 1
    assert s["flags"] == ["confirm_in_turn"], "a confirmation inside the turn must flag the run"
    assert s["config_lines"][0].endswith("reasoner=luna model=gpt-5.6-luna")


def test_the_transcript_text_never_reaches_the_record_even_with_a_kept_marker_in_it():
    assert SECRET_WORDS not in json.dumps(drive.summarise(CHILD), ensure_ascii=False)


def test_a_run_without_the_release_line_has_no_driver_stages():
    s = drive.summarise([(5, "voice_probe: REFUSED — the real app is running (pid 1) — close it first")])
    assert s["stages_driver_ms_since_release"]["end"] is None
    assert s["flags"] == ["refused_to_start"]


class _FakeChild:
    calls: list = []

    def __init__(self, argv, **kwargs):
        _FakeChild.calls.append((argv, kwargs))
        self.stdout = iter(f"{text}\n" for _, text in CHILD)

    def wait(self):
        return 0


def _patched_run_once(monkeypatch, tmp_path):
    _FakeChild.calls = []
    monkeypatch.setattr(drive.subprocess, "Popen", _FakeChild)
    monkeypatch.setattr(drive.prodlog, "snapshot", lambda *a, **k: {})
    monkeypatch.setattr(drive, "_git", lambda *a: "deadbeef")
    clip = tmp_path / "clip.wav"
    with wave.open(str(clip), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 1600)
    return clip


def test_run_once_is_ONE_child_from_the_repo_root_under_debug(monkeypatch, tmp_path):
    clip = _patched_run_once(monkeypatch, tmp_path)
    record = drive.run_once(clip, "t", scenario="search", rep=2, results_dir=tmp_path / "out")
    assert len(_FakeChild.calls) == 1, "one run must be exactly one child process"
    argv, kwargs = _FakeChild.calls[0]
    assert argv[1:] == ["-m", "muthis.voice_probe", str(clip.resolve())]
    assert kwargs["cwd"] == drive.REPO and kwargs["env"]["MUTHIS_DEBUG"] == "1"
    written = pathlib.Path(record["record_path"])
    assert written.parent == tmp_path / "out" and record["schema"] == "voice-run/2"
    assert SECRET_WORDS not in written.read_text(encoding="utf-8")


def test_a_clip_or_record_inside_the_repository_is_refused():
    with pytest.raises(SystemExit):
        drive._outside_repo(ROOT / "tests" / "anything.wav")


# ─── B0's plan and its command ────────────────────────────────────────────────

def test_the_plan_is_the_harness_prereg_phrases_on_their_screens():
    prereg = {s["id"]: s for s in json.loads(
        (ROOT / "scripts" / "harness" / "prereg.json").read_text(encoding="utf-8"))["scenarios"]}
    by_name = {s.name: s for s in b0.PLAN}
    for name, sid in (("toolfree", "S7"), ("search", "S3"), ("pointing", "S2")):
        assert [by_name[name].phrase] == prereg[sid]["turns"] and by_name[name].screen == prereg[sid]["screen"]
    assert prereg["S6"]["turns"][0].startswith(by_name["code"].phrase + ".")
    assert by_name["code"].screen == prereg["S6"]["screen"]
    assert (b0.REPS, b0.COLD_REPS) == (6, 1)


def _record(scenario, rep, *, flags=(), log_changed=False, first_token=1000, first_audio=1500):
    return {"scenario": scenario, "rep": rep, "flags": list(flags), "searches": 0,
            "clip": {"name": f"{scenario}.wav"}, "git_head": "x", "config_lines": [],
            "durable_log": {"changes": ["muthis.log changed"] if log_changed else [],
                            "attach_line_seen": False},
            "timing_ms_since_release": {"first_token": first_token, "first_audio": first_audio},
            "stages_driver_ms_since_release": {"transcript": 900, "pass_ends": [1400], "end": 5000},
            "gap_first_token_to_first_audio_ms": first_audio - first_token}


def _run_b0(monkeypatch, tmp_path, make):
    calls = []
    monkeypatch.setattr(b0, "preflight", lambda: {"problems": [], "clips": {s.name: tmp_path for s in b0.PLAN},
                                                  "reasoner": "luna", "limit_usd": 2.0,
                                                  "spent_today_usd": 0.0, "projected_usd": 0.2, "turns": 24})
    monkeypatch.setattr(b0.voice_drive, "CLIP_HOME", tmp_path)
    monkeypatch.setattr("builtins.input", lambda *a: "")
    monkeypatch.setattr(b0.time, "sleep", lambda s: None)
    monkeypatch.setattr(b0, "_beep", lambda: None)

    def fake_run_once(clip, label, *, scenario, rep, results_dir):
        calls.append((scenario, rep))
        return make(scenario, rep)
    monkeypatch.setattr(b0.voice_drive, "run_once", fake_run_once)
    return b0.main(), calls


def test_every_repetition_is_its_own_run_and_the_summary_excludes_cold_and_flagged(monkeypatch, tmp_path):
    def make(scenario, rep):
        if rep == 1:
            return _record(scenario, rep, first_audio=9000)               # cold: never in the median
        if rep == 4:
            return _record(scenario, rep, flags=["confirm_in_turn"], first_audio=99000)
        return _record(scenario, rep, first_audio=1500 + rep)
    code, calls = _run_b0(monkeypatch, tmp_path, make)
    assert code == 0
    assert calls == [(s.name, r) for s in b0.PLAN for r in range(1, 7)], "24 runs, one per repetition"
    summary = json.loads(next(tmp_path.glob("results/b0-*/summary.json")).read_text(encoding="utf-8"))
    gap = summary["scenarios"]["toolfree"]["stages_ms"]["gap_first_token_to_first_audio"]
    assert gap == {"n": 4, "median": 504.0, "min": 502, "max": 506}
    assert summary["scenarios"]["toolfree"]["flagged"] == [{"rep": 4, "flags": ["confirm_in_turn"]}]
    assert summary["scenarios"]["toolfree"]["cold"][0]["first_audio"] == 9000


def test_B0_STOPS_on_a_durable_log_change(monkeypatch, tmp_path):
    code, calls = _run_b0(monkeypatch, tmp_path,
                          lambda scenario, rep: _record(scenario, rep, log_changed=(rep == 2)))
    assert code == 4 and calls == [("toolfree", 1), ("toolfree", 2)], "B0 continued past a log change"


def test_preflight_names_the_record_command_for_a_missing_clip(monkeypatch, tmp_path):
    monkeypatch.setattr(b0.voice_drive, "CLIP_HOME", tmp_path / "nowhere")
    monkeypatch.setattr(b0.voice_probe, "process_listing", lambda: [])
    monkeypatch.setattr(b0, "_env_flags", lambda: {"MUTHIS_REASONER": "claude", "MUTHIS_DAILY_BUDGET_USD": "0.01"})
    problems = b0.preflight()["problems"]
    assert any("voice_drive.py record b0_toolfree" in p for p in problems)
    assert any(p.startswith("budget:") for p in problems), "a too-small budget must stop B0 before it starts"
