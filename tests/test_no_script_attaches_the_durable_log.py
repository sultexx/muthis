"""
test_no_script_attaches_the_durable_log.py — DEC-154: the durable log is the
record of APP sessions, and no script may write into it.

THE HAZARD THIS CLOSES. `configure_logging()` attaches ~/.muthis/logs/muthis.log
(DEC-122) unless MUTHIS_DEBUG=1 refuses it. Two diagnostic scripts called it for
its DEC-28 posture, and both were written BEFORE DEC-122 made that call attach a
file: a shared function's behaviour changed under its callers, and nothing
reddened. Running either afterwards would have appended a diagnostic session to
the record that DEC-153's counts, and every live verification since DEC-122,
read as app sessions.

THE SEAM, AND WHY IT IS NOT THE SHARED FUNCTION. The scripts take the console
posture — `logging.basicConfig` plus `silence_third_party_http_logs()`, which is
`configure_logging()` minus the file. `logging_policy.py` and `main.py` are not
touched, so the application's own start cannot change: `test_logging_privacy.py`
still proves `main.py` applies the policy, and `test_durable_log.py` that the
policy attaches the file.

THE GUARD, AND WHAT MAKES IT A CHECK. Every script under `scripts/` — the
behaviour harness included — is parsed. An import or a call of
`configure_logging` or `attach_file_log`, any import of `muthis.main` (whose
`main()` applies the policy), and any file-handler construction are violations.
An alias import is caught at the import, so renaming the function cannot slip it
past the call check. The scanner is first shown to FIRE on every forbidden form:
a scan that found nothing is indistinguishable from a broken scan.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FORBIDDEN_NAMES = frozenset({"configure_logging", "attach_file_log"})
FILE_HANDLERS = frozenset({"FileHandler", "RotatingFileHandler",
                           "TimedRotatingFileHandler", "WatchedFileHandler"})
THE_TWO = ("diag_web_research.py", "diag_doc_rag.py")


def _is_main_module(name: str) -> bool:
    return name == "muthis.main" or name.startswith("muthis.main.")


def violations(source: str) -> "list[str]":
    """Every way a script could reach the durable log, as readable strings."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _is_main_module(module):
                found.append("imports from muthis.main")
            for alias in node.names:
                if alias.name in FORBIDDEN_NAMES:
                    found.append(f"imports {alias.name}")
                if module == "muthis" and alias.name == "main":
                    found.append("imports muthis.main")
        elif isinstance(node, ast.Import):
            found.extend("imports muthis.main" for alias in node.names
                         if _is_main_module(alias.name))
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in FORBIDDEN_NAMES:
                found.append(f"calls {name}")
            if name in FILE_HANDLERS:
                found.append(f"builds a {name}")
    return found


def _scripts() -> "list[pathlib.Path]":
    return sorted(p for p in SCRIPTS.rglob("*.py") if "__pycache__" not in p.parts)


def _called(path: pathlib.Path) -> "set[str]":
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.func.attr if isinstance(node.func, ast.Attribute)
            else getattr(node.func, "id", "")
            for node in ast.walk(tree) if isinstance(node, ast.Call)}


def test_the_scan_is_looking_at_the_scripts():
    """THE POSITIVE CONTROL on coverage: a glob that matched nothing would pass
    every parametrised case below while examining nothing."""
    names = {p.name for p in _scripts()}
    assert len(names) > 20, f"only {len(names)} scripts found under {SCRIPTS}"
    assert set(THE_TWO) <= names, "the two scripts DEC-154 names are not in the scan"


@pytest.mark.parametrize("snippet,expected", [
    ("from muthis.logging_policy import configure_logging\nconfigure_logging()\n",
     "calls configure_logging"),
    ("from muthis.logging_policy import configure_logging as setup\nsetup()\n",
     "imports configure_logging"),
    ("import muthis.logging_policy as lp\nlp.attach_file_log()\n", "calls attach_file_log"),
    ("from muthis.main import main\nmain()\n", "imports from muthis.main"),
    ("from muthis import main\n", "imports muthis.main"),
    ("import muthis.main\n", "imports muthis.main"),
    ("import logging\nlogging.FileHandler('x.log')\n", "builds a FileHandler"),
    ("from logging.handlers import RotatingFileHandler\nRotatingFileHandler('x')\n",
     "builds a RotatingFileHandler"),
])
def test_the_scanner_FIRES_on_every_forbidden_form(snippet, expected):
    assert expected in violations(snippet)


def test_the_scanner_is_SILENT_on_the_console_posture():
    """THE NEGATIVE CONTROL: the replacement itself must not be flagged."""
    posture = ("import logging\n"
               "from muthis.logging_policy import LOG_FORMAT, silence_third_party_http_logs\n"
               "logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)\n"
               "silence_third_party_http_logs()\n")
    assert violations(posture) == []


@pytest.mark.parametrize("script", _scripts(),
                         ids=lambda p: p.relative_to(SCRIPTS).as_posix())
def test_no_script_can_attach_the_durable_log(script):
    assert violations(script.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("name", THE_TWO)
def test_the_two_diagnostic_scripts_keep_the_DEC_28_posture(name):
    """Dropping the file must not drop the URL-leak control: both scripts still
    configure the console and still silence the third-party HTTP loggers."""
    called = _called(SCRIPTS / name)
    assert "basicConfig" in called, f"{name} no longer configures the console"
    assert "silence_third_party_http_logs" in called, (
        f"{name} lost the DEC-28 silencing — httpx would log full URLs again")
