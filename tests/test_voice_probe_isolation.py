"""
test_voice_probe_isolation.py — DEC-157 ⑤: the voice instrument is never reachable
from normal operation and never writes the durable log.

Five guards, G1–G5 (Sultan's choice ③), and EACH IS FIRST SHOWN TO FIRE: a scan
that finds nothing is indistinguishable from a broken scan, so every check is run
once against an input built to fail it before it is trusted on the real tree.

  G1  nothing reachable from `muthis.main` imports `muthis.voice_probe`
  G2  no module but the probe hands `build()` an argument; `main()` calls `run()`
      bare, and `run()` is exactly `serve(await build())`
  G3  `build`'s one parameter defaults to None and builds a bare `Mic()`, and a
      bare `Mic()` is the real device
  G4  the probe's logging posture passes the scripts guard's own scan, with
      `build`/`close` the only names it takes from `muthis.main`
  G5  the probe refuses to start without MUTHIS_DEBUG=1

No test imports `muthis.main` (the standing rule: live credentials); G1–G3 read
the source, and the probe itself loads nothing of the app on import.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import logging
import pathlib
import wave

import pytest

from muthis import mic as mic_module
from muthis import voice_probe
from muthis.mic import Mic

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROOTS = (ROOT / "src", ROOT / "sdk")
SRC = ROOT / "src" / "muthis"
MAIN_PY = SRC / "main.py"
PROBE_PY = SRC / "voice_probe.py"
PROBE = "muthis.voice_probe"


# ─── G1: the import closure of the app ─────────────────────────────────────────

def _module_file(name: str):
    for root in ROOTS:
        base = root.joinpath(*name.split("."))
        for candidate in (base / "__init__.py", base.with_suffix(".py")):
            if candidate.is_file():
                return candidate
    return None


def _imported(tree: ast.Module, module: str, is_package: bool) -> set[str]:
    """Every module an AST imports, at ANY depth — a lazy import inside a function
    is exactly the kind that would carry the probe in unnoticed."""
    package = module if is_package else module.rpartition(".")[0]
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                base = ".".join(parts + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)  # `from . import x`
    return names


def _closure(start: str, extra_source: str | None = None) -> set[str]:
    seen, stack = set(), [start]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        path = _module_file(name)
        if path is None and not (extra_source and name == start):
            continue
        seen.add(name)
        source = extra_source if (extra_source and name == start) else path.read_text(encoding="utf-8")
        is_package = path is not None and path.name == "__init__.py"
        stack.extend(_imported(ast.parse(source), name, is_package))
        stack.extend(".".join(name.split(".")[:i]) for i in range(1, name.count(".") + 1))
    return seen


def test_G1_fires_on_a_lazy_import_inside_a_function():
    source = "def later():\n    from . import voice_probe\n"
    assert PROBE in _closure("muthis.synthetic_root", extra_source=source)
    assert "muthis.main" in _closure(PROBE), "the walk missed the probe's own lazy import"


def test_G1_the_app_never_reaches_the_probe():
    closure = _closure("muthis.main")
    assert {"muthis.kernel.turn_pass", "muthis.turn_timing", "muthis.mic"} <= closure, (
        "the walk did not reach deep into the app — it is aimed at nothing")
    assert PROBE not in closure, "a module the app imports now imports the voice probe"


def test_G1_has_no_dynamic_import_to_hide_behind():
    """The static walk's one blind spot is a dynamic import; there is none."""
    for name in sorted(_closure("muthis.main")):
        tree = ast.parse(_module_file(name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                assert called not in ("import_module", "__import__"), f"{name} imports dynamically"


# ─── G2: no other caller hands build() an argument ─────────────────────────────

def _build_calls_with_arguments(source: str) -> list[int]:
    """main.py's own calls of `build` — the only place it is called bare."""
    return [node.lineno for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "build"
            and (node.args or node.keywords)]


def _imports_the_probe(source: str, module: str) -> bool:
    return any(name == PROBE or name.startswith(PROBE + ".")
               for name in _imported(ast.parse(source), module, False))


def test_G2_fires_on_an_argument_on_an_import_and_on_a_second_taker():
    assert _build_calls_with_arguments("async def run():\n    await serve(await build(mic=x))\n")
    assert _imports_the_probe("from muthis.voice_probe import drive\n", "muthis.kernel.x")
    assert _imports_the_probe("from . import voice_probe\n", "muthis.x")
    assert _names_taken_from_main("def f():\n    from muthis.main import build\n") == {"build"}


def test_G2_only_the_probe_imports_the_probe_or_takes_anything_from_main():
    """`build` can only be handed an argument by a module that takes it from
    `muthis.main`, and no module of the app does — only the probe."""
    for path in sorted(set(SRC.rglob("*.py")) - {PROBE_PY}):
        module = "muthis." + ".".join(path.relative_to(SRC).with_suffix("").parts)
        source = path.read_text(encoding="utf-8")
        assert not _imports_the_probe(source, module), f"{module} imports the voice probe"
        assert not _names_taken_from_main(source), f"{module} takes names from muthis.main"
    assert not _build_calls_with_arguments(MAIN_PY.read_text(encoding="utf-8")), (
        "main.py hands build() an argument — production must build the real mic")


def _function(tree: ast.Module, name: str):
    return next(node for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)


def test_G2_production_starts_exactly_as_today():
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    run = _function(tree, "run")
    assert len(run.body) == 2 and ast.unparse(run.body[1]) == "await serve(await build())", (
        "run() is no longer exactly serve(await build())")
    calls = [n for n in ast.walk(_function(tree, "main")) if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "run"]
    assert calls and all(not c.args and not c.keywords for c in calls), "main() calls run() with arguments"


# ─── G3: the default microphone is the real one ────────────────────────────────

def _build_defaults_to_the_real_mic(source: str) -> bool:
    build = _function(ast.parse(source), "build")
    args = build.args
    signature_ok = (not args.posonlyargs and not args.args and [a.arg for a in args.kwonlyargs] == ["mic"]
                    and len(args.kw_defaults) == 1 and isinstance(args.kw_defaults[0], ast.Constant)
                    and args.kw_defaults[0].value is None)
    fallback = [ast.unparse(n) for n in ast.walk(build) if isinstance(n, ast.Assign)
                and ast.unparse(n.targets[0]) == "mic"]
    return signature_ok and fallback == ["mic = mic if mic is not None else Mic()"]


def test_G3_fires_on_a_mic_that_is_not_bare():
    tampered = MAIN_PY.read_text(encoding="utf-8").replace(
        "mic = mic if mic is not None else Mic()", "mic = mic if mic is not None else Mic(stream_factory=f)")
    assert not _build_defaults_to_the_real_mic(tampered)
    assert Mic(stream_factory=lambda cb: None)._stream_factory is not mic_module._default_stream_factory


def test_G3_build_defaults_to_the_real_device():
    assert _build_defaults_to_the_real_mic(MAIN_PY.read_text(encoding="utf-8"))
    assert Mic()._stream_factory is mic_module._default_stream_factory


# ─── G4: the probe's logging posture ──────────────────────────────────────────

def _scripts_guard():
    path = ROOT / "tests" / "test_no_script_attaches_the_durable_log.py"
    spec = importlib.util.spec_from_file_location("_scripts_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _names_taken_from_main(source: str) -> set[str]:
    return {alias.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom)
            and (node.module == "muthis.main" or (node.level and node.module == "main"))
            for alias in node.names}


def test_G4_fires_on_the_policy_call_and_on_taking_main():
    violations = _scripts_guard().violations
    assert "imports configure_logging" in violations("from muthis.logging_policy import configure_logging\n")
    assert _names_taken_from_main("from muthis.main import build, main\n") == {"build", "main"}
    assert _names_taken_from_main("from .main import build\n") == {"build"}


def test_G4_the_probe_takes_only_build_and_close_and_never_the_policy():
    source = PROBE_PY.read_text(encoding="utf-8")
    assert _scripts_guard().violations(source) == ["imports from muthis.main"], (
        "the probe reaches the durable log by a form the scripts guard recognises")
    assert _names_taken_from_main(source) == {"build", "close"}


# ─── G5: debug or nothing ─────────────────────────────────────────────────────

def _clip(tmp_path: pathlib.Path, rate: int = 16000, seconds: float = 0.2) -> pathlib.Path:
    path = tmp_path / "clip.wav"
    with wave.open(str(path), "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(rate)
        clip.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


def _reasons(tmp_path, **overrides):
    kwargs = dict(debug=True, clip=_clip(tmp_path), cwd=voice_probe.REPO_ROOT,
                  listing=[], own_pids=set(), handlers=[])
    kwargs.update(overrides)
    return voice_probe.refusals(**kwargs)


def test_G5_refuses_without_debug_and_only_then(tmp_path):
    assert any("MUTHIS_DEBUG=1" in r for r in _reasons(tmp_path, debug=False))
    assert _reasons(tmp_path) == [], "a clean, debug-on start was refused"


def test_G5_debug_is_read_through_the_policy_predicate():
    tree = ast.parse(PROBE_PY.read_text(encoding="utf-8"))
    called = {getattr(n.func, "id", getattr(n.func, "attr", "")) for n in ast.walk(tree)
              if isinstance(n, ast.Call)}
    assert "debug_content_enabled" in called
    assert not any(isinstance(n, ast.Constant) and n.value == "MUTHIS_DEBUG" for n in ast.walk(tree)), (
        "the probe reads MUTHIS_DEBUG itself — a second debug predicate can drift")


# ─── The other refusals, and the clip standing in for the device ───────────────

def test_the_real_app_running_refuses_the_run(tmp_path):
    listing = [(10, r"C:\repo\.venv\Scripts\python.exe -m muthis.main"),
               (11, "python -m muthis.voice_probe C:/clips/a.wav"),
               (12, r"python C:\repo\src\muthis\main.py"), (13, "")]
    assert voice_probe.real_app_pids(listing, own={11}) == [10, 12]
    assert any("real app is running" in r for r in _reasons(tmp_path, listing=listing))
    assert any("cannot verify" in r for r in _reasons(tmp_path, listing=None)), "fails OPEN"


def test_a_clip_inside_the_repository_or_in_another_format_is_refused(tmp_path):
    assert "inside the repository" in voice_probe.clip_refusal(ROOT / "tests" / "x.wav")
    assert "16000 Hz mono" in voice_probe.clip_refusal(_clip(tmp_path, rate=22050))
    assert voice_probe.clip_refusal(_clip(tmp_path)) is None


def test_a_run_outside_the_repository_root_is_refused(tmp_path):
    assert any("budget ledger" in r for r in _reasons(tmp_path, cwd=tmp_path))


def test_a_file_handler_is_seen_and_refuses(tmp_path):
    target = logging.getLogger("muthis.voice_probe.test_handler")
    handler = logging.FileHandler(tmp_path / "x.log", delay=True)
    target.addHandler(handler)
    try:
        assert target.name in voice_probe.file_handlers()
    finally:
        target.removeHandler(handler)
        handler.close()
    assert any("file handler" in r for r in _reasons(tmp_path, handlers=["root"]))


def test_the_clip_reaches_the_real_mic_byte_for_byte(tmp_path):
    pcm = bytes(range(256)) * 50
    factory = voice_probe.ClipStreamFactory(pcm, pace=0)
    mic = Mic(stream_factory=factory, min_record_seconds=0.0)
    mic.start()
    assert factory.last.delivered.wait(5)
    captured = tmp_path / "captured.wav"
    captured.write_bytes(asyncio.run(mic.stop()))
    with wave.open(str(captured), "rb") as clip:
        assert clip.readframes(clip.getnframes()) == pcm


@pytest.mark.parametrize("bad", [[], ["a", "b"]])
def test_the_entry_refuses_a_wrong_argument_count(bad):
    assert voice_probe.main(bad) == voice_probe.REFUSED
