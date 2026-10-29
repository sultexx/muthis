"""
voice_drive.py — the voice instrument's DRIVER (DEC-157 ⑤). Never imports the app.

    python scripts/voice_drive.py record <name>            record a clip with the app's own Mic
    python scripts/voice_drive.py silent <name> [seconds]  write a silent clip (default 0.2 s)
    python scripts/voice_drive.py run <clip.wav> [label]   ONE measured turn of the built app

CLIPS AND RECORDS STAY LOCAL (Sultan's choice ⑦; the repository is PUBLIC): both
live under CLIP_HOME (`~/Desktop/muthis_voice`, results in its `results/`), and
any path inside the repository is refused.

`run` launches `python -m muthis.voice_probe <clip>` as a CHILD from the
repository root (the budget ledger is the working directory's, so test spend
lands in the real one — choice ⑥) under MUTHIS_DEBUG=1, which refuses the durable
log. It stamps every line the child prints on ITS OWN clock, as the line arrives,
and then proves the durable log UNTOUCHED by content: `harness.prodlog` snapshots
`~/.muthis/logs` (size, mtime, sha256 per file) before the child starts and after
it exits. Only that directory check crosses a process boundary; the probe checks
its own handlers in-process.

THE RECORD IS SAVED COMPARABLY (DEC-157 ②): one JSON per run, schema
`voice-run/2` — git HEAD and whether the tree was dirty, the clip's sha256 and
length, the reasoner and search provider the child built, the three `[timing]`
lines (the app's clock), the transcript, pass ends and turn end on the driver's
clock (all relative to the F9 release), the tool NAMES per pass, the
first_token → first_audio gap (DEC-158), flags that keep a run out of a median,
and only allow-listed lines. Never the transcript's TEXT: under debug the child
prints it, the console shows it, and no record keeps it.

EVERY RUN IS A CLEAN SESSION: `run_once` starts one child, which builds one app
and runs one turn, so taint, the confirm gate and the documents never outlive it.
`scripts/voice_b0.py` is B0's guided command over `run_once`.

Console posture only: no `configure_logging`, no `muthis.main`, no file handler
(`tests/test_no_script_attaches_the_durable_log.py`).
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import wave

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "scripts")]

from harness import prodlog  # noqa: E402

CLIP_HOME = pathlib.Path.home() / "Desktop" / "muthis_voice"
SCHEMA = "voice-run/2"
KEEP = ("[timing]", "[probe]", "[pass]", "[budget]", "[mic]", "[vision]", "[cloud] reasoner=",
        "[search] provider=", "[confirm-gate]", "[orchestrator] tts", "budget gate closed",
        "voice_probe: REFUSED", "[main] turn")
NEVER_KEPT = "[STT] transcript"          # under debug the child prints it; no record keeps it
TIMING = re.compile(r"\[timing\] (\w+) \+(\d+) ms")
TOOLS = re.compile(r"\[pass\] #\d+ tools=(\S+)")
ATTACHED = "durable log attached"
FLAGS = {  # a flagged repetition is reported, never folded into a median
    "confirm_in_turn": ("[confirm-gate] high-impact",),
    "budget_refused": ("budget gate closed",),
    "turn_did_not_end": ("[probe] turn DID NOT END",),
    "refused_to_start": ("voice_probe: REFUSED",),
    "error": ("LOOK-only violation", "without TurnComplete", "turn failed unexpectedly", "Traceback"),
}


def _outside_repo(path: pathlib.Path) -> pathlib.Path:
    resolved = path.resolve()
    if resolved.is_relative_to(REPO.resolve()):
        raise SystemExit(f"refused: {resolved} is inside the repository — clips and records stay local")
    return resolved


def _clip_path(name: str) -> pathlib.Path:
    stem = pathlib.Path(name).stem
    if not re.fullmatch(r"[A-Za-z0-9_-]+", stem):
        raise SystemExit("refused: a clip name is letters, digits, '_' and '-' only")
    CLIP_HOME.mkdir(parents=True, exist_ok=True)
    return _outside_repo(CLIP_HOME / f"{stem}.wav")


def write_silent(name: str, seconds: float) -> pathlib.Path:
    from muthis.mic import CHANNELS, SAMPLE_RATE
    path = _clip_path(name)
    with wave.open(str(path), "wb") as clip:
        clip.setnchannels(CHANNELS)
        clip.setsampwidth(2)
        clip.setframerate(SAMPLE_RATE)
        clip.writeframes(b"\x00\x00" * int(SAMPLE_RATE * seconds))
    print(f"wrote {path} ({seconds:.2f} s of silence)")
    return path


def record(name: str) -> pathlib.Path:
    """Hold-to-talk by Enter: the app's own Mic, so the clip has the app's format."""
    from muthis.mic import Mic
    path = _clip_path(name)
    mic = Mic()
    input(f"Recording '{path.name}'. Press Enter, then speak; press Enter again to stop. ")
    mic.start()
    if not mic.is_recording:
        raise SystemExit("the microphone did not open")
    input("Recording... press Enter to stop. ")
    wav = asyncio.run(mic.stop())
    if not wav:
        raise SystemExit("nothing was captured")
    path.write_bytes(wav)
    with wave.open(str(path), "rb") as clip:
        seconds = clip.getnframes() / clip.getframerate()
    print(f"wrote {path} ({seconds:.2f} s). Play it back once before using it.")
    return path


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                          text=True, check=True).stdout.strip()


def summarise(lines: list[tuple[int, str]]) -> dict:
    """The child's output, stamped on the driver's clock, as one run's measurements.
    Driver-clock stages are relative to the F9 release line; `timing` is the app's
    own clock (ms since the release). The transcript's TEXT never leaves here."""
    release = next((at for at, text in lines if "[probe] F9 released" in text), None)
    since = (lambda at: at - release) if release is not None else (lambda at: None)

    def first(*markers):
        return next((since(at) for at, text in lines if any(m in text for m in markers)), None)

    timing = {m.group(1): int(m.group(2)) for _, text in lines for m in [TIMING.search(text)] if m}
    passes = [m.group(1).split(",") for _, text in lines for m in [TOOLS.search(text)] if m]
    gap = (timing["first_audio"] - timing["first_token"]
           if {"first_audio", "first_token"} <= timing.keys() else None)
    return {
        "release_at_driver_ms": release,
        "stages_driver_ms_since_release": {
            "transcript": first("[STT] transcript", "[STT] Scribe OK", "empty transcript"),
            "pass_ends": [since(at) for at, text in lines if "[budget] recorded" in text],
            "end": first("[main] turn ended")},
        "timing_ms_since_release": timing,
        "gap_first_token_to_first_audio_ms": gap,
        "tools_per_pass": [[] if tools == ["-"] else tools for tools in passes],
        "searches": sum(tools.count("web__search") for tools in passes),
        "flags": sorted(name for name, markers in FLAGS.items()
                        if any(m in text for _, text in lines for m in markers)),
        "config_lines": [text for _, text in lines if "[cloud] reasoner=" in text or "[search] provider=" in text],
        "kept_lines": [[at, text] for at, text in lines
                       if NEVER_KEPT not in text and any(m in text for m in KEEP)],
    }


def run_once(clip: pathlib.Path, label: str = "", *, scenario: str = "", rep: int = 0,
             results_dir: pathlib.Path | None = None) -> dict:
    """ONE child process, ONE fresh app, ONE turn — so every run starts from a clean
    session: taint, the confirm gate and the documents live in that process only."""
    clip = _outside_repo(clip)
    data = clip.read_bytes()
    with wave.open(str(clip), "rb") as wav:
        clip_seconds = wav.getnframes() / wav.getframerate()
    env = dict(os.environ, MUTHIS_DEBUG="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1",
               PYTHONPATH=os.pathsep.join(filter(None, [str(REPO / "src"), os.environ.get("PYTHONPATH")])))
    before = prodlog.snapshot()
    launched = time.monotonic()
    child = subprocess.Popen([sys.executable, "-m", "muthis.voice_probe", str(clip)], cwd=REPO,
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace")
    lines = []
    for line in child.stdout:
        lines.append((round((time.monotonic() - launched) * 1000), line.rstrip("\n")))
        print(f"{lines[-1][0]:>7} ms | {lines[-1][1]}")
    code = child.wait()
    findings = prodlog.changes(before, prodlog.snapshot())
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = {
        "schema": SCHEMA, "created_utc": stamp, "label": label, "scenario": scenario, "rep": rep,
        "git_head": _git("rev-parse", "HEAD"), "git_dirty": bool(_git("status", "--porcelain")),
        "clip": {"name": clip.name, "sha256": hashlib.sha256(data).hexdigest(),
                 "seconds": round(clip_seconds, 3)},
        "exit_code": code,
        "durable_log": {"changes": findings,
                        "attach_line_seen": any(ATTACHED in text for _, text in lines)},
        **summarise(lines),
    }
    results = results_dir or CLIP_HOME / "results"
    results.mkdir(parents=True, exist_ok=True)
    name = f"{scenario}-{rep}" if scenario else clip.stem
    out = _outside_repo(results / f"{name}-{stamp}.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    result["record_path"] = str(out)
    return result


def log_clean(result: dict) -> bool:
    return not result["durable_log"]["changes"] and not result["durable_log"]["attach_line_seen"]


def run(clip: pathlib.Path, label: str) -> int:
    result = run_once(clip, label)
    clean = log_clean(result)
    print(f"\nexit={result['exit_code']} timing={result['timing_ms_since_release']} "
          f"flags={result['flags']} durable_log={'UNCHANGED' if clean else 'CHANGED'}")
    print(f"record: {result['record_path']}")
    return result["exit_code"] if clean else 4


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "record":
        record(argv[1])
        return 0
    if len(argv) >= 2 and argv[0] == "silent":
        write_silent(argv[1], float(argv[2]) if len(argv) > 2 else 0.2)
        return 0
    if len(argv) >= 2 and argv[0] == "run":
        return run(pathlib.Path(argv[1]), argv[2] if len(argv) > 2 else "")
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
