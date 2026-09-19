# src/muthis/trust/confirm_gate.py
"""
ConfirmGate — the TWO-TURN confirmation for a high-impact call under an active
session taint (DEC-16, delivering the path DEC-10 deferred to this milestone).

WHY TWO TURNS AND NOT A VOICE PROMPT. A blocking mid-turn "yes/no" was REJECTED
by name: F9 is reserved for barge-in and must not become state-dependent,
`is_processing` refuses re-entry, `TurnVoice` is ONE continuous generation per
turn, and the turn lives inside a 90 s bound. A prompt that waits for speech
would dismantle all four. So the gate spends the turn it already has:

  TURN N    the router REFUSES the call and returns an Arabic note that is
            addressed TO THE USER and says so in its first clause — it names the
            tool, its arguments and the EXACT words to ask for, and it refuses
            further calls until the user speaks. The model speaks the request;
            nothing executed. It is NOT an internal directive and deliberately
            does not carry that family's marker — see the constant.
  TURN N+1  the user presses F9 normally and speaks. A DETERMINISTIC detector
            reads the RAW transcript and decides. The model never participates
            in its own authorization — DEC-12 ("drive the guard directly, never
            through model judgment") applied to authorization.

THE DETECTOR LIVES IN `confirm_gate_detector.py` SINCE DEC-136, and so does the
accepted-word tuple: the ≤300-line law forced the split, and the seam is the
right one because "what counts as consent" is exactly what an auditor should be
able to read end to end. Every name is re-exported below, so no call site
outside this package changed. Read that module before touching anything about
which words are accepted; read `confirm_gate_notes.py` for what is SAID.

BINDING. Approval is pinned to a sha256 of (tool name + canonical arguments) —
the grants-store pattern, applied to a CALL instead of a manifest — so a MODIFIED
call needs fresh approval, exactly as a changed manifest invalidates a grant. It
is SINGLE-USE (consumed on match), the pending state EXPIRES at the first turn
that carries no approval, and an explicit refusal clears it at once.

**DEC-136 CHANGED NONE OF THAT, AND THE RECORD SHOULD NOT READ AS IF IT DID.**
Its three rulings are a wider accepted SET (the detector), a request that names
every word in it (the notes), and a SECOND refusal note for a heard-but-not-
approving utterance (`_missed`, below). The fingerprint, the single-use rule, the
expiry and the refusal condition are byte-for-byte what they were. It is a
detection-surface and wording change, not a loosening. The canonical form and
the hash over it live in `call_binding.py` since DEC-138; nothing about the
binding changed with the move.

HONEST LIMIT, recorded rather than hidden (DEC-16): the model is the MESSENGER.
It speaks the confirmation request, so a model already under injection could word
it misleadingly — the user might approve a call described as something milder
than it is. Two things bound the damage: the directive orders the tool and its
arguments named ALOUD, and the approval binds to the hash of the REAL call, not
to whatever was said about it. Removing the limit entirely required the KERNEL to
author the spoken confirmation, which was taken to mean touching `TurnVoice` —
recorded as POST-LAUNCH research ("kernel-authored confirmation"), accepted for
launch. **DEC-135 measured the messenger WORKING on `claude` and failing on `luna`,
so the kernel-messenger case was NOT made; a prompt half that holds on one model and
not the other is precisely a non-guarantee.** SUPERSEDED by DEC-138, which built it
without touching `TurnVoice`; the limit is BOUNDED now, not gone (DEC-138 ⑤).

THE LIMIT MATERIALISED IN PRODUCTION, and this file's constant is what changed
(DEC-95). A live session logged `high-impact web__search refused — awaiting spoken
approval` repeatedly, then `agentic cap (4) hit`: the search never ran, four passes
were spent, and the user never perceived a request. This directive WAS the ONLY
channel, so a refusal could fail SILENTLY for EVERY high-impact tool — SUPERSEDED
by DEC-138, which gave the kernel its own spoken request (`confirm_gate_speech.py`).
OPEN ITEM, NOT TAKEN HERE: this gate has NO COUNTER (`FetchGate` and `SandboxGate`
become TERMINAL; this one refuses identically forever, while taint is sticky with
no clearing path — once per TURN now: DEC-131's brake SUPERSEDED the retrying
model that spent every pass until `AGENTIC_CAP_NOTE_AR` told the user to ask
again). A counter changes an AUTHORIZATION path and is a ruling, so it is
deliberately not taken beside a wording fix. **DEC-136 ruling 3 makes the repeats
DISTINGUISHABLE; it does not make them FINITE, and those are different defects.**

AND THE ACCEPT BRANCH HAD NEVER RUN LIVE when DEC-135 counted: `approval heard`
ZERO times across the durable log — 21 sessions, 78 turns. SUPERSEDED after
DEC-138 by that same log: two approvals heard — the first released its call and
it ran; the second was DESTROYED when the re-issued arguments differed and the
rebind below replaced it. 1 of 2 live: weigh that before trusting the flow.

Nothing here is logged but tool NAMES and decisions: arguments carry the model's
query, which is the user's private question (DEC-20/DEC-28), so they reach the
model's context and never a log line.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Mapping, Optional

# ─── The DETECTOR, EXTRACTED ─────────────────────────────────────────────────
# Moved to `confirm_gate_detector.py` at DEC-136 — a MOVE plus the ruling that
# forced it, with the word tuple as its centre. Re-exported here so every
# existing import still resolves against `muthis.trust.confirm_gate`, including
# `_APPROVALS` / `_REFUSALS`, which `test_mode_exits.py` reads by name.
from .confirm_gate_detector import (  # noqa: F401 — re-export, kept at its old home
    APPROVAL_WORD_AR, APPROVAL_WORDS_AR, APPROVE, DIRECTIVE_MARKER_AR, REFUSE,
    _APPROVALS, _REFUSALS, detect_confirmation, strip_directive_lines,
)
# ─── The model-facing Arabic surfaces, EXTRACTED ─────────────────────────────
# Moved to `confirm_gate_notes.py` (DEC-131) — a MOVE ONLY, nothing reworded at
# the move; `CONFIRM_RETRY_AR` and `confirm_note` arrived there at DEC-136.
from .confirm_gate_notes import (  # noqa: F401 — re-export, kept at its old home
    CONFIRM_DIRECTIVE_AR, CONFIRM_RETRY_AR, MAX_ARGS_CHARS, MAX_ARG_CHARS,
    confirm_note, render_args, render_words,
)
# ─── The BINDING, EXTRACTED ──────────────────────────────────────────────────
# Moved to `call_binding.py` (DEC-138) — a MOVE ONLY, the function byte-identical
# and proven so by hash. It left because it gained a SECOND CONSUMER, not because
# of the ceiling: the same canonical bytes are hashed here and SPOKEN by
# `confirm_gate_speech.py`, and a mechanism with two consumers belongs to neither.
from .call_binding import call_fingerprint, canonical_call  # noqa: F401 — re-export
# ─── The KERNEL'S OWN SPOKEN REQUEST ─────────────────────────────────────────
# `confirm_gate_speech.py` (DEC-138). Its own module because the renderer needs
# `json` and the notes module is import-locked to `__future__` and `typing` by
# its own guard — which is never lowered to let work through.
from .confirm_gate_speech import spoken_request  # noqa: F401 — re-export

logger = logging.getLogger("muthis.trust.confirm_gate")


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
        # Did the LAST observed utterance reach the detector and come back as
        # NEITHER answer? It selects the retry note (DEC-136 ruling 3) and does
        # nothing else — it never affects WHETHER a call is refused, which is
        # why widening the accepted set and this flag are separate rulings.
        self._missed = False
        # DEC-138: the kernel's OWN utterance for the refusal just taken, built
        # from the canonical bytes and handed over ONCE. None whenever nothing is
        # outstanding to say — which is every state but "refused, not yet
        # spoken", so a pass that refuses nothing can never speak.
        self._spoken: Optional[str] = None

    @property
    def pending_tool(self) -> Optional[str]:
        """The tool awaiting approval, for tests and logs — never the args."""
        return self._pending.tool if self._pending is not None else None

    def take_spoken_request(self) -> Optional[str]:
        """The kernel's approval request, handed over ONCE and cleared.

        ONE-SHOT, AND THAT IS THE WHOLE OF THE S3 CASE. A pass can carry several
        refusable calls; only the first is dispatched (`turn_pass.py`'s
        first-router-call-wins rule), but nothing stopped a future caller from
        looping. Clearing on hand-over makes "spoke twice for one pass"
        unrepresentable rather than merely unusual.

        IT IS NOT `pending_tool`-SHAPED AND MUST NOT BECOME SO: a pending state
        SURVIVES the utterance (it is what the next turn's approval matches), so
        a reader keyed on the pending would speak the same request every pass —
        DEC-131's loop, rebuilt on the other side of the mouth."""
        spoken, self._spoken = self._spoken, None
        return spoken

    @property
    def awaiting_approval(self) -> bool:
        """True while a REFUSED call is still waiting for the user's word.

        IT IS NOT `pending_tool is not None`, AND THE DIFFERENCE IS THE WHOLE
        POINT (DEC-131). `observe()` sets `approved` on the pending state and
        LEAVES IT IN PLACE, so the name-only accessor stays truthy ACROSS the
        approval. A brake keyed on that would gag the very pass that must
        re-issue the call the user just approved, and the approval could never
        be spent — the fix would break the success path it exists to reach.
        This one goes False the moment the word is heard."""
        return self._pending is not None and not self._pending.approved

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
        # THE THREE OUTCOMES ARE NOT TWO (DEC-136 ruling 3). A REFUSAL is a
        # deliberate answer and a turn with no transcript never reaches here, so
        # only `None` means "the user spoke and was understood as neither" — the
        # ONE state the retry note may report. Telling someone who said «لا»
        # that he was not understood would be a false claim about his intent.
        self._missed = decision is None
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
        refinement of DEC-3-A).

        THE CLEAN-SESSION ARM IS ALSO WHY AN EXPERIMENT HERE MUST BE STAGED: the
        taint is raised only AFTER a call returns, so the FIRST tainting call of
        a process can never be gated. A test scenario must taint on an earlier,
        separate call — `docs__open` does, and is not high-impact (DEC-134)."""
        if not (high_impact and tainted):
            return None
        canonical, fingerprint = canonical_call(tool, args)
        pending = self._pending
        if pending is not None and pending.approved and pending.fingerprint == fingerprint:
            self._pending = None      # SINGLE-USE: consumed the moment it matches
            self._missed = False      # nothing outstanding to explain any more
            self._spoken = None       # nothing outstanding to SAY either
            logger.info("[confirm-gate] approved call released: %s", tool)
            return None
        # Any mismatch — no pending, not yet approved, or DIFFERENT arguments —
        # refuses and (re)places the pending. Rebinding on a modified call is the
        # point: an approval must never travel to a call the user never heard.
        self._pending = _Pending(fingerprint=fingerprint, tool=tool)
        # The log distinguishes the two refusals for the same reason the NOTE
        # does: three identical lines were what made the live loop unreadable.
        logger.info("[confirm-gate] high-impact %s refused — awaiting spoken "
                    "approval%s", tool,
                    " (RETRY: last utterance matched no approval word)"
                    if self._missed else "")
        # DEC-138: the USER-facing half, built HERE because this is the only
        # place holding the canonical bytes and the fingerprint together.
        # `spoken_request` is handed `canonical` and NEVER `args`, so it is
        # structurally unable to describe a payload the fingerprint does not
        # cover — the divergence is an absence of means, not a check.
        self._spoken = spoken_request(tool, canonical, APPROVAL_WORDS_AR)
        return confirm_note(tool, args, APPROVAL_WORDS_AR, missed=self._missed)


__all__ = [
    "APPROVAL_WORDS_AR",
    "APPROVAL_WORD_AR",
    "APPROVE",
    "CONFIRM_DIRECTIVE_AR",
    "CONFIRM_RETRY_AR",
    "ConfirmGate",
    "DIRECTIVE_MARKER_AR",
    "MAX_ARGS_CHARS",
    "MAX_ARG_CHARS",
    "REFUSE",
    "call_fingerprint",
    "canonical_call",
    "confirm_note",
    "detect_confirmation",
    "render_args",
    "render_words",
    "spoken_request",
    "strip_directive_lines",
]
