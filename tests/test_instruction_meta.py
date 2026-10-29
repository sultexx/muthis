"""
test_instruction_meta.py — THE META-TEST: every registry guard FIRES (DEC-157,
the standard approved after the facts round).

A guard that has never fired is not a guard. The shared checker builds each
entry's guard from its declared families (`src/muthis/instructions/guard.py`);
this file runs every guard through SEVEN checks, in-process, mutating no file:

  1. the real text passes;
  2. the empty string fails;
  3. same-length FILLER fails: every character becomes U+0640, newlines kept
     (DEC-139's method). Its self-check runs too: normalize_ar strips U+0640, so
     no family token can survive in the filler;
  4. with each required family's words replaced by filler, the guard fails and
     NAMES that family;
  5. with one forbidden member spliced in, the guard fails and names its family;
  6. with one word that belongs to no family replaced, the guard still PASSES —
     the check that rejects a byte-hash guard, which passes 2-5. An entry with no
     such word is REPORTED (`NO_FREE_WORD`), never skipped;
  7. locality: with this entry's slot blanked in the full rendering, only this
     entry's guard fails.

THE POSITIVE CONTROL. Six deliberately broken guards must each be rejected AT
ITS STATED CHECK, and a correct reference guard, whose matching is written
independently of the checker's, must be accepted, so a meta-test that rejects
everything cannot pass.

ITS LIMIT. This proves each guard responds to its own declared words and
ignores everything else. It does not prove they are the right words, or
anything about the model's behaviour.

Run:  set PYTHONPATH=src && python -m pytest tests/test_instruction_meta.py -q
"""

from __future__ import annotations

import hashlib
import re

import pytest

from muthis.instructions import guard as G
from muthis.instructions import render as R
from muthis.kernel.verbosity import normalize_ar
from muthis.persona import build_saudi_persona_prompt

SIZE = (1280, 720)
FILLER = "ـ"
STRANGER = "ززز"          # check 6's replacement: in no family, and no word of the prompt
REG = R.load()
GUARDED = [e for e in REG["entries"] if "required" in e]
REAL = {e["id"]: G.guard_for(e) for e in GUARDED}

# REPORTED, not skipped: a one-word heading whose word IS its family has no word
# to replace, so check 6 cannot run on it, and a byte-hash guard on it would go
# undetected. The set is pinned so that a new such entry is seen, not absorbed.
NO_FREE_WORD = {
    "C002": "a one-word heading (the dialect section); its word is its only family",
    "C010": "a one-word heading (the coordinates section); its word is its only family",
}


def text_of(entry: dict) -> str:
    return R.entry_text(entry, *SIZE)


def filler(text: str) -> str:
    return "".join(c if c == "\n" else FILLER for c in text)


def words(text: str) -> list[tuple[int, int, list[str]]]:
    """Each whitespace-delimited word of the RAW text, with its normalised tokens."""
    return [(m.start(), m.end(), G.tokens(m.group())) for m in re.finditer(r"\S+", text)]


def covered(ws: list, members) -> set[int]:
    """The words any member's token window covers — what check 4 blanks."""
    flat = [(token, i) for i, (_, _, toks) in enumerate(ws) for token in toks]
    hit = set()
    for member in members:
        window = G.member_tokens(member)
        for k in range(len(flat) - len(window) + 1):
            if tuple(t for t, _ in flat[k:k + len(window)]) == window:
                hit.update(i for _, i in flat[k:k + len(window)])
    return hit


def blank(text: str, ws: list, indices: set[int]) -> str:
    out = list(text)
    for i in indices:
        start, end, _ = ws[i]
        out[start:end] = FILLER * (end - start)
    return "".join(out)


def free_word(entry: dict, ws: list) -> int | None:
    families = list(entry["required"]) + list(G.forbidden_for(entry).values())
    taken = {t for f in families for m in f for t in G.member_tokens(m)}
    for i, (_, _, toks) in enumerate(ws):
        if toks and not set(toks) & taken and any(c.isalpha() for c in "".join(toks)):
            return i
    return None


def first_rejection(entry: dict, guard) -> tuple[int, str] | None:
    """The first of the seven checks `guard` fails on `entry`; None if none."""
    text, ws = text_of(entry), words(text_of(entry))
    if not guard(text).ok:
        return 1, "the real text fails"
    if guard("").ok:
        return 2, "the empty string passes"
    if guard(filler(text)).ok:
        return 3, "same-length filler passes"
    for family in entry["required"]:
        verdict = guard(blank(text, ws, covered(ws, family)))
        if verdict.ok or G.family_name(family) not in verdict.missing:
            return 4, f"removing family «{G.family_name(family)}» is not failed by name"
    at = ws[len(ws) // 2][0]
    for name, members in G.forbidden_for(entry).items():
        for member in members:
            verdict = guard(text[:at] + member + " " + text[at:])
            if verdict.ok or name not in verdict.forbidden:
                return 5, f"splicing «{member}» is not failed by name «{name}»"
    i = free_word(entry, ws)
    if i is not None and not guard(text[:ws[i][0]] + STRANGER + text[ws[i][1]:]).ok:
        return 6, "replacing a word that belongs to no family fails"
    blanked = {**REG, "entries": [{**e, "text": ""} if e["id"] == entry["id"] else e
                                  for e in REG["entries"]]}
    full, spans = R.render(blanked, *SIZE), R.slots(blanked, *SIZE)
    for other in GUARDED:
        start, end = spans[other["id"]]
        own = other["id"] == entry["id"]
        if (guard if own else REAL[other["id"]])(full[start:end]).ok == own:
            return 7, ("its own guard passes with its slot blanked" if own
                       else f"blanking it fails the guard of {other['id']}")
    return None


# ─── The real guards ─────────────────────────────────────────────────────────

def test_the_filler_self_check_no_token_survives_normalisation():
    assert all(normalize_ar(filler(text_of(e))) == "" for e in REG["entries"])


def test_the_word_split_agrees_with_the_checker_token_for_token():
    """Check 4 blanks RAW words; it may only do so if they carry exactly the
    tokens the guard reads."""
    for entry in REG["entries"]:
        text = text_of(entry)
        assert [t for _, _, toks in words(text) for t in toks] == G.tokens(text), entry["id"]


@pytest.mark.parametrize("entry", GUARDED, ids=[e["id"] for e in GUARDED])
def test_every_guard_fires(entry):
    rejected = first_rejection(entry, REAL[entry["id"]])
    assert rejected is None, f"{entry['id']}: rejected at check {rejected[0]}: {rejected[1]}"


def test_entries_with_no_free_word_are_reported_not_skipped():
    found = {e["id"] for e in GUARDED if free_word(e, words(text_of(e))) is None}
    assert found == set(NO_FREE_WORD), f"check 6 cannot run on {sorted(found)}"


# ─── The positive control ────────────────────────────────────────────────────

def _disabled(entry):
    return lambda text: G.Verdict(True)


def _length_only(entry):
    size = len(text_of(entry))
    return lambda text: G.Verdict(len(text) == size)


def _byte_hash(entry):
    """Fails on ANY byte change and then names EVERY family, so it passes checks
    2-5 exactly as a real guard would."""
    pinned = hashlib.sha256(text_of(entry).encode()).hexdigest()
    names = tuple(G.family_name(f) for f in entry["required"])
    denied = tuple(G.forbidden_for(entry))
    return lambda text: (G.Verdict(True) if hashlib.sha256(text.encode()).hexdigest() == pinned
                         else G.Verdict(False, names, denied))


def _first_family_only(entry):
    return G.make_guard(entry["required"][:1], {})


def _reads_the_live_prompt(entry):
    start, end = R.slots(REG, *SIZE)[entry["id"]]
    return lambda text: REAL[entry["id"]](build_saudi_persona_prompt(*SIZE)[start:end])


def _fails_without_naming(entry):
    return lambda text: G.Verdict(REAL[entry["id"]](text).ok)


CONTROLS = [(_disabled, 2), (_length_only, 3), (_byte_hash, 6), (_first_family_only, 4),
            (_reads_the_live_prompt, 2), (_fails_without_naming, 4)]
# Every stated check is reachable only where the entry has two families (control 4)
# and a free word (control 3): every guarded entry except the reported two.
BITE = [e for e in GUARDED if len(e["required"]) >= 2 and e["id"] not in NO_FREE_WORD]


def test_the_controls_bite_on_every_entry_but_the_reported_two():
    assert {e["id"] for e in GUARDED} - {e["id"] for e in BITE} == set(NO_FREE_WORD)


@pytest.mark.parametrize("make,check", CONTROLS, ids=[m.__name__.strip("_") for m, _ in CONTROLS])
def test_each_broken_guard_is_rejected_at_its_stated_check(make, check):
    wrong = {e["id"]: first_rejection(e, make(e)) for e in BITE}
    wrong = {k: v for k, v in wrong.items() if v is None or v[0] != check}
    assert not wrong, f"{make.__name__}: not rejected at check {check} on {wrong}"


def _reference(entry):
    """A correct guard whose MATCHING shares no code with the checker's: a
    whole-token regex over the normalised string."""
    forbidden = G.forbidden_for(entry)

    def has(member, norm):
        return re.search(r"(?<!\S)" + re.escape(normalize_ar(member)) + r"(?!\S)", norm) is not None

    def guard(text):
        norm = normalize_ar(text)
        missing = tuple(f[0] for f in entry["required"] if not any(has(m, norm) for m in f))
        hit = tuple(n for n, ms in forbidden.items() if any(has(m, norm) for m in ms))
        return G.Verdict(not missing and not hit, missing, hit)
    return guard


def test_the_correct_reference_guard_is_accepted_on_every_entry():
    rejected = {e["id"]: r for e in GUARDED if (r := first_rejection(e, _reference(e)))}
    assert not rejected, f"the reference guard was rejected: {rejected}"
