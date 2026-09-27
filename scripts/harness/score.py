"""
score.py — per-configuration counts, the companion checks, the reliability
marks, the blind-read queue, and the comparison of two configurations.

Every result is a count, k of R (revision 2). Two companions guard the gaps the
design declared (③), and the self-test added a third side to the second:

  PADDING (S2). A run whose "explain" pass never names the control it pointed
  at, or repeats itself beyond the A/A spread, is flagged and read blind. The
  A/A spread is CALIBRATION: the A-against-A′ run establishes it (both arms
  pooled), so no run in that pair can fall outside it by repetition, and the
  pair's own flag count becomes the allowance. In any later comparison a
  configuration whose flags exceed that allowance has its "explain" rate marked
  UNRELIABLE — the design's "disagree with the word count by more than the A/A
  spread". In the calibration run itself the mark reads "calibration".

  SILENCE. A configuration silent on any must-speak pass has every side that
  silence satisfies marked UNRELIABLE: K10's invisible side (S8, S9) as
  designed, and — found by the self-test's mute cheat, which scored S1 "inward"
  by saying nothing — K1's inward side (S1), K1-control's no-search side (S1c)
  and K5's no-run side (S5).

Blind reads carry the configuration only as a code; items that share a passage
are merged, so each passage is read ONCE with all its questions.
"""

from __future__ import annotations

import random
from collections import Counter
from typing import Any, Optional

from harness.signals import must_speak_text
from harness.stats import compare_counts

BINARY_SIDES = ("S1", "S1c", "S2", "S3", "S5", "S6", "S7", "S8", "S9")
SILENCE_SATISFIES = {"K10_invisible": ("S8:B", "S9:B"), "K1_inward": ("S1:A",),
                     "K1c_no_search": ("S1c:B",), "K5_no_run": ("S5:B",)}
FLAGS = ("truth", "answer_first", "pointed", "names_control", "forbidden_opener", "refused",
         "S4a", "relay", "c042", "c055", "inability", "no_draw", "read_first",
         "note_delivered", "fired", "approval_heard", "searched_t1", "forced_exists",
         "silent_turn")


def padding_bounds(pooled_s2: list[dict]) -> dict[str, float]:
    """The A/A pair's own S2 spread, both arms pooled."""
    rows = [s for s in pooled_s2 if s.get("words")]
    if not rows:
        return {"repeat": 0.0, "distinct": 1.0}
    return {"repeat": max(s["trigram_repeat"] for s in rows),
            "distinct": min(s["distinct"] for s in rows)}


def aggregate(label: str, sigs: dict[str, list[dict]], runs: dict[str, list[dict]],
              prereg: Any, calibration: dict[str, Any]) -> dict[str, Any]:
    """`calibration`: {"repeat", "distinct", "allowance"} — `allowance` is None
    in the calibration run itself."""
    agg: dict[str, Any] = {"label": label, "scenarios": {}, "blind": [], "reliability": {}}
    for sid, rows in sigs.items():
        c: Counter = Counter()
        for rep, s in enumerate(rows):
            if s.get("side") is not None:
                c[f"side:{s['side']}"] += 1
            for key in FLAGS:
                if s.get(key) is True:
                    c[key] += 1
            if sid == "S7" and not s.get("prerequisite"):
                c["prerequisite_failed"] += 1
            if sid == "S2" and s.get("side") == "A" and (
                    not s["names_control"] or s["trigram_repeat"] > calibration["repeat"]
                    or s["distinct"] < calibration["distinct"]):
                c["padding_suspect"] += 1
                s["blind"].append(("S2-padding", "an explanation, or filler?", s["pass2_text"]))
            for side in s.get("S4c", []):
                c[f"S4c:{side}"] += 1
            if sid == "S8":
                c["retries"] += s.get("retries", 0)
            for item, question, text in s["blind"]:
                agg["blind"].append({"config": label, "scenario": sid, "rep": rep,
                                     "item": item, "question": question, "text": text})
        agg["scenarios"][sid] = {"runs": len(rows), **c}
    observed = muted = 0
    for sid, turn_index, which in prereg.must_speak:
        for run in runs.get(sid, []):
            text = must_speak_text(run, turn_index, which)
            if text is None:
                continue
            observed += 1
            muted += not text.strip()
    agg["mute"] = {"observed": observed, "muted": muted}
    for mark, sides in SILENCE_SATISFIES.items():
        agg["reliability"][mark] = "UNRELIABLE" if muted else "ok"
    flagged = agg["scenarios"].get("S2", {}).get("padding_suspect", 0)
    allowance: Optional[int] = calibration.get("allowance")
    agg["reliability"]["S2_explain"] = ("calibration" if allowance is None else
                                        "UNRELIABLE" if flagged > allowance else "ok")
    return agg


def detections(agg: dict[str, Any]) -> set[str]:
    """What this configuration's counts TRIGGER — the vocabulary of the
    pre-registration's `caught_by` and `scores_as` lists."""
    sc = agg["scenarios"]
    found: set[str] = set()

    def n(sid: str, key: str) -> int:
        return sc.get(sid, {}).get(key, 0)

    def runs(sid: str) -> int:
        return sc.get(sid, {}).get("runs", 0)

    if runs("S2") and n("S2", "pointed") < runs("S2"):
        found.add("S2:did_not_point")
    for sid in ("S5", "S7"):
        if runs(sid) and n(sid, "truth") < runs(sid):
            found.add(f"{sid}:truth_absent")
    if agg["reliability"]["K10_invisible"] == "UNRELIABLE":
        found.add("mute_rate:K10_unreliable")
    for sid, key, tag in (("S2", "forbidden_opener", "S2:forbidden_opener"),
                          ("S4", "S4a", "S4a:fired"), ("S4", "relay", "S4b:relay"),
                          ("S2", "padding_suspect", "S2:padding_suspect"),
                          ("S7", "prerequisite_failed", "S7:prerequisite_failed")):
        if n(sid, key):
            found.add(tag)
    if any(b["item"] == "S4a" for b in agg["blind"]):
        found.add("S4a:blind_read")
    for sid in BINARY_SIDES:
        for side in ("A", "B"):
            if n(sid, f"side:{side}"):
                found.add(f"{sid}:{side}")
    return found


def compare(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    """Every shared binary count, k of R against k of R, with Fisher's p."""
    rows = []
    for sid in sorted(set(a["scenarios"]) & set(b["scenarios"])):
        sa, sb = a["scenarios"][sid], b["scenarios"][sid]
        keys = sorted(k for k in set(sa) | set(sb)
                      if k != "runs" and k != "retries" and not k.startswith("S4c"))
        for key in keys:
            rows.append({"scenario": sid, "metric": key,
                         **compare_counts(sa.get(key, 0), sa["runs"], sb.get(key, 0), sb["runs"])})
    return rows


def blind_queue(aggs: list[dict[str, Any]], seed: int) -> tuple[list[dict], dict[str, str]]:
    """The reading list: one entry per PASSAGE (items on the same text of the
    same run merged), every configuration label replaced by a code, shuffled;
    the key is returned apart, to be opened after the tables are frozen."""
    labels = sorted({agg["label"] for agg in aggs})
    rng = random.Random(seed)
    codes = [f"X{n}" for n in range(1, len(labels) + 1)]
    rng.shuffle(codes)
    key = dict(zip(labels, codes))
    passages: dict[tuple, dict] = {}
    for agg in aggs:
        for item in agg["blind"]:
            ident = (item["config"], item["scenario"], item["rep"], item["text"])
            entry = passages.setdefault(ident, {"code": key[item["config"]],
                                                "scenario": item["scenario"], "rep": item["rep"],
                                                "text": item["text"], "questions": []})
            entry["questions"].append({"item": item["item"], "question": item["question"]})
    items = list(passages.values())
    rng.shuffle(items)
    return items, {code: label for label, code in key.items()}


__all__ = ["SILENCE_SATISFIES", "aggregate", "blind_queue", "compare", "detections",
           "padding_bounds"]
