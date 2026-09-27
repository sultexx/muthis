"""
prereg.py — the frozen pre-registration, loaded once, hashed, and made usable.

`prereg.json` is the ONE definition of every scenario, every word rule and every
threshold. The code reads it rather than restating it, so a rule cannot drift
between the file a reader audits and the code that scores. Its sha256 goes into
every run record: a run scored under a different pre-registration is a different
experiment.

THE RULE THAT FIXES REVISION 1's CRITICAL FLAW LIVES HERE (`source_identical`).
A word rule quotes words from an instruction. In an INSTRUCTION comparison the
instruction may be reworded in one configuration, and a matcher quoted from the
other would then misjudge it — a fabricated regression or improvement. So a rule
counts only when its SOURCE text is present, byte for byte, in BOTH
configurations' texts; otherwise it is disabled and its items go to a blind
human read. The check is mechanical and runs before any row is scored.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Optional

HERE = pathlib.Path(__file__).resolve().parent
PREREG_PATH = HERE / "prereg.json"
FIXTURES = HERE / "fixtures"


@dataclass(frozen=True)
class Source:
    kind: str                      # "persona" (a quoted clause) or "constant"
    text: str = ""                 # the quoted clause, for kind == "persona"
    module: str = ""               # for kind == "constant"
    name: str = ""


@dataclass(frozen=True)
class Rule:
    id: str
    source: Source
    tokens: tuple[str, ...]
    position: str                  # "anywhere" or "opening"
    positives: tuple[str, ...]
    negatives: tuple[str, ...]


@dataclass(frozen=True)
class Threshold:
    id: str
    value: int
    source: Source


@dataclass(frozen=True)
class Scenario:
    id: str
    conflict: str
    screen: str
    turns: tuple[str, ...]
    sides: dict = field(default_factory=dict)
    control_label: tuple[str, ...] = ()
    truth: Optional[str] = None
    runner: str = "docker"

    def turn_texts(self) -> list[str]:
        """The utterances with the fixture paths filled in."""
        paths = fixture_paths()
        return [t.format(DOC=paths["doc"], RECUR=paths["recur"], CODE=paths["code"])
                for t in self.turns]


@dataclass(frozen=True)
class Prereg:
    sha256: str
    runs_per_configuration: int
    sent_image: tuple[int, int]
    scenarios: dict[str, Scenario]
    rules: dict[str, Rule]
    thresholds: dict[str, Threshold]
    must_speak: tuple[tuple[str, int, str], ...]
    cheats: dict[str, dict]            # name -> {caught_by, scores_as | control}


def fixture_paths() -> dict[str, str]:
    return {"doc": str(FIXTURES / "doc_product.md"),
            "recur": str(FIXTURES / "recurrence.py"),
            "code": str(FIXTURES / "explain_me.py")}


def _source(raw: dict) -> Source:
    return Source(kind=raw["kind"], text=raw.get("text", ""),
                  module=raw.get("module", ""), name=raw.get("name", ""))


def constant_value(source: Source) -> Any:
    """The CURRENT value of a constant source in this process — after any
    configuration rebinding, which is exactly what makes it per-configuration."""
    return getattr(importlib.import_module(source.module), source.name)


def load(path: pathlib.Path = PREREG_PATH) -> Prereg:
    raw_bytes = path.read_bytes()
    raw = json.loads(raw_bytes.decode("utf-8"))
    rules = {}
    for r in raw["rules"]:
        source = _source(r["source"])
        tokens = r["tokens"]
        if tokens == "FROM_SOURCE":           # the constant IS the word list
            tokens = list(constant_value(source))
        rules[r["id"]] = Rule(id=r["id"], source=source, tokens=tuple(tokens),
                              position=r["position"], positives=tuple(r["positives"]),
                              negatives=tuple(r["negatives"]))
    scenarios = {
        s["id"]: Scenario(id=s["id"], conflict=s["conflict"], screen=s["screen"],
                          turns=tuple(s["turns"]), sides=s.get("sides", {}),
                          control_label=tuple(s.get("control_label", ())),
                          truth=s.get("truth"), runner=s.get("runner", "docker"))
        for s in raw["scenarios"]}
    thresholds = {t["id"]: Threshold(id=t["id"], value=int(t["value"]),
                                     source=_source(t["source"]))
                  for t in raw["thresholds"]}
    return Prereg(sha256=hashlib.sha256(raw_bytes).hexdigest(),
                  runs_per_configuration=int(raw["runs_per_configuration"]),
                  sent_image=tuple(raw["sent_image"]), scenarios=scenarios, rules=rules,
                  thresholds=thresholds,
                  must_speak=tuple(tuple(m) for m in raw["must_speak"]),
                  cheats=dict(raw["cheats"]))


def source_text_in(source: Source, texts: dict[str, Any]) -> Optional[str]:
    """The source as it stands in ONE configuration's declared texts, or None
    when that configuration no longer contains it. `texts` carries the persona
    under "persona" and each constant under "module.NAME"."""
    if source.kind == "persona":
        return source.text if source.text in texts["persona"] else None
    value = texts.get(f"{source.module}.{source.name}")
    return None if value is None else repr(value)


def source_identical(source: Source, texts_a: dict, texts_b: dict) -> bool:
    """THE GUARANTEE: a quoted matcher counts only on a source both
    configurations carry byte for byte."""
    in_a, in_b = source_text_in(source, texts_a), source_text_in(source, texts_b)
    return in_a is not None and in_a == in_b


def missing_in_production(prereg: Prereg, production_texts: dict) -> list[str]:
    """A rule or threshold whose source is absent from PRODUCTION means the
    pre-registration went stale against the tree — refuse rather than score."""
    items = list(prereg.rules.values()) + list(prereg.thresholds.values())
    return [item.id for item in items
            if source_text_in(item.source, production_texts) is None]


__all__ = ["Prereg", "Rule", "Scenario", "Source", "Threshold", "constant_value",
           "fixture_paths", "load", "missing_in_production", "source_identical",
           "source_text_in", "PREREG_PATH", "FIXTURES"]
