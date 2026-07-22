# tests/test_stage_file_gate.py
"""Unit guard mirroring the live SOP's DETERMINISTIC gate check (DEC-12).

The sandbox stages model-provided files[] through `stage_file_gate` — so THIS
is the guard that protects an execution turn, and the live SOP's CHECK 3 now
exercises it directly instead of trusting the model to refuse. This locks the
gate's contract against regression in CI: secret-BEARING names are refused by
name with the blocked note and ZERO file content echoed back; ordinary text
files pass; binary content is refused as non-text.

The path-structure guard (DEC-13) is proven too: a staged name is BARE by
contract (schema §2.1), so any name with a path separator or a `..` traversal
reference is refused OUTRIGHT — closing `/work` escape at the root — while a
legal `..` inside a separator-free name (`archive..bak`) still passes. Enforce
the contract; do NOT over-reject.
"""

from __future__ import annotations

import pytest

from muthis.file_reader import (
    FILE_BLOCKED_AR,
    FILE_NAME_NOT_BARE_AR,
    FILE_NOT_TEXT_AR,
    stage_file_gate,
)

# A canary that must never appear in a returned note (privacy: no content leak).
SECRET_CONTENT = b"API_KEY=stage_gate_leak_canary_value"


@pytest.mark.parametrize("name", [
    ".env", ".ENV", ".env.local", ".env.production",       # exact + .env.* prefix
    "id_rsa", "id_rsa.pub", "id_ed25519", "id_ecdsa", "id_dsa",  # key material prefix
    "credentials", ".netrc", ".npmrc", ".pypirc", ".git-credentials",  # exact names
    "server.pem", "private.key", "cert.pfx", "bundle.p12",  # key-material suffix
    "trust.der", "vault.kdbx", "app.keystore",
])
def test_secret_named_files_are_refused_with_no_content_leak(name):
    note = stage_file_gate(name, SECRET_CONTENT)
    assert note == FILE_BLOCKED_AR                       # refused BY NAME
    assert "canary" not in note and "API_KEY" not in note  # zero content in the note


@pytest.mark.parametrize("name", ["main.py", "data.csv", "notes.txt", "query.sql", "app.js", "README.md"])
def test_ordinary_text_files_pass_the_gate(name):
    assert stage_file_gate(name, b"print('hello world')") is None


def test_binary_content_is_refused_as_non_text():
    note = stage_file_gate("payload.dat", b"\x00\x01\x02\x03BINARY")
    assert note == FILE_NOT_TEXT_AR


def test_case_folding_defeats_a_capitalised_secret_name():
    # The model must not launder a secret past the gate by changing case.
    assert stage_file_gate("ID_RSA", SECRET_CONTENT) == FILE_BLOCKED_AR
    assert stage_file_gate("Server.PEM", SECRET_CONTENT) == FILE_BLOCKED_AR


# ─── DEC-13: a staged name must be BARE — path structure is refused outright ───

@pytest.mark.parametrize("name", [
    "sub/.env", "a/b/.env", "/tmp/.env", "sub/.env.local",   # secret laundered behind a dir
    "sub/credentials", "sub/id_rsa", "dir/server.pem",       # more path-prefixed secrets
    "..\\.env", "sub\\.env", "..\\credentials",              # backslash separator variants
    "..", "sub/main.py", "/etc/passwd",                      # traversal / any dir / absolute
])
def test_path_structure_in_a_staged_name_is_refused(name):
    # The escape the GATE FINDING demonstrated: a secret laundered behind a
    # directory. DEC-13 refuses ANY non-bare name by construction — before the
    # secret-name check even runs — so /work traversal is closed at the root.
    assert stage_file_gate(name, SECRET_CONTENT) == FILE_NAME_NOT_BARE_AR


@pytest.mark.parametrize("name", ["archive..bak", "..config", "my.notes.txt", "v1..2.data"])
def test_a_double_dot_inside_a_bare_name_is_not_a_traversal(name):
    # `..` leading or embedded in a separator-free name is a legal file name, not
    # a traversal segment — allowing it proves DEC-13 enforces the contract
    # WITHOUT over-rejecting (a guard that refuses everything is not a guard).
    assert stage_file_gate(name, b"ordinary content") is None
