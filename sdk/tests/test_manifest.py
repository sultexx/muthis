# sdk/tests/test_manifest.py
"""muthis-plugin.toml loader: happy path + every refusal the contract makes."""

from __future__ import annotations

import pytest

from muthis_sdk import ManifestError, load_manifest
from muthis_sdk.manifest import parse_manifest

GOOD = """
[plugin]
name    = "file_read"
version = "1.0.0"
sdk     = ">=2.0.0a1,<3"
kind    = "native"
entry   = "muthis_plugins.file_read.plugin:FileReadPlugin"

[descriptions]
ar = "يقرأ ملفًا نصّيًا محليًا بأسطر مرقّمة ليؤسس الشرح على المحتوى الحقيقي"
en = "Reads a local text file with numbered lines"

[capabilities]
required = ["perceive.files.read"]

[tools.read_local_file]
read_only = true
"""


def _write(tmp_path, text):
    (tmp_path / "muthis-plugin.toml").write_text(text, encoding="utf-8")
    return tmp_path


def test_happy_path(tmp_path):
    m = load_manifest(_write(tmp_path, GOOD))
    assert m.name == "file_read" and m.kind == "native"
    assert m.capabilities_required == ("perceive.files.read",)
    assert [t.name for t in m.tools] == ["read_local_file"]
    assert m.tools[0].read_only is True
    assert "يقرأ" in m.description_ar


def test_missing_manifest_file(tmp_path):
    with pytest.raises(ManifestError, match="no muthis-plugin.toml"):
        load_manifest(tmp_path)


def test_arabic_description_is_mandatory(tmp_path):
    bad = GOOD.replace('ar = "يقرأ ملفًا نصّيًا محليًا بأسطر مرقّمة ليؤسس الشرح على المحتوى الحقيقي"', 'ar = ""')
    with pytest.raises(ManifestError, match="non-empty 'ar'"):
        load_manifest(_write(tmp_path, bad))


def test_unknown_capability_refused_closed_enum(tmp_path):
    bad = GOOD.replace('required = ["perceive.files.read"]', 'required = ["input.mouse"]')
    with pytest.raises(ManifestError, match="enum is closed"):
        load_manifest(_write(tmp_path, bad))


def test_bad_kind_refused():
    data = {
        "plugin": {"name": "x", "version": "1.0.0", "sdk": ">=2", "kind": "inproc"},
        "descriptions": {"ar": "وصف"},
        "tools": {"x": {}},
    }
    with pytest.raises(ManifestError, match="kind"):
        parse_manifest(data)


def test_tools_table_required():
    data = {
        "plugin": {"name": "x", "version": "1.0.0", "sdk": ">=2", "kind": "native"},
        "descriptions": {"ar": "وصف"},
    }
    with pytest.raises(ManifestError, match="tools"):
        parse_manifest(data)


def test_bad_tool_name_refused():
    data = {
        "plugin": {"name": "x", "version": "1.0.0", "sdk": ">=2", "kind": "native"},
        "descriptions": {"ar": "وصف"},
        "tools": {"Bad-Name": {}},
    }
    with pytest.raises(ManifestError, match="tool name"):
        parse_manifest(data)


def test_invalid_toml_wrapped(tmp_path):
    with pytest.raises(ManifestError, match="invalid TOML"):
        load_manifest(_write(tmp_path, "[plugin\nname="))
