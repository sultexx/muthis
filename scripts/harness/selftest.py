"""
selftest.py — the harness tested BEFORE it measures anything real.

Every check is a claim about the harness that could be false, and each is shown
able to FAIL: a word rule fires on its positives AND stays silent on its
negatives; the production-log check FIRES on a stand-in it can see changed; the
fingerprint derivation classifies a model change and an instruction change; a
configuration that misdeclares itself is refused; a run reporting another
model id is dropped; and every pre-registered cheat is driven through the REAL
graph (real router, gate, taint, notes, and real Docker for S5) and must be
CAUGHT by the tags the pre-registration names — while the honest policy
triggers none of them.

No provider is called and no key is read. The real log directory is only hashed.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import pathlib
import shutil
import sys
import tempfile

from muthis.vision.downscale import downscale_to_max_width

from harness import prodlog
from harness.canned import placeholder_png
from harness.config import (Configuration, canonical_catalogue, comparison_type,
                            cross_model_refusal, production_catalogue_sha,
                            production_persona, sha)
from harness.policies import ScriptedReasoner
from harness.prereg import PREREG_PATH, load, missing_in_production
from harness.record import MemoryLogHandler, RunRecorder
from harness.selftest_drive import SCREENS, Results, cheats, scripted
from harness.selftest_units import live_gates, model_block, unit_signals
from harness.runner import (HOME, catalogue_now, fingerprint_constants, prepare,
                            run_configuration, signals_for)
from harness.words import rule_matches

C047_EXAMPLE, C047_REWORD = '"أدوّر لك عن ..."', '"أبحث لك عن ..."'


def word_rules(res: Results, prereg) -> None:
    for rule in prereg.rules.values():
        for text in rule.positives:
            res.check(f"word rule {rule.id} FIRES on a positive", rule_matches(rule, text), text)
        for text in rule.negatives:
            res.check(f"word rule {rule.id} SILENT on a negative",
                      not rule_matches(rule, text), text)


def prodlog_fires(res: Results) -> None:
    stand_in = pathlib.Path(tempfile.mkdtemp(prefix="muthis_prodlog_standin_"))
    try:
        (stand_in / "muthis.log").write_text("line one\n", encoding="utf-8")
        base = prodlog.snapshot(stand_in)
        res.check("prod-log check SILENT when nothing changed",
                  prodlog.changes(base, prodlog.snapshot(stand_in)) == [])
        with (stand_in / "muthis.log").open("a", encoding="utf-8") as handle:
            handle.write("an appended line\n")
        res.check("prod-log check FIRES on an append",
                  prodlog.changes(base, prodlog.snapshot(stand_in)),
                  prodlog.changes(base, prodlog.snapshot(stand_in)))
        base = prodlog.snapshot(stand_in)
        (stand_in / "muthis.log.1").write_text("rotated\n", encoding="utf-8")
        res.check("prod-log check FIRES on a rotation file",
                  prodlog.changes(base, prodlog.snapshot(stand_in)),
                  prodlog.changes(base, prodlog.snapshot(stand_in)))
        base = prodlog.snapshot(stand_in)
        (stand_in / "muthis.log.1").unlink()
        res.check("prod-log check FIRES on a removal", prodlog.changes(base, prodlog.snapshot(stand_in)))
        base = prodlog.snapshot(stand_in)
        stat = (stand_in / "muthis.log").stat()
        os.utime(stand_in / "muthis.log", ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))
        res.check("prod-log check FIRES on a touch (mtime only)",
                  prodlog.changes(base, prodlog.snapshot(stand_in)))
    finally:
        shutil.rmtree(stand_in, ignore_errors=True)
    probe = logging.getLogger("muthis.harness.selftest.probe")
    res.check("handler scan SILENT before a foreign handler", not prodlog.foreign_handlers())
    foreign = logging.StreamHandler(io.StringIO())   # the branch a FileHandler takes
    probe.addHandler(foreign)
    try:
        res.check("handler scan FIRES on a non-console stream handler",
                  prodlog.foreign_handlers(), prodlog.foreign_handlers())
    finally:
        probe.removeHandler(foreign)
    # A FileHandler IS a StreamHandler subclass, so the allow-list checks the EXACT
    # type: a subclass on the very console stream must still be foreign.
    subclass = type("ConsoleLookalike", (logging.StreamHandler,), {})(sys.stderr)
    probe.addHandler(subclass)
    try:
        res.check("handler scan FIRES on a StreamHandler SUBCLASS on stderr (a FileHandler's "
                  "shape)", issubclass(logging.FileHandler, logging.StreamHandler)
                  and prodlog.foreign_handlers(), prodlog.foreign_handlers())
    finally:
        probe.removeHandler(subclass)
    kept = MemoryLogHandler(RunRecorder(config="probe", scenario="probe", rep=0, model="probe"))
    probe.addHandler(kept)
    try:
        res.check("handler scan: the harness's in-memory handler FIRES unless allowed",
                  prodlog.foreign_handlers() and not prodlog.foreign_handlers((MemoryLogHandler,)))
    finally:
        probe.removeHandler(kept)


def fingerprints(res: Results, prereg, catalogue: list) -> None:
    persona = production_persona(prereg.sent_image)
    base = Configuration(label="A", reasoner="luna", model="gpt-5.6-luna",
                         persona_sha256=sha(persona), catalogue_sha256=sha_catalogue(catalogue),
                         baseline=True)
    reworded = HOME / "selftest" / "persona_reword.txt"
    reworded.parent.mkdir(parents=True, exist_ok=True)
    reworded.write_text(persona.replace(C047_EXAMPLE, C047_REWORD, 1), encoding="utf-8")
    note = "muthis.kernel.verification_notes.VERIFY_FALLBACK_AR"
    variants = {
        "A2 (same everything)": (base.with_label("A2"), "identical"),
        "M (model id changed)": (Configuration(**{**base.__dict__, "label": "M",
                                                  "model": "gpt-6-hypothetical"}), "model"),
        "E (effort changed)": (Configuration(**{**base.__dict__, "label": "E",
                                                "effort": "xhigh"}), "model"),
        "I1 (persona reworded)": (Configuration(**{**base.__dict__, "label": "I1",
                                                   "persona": str(reworded), "baseline": False,
                                                   "persona_sha256": sha(reworded.read_text(
                                                       encoding="utf-8"))}), "instruction"),
        "I2 (a note rebound)": (Configuration(**{**base.__dict__, "label": "I2", "baseline": False,
                                                 "notes": {note: "نص بديل للاختبار"}}),
                                "instruction"),
        "I3 (model AND persona)": (Configuration(**{**base.__dict__, "label": "I3",
                                                    "model": "gpt-6-hypothetical",
                                                    "persona": str(reworded), "baseline": False,
                                                    "persona_sha256": sha(reworded.read_text(
                                                        encoding="utf-8"))}), "instruction"),
    }
    configs = [base] + [v[0] for v in variants.values()]
    constants = fingerprint_constants(prereg, configs)
    fp_a = prepare(base, prereg, constants, catalogue)
    res.check("baseline A passes its own declaration", fp_a["errors"] == [], fp_a["errors"])
    # Written out by hand, not derived: the test must not reuse the logic it checks.
    names_another_model = {"M (model id changed)", "I3 (model AND persona)"}
    for name, (cfg, expected) in variants.items():
        fp = prepare(cfg, prereg, constants, catalogue)
        got = comparison_type(fp_a["fingerprint"], fp["fingerprint"])
        res.check(f"fingerprint: A vs {name} derives '{expected}'", got == expected, got)
        res.check(f"{name} passes its OWN declaration", fp["errors"] == [], fp["errors"])
        refused = cross_model_refusal(fp_a["fingerprint"], fp["fingerprint"]) is not None
        want = name in names_another_model
        res.check(f"cross-model refusal {'FIRES' if want else 'is silent'}: A vs {name}",
                  refused == want, refused)
    lies = {
        "a wrong persona sha": Configuration(**{**base.__dict__, "persona_sha256": "0" * 64}),
        "a baseline that rebinds a note": Configuration(**{**base.__dict__,
                                                           "notes": {note: "x"}}),
        "luna declared exclusive": Configuration(**{**base.__dict__, "cost_model": "exclusive"}),
        "a baseline on a reworded persona": Configuration(
            **{**variants["I1 (persona reworded)"][0].__dict__, "baseline": True}),
    }
    for name, cfg in lies.items():
        errors = prepare(cfg, prereg, constants, catalogue)["errors"]
        res.check(f"declaration REFUSED: {name}", errors != [], errors)


def sha_catalogue(catalogue: list) -> str:
    return sha(canonical_catalogue(catalogue))


def echo(res: Results, prereg) -> None:
    png = placeholder_png(1920, 1080)
    persona = production_persona(prereg.sent_image)
    cfg = scripted("honest", persona_sha=sha(persona), model="gpt-5.6-luna")
    runs = run_configuration(cfg, prereg, ["S7"], 1, {n: png for n in SCREENS},
                             lambda cat, sc: ScriptedReasoner("honest", sc.id), 0.5)
    texts = {"persona": persona}
    _, _, excluded = signals_for(runs, prereg, texts, {}, {})
    res.check("echo check DROPS a run whose reported id is not the configured one",
              excluded.get("S7") == {"echo": 1}, excluded)


def main() -> Results:
    res = Results()
    prereg = load()
    # The self-test's own records start empty each time (the harness home, never the repo).
    shutil.rmtree(HOME / "selftest" / "runs", ignore_errors=True)
    with prodlog.Guard(extra_allowed=(MemoryLogHandler,)) as guard:
        catalogue = catalogue_now()
        res.check("catalogue = tests/snapshots/look_tools_v8.json",
                  sha_catalogue(catalogue) == production_catalogue_sha())
        persona = production_persona(prereg.sent_image)
        prod_texts = prepare(scripted("probe", persona_sha=sha(persona)), prereg,
                             fingerprint_constants(prereg, []), catalogue)["texts"]
        res.check("every rule and threshold source is present in production",
                  missing_in_production(prereg, prod_texts) == [],
                  missing_in_production(prereg, prod_texts))
        sent = asyncio.run(downscale_to_max_width(placeholder_png(1920, 1080)))
        width, height = sent.sent_width, sent.sent_height   # (0, 0) on a Pillow failure
        res.check("a 1920x1080 frame is SENT at the pre-registered size",
                  (width, height) == tuple(prereg.sent_image), (width, height))
        stand_in = pathlib.Path(tempfile.mkdtemp(prefix="muthis_prereg_standin_"))
        try:
            text = PREREG_PATH.read_bytes().replace(b"\r\n", b"\n")
            (stand_in / "lf.json").write_bytes(text)
            (stand_in / "crlf.json").write_bytes(text.replace(b"\n", b"\r\n"))
            res.check("the pre-registration hash is the same under LF and CRLF",
                      load(stand_in / "lf.json").sha256 == load(stand_in / "crlf.json").sha256
                      == prereg.sha256)
        finally:
            shutil.rmtree(stand_in, ignore_errors=True)
        word_rules(res, prereg)
        limits = unit_signals(res, prereg)
        prodlog_fires(res)
        live_gates(res, prereg)
        model_block(res, prereg)
        fingerprints(res, prereg, catalogue)
        echo(res, prereg)
        res.report = {**cheats(res, prereg, catalogue), "limits": limits}
        res.check("the REAL production log is unchanged across the whole self-test",
                  guard.verify() == [], guard.verify())
    return res


__all__ = ["Results", "main"]
