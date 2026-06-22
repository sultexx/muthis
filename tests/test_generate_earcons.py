"""
test_generate_earcons.py — the earcon SYNTHESIS (numeric, no audio device).

These pin the premium click-free design of scripts/generate_earcons.py (a
DEV/asset script, so it is loaded by path — it is not an importable package):

  * the cues are PREMIUM length (~0.5–0.9 s), not the old ~0.24/0.28 s beeps,
  * every cue starts AND ends at TRUE zero — a raised-cosine attack (no onset
    click) and a final release ramp (no end-of-buffer pop, the old bug where an
    exponential decay was truncated at ~10% amplitude and clicked),
  * low peak amplitude with clipping headroom (~0.28, well under full scale),
  * and main() writes 16-bit / mono / 44.1 kHz WAVs whose tail is click-free in
    the actual FILE bytes.

numpy is a DEV/asset dependency (the runtime plays the WAVs with winsound), so
the whole module skips cleanly if numpy is unavailable.

Run:  set PYTHONPATH=src && python -m pytest tests/test_generate_earcons.py -q
"""

from __future__ import annotations

import importlib.util
import wave
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

_GEN_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_earcons.py"


def _load_generator():
    """Load the by-path DEV script as a throwaway module (not on sys.path)."""
    spec = importlib.util.spec_from_file_location("generate_earcons", _GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _both_earcons(gen):
    return {"listening": gen._build_listening(), "processing": gen._build_processing()}


def test_earcons_are_premium_length_not_short_beeps():
    gen = _load_generator()
    assert gen.SAMPLE_RATE == 44100
    durations = {n: len(a) / gen.SAMPLE_RATE for n, a in _both_earcons(gen).items()}
    # Premium length — far past the old ~0.24/0.28 s beeps, but still snappy.
    assert 0.5 <= durations["listening"] <= 0.9
    assert 0.5 <= durations["processing"] <= 1.0
    # processing is the longer, mellower "working" chime.
    assert durations["processing"] > durations["listening"]


def test_envelope_starts_and_ends_at_true_zero_no_click():
    gen = _load_generator()
    sr = gen.SAMPLE_RATE
    for name, arr in _both_earcons(gen).items():
        # Onset is zero (raised-cosine attack) → no onset click.
        assert abs(float(arr[0])) < 1e-9, f"{name} onset is not zero"
        # The LAST sample is exactly zero (release ramp) → no end-of-buffer pop.
        assert abs(float(arr[-1])) < 1e-9, f"{name} tail is not zero"
        # The whole final 5 ms is near-silent (well under the ~0.28 peak), proving
        # the buffer isn't cut mid-swing like the old ~10% exponential tail.
        tail = float(np.abs(arr[-int(sr * 0.005):]).max())
        assert tail < 0.05, f"{name} tail is not click-free (max|last 5ms|={tail:.4f})"


def test_peak_amplitude_has_clipping_headroom():
    gen = _load_generator()
    for name, arr in _both_earcons(gen).items():
        peak = float(np.abs(arr).max())
        assert 0.05 < peak <= 0.30, f"{name} peak {peak:.3f} out of premium range"


def test_main_writes_clickfree_16bit_mono_wavs(tmp_path, monkeypatch):
    gen = _load_generator()
    monkeypatch.setattr(gen, "OUT_DIR", tmp_path)
    gen.main()
    for name in ("listening", "processing"):
        path = tmp_path / f"{name}.wav"
        assert path.exists(), f"{name}.wav not written"
        with wave.open(str(path), "rb") as wf:
            assert wf.getnchannels() == 1           # mono
            assert wf.getsampwidth() == 2           # 16-bit
            assert wf.getframerate() == 44100
            n = wf.getnframes()
            pcm = np.frombuffer(wf.readframes(n), dtype="<i2")
        assert n / 44100 >= 0.5                      # premium length in the file
        assert int(pcm[-1]) == 0                     # click-free tail in the FILE bytes
        assert int(np.abs(pcm[-int(44100 * 0.005):]).max()) < int(0.05 * 32767)
