# src/muthis/trust/confirm_gate.py
"""
ConfirmGate — the TWO-TURN confirmation for a high-impact call under an active
session taint (DEC-16, delivering the path DEC-10 deferred to this milestone).

WHY TWO TURNS AND NOT A VOICE PROMPT. A blocking mid-turn "yes/no" was REJECTED
by name: F9 is reserved for barge-in and must not become state-dependent,
`is_processing` refuses re-entry, `TurnVoice` is ONE continuous generation per
turn, and the turn lives inside a 90 s bound. A prompt that waits for speech
would dismantle all four. So the gate spends the turn it already has:

  TURN N    the router REFUSES the call and returns an INTERNAL-DIRECTIVE Arabic
            note that names the tool, names its arguments, names the EXACT word
            to ask for, and forbids repeating the call this turn. The model
            speaks the request; nothing executed.
  TURN N+1  the user presses F9 normally and speaks. A DETERMINISTIC detector
            reads the RAW transcript and decides. The model never participates
            in its own authorization — DEC-12 ("drive the guard directly, never
            through model judgment") applied to authorization.

THE DETECTOR IS THE SECURITY BOUNDARY, so its shape is deliberate:

  * STRIP, THEN ISOLATE. `turn_pass` hands over `user_input`, which by then is
    the transcript PLUS any kernel-authored directive lines the orchestrator
    prepended (the verbosity directive; `INTERRUPTED_NOTE_AR` after a barge-in).
    Whole-utterance isolation on THAT would refuse every approval spoken while
    sticky SHORT/DETAILED is on. So directive lines are dropped first — they all
    carry the `DIRECTIVE_MARKER_AR` family marker — and isolation then applies to
    the remainder, which is exactly the bare transcript. The user's ENTIRE
    utterance must be the approval word.
  * THE FAILURE IS ASYMMETRIC BY CONSTRUCTION. If a future directive ever omits
    the marker, its line survives the strip, the remainder no longer EQUALS the
    approval word, and the call is refused: a FALSE NEGATIVE (friction), never a
    FALSE POSITIVE (an authorization bypass). Every unknown lands on the safe
    side, and a test feeds an unstripped prefix to prove it.
  * THE WORD SET IS NARROW ON PURPOSE and must not be widened. Colloquial
    affirmatives («تمام», «أيه», «زين», «نعم») occur constantly in unrelated
    speech; each one added is an accidental authorization waiting for a
    coincidence. Refusal words may be broader — a false refusal is friction.
    Narrowness is only humane because the turn-N directive NAMES the word, so
    the user is told exactly what to say: low false-positives AND low friction.

BINDING. Approval is pinned to a sha256 of (tool name + canonical arguments) —
the grants-store pattern, applied to a CALL instead of a manifest — so a MODIFIED
call needs fresh approval, exactly as a changed manifest invalidates a grant. It
is SINGLE-USE (consumed on match), the pending state EXPIRES at the first turn
that carries no approval, and an explicit refusal clears it at once.

HONEST LIMIT, recorded rather than hidden (DEC-16): the model is the MESSENGER.
It speaks the confirmation request, so a model already under injection could word
it misleadingly — the user might approve a call described as something milder
than it is. Two things bound the damage: the directive orders the tool and its
arguments named ALOUD, and the approval binds to the hash of the REAL call, not
to whatever was said about it. Removing the limit entirely requires the KERNEL to
author the spoken confirmation, which means touching `TurnVoice` — recorded as
POST-LAUNCH research ("kernel-authored confirmation"), accepted for launch.

Nothing here is logged but tool NAMES and decisions: arguments carry the model's
query, which is the user's private question (DEC-20/DEC-28), so they reach the
model's context and never a log line.

`normalize_ar` is imported from the kernel's verbosity module rather than
re-implemented: a second home for a security-relevant text transform is how the
two drift, and the STT tolerance it provides (tashkeel, hamza forms, tatweel,
Arabic-Indic digits, punctuation) is already pinned by `test_verbosity.py`.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from typing import Any, Mapping, Optional

from ..kernel.verbosity import normalize_ar

logger = logging.getLogger("muthis.trust.confirm_gate")

# The family marker every kernel-authored directive line carries. It is the
# SHARED CORE of the family, not one member's exact opening: `DIRECTIVE_OPEN_AR`
# (verbosity) and `INTERRUPTED_NOTE_AR` (barge-in) word their openings
# differently, and matching either one exactly would leave the other in place. A
# test pins that both real constants contain this.
DIRECTIVE_MARKER_AR = "توجيه داخلي"

APPROVE = "approve"
REFUSE = "refuse"

# The word the turn-N directive tells the user to SAY. Because the accepted set
# below is normalized with the same function, the named word is always accepted.
APPROVAL_WORD_AR = "أوافق"

# Written in natural spelling and normalized once at import — readable here,
# STT-tolerant at match time, and impossible to spell inconsistently.
_APPROVALS = frozenset(normalize_ar(word) for word in ("أوافق", "موافق", "وافق"))
_REFUSALS = frozenset(normalize_ar(word) for word in ("ألغِ", "لا توافق", "لا"))

# Bounds for rendering the model's own arguments back to it: a note must stay a
# note even when the call carries a large code blob.
MAX_ARG_CHARS = 120
MAX_ARGS_CHARS = 400

# NOTE the wording: it deliberately does NOT reproduce the §3.2 wrapper's
# delimiter phrasing. That form has exactly one home (DEC-14, allow-list-guarded)
# and a note the model reads must never look like the boundary it reads inside.
_CONFIRM_DIRECTIVE_AR = (
    "توجيه داخلي (لا يراه المستخدم): هذه الأداة عالية الأثر، وسبق أن دخلت هذه "
    "الجلسة بياناتٌ من مصادر خارجية لا نثق فيها، فما نُفِّذ الطلب وينتظر إذن "
    "المستخدم الصوتي. لا تعِد "
    "استدعاء الأداة في هذه الجولة. الآن اطلب الإذن بصوتك: اذكر اسم الأداة "
    "«{tool}» ومعاملاتها كما هي ({args})، واطلب منه أن يقول كلمة «{word}» "
    "وحدها في الجولة القادمة ليُنفَّذ الطلب."
)


def strip_directive_lines(text: str) -> str:
    """Drop every kernel-authored directive line, leaving the bare transcript.

    Directives are always prepended as WHOLE lines by the orchestrator
    (`verbosity.attach` and the barge-in note both join with "\\n"), and neither
    constant contains a newline of its own, so a line-wise filter removes exactly
    them. A line the filter does not recognise SURVIVES, which is what makes the
    unknown case fail closed at the isolation step."""
    return "\n".join(line for line in text.splitlines()
                     if DIRECTIVE_MARKER_AR not in line)


def detect_confirmation(text: str) -> Optional[str]:
    """APPROVE / REFUSE / None for one raw transcript — pure, no state.

    Whole-utterance isolation: the normalized remainder must EQUAL a word in the
    set. An approval word inside a longer sentence is not an approval — the same
    rule that stops «أي ضلع أطول؟» from flipping verbosity, applied where the
    stakes are authorization rather than reply length."""
    utterance = normalize_ar(strip_directive_lines(text))
    if utterance in _APPROVALS:
        return APPROVE
    if utterance in _REFUSALS:
        return REFUSE
    return None


def call_fingerprint(tool: str, args: Mapping[str, Any]) -> str:
    """The pin: sha256 over the tool name + its CANONICAL arguments.

    `sort_keys` makes two equal argument dicts hash equal whatever order the
    stream produced them in; `default=str` keeps an exotic value from raising.
    A value that defeats even that falls back to `repr`, which is
    insertion-ordered — so the worst case is two equal calls hashing apart, i.e.
    a re-confirmation (friction), never two different calls hashing together."""
    try:
        canonical = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001 — a gate must never raise into a turn
        canonical = repr(args)
    return hashlib.sha256(f"{tool}\n{canonical}".encode("utf-8")).hexdigest()


def _render_args(args: Mapping[str, Any]) -> str:
    """The arguments as the model must say them aloud — bounded, single-line."""
    parts = []
    for key in sorted(args, key=str):
        value = str(args[key]).replace("\n", " ")
        parts.append(f"{key}={value[:MAX_ARG_CHARS]}…" if len(value) > MAX_ARG_CHARS
                     else f"{key}={value}")
    return "، ".join(parts)[:MAX_ARGS_CHARS] if parts else "بلا معاملات"


@dataclasses.dataclass(frozen=True)
class _Pending:
    """The ONE call awaiting the user's word. Replaced, never queued: a second
    high-impact call supersedes the first, so an unapproved call can never sit
    behind another waiting to be released by an unrelated approval."""

    fingerprint: str
    tool: str
    approved: bool = False


class ConfirmGate:
    """Built ONCE at the composition root and injected into the router, beside
    the DEC-14 wrap and the DEC-15 taint — one place to audit every security
    consequence of a tool call. Never raises (Law 11)."""

    def __init__(self) -> None:
        self._pending: Optional[_Pending] = None
        # Nothing to observe until a turn arms it: a stray observe() before the
        # first turn must not spend the turn's one look.
        self._observed_this_turn = True

    @property
    def pending_tool(self) -> Optional[str]:
        """The tool awaiting approval, for tests and logs — never the args."""
        return self._pending.tool if self._pending is not None else None

    def new_turn(self) -> None:
        """Arm the coming turn's ONE observation.

        Called from the SAME per-turn hook that resets the sandbox gate
        (`TurnPass.new_turn_voice`) — DEC-19 forbids inventing a second
        turn-boundary mechanism, and this one is proven live."""
        self._observed_this_turn = False

    def observe(self, user_text: str) -> None:
        """The turn's ONE look at the raw transcript.

        ONE-SHOT on purpose: `consume()` runs once per agentic PASS, and a
        continuation pass carries either empty text or the refresh follow-up
        constant. Without the one-shot those passes would count as "a turn
        carrying no approval" and expire the pending state INSIDE the very turn
        that created it, so the approval could never arrive.

        A turn that never delivers a transcript neither approves nor expires —
        expiry is driven by an utterance the user actually spoke."""
        if self._observed_this_turn:
            return
        self._observed_this_turn = True
        if self._pending is None:
            return
        decision = detect_confirmation(user_text)
        if decision == APPROVE:
            self._pending = dataclasses.replace(self._pending, approved=True)
            logger.info("[confirm-gate] approval heard for %s", self._pending.tool)
            return
        # An explicit refusal and a silent turn both clear the pending state, but
        # they stay separate branches: DEC-16 states them as two rules, and only
        # one of them would survive a change to the expiry policy.
        logger.info("[confirm-gate] %s for %s — pending cleared",
                    "refusal heard" if decision == REFUSE else "no approval this turn",
                    self._pending.tool)
        self._pending = None

    def refusal_for(self, tool: str, args: Mapping[str, Any], *,
                    high_impact: bool, tainted: bool) -> Optional[str]:
        """The router's chokepoint: the Arabic refusal note, or None to proceed.

        Both conditions must hold. A high-impact call in a CLEAN session runs
        untouched, and so does every contained call in a tainted one — which is
        how a network-less sandbox run keeps its friction-free loop (DEC-15's
        refinement of DEC-3-A)."""
        if not (high_impact and tainted):
            return None
        fingerprint = call_fingerprint(tool, args)
        pending = self._pending
        if pending is not None and pending.approved and pending.fingerprint == fingerprint:
            self._pending = None      # SINGLE-USE: consumed the moment it matches
            logger.info("[confirm-gate] approved call released: %s", tool)
            return None
        # Any mismatch — no pending, not yet approved, or DIFFERENT arguments —
        # refuses and (re)places the pending. Rebinding on a modified call is the
        # point: an approval must never travel to a call the user never heard.
        self._pending = _Pending(fingerprint=fingerprint, tool=tool)
        logger.info("[confirm-gate] high-impact %s refused — awaiting spoken approval", tool)
        return _CONFIRM_DIRECTIVE_AR.format(
            tool=tool, args=_render_args(args), word=APPROVAL_WORD_AR)


__all__ = [
    "APPROVAL_WORD_AR",
    "APPROVE",
    "ConfirmGate",
    "DIRECTIVE_MARKER_AR",
    "MAX_ARGS_CHARS",
    "MAX_ARG_CHARS",
    "REFUSE",
    "call_fingerprint",
    "detect_confirmation",
    "strip_directive_lines",
]
