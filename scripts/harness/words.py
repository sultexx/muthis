"""
words.py — the text measures the scorer uses, and nothing else: words and digit
runs under the project's own normalizer, sentences, repetition, and the
quoted-word matcher.

Normalization is `kernel.verbosity.normalize_ar` (tashkeel, tatweel, hamza-alif,
ta marbuta, digits, punctuation), applied to the rule and the text alike, so no
normalization of the harness's own enters a match.

COMPUTED TRUTH IS MATCHED AS A DIGIT RUN, NEVER AS A WORD. The normalizer leaves
"=896", "366يوم" and "366-day" as single words, so a word match scores a correct
"f(37)=896" as WRONG — found by the self-test, before any live run.

THE WORD MATCHER'S REACH IS NARROW, AND ITS LIMITS ARE MEASURED (selftest): a
token matches a whole normalized word, or that word behind ONE proclitic
(و ف ب ل); a multi-word token matches a contiguous window. It does not see a
dialect conjugation («بدوّر» for «أدوّر»), a transliteration («دوكر» for
«Docker»), the article on a Latin word («الـDocker») or a hyphenated compound.
So where the design names a structural signal beside a word rule, a
disagreement between them goes to a reader rather than to a side.
"""

from __future__ import annotations

import re

from muthis.kernel.verbosity import normalize_ar

SENTENCE_END = re.compile(r"[.!?؟…]+")
PROCLITICS = ("و", "ف", "ب", "ل")
_DIGITS = re.compile(r"[0-9]+")


def norm_words(text: str) -> list[str]:
    return normalize_ar(text).casefold().split()


def digit_runs(text: str) -> list[str]:
    """Every maximal run of digits, after the normalizer maps Arabic-Indic
    digits: "f(37)=896" → ["37", "896"]; "1896" → ["1896"], never "896"."""
    return _DIGITS.findall(normalize_ar(text))


def has_truth(truth: str, text: str) -> bool:
    return truth in digit_runs(text)


def sentences(text: str) -> int:
    return len([c for c in SENTENCE_END.split(text) if c.strip()])


def first_sentence(text: str) -> str:
    return SENTENCE_END.split(text)[0] if text else ""


def repetition(text: str) -> tuple[float, float]:
    """(distinct-word ratio, repeated-trigram rate) — 1.0 and 0.0 for a text too
    short to repeat anything. The ratio falls with length on ANY text, so it is
    read beside the trigram rate, never alone."""
    words = norm_words(text)
    if not words:
        return 1.0, 0.0
    trigrams = [tuple(words[i:i + 3]) for i in range(len(words) - 2)]
    distinct = len(set(words)) / len(words)
    repeated = 1 - len(set(trigrams)) / len(trigrams) if trigrams else 0.0
    return distinct, repeated


def tokens_match(tokens, position: str, text: str) -> bool:
    words = norm_words(text)
    for token in tokens:
        tw = norm_words(token)
        if not tw:
            continue
        if position == "opening":
            head = words[:len(tw)]
            if head == tw or (len(tw) == 1 and head
                              and head[0] in {p + tw[0] for p in PROCLITICS}):
                return True
            continue
        for i in range(len(words) - len(tw) + 1):
            window = words[i:i + len(tw)]
            if window == tw:
                return True
            if len(tw) == 1 and window[0] in {p + tw[0] for p in PROCLITICS}:
                return True
    return False


def rule_matches(rule, text: str) -> bool:
    return tokens_match(rule.tokens, rule.position, text)


__all__ = ["PROCLITICS", "SENTENCE_END", "digit_runs", "first_sentence", "has_truth",
           "norm_words", "repetition", "rule_matches", "sentences", "tokens_match"]
