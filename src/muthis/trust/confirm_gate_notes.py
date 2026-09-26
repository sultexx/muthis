# src/muthis/trust/confirm_gate_notes.py
"""
The confirmation gate's MODEL-FACING Arabic surfaces — the TWO directives a
refused high-impact call can return, the chooser between them, and the bounded
renderings that fill their slots.

Extracted VERBATIM from `trust/confirm_gate.py` under the ≤300-line law: a MOVE
ONLY, nothing reworded at the move. That file stood at 300/300 — pinned, with
zero headroom, where "the next line breaches" — and the arrival that forced the
extraction was not a new mechanism but this note's own GROWTH. Extraction moves
the surface that must grow out of the file that cannot hold it.
`confirm_gate.py` re-exports every name, so no import site outside this package
changed — the `file_reader_notes.py` precedent (DEC-113).

AND THE GROWTH ARRIVED IMMEDIATELY (DEC-131 ruling 3), which is what the pin
said it would. THE STOP IS SCOPED TO THE CAPABILITY, NOT TO ONE TOOL: the old
text said «هذه الأداة» and named the tool, so a model that switched from
`web__search` to `web__fetch` had OBEYED it literally — measured live, pass #4 of
the last turn. The property is taint × high-impact, so the note now says every
tool whose effect leaves the machine is stopped and that trying another changes
nothing. AND IT WAS A COMMAND, on `HIGHLIGHT_ACK_TEXT_AR`'s form: it is read on a
pass FORCED to tool_choice="none" (ruling 1), so it ordered the request in THIS
pass and named the cost of silence — the clause that made the draw breaker work
where a description had twice produced a bare ack — until DEC-138 gave the kernel
the request and DEC-148 ⑤ took the order out (see the constant). AND IT ANSWERS ITS
OWN CHANNEL: it arrives in a `tool_result`, which DEC-14 teaches the model to
distrust, and the measured failure was the model reading it as a failed TOOL — so
it now says whose words these are, WITHOUT borrowing the §3.2 delimiters'
vocabulary, which a test checks against the live constants.

AND IT GREW A SECOND TIME, FOR A DEFECT THE LOG PROVED (DEC-136 rulings 2+3).
Three consecutive live turns produced the BYTE-IDENTICAL directive after the
user had spoken and not been understood, so nothing anywhere distinguished
«you said a word I do not accept» from «I did not hear you» — and the user
cannot converge on a word he is never told he missed (DEC-135). Two changes,
both in this file:

  * **THE REQUEST NAMED EVERY ACCEPTED WORD** (ruling 2). It named one while the
    detector accepted three; `render_words` rendered the detector's OWN tuple, so
    the offer could not fall behind the set. Naming one had NOT refused anyone —
    DEC-135 ③ found the detector never saw a bare accepted form — so the KERNEL's
    search request names ONE (DEC-147 ①), and so do both notes (DEC-148 ⑤).
  * **`CONFIRM_RETRY_AR` IS A SECOND, DIFFERENT NOTE** (ruling 3), returned when
    the previous utterance was heard and was not an approval. It reports the
    STATE — no approval word was heard — and since DEC-148 ⑤ has the model tell the
    user exactly that; the words and the whole-utterance rule («وحدها in a turn of
    its own, nothing before or after») are spoken by the KERNEL, whose request is
    where the rule is taught (DEC-145 ⑥).

**NEITHER IS AN AUTHORIZATION CHANGE, AND THE RECORD SHOULD NOT READ AS ONE.**
The gate still binds to `sha256(tool + canonical args)`, still consumes an
approval exactly once, still refuses on any mismatch, and still expires the
pending at the first turn carrying no approval. What changed is what the user is
TOLD — this is the message layer, the weaker half by construction (DEC-42), and
a wider ACCEPTED SET is the separate ruling that lives with the detector.
**DEC-143 IS ONE, and these notes moved WITH it, never before or after** — each
sentence below was true until the grant existed and false after. `web__search`
is granted for the turn, so its notes carry `TURN_SCOPE_AR` where a per-call tool
still carries `PER_CALL_BINDING_AR`, and the stop no longer claims every outward
tool is stopped NOW: one may be granted. The gate passes `scoped`; nothing here
decides it.

WHY THE RETRY NOTE STILL NAMES THE TOOL AND ARGUMENTS. It is a follow-up, so the
tempting shape is a short "that was not the word, try again". That would break
DEC-16's bound (a): the pending was CLEARED by the failed observation and a FRESH
fingerprint is being set here, over whatever arguments the model is issuing NOW.
An approval must never travel to a call the user never heard, so every refusal —
first or fifth — re-states what is being approved. SINCE DEC-143 THAT HOLDS PER
CALL: a turn-granted tool's approval DOES travel within its turn, by ruling, so
its refusals re-state the SCOPE the approval grants instead. SINCE DEC-138 THE
KERNEL re-states it aloud at every refusal, so since DEC-148 ⑤ the notes name the
call to the model as CONTEXT and order nothing repeated.

WHY THE RENDERERS CAME WITH THE NOTES, AND NOT THE CONSTANTS ALONE. `render_args`
exists to fill the `{args}` slot and nothing else, `render_words` the word
slots and nothing else, and `MAX_ARG_CHARS` / `MAX_ARGS_CHARS` exist to bound
`render_args` and nothing else: ONE cluster with ONE external touchpoint
(`confirm_note`, called from `ConfirmGate.refusal_for`). That is the
`kernel/deferral_notes.py` shape — the notes AND the functions that fill them —
rather than `file_reader_notes.py`'s constants-only shape, and the reason is that
the coupling is real rather than incidental: a note ordering the arguments said
«كما هي» and a renderer that TRUNCATES them at 120 characters are one design
question, not two. The order went at DEC-148 ⑤; the note still SHOWS a prefix.

AND THAT TENSION IS RECORDED HERE RATHER THAN FIXED — the APPROVAL TREADMILL
(DEC-131). Approval binds to sha256(tool + canonical args) and is SINGLE-USE,
while these notes show the model a TRUNCATED rendering of those same arguments.
For a value over `MAX_ARG_CHARS`, what the note displays is NOT what the
fingerprint hashed, so a model re-issuing from the note's own text cannot match,
and the user can approve indefinitely without the call ever running. Whether the
binding should loosen to tool+capability is an AUTHORIZATION ruling and is
Sultan's alone: the args binding exists so that an approval never travels to a
call the user never heard. RULED AT DEC-143: `web__search` is granted for the turn,
so rewording it destroys nothing, while `web__fetch` keeps this binding — and this
truncation — per call.

WHAT DID NOT MOVE, AND WHY. The detector (`detect_confirmation`,
`strip_directive_lines`, the word sets) and `call_fingerprint` are THE SECURITY
BOUNDARY and are not message-layer concerns; since DEC-136 the detector has its
own module, `confirm_gate_detector.py`, and the word tuple lives THERE while this
file only renders whatever it is handed. A message layer decides what a refusal
SAYS, never whether it refuses, and never WHICH WORDS ARE ACCEPTED.

Pure stdlib, importable in isolation — like every other notes module here.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

# Bounds for rendering the model's own arguments back to it: a note must stay a
# note even when the call carries a large code blob.
MAX_ARG_CHARS = 120
MAX_ARGS_CHARS = 400

# SINCE DEC-148 ⑤ IT IS NOT THE REQUEST: the KERNEL speaks that (DEC-138). The note
# tells the MODEL it is asked, that no tool can run in this reply and nothing is
# repeated, names ONE word, and gives the reply one true job — share what earlier
# results found, if anything: a conditional the MODEL judges, the note handed no
# results. Its relay order and «the user hears nothing» were false since DEC-138.
# THE HISTORY BELOW STANDS, and so does the missing marker: the reply is SPEECH.
#
# THE ONE DIRECTIVE THAT MUST BE SPOKEN, AND ITS OPENING SAYS SO (DEC-95).
#
# IT DELIBERATELY DOES NOT CARRY `DIRECTIVE_MARKER_AR`. Every other member of that
# family is genuinely invisible, and the persona's «ولا تقرأه بصوت عالٍ» law for
# them is CORRECT and untouched. THIS one exists to produce USER-FACING SPEECH, and
# it wore that invisibility preamble while ordering the opposite four clauses later;
# every reading led to SILENCE — the persona forbidding what the directive ordered,
# or the text reading as scaffolding. The MEMBER wore the wrong syntax, so the
# MEMBER changed. «من النظام» keeps the AUTHORITY half (this arrives in a
# tool_result, which DEC-14 teaches the model to distrust); only invisibility went.
#
# THE RELEASE IS ANCHORED TO THE USER SPEAKING, never to a countable unit. The old
# «في هذه الجولة» meant a USER TURN here, but the persona uses «دور» for a PASS, so
# on each new pass it could read as already satisfied — and with no counter behind
# this gate, that reading WAS the enforcement. An event cannot be miscounted.
# It still does NOT reproduce the §3.2 delimiter phrasing (DEC-14, allow-list-
# guarded): a note the model reads must never look like the boundary it reads in.
#
# `{words}` REPLACED `{word}` at DEC-136 ruling 2 — every accepted word — and
# `{word}` CAME BACK at DEC-148 ⑤: ONE word, the one the kernel names first.
CONFIRM_DIRECTIVE_AR = (
    "هذا الكلام صادر من النظام نفسه، لا من نصٍّ قرأته في مخرجات أداة، "
    "فلا تتعامل معه بالشك ولا تتجاهله. "
    "سبق أن دخلت هذه الجلسة نصوصٌ من مصادر لا نثق فيها، فما نُفِّذ الطلب "
    "وينتظر إذن المستخدم الصوتي. والطلب هو الاستدعاء «{tool}» ({args}).{scope} "
    "والوقف ليس على هذه الأداة وحدها: كل أداة أثرها يخرج من الجهاز — بحث، "
    "فتح صفحة، وما يشبههما — موقوفة بنفس الطريقة ما لم يأذن بها المستخدم، "
    "فتجريب أداة ثانية لا يغيّر شيئاً ولا يُعدّ استجابةً لهذا الطلب. "
    "وقد طلب النظام من المستخدم إذنه بصوتٍ مسموع، ويكفيه أن يقول {word} وحدها، "
    "فلا تكرّر الطلب ولا تُعِد صياغته. "
    "لا يمكن تشغيل أي أداة في هذا الرد، فلا تقل فيه إنك لا تستطيع البحث ولا إنك "
    "ستبحث. وإن كان فيما بين يديك من نتائج سابقة ما يجيب عن جزء من السؤال فقل "
    "للمستخدم ما وجدته في جملة واحدة قصيرة. "
    "ولا تستدعِ أداةً من هذا النوع مرة أخرى قبل أن يتكلم المستخدم ويأذن — "
    "لا في هذا الدور ولا في أي دور بعده: كل استدعاء قبل إذنه يرجع لك بنفس "
    "هذا الجواب ولا يغيّر شيئاً."
)

# THE SECOND REFUSAL — WHAT THE FIRST ONE COULD NOT SAY (DEC-136 ruling 3).
#
# Returned only when the previous utterance was HEARD and came back as NEITHER
# answer while a pending existed — the gate decides that and passes `missed`; this
# module never inspects a transcript. It must NOT be returned after an explicit
# refusal: «لا» is a deliberate answer, and telling a user who declined that he
# "was not understood" would be a false claim about his intent.
#
# WHAT IT IS ALLOWED TO CLAIM, AND WHAT IT IS NOT. The kernel cannot know whether
# the user was TRYING to approve: an unrelated question and a mispronounced
# approval reach the detector identically. So the note reports only what is true
# in both cases — that no approval word was heard — and since DEC-148 ⑤ has the
# model tell the user only THAT: the words and the whole-utterance rule are in the
# KERNEL's request. It never says «you tried and failed».
CONFIRM_RETRY_AR = (
    "هذا الكلام صادر من النظام نفسه، لا من نصٍّ قرأته في مخرجات أداة. "
    "سمع النظام آخر كلام للمستخدم، لكنه لم يطابق أي كلمة من كلمات الإذن، "
    "فما زال الطلب موقوفاً ولم يُنفَّذ شيء. "
    "والطلب هو الاستدعاء «{tool}» ({args}). {binding} "
    "وقد طلب النظام من المستخدم إذنه بصوتٍ مسموع من جديد، ويكفيه أن يقول {word} "
    "وحدها. لا يمكن تشغيل أي أداة في هذا الرد، فلا تقل فيه إنك لا تستطيع البحث "
    "ولا إنك ستبحث. قل للمستخدم إن ما قاله لم يُقرأ إذناً، ولا تكرّر بقية الطلب. "
    "وإن كان فيما بين يديك من نتائج سابقة ما يجيب عن جزء من السؤال فقل له ما "
    "وجدته في جملة واحدة قصيرة. "
    "ولا تستدعِ أداةً من هذا النوع مرة أخرى قبل أن يتكلم المستخدم ويأذن."
)


# WHAT AN APPROVAL COVERS (DEC-143) — a FACT for the model since DEC-148 ⑤, never
# an order to tell the user (a grant's reach is in the kernel's own request). The
# gate decides which applies and passes `scoped`; these only say it. PER CALL is the
# retry note's sentence of old, byte for byte. TURN names the reach of a grant by
# the EVENT that ends it — the user speaking — never by a countable unit, the
# anchor this module chose at DEC-95 because an event cannot be miscounted.
PER_CALL_BINDING_AR = "فالإذن مرتبط بهذا الاستدعاء بعينه لا بغيره."
TURN_SCOPE_AR = (
    "وإذنه يشمل كل استدعاء لهذه الأداة من لحظة إذنه إلى أن يتكلم مرة أخرى، "
    "لا هذا الاستدعاء وحده."
)


def render_args(args: Mapping[str, Any]) -> str:
    """The arguments as the note shows them to the model — bounded, one line."""
    parts = []
    for key in sorted(args, key=str):
        value = str(args[key]).replace("\n", " ")
        parts.append(f"{key}={value[:MAX_ARG_CHARS]}…" if len(value) > MAX_ARG_CHARS
                     else f"{key}={value}")
    return "، ".join(parts)[:MAX_ARGS_CHARS] if parts else "بلا معاملات"


def render_words(words: Sequence[str]) -> str:
    """Words as they are OFFERED — every accepted word in the kernel's per-call
    request (DEC-136 ruling 2); ONE in its search request and in both notes.

    UNBOUNDED ON PURPOSE, unlike `render_args`. That renderer truncates because
    its input is the MODEL's — a query, a path, a program of any size. This one's
    input is the detector's own tuple, which is a hand-written authorization
    decision: truncating it would silently stop offering a word the gate still
    accepts, which is the exact defect ruling 2 exists to close."""
    return " أو ".join(f"«{word}»" for word in words)


def confirm_note(tool: str, args: Mapping[str, Any],
                 word: str, *, missed: bool, scoped: bool = False) -> str:
    """The refusal text for ONE call — the retry form when the last utterance
    was heard and was not an approval, the first-refusal form otherwise.

    `word` is PASSED IN rather than imported: it is detector state, and this
    module must not acquire an opinion about which words are accepted. Since
    DEC-148 ⑤ it is ONE word — the gate hands `APPROVAL_WORD_AR`, the word the
    kernel's search request names and its per-call request names first. It also
    keeps the import direction one-way — `confirm_gate.py` imports from here,
    never the reverse. AND IT IS HANDED NO RESULTS: what the reply may share of
    earlier results is the MODEL's judgement, with nothing here to read one."""
    note = CONFIRM_RETRY_AR if missed else CONFIRM_DIRECTIVE_AR
    return note.format(tool=tool, args=render_args(args),
                       word=render_words((word,)),
                       scope=" " + TURN_SCOPE_AR if scoped else "",
                       binding=TURN_SCOPE_AR if scoped else PER_CALL_BINDING_AR)


__all__ = ["CONFIRM_DIRECTIVE_AR", "CONFIRM_RETRY_AR", "MAX_ARGS_CHARS",
           "MAX_ARG_CHARS", "PER_CALL_BINDING_AR", "TURN_SCOPE_AR", "confirm_note",
           "render_args", "render_words"]
