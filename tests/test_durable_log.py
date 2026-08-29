# tests/test_durable_log.py
"""The DURABLE LOG and the one combination it refuses.

WHY THE REFUSAL IS THE SUBJECT OF THIS FILE. Until now Mut'his logs died with
the terminal, so DEC-61's PERMANENCE criterion held BY ACCIDENT. A file handler
re-classifies 248 existing call sites at once, and MUTHIS_DEBUG=1 unseals the
two most sensitive surfaces in the project — the STT transcript and the code
submitted to the sandbox. Debug content and a durable log must therefore never
coexist.

THE PROPERTY IS "UNREPRESENTABLE", NOT "REJECTED", AND BOTH HALVES ARE ASSERTED:
the refusal returns before anything is built (so no handler exists to leak), AND
the tree contains exactly ONE place that can build one (so there is no second
path around the guard). The second half is what makes this checkable in one
place rather than across 248 sites — without it, "the guard works" is a claim
about one function while another module quietly opens its own file.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from muthis.logging_policy import (
    DEBUG_ENV, LOG_BACKUPS, LOG_DIR, LOG_FILENAME, LOG_MAX_BYTES,
    attach_file_log, configure_logging, debug_content_enabled,
)

SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture(autouse=True)
def _restore_root_handlers():
    """Adding a handler to the ROOT logger outlives the test that added it —
    every assertion here would then be read against a polluted root.

    THE ROOT LEVEL IS SET AND RESTORED TOO, and the reason is a real difference
    between production and pytest: `configure_logging` normally raises the root
    to INFO through `basicConfig`, but `basicConfig` does NOTHING when the root
    already has handlers — and pytest's logging plugin installs one before any
    test runs. Left alone the root sits at WARNING here, every INFO record is
    dropped before it can reach a handler, and "the log file is empty" would
    read as a defect in the policy instead of an artefact of the harness."""
    root = logging.getLogger()
    before = list(root.handlers)
    before_level = root.level
    root.setLevel(logging.INFO)
    yield
    for handler in list(root.handlers):
        if handler not in before:
            handler.close()
            root.removeHandler(handler)
    root.setLevel(before_level)


def _file_handlers():
    """OUR handlers only. pytest's own logging plugin keeps a `_FileHandler` on
    the root aimed at the null device, so a bare `isinstance(h, FileHandler)`
    reports a handler this code never attached — and every assertion below would
    then be read against pytest's plumbing rather than the policy."""
    return [h for h in logging.getLogger().handlers
            if isinstance(h, RotatingFileHandler)]


# ───────────────── the refusal — the ruling this file guards ────────────────

def test_MUTHIS_DEBUG_refuses_the_durable_log(tmp_path):
    """The pair that must not exist: unsealed content AND a permanent file."""
    assert attach_file_log(debug=True, directory=tmp_path) is None
    assert _file_handlers() == [], "a file handler was attached under MUTHIS_DEBUG"
    assert list(tmp_path.iterdir()) == [], "a log file was created under MUTHIS_DEBUG"


def test_the_refusal_reads_the_REAL_environment(monkeypatch, tmp_path):
    """The production read, not just the injected seam — a guard wired only to
    the test parameter would pass while the shipped path attaches anyway."""
    monkeypatch.setenv(DEBUG_ENV, "1")
    assert debug_content_enabled() is True
    assert attach_file_log(directory=tmp_path) is None
    assert _file_handlers() == []


def test_configure_logging_carries_the_refusal_too(monkeypatch, tmp_path):
    """The composition root's ONE call is the path production actually takes."""
    monkeypatch.setenv(DEBUG_ENV, "1")
    assert configure_logging(directory=tmp_path) is None
    assert _file_handlers() == []


# ─── the POSITIVE control — without it every assertion above is vacuous ─────

def test_without_the_flag_the_log_IS_attached_and_written(monkeypatch, tmp_path):
    """The control that fails on a function which never attaches anything. A
    refusal test alone passes trivially against a no-op."""
    monkeypatch.delenv(DEBUG_ENV, raising=False)
    path = attach_file_log(directory=tmp_path)
    assert path is not None
    assert len(_file_handlers()) == 1
    logging.getLogger("muthis.test").info("a durable line")
    for handler in _file_handlers():
        handler.flush()
    assert path.exists()
    assert "a durable line" in path.read_text(encoding="utf-8")


def test_the_flag_set_to_anything_else_does_not_refuse(monkeypatch, tmp_path):
    """`stt.py` compares to "1" exactly; MUTHIS_DEBUG=0 is OFF, so the log
    attaches. Asserted so the two reads cannot drift apart silently."""
    monkeypatch.setenv(DEBUG_ENV, "0")
    assert attach_file_log(directory=tmp_path) is not None


# ────────────── unrepresentable: exactly ONE construction site ──────────────

def test_only_one_place_in_the_tree_can_build_a_file_handler():
    """The half that makes the guard a PROPERTY rather than a local check. If a
    second module opens its own file, the refusal above protects nothing."""
    sites = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in ("RotatingFileHandler(", "logging.FileHandler(",
                       "FileHandler("):
            if needle in text:
                sites.append(path.name)
                break
    assert sites, "the scan found nothing — it is broken, not the tree clean"
    assert sites == ["logging_policy.py"], (
        "a second file-handler construction site exists, so MUTHIS_DEBUG=1 can "
        f"coexist with a durable log through it: {sites}")


def test_the_console_survives_the_file_attachment(monkeypatch, tmp_path):
    """Order is load-bearing: `basicConfig` installs the console handler only
    when the root has NONE, so attaching the file FIRST silences the console for
    the whole run — the durable log would arrive by taking the live one away.

    ASSERTED BEHAVIOURALLY, AND THE FIRST VERSION OF THIS TEST WAS NOT. It
    compared source positions — `body.index("basicConfig") < body.index(
    "attach_file_log")` — and a mutation that genuinely reordered the two CALLS
    stayed GREEN, because the DOCSTRING names `basicConfig` above them both. The
    test was reading prose and reporting on mechanism. Driving the real
    configuration on an empty root is the only form that cannot be satisfied by
    a comment."""
    monkeypatch.delenv(DEBUG_ENV, raising=False)
    root = logging.getLogger()
    saved = list(root.handlers)
    for handler in saved:                     # basicConfig no-ops on a root that
        root.removeHandler(handler)           # already has handlers — pytest's
    try:
        assert configure_logging(directory=tmp_path) is not None
        assert any(type(h) is logging.StreamHandler for h in root.handlers), (
            "no console handler — the file was attached first, so basicConfig "
            "found the root already populated and installed nothing")
        assert len(_file_handlers()) == 1
    finally:
        for handler in list(root.handlers):
            if handler not in saved:
                handler.close()
                root.removeHandler(handler)
        for handler in saved:
            root.addHandler(handler)


# ───────────────────────── bounded, and fails soft ──────────────────────────

def test_rotation_is_bounded_as_ruled(monkeypatch, tmp_path):
    """The constants AND the handler actually built from them — a bound declared
    in a module and not passed to the handler bounds nothing."""
    monkeypatch.delenv(DEBUG_ENV, raising=False)
    assert LOG_MAX_BYTES == 2 * 1024 * 1024
    assert LOG_BACKUPS == 3
    assert attach_file_log(directory=tmp_path) is not None
    handler = _file_handlers()[0]
    assert handler.maxBytes == LOG_MAX_BYTES
    assert handler.backupCount == LOG_BACKUPS


def test_the_log_lives_outside_the_repository():
    """A log inside the tree is one `git add -A` from publication."""
    repo = Path(__file__).resolve().parents[1]
    assert repo not in LOG_DIR.parents and LOG_DIR != repo
    assert LOG_DIR.name == "logs" and LOG_DIR.parent.name == ".muthis"
    assert LOG_FILENAME == "muthis.log"


def test_an_unwritable_directory_degrades_to_console(monkeypatch, tmp_path):
    """A log that cannot be written must degrade the diagnosis, never the app."""
    monkeypatch.delenv(DEBUG_ENV, raising=False)
    blocked = tmp_path / "blocked"
    blocked.write_text("I am a file, not a directory", encoding="utf-8")
    assert attach_file_log(directory=blocked) is None      # did not raise
    assert _file_handlers() == []


# ───────── the privacy policy still governs what reaches the file ───────────

def test_the_http_silencing_reaches_the_file_too(monkeypatch, tmp_path):
    """The silencing is at LOGGER level, so it applies to every handler. A full
    request URL must be no more writable to disk than it was printable."""
    monkeypatch.delenv(DEBUG_ENV, raising=False)
    path = configure_logging(directory=tmp_path)
    assert path is not None
    logging.getLogger("httpx").info(
        "HTTP Request: GET https://example.com/?q=the+users+private+question")
    for handler in _file_handlers():
        handler.flush()
    assert "private+question" not in path.read_text(encoding="utf-8")
