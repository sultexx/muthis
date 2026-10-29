# src/muthis/instructions/guard.py
"""
guard.py — the SHARED CHECKER: it turns a registry entry's declared word
families into that entry's guard.

A GUARD IS A PURE FUNCTION OF THE TEXT IT IS GIVEN. It never reads the
registry, the manifest or the composed prompt, which is what lets the meta-test
(`tests/test_instruction_meta.py`) run every guard in-process on deliberately
broken inputs, where DEC-139 needed six scratch clones.

MATCHING. The text and every member go through `kernel.verbosity.normalize_ar`
(tashkeel, tatweel, hamza-alif, ta marbuta, digits, nineteen punctuation marks)
and are split on whitespace; nothing else is folded, so a tool name keeps its
case. A member is present when its tokens appear as a contiguous window of the
text's tokens. A member may therefore be a PHRASE, and a prohibition is declared
with its negation: delete the negation from C014's "you cannot press" phrase and
the window is gone. (No law text is written in this file: the one-home tests scan
`src/**/*.py`, and a copy here would be a third source.)

A FAMILY is one obligation, met by ANY of its members, and named by its first.
A required family that is missing, or a forbidden family that is present, fails
the guard, and the verdict NAMES it: a failure that cannot say which family went
missing cannot be acted on.

THE §3.2 DELIMITER is forbidden in every entry, because a rule the model reads
must never resemble the boundary it reads inside. Its words are DERIVED here
from the delimiter's one home, `kernel.untrusted_content` (the fixed segments of
WRAP_OPEN_AR and WRAP_CLOSE_AR, placeholders dropped), never copied.

ITS LIMIT. A guard proves that its declared words are present and its forbidden
ones absent. It does not prove they are the right words, and nothing here
measures what the model does; that is the behaviour harness's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from muthis.kernel.untrusted_content import WRAP_CLOSE_AR, WRAP_OPEN_AR
from muthis.kernel.verbosity import normalize_ar

DELIMITER_FAMILY = "§3.2 delimiter"


@dataclass(frozen=True)
class Verdict:
    ok: bool
    missing: tuple[str, ...] = ()      # required families absent, by name
    forbidden: tuple[str, ...] = ()    # forbidden families present, by name


Guard = Callable[[str], Verdict]


def tokens(text: str) -> list[str]:
    return normalize_ar(text).split()


def member_tokens(member: str) -> tuple[str, ...]:
    found = tuple(tokens(member))
    if not found:
        raise ValueError(f"a family member normalises to nothing: {member!r}")
    return found


def present(window: Sequence[str], text_tokens: Sequence[str]) -> bool:
    n = len(window)
    return any(tuple(text_tokens[i:i + n]) == tuple(window)
               for i in range(len(text_tokens) - n + 1))


def delimiter_members() -> tuple[str, ...]:
    return tuple(part.strip() for form in (WRAP_OPEN_AR, WRAP_CLOSE_AR)
                 for part in form.strip("[]").split(" — ") if "{" not in part)


def family_name(members: Sequence[str]) -> str:
    return members[0]


def make_guard(required: Sequence[Sequence[str]],
               forbidden: Mapping[str, Sequence[str]]) -> Guard:
    need = [(family_name(f), [member_tokens(m) for m in f]) for f in required]
    deny = [(name, [member_tokens(m) for m in ms]) for name, ms in forbidden.items()]

    def guard(text: str) -> Verdict:
        have = tokens(text)
        missing = tuple(n for n, windows in need if not any(present(w, have) for w in windows))
        hit = tuple(n for n, windows in deny if any(present(w, have) for w in windows))
        return Verdict(not missing and not hit, missing, hit)

    return guard


def forbidden_for(entry: dict) -> dict[str, list[str]]:
    """The shared delimiter family, then the entry's own forbidden families."""
    return {DELIMITER_FAMILY: list(delimiter_members()), **entry.get("forbidden", {})}


def guard_for(entry: dict) -> Guard:
    return make_guard(entry["required"], forbidden_for(entry))
