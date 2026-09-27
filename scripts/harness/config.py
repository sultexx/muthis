"""
config.py — a CONFIGURATION, its declared hashes, its fingerprint, and the
comparison type DERIVED from two fingerprints.

A configuration declares what the model will see: the persona, the catalogue,
any rebound note constant, the reasoner and its model, effort and cost model.
Revision 2 ruling ①: each configuration is checked against its OWN declared
hashes, so B — by definition not production — can be tested at all; only a
configuration marked `baseline` must also hash equal to production.

The comparison type is never chosen by hand. Two configurations whose
instruction fingerprints (persona, catalogue, notes) are equal make a MODEL
comparison, where quoted-word matching is sound because both read the same
text; any difference makes an INSTRUCTION comparison, where it is not (see
`prereg.source_identical`). A against A′ is identical by construction.

Rebinding (the DEC-100 method): a note override replaces the constant IN THIS
PROCESS, in every module that holds the same object, for the duration of a run.
`src/` is never edited. A landing check (in `score.py`) proves each rebound
text actually reached the model.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any, Iterator

REPO = pathlib.Path(__file__).resolve().parents[2]
V8_SNAPSHOT = REPO / "tests" / "snapshots" / "look_tools_v8.json"
COST_MODELS = {"luna": "inclusive", "claude": "exclusive", "scripted": "none"}


@dataclass(frozen=True)
class Configuration:
    label: str
    reasoner: str                      # "luna" | "claude" | "scripted"
    model: str
    effort: str = "high"
    max_tokens: int = 4096
    cost_model: str = "inclusive"
    persona: str = "production"        # "production" or a path to a persona text file
    persona_sha256: str = ""
    catalogue_sha256: str = ""
    notes: dict = field(default_factory=dict)   # "module.NAME" -> replacement text
    baseline: bool = False
    policy: str = ""                   # the scripted policy, for reasoner == "scripted"

    @classmethod
    def from_json(cls, path: pathlib.Path) -> "Configuration":
        return cls(**json.loads(pathlib.Path(path).read_text(encoding="utf-8")))

    def with_label(self, label: str) -> "Configuration":
        return Configuration(**{**self.__dict__, "label": label})


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_catalogue(tools: list) -> str:
    return json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def production_persona(sent: tuple[int, int]) -> str:
    from muthis.cloud.claude_agent import LOOK_SYSTEM_PROMPT
    from muthis.persona import resolve_system_prompt
    return resolve_system_prompt(LOOK_SYSTEM_PROMPT, sent[0], sent[1])


def production_catalogue_sha() -> str:
    return sha(canonical_catalogue(json.loads(V8_SNAPSHOT.read_text(encoding="utf-8"))))


def compose_persona(cfg: Configuration, sent: tuple[int, int]) -> str:
    if cfg.persona == "production":
        return production_persona(sent)
    return pathlib.Path(cfg.persona).read_text(encoding="utf-8")


@contextlib.contextmanager
def apply_notes(cfg: Configuration) -> Iterator[None]:
    """Rebind each overridden constant wherever this process holds it, and
    restore every binding afterwards — whatever happens inside."""
    saved: list[tuple[Any, str, Any]] = []
    try:
        for dotted, text in cfg.notes.items():
            module_name, name = dotted.rsplit(".", 1)
            original = getattr(importlib.import_module(module_name), name)
            for module in list(sys.modules.values()):
                namespace = getattr(module, "__dict__", None)
                if not namespace:
                    continue
                for attr, value in list(namespace.items()):
                    if value is original:
                        saved.append((module, attr, value))
                        setattr(module, attr, text)
        yield
    finally:
        for module, attr, value in reversed(saved):
            setattr(module, attr, value)


def texts_for(persona: str, constants: list[str]) -> dict[str, Any]:
    """The texts a word rule may quote from: the persona, and each named
    constant's CURRENT value (so call this inside `apply_notes`)."""
    texts: dict[str, Any] = {"persona": persona}
    for dotted in constants:
        module_name, name = dotted.rsplit(".", 1)
        texts[dotted] = getattr(importlib.import_module(module_name), name)
    return texts


def fingerprint(cfg: Configuration, persona: str, catalogue: list,
                texts: dict[str, Any]) -> dict[str, Any]:
    constants = {k: sha(repr(v)) for k, v in sorted(texts.items()) if k != "persona"}
    return {"instructions": {"persona": sha(persona),
                             "catalogue": sha(canonical_catalogue(catalogue)),
                             "constants": constants},
            "model": {"reasoner": cfg.reasoner, "model": cfg.model, "effort": cfg.effort}}


def comparison_type(fp_a: dict, fp_b: dict) -> str:
    """DERIVED, never chosen: identical, model, or instruction."""
    if fp_a == fp_b:
        return "identical"
    if fp_a["instructions"] == fp_b["instructions"]:
        return "model"
    return "instruction"


def verify_declared(cfg: Configuration, persona: str, catalogue: list,
                    texts: dict[str, Any], sent: tuple[int, int]) -> list[str]:
    """Every mismatch between what the configuration DECLARED and what this
    process will actually send. An empty list is the only passing answer."""
    errors = []
    if sha(persona) != cfg.persona_sha256:
        errors.append(f"{cfg.label}: persona sha256 {sha(persona)[:12]} != declared "
                      f"{cfg.persona_sha256[:12]}")
    cat_sha = sha(canonical_catalogue(catalogue))
    if cat_sha != cfg.catalogue_sha256:
        errors.append(f"{cfg.label}: catalogue sha256 {cat_sha[:12]} != declared "
                      f"{cfg.catalogue_sha256[:12]}")
    for dotted, text in cfg.notes.items():
        if texts.get(dotted) != text:
            errors.append(f"{cfg.label}: note {dotted} did not rebind")
    if COST_MODELS.get(cfg.reasoner) not in (cfg.cost_model, "none"):
        errors.append(f"{cfg.label}: cost model {cfg.cost_model!r} does not match "
                      f"the {cfg.reasoner} agent ({COST_MODELS.get(cfg.reasoner)})")
    if cfg.baseline:
        if sha(persona) != sha(production_persona(sent)):
            errors.append(f"{cfg.label}: a BASELINE whose persona is not production's")
        if cat_sha != production_catalogue_sha():
            errors.append(f"{cfg.label}: a BASELINE whose catalogue is not "
                          "tests/snapshots/look_tools_v8.json")
        if cfg.notes:
            errors.append(f"{cfg.label}: a BASELINE may not rebind notes")
    return errors


__all__ = ["Configuration", "apply_notes", "canonical_catalogue", "comparison_type",
           "compose_persona", "fingerprint", "production_catalogue_sha",
           "production_persona", "sha", "texts_for", "verify_declared"]
