# src/muthis/kernel/session_taint.py
"""
SessionTaint — the session-sticky untrusted-content state (DEC-2, DEC-15).

Once adversarial content has entered the model's context, the injection and
exfiltration risk does NOT end when the ingesting turn ends: the content is in
the transcript, and the model keeps reasoning over it. A per-turn flag drops the
guard while the threat is still live, so this state is STICKY for the whole
session — its lifetime is the PROCESS.

DELIBERATELY CONTRASTED WITH SandboxGate. That gate is rebuilt EVERY turn (the
≤3-runs/turn budget must reset), and it is the nearest pattern in the codebase —
so it is the pattern someone would reach for by analogy, and wiring this object
that way would silently defeat DEC-15 while every other test stayed green. This
object is built ONCE at the composition root and never rebuilt;
`tests/test_session_taint.py` asserts it survives the per-turn reset hook.

FOUR properties that are absences, each load-bearing:
  * NO clearing method. A "clear the taint" command would itself be a
    social-engineering channel — exactly the capability an injected page would
    ask the user to trigger. A new process is the ONLY reset.
  * NO persistence. No file, no ledger, no disk: working memory lives in RAM and
    dies with the session (the privacy-first posture, and the LRU-cache rule of
    DEC-17). This module imports `logging` and nothing else, which is what makes
    that structural rather than a promise.
  * NO model-visible surface. Enforcement is STRUCTURAL at the router (this
    supersedes the roadmap §3.2/§3.4 "taint status line" framing). Telling the
    model would add a promptable surface — one more thing injected content can
    argue with — and buy no guarantee. This module therefore contains no Arabic
    at all: it speaks to neither the model nor the user.
  * NO enforcement HERE. T4 raises and records; the confirmation gate that reads
    this state lands at T5 with the high-impact classification, because those are
    ONE concern (DEC-16).

WHO may raise it is NOT this object's business: classification is kernel-side,
derived at mount from the granted capability / MCP hint, never from a plugin's
self-declaration (DEC-15). The router is the single site that decides, and it
raises here in the SAME branch that applies the DEC-14 wrap — one classification,
both consequences, so a result can never be wrapped without raising.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("muthis.kernel.session_taint")


class SessionTaint:
    """One per process. Flips once, from clean to tainted, and stays there."""

    def __init__(self) -> None:
        self._tainted = False

    @property
    def tainted(self) -> bool:
        """Read-only: there is no setter, so the only way in is raise_taint."""
        return self._tainted

    def raise_taint(self, provenance: str) -> None:
        """Record that untrusted content entered the session.

        IDEMPOTENT: raising an already-raised taint is a no-op, so the English
        log line lands exactly ONCE per session (the record, not a per-call
        stream). Never throws — the name is DEC-2's vocabulary ("raisers"), not
        an exception (Law 11: a security record must not be able to kill a turn).

        `provenance` is the kernel's own route label (e.g. "mcp:demo") — never
        content, never a URL, so logging it is safe under DEC-20/DEC-28.
        """
        if self._tainted:
            return
        self._tainted = True
        logger.info(
            "[session-taint] session TAINTED by %s — sticky for the rest of the "
            "process (no clearing path by design)", provenance)


__all__ = ["SessionTaint"]
