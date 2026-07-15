#!/usr/bin/env python3
# scripts/generate_earcons.py
"""
generate_earcons.py — synthesize the two bundled UI earcons (DEV/ASSET step).

Produces assets/earcons/listening.wav and processing.wav: premium, soft, modern
chimes (Apple/Windows-like), NOT clicks or beeps. Every tone rides ONE unified
envelope — gentle raised-cosine ATTACK, long exponential DECAY, then a final
raised-cosine RELEASE that forces the tail to TRUE zero — so there is no
onset click and, crucially, no end-of-buffer discontinuity (the old bug: an
exponential decay truncated at ~10% amplitude popped at the cut). Layered with a
soft 2nd harmonic (octave) for warmth, low peak amplitude (well under clipping).

  * listening  — a bright RISING perfect fifth (C5 → G5): two notes that OVERLAP
    (the fifth enters while the root still rings) so it reads as one connected
    "ready" gesture, not two blips.
  * processing — a single warm low chime (G4) with a long mellow decay and a
    subtle second strike (echo): a calm "working on it" feel.

This is a DEV-ONLY dependency on numpy (asset generation). The RUNTIME plays the
resulting WAVs with winsound only — numpy is never imported at runtime.

Run:  python scripts/generate_earcons.py
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100
OUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "earcons"

# Equal-tempered frequencies (Hz). C5→G5 is a bright "ready" perfect fifth.
C5, G5, G4 = 523.25, 783.99, 392.00

# Envelope timing (seconds). The 20 ms attack kills the onset click; the 40 ms
# release is the load-bearing fix — it fades whatever the exponential tail still
# is (a few %) down to a TRUE zero last sample, so no end-of-buffer pop.
ATTACK_S = 0.020
RELEASE_S = 0.040
# Peak amplitude after normalization — well under full scale, zero clipping room.
PEAK_AMP = 0.28


def _adsr_note(
    freq: float,
    length_s: float,
    *,
    tau_s: float,
    harmonic2: float = 0.20,
    attack_s: float = ATTACK_S,
) -> np.ndarray:
    """A single note: fundamental + a soft octave (2f) for warmth, shaped by a
    raised-cosine ATTACK then an exponential DECAY. The final release-to-zero is
    applied ONCE to the whole mixed buffer (see `_release`), not per note, so
    overlapping notes never each cut to silence mid-chord."""
    n = int(SAMPLE_RATE * length_s)
    t = np.arange(n) / SAMPLE_RATE
    wave_ = np.sin(2 * np.pi * freq * t) + harmonic2 * np.sin(2 * np.pi * (2 * freq) * t)
    wave_ /= 1.0 + harmonic2
    env = np.exp(-t / tau_s)                      # slow exponential ring-out
    a = min(int(SAMPLE_RATE * attack_s), n)
    if a > 0:                                     # raised-cosine fade-in (0→1)
        env[:a] *= 0.5 * (1 - np.cos(np.linspace(0, np.pi, a)))
    return wave_ * env


def _mix(components: list[tuple[np.ndarray, float]], total_s: float) -> np.ndarray:
    """Sum notes into one buffer at their start offsets (seconds), so a later
    note enters while earlier ones still ring (the overlap that makes a chime
    feel connected instead of like separate beeps)."""
    buf = np.zeros(int(SAMPLE_RATE * total_s))
    for samples, start_s in components:
        i = int(SAMPLE_RATE * start_s)
        end = min(i + len(samples), len(buf))
        buf[i:end] += samples[: end - i]
    return buf


def _normalize(buf: np.ndarray, peak: float = PEAK_AMP) -> np.ndarray:
    """Scale so the loudest sample sits at `peak` (constant perceived level,
    guaranteed headroom below clipping)."""
    return buf * (peak / max(float(np.abs(buf).max()), 1e-9))


def _release(buf: np.ndarray, release_s: float = RELEASE_S) -> np.ndarray:
    """The click-free guarantee: multiply the LAST `release_s` by a raised-cosine
    ramp 1→0 so the final sample is EXACTLY zero — no discontinuity at the cut,
    whatever the exponential tail had reached."""
    r = min(int(SAMPLE_RATE * release_s), len(buf))
    if r > 0:
        ramp = 0.5 * (1 - np.cos(np.linspace(0, np.pi, r)))   # 0→1
        buf[-r:] *= ramp[::-1]                                 # 1→0, last sample = 0
    return buf


def _build_listening() -> np.ndarray:
    """Rising perfect fifth C5 → G5 (~0.65 s). The fifth enters at 0.15 s while
    the root still rings, so the two notes overlap into one bright gesture."""
    total = 0.65
    root = _adsr_note(C5, total, tau_s=0.18, harmonic2=0.22)
    fifth = _adsr_note(G5, total - 0.15, tau_s=0.18, harmonic2=0.22)
    return _release(_normalize(_mix([(root, 0.0), (fifth, 0.15)], total)))


def _build_processing() -> np.ndarray:
    """A single warm low G4 chime (~0.78 s) with a long mellow decay, plus a
    subtle second strike at 0.18 s for a calm, breathing 'working' feel."""
    total = 0.78
    strike = _adsr_note(G4, total, tau_s=0.25, harmonic2=0.20)
    echo = 0.32 * _adsr_note(G4, total - 0.18, tau_s=0.22, harmonic2=0.20)
    return _release(_normalize(_mix([(strike, 0.0), (echo, 0.18)], total)))


def _write_wav(path: Path, samples: np.ndarray) -> None:
    """Write float [-1, 1] samples as 16-bit PCM mono WAV."""
    pcm = np.clip(samples, -1.0, 1.0)
    pcm16 = (pcm * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm16.tobytes())
    print(f"wrote {path}  ({len(pcm16)} samples, {len(pcm16) / SAMPLE_RATE:.3f}s)")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_wav(OUT_DIR / "listening.wav", _build_listening())
    _write_wav(OUT_DIR / "processing.wav", _build_processing())


if __name__ == "__main__":
    main()
