# src/muthis/voice_probe.py
"""
voice_probe.py — the voice instrument's entry (DEC-157 ⑤). NOT part of the app.

ONE JOB: run ONE turn of the BUILT app from a recorded clip, so the time from F9
release to the first spoken word is measured on the real pipeline. Run only as a
CHILD of `scripts/voice_drive.py`, from the repository root, under MUTHIS_DEBUG=1:

    python -m muthis.voice_probe <clip.wav>

WHAT IS REAL: everything `main.build()` assembles — STT, screen capture, the
reasoner, the router, the voice, the overlay, and the budget ledger in the working
directory (Sultan's choice ⑥: test spend lands in the real ledger). WHAT IS NOT:
the microphone's DEVICE, replaced by the clip through `Mic`'s own `stream_factory`
(build's ONLY seam, choice ①), and the KEYBOARD: F9 goes through the BUILT
controller (choice ②) — `on_press` on a worker thread, as the keyboard thread
calls it, and `on_activate` through `call_soon_threadsafe`, as the listener
schedules it. Never a synthetic keystroke. The listener is built and never
started; MCP servers are never mounted (none is offered to the model).

NEVER REACHABLE FROM NORMAL OPERATION (choice ③). Guards G1–G5, each first shown
to fire, are in `tests/test_voice_probe_isolation.py`: nothing reachable from
`muthis.main` imports this module (G1); no other module passes `build()` an
argument (G2); the default mic is the real device (G3); this module's logging
posture passes the scripts guard's own scan, `build`/`close` being the only names
it takes from `muthis.main` (G4); it refuses to start without MUTHIS_DEBUG=1 (G5).

THE DURABLE LOG, REFUSED TWICE (choice ④): this module never calls
`configure_logging` — it takes the scripts' console posture — and it runs only
under MUTHIS_DEBUG=1, where `attach_file_log` returns before building a handler.
It also refuses while any logger holds a file handler, outside the repository
root (the ledger), on a clip inside the repository (clips are never committed,
choice ⑦), and while the real app runs. The driver compares the log directory
byte for byte before and after.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import wave
from typing import Callable, Iterable, Optional

from . import turn_timing
from .logging_policy import LOG_FORMAT, debug_content_enabled, silence_third_party_http_logs
from .mic import CHANNELS, SAMPLE_RATE, Mic

logger = logging.getLogger("muthis.voice_probe")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BLOCK_FRAMES = 1024                    # one PortAudio-sized callback block (64 ms)
TURN_TIMEOUT_S = 150.0                 # the orchestrator's 90 s session bound, plus room
REFUSED = 2

# The real app is `python -m muthis.main` (README) or `src/muthis/main.py` run directly.
APP_COMMAND = re.compile(r"muthis(?:\.main\b|[\\/]main\.py\b)")
_LISTING_PS = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
               "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")


# ─── The clip, standing in for the device ─────────────────────────────────────

class ClipStream:
    """The object `Mic` expects from a stream factory: start/stop/close. Delivers
    the clip's PCM to the callback in device-sized blocks, PACED in real time (a
    held key lasts as long as the clip), then stops — `delivered` is the hold."""

    def __init__(self, pcm: bytes, callback: Callable[..., None], pace: float = 1.0) -> None:
        self._pcm, self._callback, self._pace = pcm, callback, pace
        self._stop = threading.Event()
        self.delivered = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="voice-probe-clip", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        step = BLOCK_FRAMES * 2 * CHANNELS
        began = time.monotonic()
        for index, offset in enumerate(range(0, len(self._pcm), step)):
            due = began + index * BLOCK_FRAMES / SAMPLE_RATE * self._pace
            while not self._stop.is_set() and time.monotonic() < due:
                time.sleep(0.002)
            if self._stop.is_set():
                break
            block = self._pcm[offset:offset + step]
            self._callback(block, len(block) // (2 * CHANNELS), None, None)
        self.delivered.set()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def close(self) -> None:
        pass


class ClipStreamFactory:
    """`Mic(stream_factory=...)`: one ClipStream per hold, the last one kept."""

    def __init__(self, pcm: bytes, pace: float = 1.0) -> None:
        self._pcm, self._pace = pcm, pace
        self.last: Optional[ClipStream] = None

    def __call__(self, callback: Callable[..., None]) -> ClipStream:
        self.last = ClipStream(self._pcm, callback, self._pace)
        return self.last


def read_clip(path: pathlib.Path) -> bytes:
    """The clip's PCM — 16 kHz mono 16-bit, the format `Mic` produces. Anything
    else is refused by `clip_refusal`, never resampled."""
    with wave.open(str(path), "rb") as clip:
        return clip.readframes(clip.getnframes())


def clip_refusal(path: pathlib.Path) -> Optional[str]:
    resolved = path.resolve()
    if resolved.is_relative_to(REPO_ROOT):
        return "the clip is inside the repository — clips stay local and are never committed"
    if not resolved.is_file():
        return f"no clip at {resolved}"
    try:
        with wave.open(str(resolved), "rb") as clip:
            shape = (clip.getframerate(), clip.getnchannels(), clip.getsampwidth())
    except (wave.Error, EOFError) as exc:
        return f"the clip is not a readable WAV ({exc})"
    if shape != (SAMPLE_RATE, CHANNELS, 2):
        return f"the clip is {shape[0]} Hz x{shape[1]} {shape[2] * 8}-bit; the mic's format is 16000 Hz mono 16-bit"
    return None


# ─── The refusals, as one pure function ───────────────────────────────────────

def process_listing() -> Optional[list[tuple[int, str]]]:
    """(pid, command line) of every python process, or None if it could not be
    read — which REFUSES the run (fail closed: unverified is not 'not running')."""
    script = base64.b64encode(_LISTING_PS.encode("utf-16-le")).decode("ascii")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", script],
                             capture_output=True, text=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    rows = []
    for line in out.splitlines():
        pid, _, command = line.partition("\t")
        if pid.strip().isdigit():
            rows.append((int(pid), command.strip()))
    return rows


def real_app_pids(listing: Iterable[tuple[int, str]], own: Iterable[int]) -> list[int]:
    own = set(own)
    return sorted(pid for pid, command in listing
                  if pid not in own and command and APP_COMMAND.search(command))


def file_handlers() -> list[str]:
    """Every logger holding a file handler — the durable log's one shape."""
    loggers = [logging.getLogger()] + [item for item in logging.Logger.manager.loggerDict.values()
                                       if isinstance(item, logging.Logger)]
    return sorted({lg.name for lg in loggers for handler in lg.handlers
                   if isinstance(handler, logging.FileHandler)})


def refusals(*, debug: bool, clip: pathlib.Path, cwd: pathlib.Path,
             listing: Optional[list[tuple[int, str]]], own_pids: Iterable[int],
             handlers: list[str]) -> list[str]:
    reasons = []
    if not debug:
        reasons.append("MUTHIS_DEBUG=1 is required: it is what refuses the durable log")
    problem = clip_refusal(clip)
    if problem:
        reasons.append(problem)
    if cwd.resolve() != REPO_ROOT:
        reasons.append(f"run from {REPO_ROOT}: the budget ledger is the working directory's")
    if listing is None:
        reasons.append("cannot list processes, so cannot verify the real app is not running")
    else:
        running = real_app_pids(listing, own_pids)
        if running:
            reasons.append(f"the real app is running (pid {', '.join(map(str, running))}) — close it first")
    if handlers:
        reasons.append(f"a file handler is attached ({', '.join(handlers)}) — the durable log must not be")
    return reasons


# ─── The one turn ─────────────────────────────────────────────────────────────

async def _wait_for(predicate: Callable[[], bool], timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


async def drive(pcm: bytes) -> int:
    """Build the real app with the clip as its microphone, hold F9 for the clip
    through the built controller, release it, and wait for the turn to end."""
    from muthis.main import build, close    # lazy: importing this module loads nothing of the app

    if file_handlers():                     # the app's own import must not have attached one
        print("voice_probe: REFUSED — a file handler appeared on import", file=sys.stderr)
        return REFUSED
    factory = ClipStreamFactory(pcm)
    app = await build(mic=Mic(stream_factory=factory))
    controller, loop = app.controller, asyncio.get_running_loop()
    seconds = len(pcm) / (SAMPLE_RATE * 2 * CHANNELS)

    def hold() -> None:                     # the keyboard thread's part, F9 down → up
        controller.on_press()
        if factory.last is not None:
            factory.last.delivered.wait(timeout=seconds + 5.0)
        turn_timing.turn_started()          # the clock starts at the release
        logger.info("[probe] F9 released after %.2f s — scheduling the turn", seconds)
        loop.call_soon_threadsafe(controller.on_activate)

    try:
        logger.info("[probe] built — pressing F9 through the built controller")
        await asyncio.to_thread(hold)
        started = await _wait_for(lambda: controller.is_processing, 5.0)
        ended = started and await _wait_for(lambda: not controller.is_processing, TURN_TIMEOUT_S)
        logger.info("[probe] turn %s", "ended" if ended else "DID NOT END")
        return 0 if ended else 3
    finally:
        turn_timing.reset()
        await close(app)


def main(argv: Optional[list[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m muthis.voice_probe <clip.wav>", file=sys.stderr)
        return REFUSED
    clip = pathlib.Path(args[0])
    reasons = refusals(debug=debug_content_enabled(), clip=clip, cwd=pathlib.Path.cwd(),
                       listing=process_listing(), own_pids={os.getpid(), os.getppid()},
                       handlers=file_handlers())
    if reasons:
        for reason in reasons:
            print(f"voice_probe: REFUSED — {reason}", file=sys.stderr)
        return REFUSED
    # The scripts' console posture — `configure_logging()` minus the file. Never
    # the policy call itself: that is the one that attaches the durable log.
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    silence_third_party_http_logs()
    return asyncio.run(drive(read_clip(clip)))


__all__ = ["ClipStream", "ClipStreamFactory", "clip_refusal", "drive", "file_handlers",
           "main", "process_listing", "read_clip", "real_app_pids", "refusals"]


if __name__ == "__main__":
    sys.exit(main())
