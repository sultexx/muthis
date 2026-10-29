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

THE RECORD IS SAVED COMPARABLY (DEC-157 ②): one JSON per run, a fixed schema —
git HEAD and whether the tree was dirty, the clip's sha256 and length, the three
`[timing]` lines, and only the lines on an allow-list (timing, probe, pass, budget,
mic, vision, voice). Never the transcript: under debug the child prints it, the
console shows it, and the record does not keep it.

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
SCHEMA = "voice-run/1"
KEEP = ("[timing]", "[probe]", "[pass]", "[budget]", "[mic]", "[vision]",
        "[orchestrator] tts", "voice_probe: REFUSED", "[main] turn")
TIMING = re.compile(r"\[timing\] (\w+) \+(\d+) ms")
ATTACHED = "durable log attached"


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


def run(clip: pathlib.Path, label: str) -> int:
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
    kept, attached, release_ms = [], False, None
    for line in child.stdout:
        at_ms = round((time.monotonic() - launched) * 1000)
        line = line.rstrip("\n")
        print(f"{at_ms:>7} ms | {line}")
        attached = attached or ATTACHED in line
        if "[probe] F9 released" in line:
            release_ms = at_ms
        if any(marker in line for marker in KEEP):
            kept.append([at_ms, line])
    code = child.wait()
    findings = prodlog.changes(before, prodlog.snapshot())
    timing = {m.group(1): int(m.group(2)) for _, text in kept for m in [TIMING.search(text)] if m}
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = {
        "schema": SCHEMA, "created_utc": stamp, "label": label,
        "git_head": _git("rev-parse", "HEAD"), "git_dirty": bool(_git("status", "--porcelain")),
        "clip": {"name": clip.name, "sha256": hashlib.sha256(data).hexdigest(),
                 "seconds": round(clip_seconds, 3)},
        "exit_code": code, "timing_ms_since_release": timing,
        "release_at_driver_ms": release_ms,
        "durable_log": {"changes": findings, "attach_line_seen": attached},
        "kept_lines": kept,
    }
    results = CLIP_HOME / "results"
    results.mkdir(parents=True, exist_ok=True)
    out = _outside_repo(results / f"{clip.stem}-{stamp}.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    clean = not findings and not attached
    print(f"\nexit={code} timing={timing} durable_log={'UNCHANGED' if clean else 'CHANGED: ' + str(findings)}")
    print(f"record: {out}")
    return code if clean else 4


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
