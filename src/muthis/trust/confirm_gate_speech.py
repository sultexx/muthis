# src/muthis/trust/confirm_gate_speech.py
"""
What the KERNEL ITSELF says when it refuses a high-impact call (DEC-138).

THE MODULE EXISTS BECAUSE OF A CONSTRAINT, NOT A PREFERENCE, and the constraint
was MEASURED rather than argued: `speakable` below must round-trip the canonical
form through JSON, `confirm_gate_notes.py` is import-locked to `__future__` and
`typing` by its own structural guard, and `confirm_gate.py` MEASURED 314 with
DEC-138 applied — a breach of the 300-line LAW, not merely of its pin. Relaxing
the notes module's guard was REFUSED BY NAME — a guard is never lowered to let
work through. So the arrival became an extraction, on the two precedents this same
gate already produced: `confirm_gate_notes.py` (DEC-131) and
`confirm_gate_detector.py` (DEC-136). The binding left the same commit-pair for
a different reason — a SECOND CONSUMER — and `call_binding.py` is its home.

WHY THE ROUND TRIP IS NOT OPTIONAL, and it is the finding that decided the
shape. `json.loads` turns `true` back into Python `True`, and `str(True)` is
"True" — so a renderer that stringified the parsed values would REINTRODUCE the
divergence inside the fix meant to remove it. Each value is therefore
RE-ENCODED, which puts it back into exactly the form that was hashed.

THE FOUR AXES, measured against `render_args` rather than supposed, and they are
why lifting a truncation bound would have fixed NOTHING: `str(True)` is "True"
where JSON is `true`; `str(None)` is "None" where JSON is `null`; a nested dict
is Python `repr` with single quotes where JSON uses double; and a spoken
renderer flattens newlines. TWO OF THE FOUR BITE ON SHORT VALUES, where no
bound is involved at all.

THE PROPERTY THIS MODULE EXISTS TO HOLD: nothing here ever receives `args`.
`speakable` is handed the canonical STRING — the same bytes the fingerprint was
taken over — so it is structurally unable to describe a payload the approval
does not cover. Divergence is an ABSENCE OF MEANS, not a check somebody could
delete. `render_args` in the notes module is the deliberate contrast: it takes
the dict, it feeds a note the MODEL reads, and it is untouched (DEC-42).

THE CAPTION. Everything spoken is also SHOWN — `VoiceOut.speak` captions at its
first statement and `TurnVoice._feed` captions every sentence, and no
per-utterance suppression exists. DEC-20 restricted the domain badge to the
DOMAIN because a URL can carry the user's private query, so this text reaching
the caption bar is a NARROW, EXPLICIT EXCEPTION ruled for THIS SURFACE ALONE
(DEC-138). Four grounds, recorded where the text is: DEC-20 ruled on an
UNREQUESTED surface and this is an AUTHORIZATION DECISION, where hiding it means
approving what you cannot see; the arguments are ALREADY ordered spoken, so
suppressing the caption would hide from the eye what stays in the ear; the
caption is EPHEMERAL — no disk, no bug report, which is DEC-61's own
permanence-and-audience test; and the alternative is worse, because a decision
that can be heard but not read leaves a user who mishears with no recourse.
IT GENERALISES TO NO OTHER KERNEL SPEECH, AND DEC-20'S BADGE RULING STANDS.

IT IS A SERIALISATION, NEVER A SUMMARY. No paraphrase, no selection, no
translation: the kernel STORES, NUMBERS and BOUNDS-CHECKS and never INTERPRETS
TEXT (DEC-66), and `step_verification.py` refuses the same temptation one domain
over. Whether to call, what arguments to compose and any framing of why all stay
with the MODEL; this module only says what the model already chose.

Stdlib plus ONE sibling — `render_words`, imported rather than copied so a word
cannot be ACCEPTED without being OFFERED (DEC-136 ruling 2). Never raises.
"""

from __future__ import annotations

import json
from typing import Sequence

from .confirm_gate_notes import render_words

# THE SENTENCE THE KERNEL SPEAKS. It is NOT `CONFIRM_DIRECTIVE_AR` in another
# register: that constant ORDERS THE MODEL to ask, and this one IS the asking.
# So it drops every clause addressed to the model — the "these are the system's
# own words, do not distrust them" framing exists because the directive arrives
# in a `tool_result` the model is taught to distrust (DEC-14), and a sentence
# the kernel speaks reaches the user through the mouth with no such channel to
# defend. It names EVERY accepted word, for DEC-136 ruling 2's reason exactly.
SPOKEN_REQUEST_AR = (
    "وقفت طلباً لأنه يحتاج إذنك. الأداة «{tool}»، ومعاملاتها: {args}. "
    "إن أذنت فقل {words} — كلمة واحدة وحدها في دور مستقل، بلا أي كلام "
    "قبلها أو بعدها، فالجملة التي تحوي الكلمة لا تُقرأ إذناً."
)

# AN ABBREVIATION MUST DECLARE ITSELF IN WORDS, NEVER IN AN ELLIPSIS. A trailing
# «…» is INAUDIBLE, so the cut `render_args` makes is silent to the ear and a
# user hearing a truncated target cannot know he heard a prefix. Three
# declarations, each answering a question the cut otherwise leaves open: THAT it
# was cut, HOW MUCH was left out, and WHICH argument is partial — which is why
# argument NAMES are never abbreviated, only their values.
SPOKEN_CUT_AR = " (قرأتُ أول {spoken} حرفاً من «{key}»، وبقي {omitted} حرفاً لم أنطقها)"

# The bound on ONE spoken value. Deliberately larger than `MAX_ARG_CHARS`: that
# one bounds a note the MODEL reads, where brevity costs nothing, while this
# bounds what a HUMAN must hold in his head while deciding — and a URL cut
# shorter than its path is a target he cannot recognise.
MAX_SPOKEN_VALUE_CHARS = 160


def _spoken_value(key: str, text: str) -> str:
    """One value, flattened to a line and bounded with its cut DECLARED."""
    flat = text.replace(chr(10), " ")
    if len(flat) <= MAX_SPOKEN_VALUE_CHARS:
        return flat
    return flat[:MAX_SPOKEN_VALUE_CHARS] + SPOKEN_CUT_AR.format(
        spoken=MAX_SPOKEN_VALUE_CHARS, key=key,
        omitted=len(flat) - MAX_SPOKEN_VALUE_CHARS)


def speakable(canonical: str) -> str:
    """The arguments as the USER must hear them — derived from the canonical
    bytes and from NOTHING ELSE.

    IT DOES NOT TAKE `args`, AND THAT IS THE WHOLE PROPERTY. See the module
    docstring for why the values are RE-ENCODED rather than `str()`-ed.

    A canonical string that will not parse is `canonical_call`'s `repr`
    fallback; it is spoken whole under the same bound, because the alternative —
    saying nothing about the arguments — is the silent case this design exists
    to end."""
    try:
        parsed = json.loads(canonical)
    except Exception:  # noqa: BLE001 — a note must never raise into a turn
        parsed = None
    if not isinstance(parsed, dict):
        return _spoken_value("", canonical)
    if not parsed:
        return "بلا معاملات"
    return "، ".join(
        f"{key}={_spoken_value(key, json.dumps(value, ensure_ascii=False))}"
        for key, value in parsed.items())


def spoken_request(tool: str, canonical: str, words: Sequence[str]) -> str:
    """The kernel's OWN sentence for one refused call.

    `canonical` rather than `args`, for the reason above. The tool name is the
    model-visible one the router dispatched on, so the name the user hears is
    the name the fingerprint covers.

    ONE FORM, NOT TWO (DEC-138 ruling 2). The notes module carries a retry
    variant because the MODEL might not relay the first request; the KERNEL
    always relays, so the case that split covers cannot arise here. A wrong word
    is still answered by the existing textual retry note."""
    return SPOKEN_REQUEST_AR.format(tool=tool, args=speakable(canonical),
                                    words=render_words(words))


__all__ = ["MAX_SPOKEN_VALUE_CHARS", "SPOKEN_CUT_AR", "SPOKEN_REQUEST_AR",
           "speakable", "spoken_request"]
