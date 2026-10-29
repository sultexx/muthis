"""
test_secret_scan.py — the pre-push secret scanner's POSITIVE CONTROL, run from the
tree (DEC-157's round).

WHY IT IS HERE. `scripts/secret_scan.py` is the standing scan run before every
push of a PUBLIC repository. It lived only in session scratch folders and was lost
with one; a scan whose tool can vanish is a procedure that can silently stop.
Committing it fixed the vanishing. This file fixes the other half: a clean scan is
worth exactly what its control is worth, so the control runs in the suite, where
it is proven on every run rather than remembered before a push.

WHAT IT PROVES. The control builds a scratch repository, plants one synthetic
value per detector in a file it then DELETES plus one in a commit message, and
requires the scanner's own pipeline to find all twelve — so a detector that
stopped matching, or a pipeline that stopped reading history, fails here. It also
proves the scanner never prints a value (only its length, entropy and booleans)
and that the scanner's own source holds no whole value, so a scan of this
repository can never report the tool that runs it.

WHAT IT DOES NOT PROVE. That this repository is clean. That is the `scan` run
itself, read by a person before a push; the suite never scans the real history.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import shutil

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCANNER = ROOT / "scripts" / "secret_scan.py"


def _scanner():
    spec = importlib.util.spec_from_file_location("secret_scan", SCANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scanner():
    assert shutil.which("git"), "the scanner drives git; the control cannot run without it"
    return _scanner()


@pytest.fixture(scope="module")
def control_run(scanner, tmp_path_factory):
    """The control builds a repository, so it runs ONCE and every assertion below
    reads the same run's stdout."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        scanner.control(tmp_path_factory.mktemp("secret_scan_control"))
    return buffer.getvalue()


def test_the_control_finds_every_planted_value(scanner, control_run):
    planted = len(scanner.planted_values())
    assert planted == len(scanner.DETECTORS) == 12, "one plant per detector, twelve detectors"
    assert f"planted={planted} found={planted} missing=[]" in control_run
    assert "found_in_commit_message=True" in control_run
    assert "planted_file_absent_from_HEAD=True" in control_run
    assert "secret_path_found=True" in control_run
    assert control_run.rstrip().endswith("CONTROL PASSED")


def test_the_control_never_prints_a_planted_value(scanner, control_run):
    for name, value in scanner.planted_values().items():
        assert value.decode() not in control_run, f"the control printed the {name} value"


def test_the_scanner_source_holds_no_whole_value(scanner):
    """Every plant is assembled at runtime. A literal plant in this file would make
    each real scan report the scanner itself — a standing false finding that
    teaches the reader to skip the one line that matters."""
    source = SCANNER.read_bytes()
    hits = sorted(name for name, rx in scanner.COMPILED.items() if rx.search(source))
    assert not hits, f"the scanner's source matches its own detectors: {hits}"


def test_the_source_check_above_can_fire(scanner):
    """The check above is only worth something if a whole value WOULD match: the
    assembled plants, joined into one text, are found by every detector."""
    text = b"\n".join(scanner.planted_values().values())
    missed = sorted(name for name, rx in scanner.COMPILED.items() if not rx.search(text))
    assert not missed, f"detectors that do not fire on their own plant: {missed}"
