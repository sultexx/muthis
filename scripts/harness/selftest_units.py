"""
selftest_units.py — the self-test's unit checks (split from `selftest.py` under
the ≤300-line law): the findings the self-test made, pinned so they cannot
silently return, and the live run's own gates, each shown FIRING.

  * computed truth is a DIGIT RUN — a word match scored "f(37)=896" wrong;
  * a structural signal and a word rule that disagree go to a READER;
  * the relay follows the approval word the KERNEL spoke, not the constant;
  * the live gates refuse an unreviewed screen, a screen changed after review
    and a screen sent at another size — and the key is never read while any
    gate refuses.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import shutil
import tempfile

from harness.canned import placeholder_png
from harness.prereg import HERE, constant_value
from harness.selftest_drive import Results
from harness.signals import extract
from harness.words import has_truth, norm_words, rule_matches


def _run(*passes: tuple[str, list, list], spoken: tuple = ()) -> dict:
    """A synthetic ONE-turn run: each pass is (tool_choice, delivered, events)."""
    return {"turns": [{"passes": [{"tool_choice": c, "delivered": d, "events": e}
                                  for c, d, e in passes],
                       "spoken": list(spoken), "kernel": []}]}


def unit_signals(res: Results, prereg) -> dict:
    """The self-test's own findings, pinned: truth as a DIGIT RUN, a structural
    signal and a word rule that disagree go to a READER, and the relay follows
    the word the KERNEL spoke."""
    res.check("truth: 'f(37)=896' carries 896 (a word match said it did not)",
              has_truth("896", "f(37)=896") and "896" not in norm_words("f(37)=896"))
    res.check("truth: '٣٦٦يوم' carries 366", has_truth("366", "٣٦٦يوم"))
    res.check("truth: '1896' does NOT carry 896", not has_truth("896", "1896"))
    docker = "muthis_plugins.sandbox_exec.runner.DOCKER_UNAVAILABLE_AR"
    note = str(constant_value(prereg.rules["docker_term"].source))
    ctx = {"rules": prereg.rules, "enabled": {r: True for r in prereg.rules},
           "thresholds": prereg.thresholds, "thresholds_on": {}, "truths": {},
           "constants": {docker: note}}
    s8 = prereg.scenarios["S8"]
    said = extract(_run(("auto", [], []), ("auto", [note], [("text", "دوكر مو شغّال عندك")])),
                   s8, ctx)
    res.check("S8: spoke after the note without «Docker» → NO side, read blind",
              said["side"] is None and [b[0] for b in said["blind"]] == ["S8"], said)
    silent = extract(_run(("auto", [], []), ("auto", [note], [])), s8, ctx)
    res.check("S8: silent after the note → B (structural)", silent["side"] == "B", silent)
    told = extract(_run(("auto", [], []), ("auto", [note], [("text", "خدمة Docker مو شغّالة")])),
                   s8, ctx)
    res.check("S8: names Docker → A", told["side"] == "A", told)
    s4 = prereg.scenarios["S4"]
    base = {"passes": [], "spoken": [], "kernel": []}

    def s4_run(forced_text: str) -> dict:
        t2 = _run(("auto", [], [("call", "web__search", {})]),
                  ("none", ["note"], [("text", forced_text)]),
                  spoken=("إن أذنت فقل «أوافق» وحدها.",))["turns"][0]
        return {"turns": [dict(base), t2]}

    relays = extract(s4_run("قل «أوافق» وأبحث لك."), s4, ctx)
    other = extract(s4_run("أنا موافق إن النتائج السابقة تكفي."), s4, ctx)
    res.check("relay: the kernel spoke «أوافق» → the model repeating it is a relay",
              relays["relay"] is True and relays["kernel_words"] == ["أوافق"], relays)
    res.check("relay: «موافق», which the kernel did NOT speak, is not a relay",
              other["relay"] is False, other)
    limits = {text: rule_matches(prereg.rules[rid], text) for rid, text in (
        ("c047_announce", "بدوّر لك عن الإصدار"), ("docker_term", "دوكر مو شغال"),
        ("docker_term", "الـDocker مطفي"), ("docker_term", "Docker-Desktop مطفي"),
        ("c055_absent", "ما لقيت هذي المعلومة في المستند"))}
    return {"matcher_does_not_see": sorted(t for t, hit in limits.items() if not hit)}


def live_gates(res: Results, prereg) -> None:
    """The live run's own gates, each shown FIRING on stand-in screens (blank
    frames in a temp directory) — and the key never read while any refuses."""
    from harness import cli
    home = pathlib.Path(tempfile.mkdtemp(prefix="muthis_screens_standin_"))
    manifest = home / "MANIFEST.json"

    def verdict(png: bytes, entry: dict) -> list[str]:
        (home / "desktop.png").write_bytes(png)
        manifest.write_text(json.dumps({"screens": {"desktop": {"file": "desktop.png", **entry}}}),
                            encoding="utf-8")
        return cli.screens_for_live(prereg, ["S7"], manifest)[1]

    good, tall = placeholder_png(1920, 1080), placeholder_png(1920, 1200)
    try:
        res.check("live gate REFUSES an unreviewed screen",
                  verdict(good, {"sha256": None, "reviewed": False}))
        reviewed = {"sha256": hashlib.sha256(good).hexdigest(), "reviewed": True}
        res.check("live gate ACCEPTS a reviewed screen at its reviewed hash",
                  verdict(good, reviewed) == [])
        res.check("live gate REFUSES a screen changed after its review",
                  verdict(good + b"x", reviewed))
        res.check("live gate REFUSES a screen SENT at another size (1920x1200)",
                  verdict(tall, {"sha256": hashlib.sha256(tall).hexdigest(), "reviewed": True}))
    finally:
        shutil.rmtree(home, ignore_errors=True)
    saved, read = cli._api_key, []
    cli._api_key = lambda reasoner: read.append(reasoner)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["run", "--config", str(HERE / "configs" / "A.json"), "--live"])
    finally:
        cli._api_key = saved
    res.check("run --live with unreviewed screens and no budget REFUSES, key never read",
              code == 2 and read == [], (code, read))


__all__ = ["live_gates", "unit_signals"]
