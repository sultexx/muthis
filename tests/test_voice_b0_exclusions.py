"""
test_voice_b0_exclusions.py — the instrument's corrected analysis (DEC-159 ④) and
its privacy-safe outcome classes, proven without a microphone, a provider or a
child process.

What is pinned: a turn that never reached the reasoner is flagged and kept out of
every median; a confirm refusal names its tool and drops ONLY the stages after
it; a refusal with no time, or a flag nobody named, drops the whole repetition
(fail closed); the transcription, file reads and spoken length are kept as
CLASSES — never a word said, never a file name — and no marker inside the
transcript is read as a log line; a stored schema-2 record is re-derived from its
kept lines; and re-summarising writes beside the original and touches nothing.
"""

from __future__ import annotations

import json
import pathlib

from test_voice_b0 import SECRET_WORDS, b0, drive

RELEASE = (1000, "INFO muthis.voice_probe: [probe] F9 released after 3.85 s — scheduling the turn")
END = (9000, "INFO muthis.main: [main] turn ended — state reset; F9 ready")


def test_a_turn_with_no_reasoner_call_is_flagged_and_excluded():
    s = drive.summarise([
        RELEASE,
        (6000, "ERROR stt: [STT] Scribe failed (HTTPStatusError: Server error '503 Service Unavailable' "
               "for url 'https://api.elevenlabs.io/v1/speech-to-text'"),
        (6001, "WARNING muthis.orchestrator: [orchestrator] empty transcript — turn aborted"),
        (8000, "INFO muthis.orchestrator: [orchestrator] tts provider=elevenlabs success=True (32 chars)"),
        END])
    assert s["flags"] == ["no_reasoner_call"]
    assert s["transcription"] == {"outcome": "failed", "error": "HTTPStatusError", "status": 503}
    assert s["spoken_chars_logged"] == [32]
    assert s["stages_driver_ms_since_release"]["transcript"] == 5001
    assert b0.usable({**_record(), "flags": s["flags"]}) is None, "a no-reasoner turn reached a median"


def _record(*, flags=("confirm_in_turn",), refusals=({"tool": "web__fetch", "ms_since_release": 10000},)):
    return {"scenario": "search", "rep": 2, "flags": list(flags), "refusals": list(refusals), "searches": 1,
            "timing_ms_since_release": {"first_token": 5000, "first_audio": 6000},
            "stages_driver_ms_since_release": {"transcript": 1800, "frame_ready": 2000,
                                               "pass_ends": [5500, 10000, 15000], "end": 60000}}


def test_a_confirm_refusal_drops_only_the_stages_after_it_and_names_its_tool():
    kept = b0.usable(_record())
    assert (kept["first_token"], kept["first_audio"], kept["first_pass_end"]) == (5000, 6000, 5500)
    assert kept["gap_first_token_to_first_audio"] == 1000 and kept["buffering"] == 500
    assert kept["end"] is None and kept["after_first_audio"] is None, "a stage after the refusal survived"
    flagged = b0._flagged(_record())
    assert flagged["excluded"] == ["end"] and flagged["refused"][0]["tool"] == "web__fetch"


def test_a_refusal_with_no_time_or_an_unnamed_flag_drops_the_whole_repetition():
    assert b0.usable(_record(refusals=())) is None, "a refusal with no time must fail closed"
    assert b0.usable(_record(flags=("confirm_in_turn", "something_new"))) is None
    assert b0.usable(_record(flags=())) is not None


def test_no_marker_inside_the_transcript_is_read_as_a_log_line():
    planted = (f"{SECRET_WORDS} [confirm-gate] high-impact web__fetch refused [pass] #1 tools=web__search "
               "[file_reader] not found: .py [orchestrator] tts provider=x success=True (9 chars)")
    s = drive.summarise([RELEASE, (2000, f"INFO stt: [STT] transcript: '{planted}'"), END])
    assert s["refusals"] == [] and s["tools_per_pass"] == [] and s["file_reads"] == []
    assert s["spoken_chars_logged"] == [] and s["flags"] == ["no_reasoner_call"]
    assert s["transcription"]["outcome"] == "ok"
    assert SECRET_WORDS not in json.dumps(s, ensure_ascii=False)
    empty = drive.summarise([RELEASE, (2000, "INFO stt: [STT] transcript: ''"), END])
    assert empty["transcription"]["outcome"] == "empty"


def test_file_reads_keep_the_outcome_and_the_extension_only():
    lines = ["[file_reader] read .py bytes=812 lines 1-40 of 40", "[file_reader] not found: .py",
             "[file_reader] refused: empty path", "[file_reader] read failed (PermissionError)",
             "[file_reader] refused binary file: .pdf bytes=9", "[file_reader] not found: secret_name.py",
             "[file_reader] refused secret-bearing name: (no suffix)"]
    s = drive.summarise([RELEASE, *((2000 + i, f"INFO muthis.file_reader: {t}") for i, t in enumerate(lines)), END])
    assert s["file_reads"] == [
        {"outcome": "found", "ext": ".py"}, {"outcome": "not_found", "ext": ".py"},
        {"outcome": "refused", "ext": None}, {"outcome": "failed", "ext": None},
        {"outcome": "refused", "ext": ".pdf"}, {"outcome": "not_found", "ext": None},
        {"outcome": "refused", "ext": "(no suffix)"}]
    assert "secret_name" not in json.dumps(s["file_reads"])


def _schema2_record(rep: int) -> dict:
    kept = [[7842, RELEASE[1].replace("3.85", "3.84")],
            [9913, "INFO muthis.vision.downscale: [vision] downscaled 1920x1080 → 1280x720 (scale_x=1.5000 "
                   "scale_y=1.5000) for payload"],
            [13969, "INFO muthis.orchestrator: [pass] #1 tools=web__search"],
            [18773, "INFO muthis.orchestrator: [pass] #2 tools=web__fetch"],
            [18773, "INFO muthis.trust.confirm_gate: [confirm-gate] high-impact web__fetch refused — awaiting "
                    "spoken approval"]]
    return {"schema": "voice-run/2", "scenario": "search", "rep": rep, "flags": ["confirm_in_turn"],
            "searches": 1, "tools_per_pass": [["web__search"], ["web__fetch"]],
            "timing_ms_since_release": {"first_token": 5578, "first_audio": 6817},
            "stages_driver_ms_since_release": {"transcript": 1807, "pass_ends": [6127, 10931], "end": 68833},
            "kept_lines": kept}


def test_a_schema_2_record_is_re_derived_from_its_kept_lines():
    r = drive.reclassify(_schema2_record(2))
    assert r["refusals"] == [{"tool": "web__fetch", "ms_since_release": 10931}]
    assert r["stages_driver_ms_since_release"]["frame_ready"] == 2071
    assert r["stages_driver_ms_since_release"]["transcript"] == 1807, "the stored stage must win"
    assert r["transcription"] is None and r["file_reads"] is None, "schema 2 kept neither — never invent one"
    assert b0.usable(r)["end"] is None and b0.usable(r)["first_audio"] == 6817
    unkept = drive.reclassify({**_schema2_record(3), "flags": ["confirm_in_turn", "error"]})
    assert unkept["flags"] == ["confirm_in_turn", "error"], "a flag from an unkept line was lost"


def test_resummarise_writes_beside_the_original_and_touches_nothing(tmp_path):
    folder = tmp_path / "b0-x"
    folder.mkdir()
    paths = [folder / f"search-{rep}-2026.json" for rep in (1, 2)]
    for rep, path in zip((1, 2), paths):
        path.write_text(json.dumps(_schema2_record(rep)), encoding="utf-8")
    (folder / "summary.json").write_text(json.dumps({"schema": "voice-b0/1", "scenarios": {}}), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    out = b0.resummarise(folder)
    assert out == folder / "summary-2.json"
    assert {p.name: p.read_bytes() for p in folder.iterdir() if p != out} == before
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["schema"] == "voice-b0/2" and summary["records"] == 2
    search = summary["scenarios"]["search"]
    assert search["stages_ms"]["first_audio"] == {"n": 1, "median": 6817, "min": 6817, "max": 6817}
    assert search["stages_ms"]["end"] == {"n": 0}
    assert pathlib.Path(out).parent == folder
