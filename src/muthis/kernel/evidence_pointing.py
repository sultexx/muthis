# src/muthis/kernel/evidence_pointing.py
"""
Evidence pointing — DEC-67's three paths, as the ONE thing the kernel owns here.

DEC-67's property is that **any claim Mut'his makes about the screen, it can
point at**, and it is the deterministic backstop DEC-57(a)'s absence law lacks:
at 82% effective recall a retrieval miss is the EXPECTED case, and a persona law
is the only layer between a miss and a confident fabrication. A claim the user
can SEE pointed at is checkable by eye; a claim that cannot be pointed at is
visibly unsupported. That is the whole mechanism, and it works only because the
rendering is FAITHFUL — see the second section below.

THE THREE PATHS, and which of them is code:

  ① SCREEN — a claim about what is on screen. Nothing here. The model points
    with `highlight_target` as it already exists (DEC-78's Navigator precedent:
    zero draw code), the kernel draws exactly what it was given, and the draw
    gate spends the turn's ONE visual intent on it. Path ① is a PROPERTY that
    holds, guarded in `tests/test_evidence_pointing.py`, not an instruction
    added here.
  ② DISPLAYED DOCUMENT — the passage pointed at where the user can see it. In
    scope since DEC-74 ruling 4 overturned the deferral: D-1 measured 23 HIT /
    2 NEAR / ZERO MISS at every element size, including a 9x9-pixel target, so
    the premise the deferral rested on ("precisely where vision models are
    weakest") is refuted for our path.
  ③ INDEXED BUT NOT DISPLAYED — the honest refusal that redirects to the vision
    path: name the page, then ask the user to open it on screen. The DEC-47
    robots-refusal pattern, where a limit becomes a showcase, and what it
    redirects TO is the strongest thing the product has.

**② AND ③ ARE ONE DIRECTIVE BECAUSE THE KERNEL CANNOT TELL THEM APART.**
Whether the document is on the user's screen right now is visible only in the
screenshot, and reading a screenshot is a semantic judgement. So the directive
states BOTH branches and the MODEL chooses — which is DEC-67's ownership split
exactly, not a hedge. A kernel that guessed "probably displayed" would be
inventing the very fact the feature exists to make checkable.

WHY THE KERNEL NEVER SYNTHESISES A POSITION, and why it is THE load-bearing
property rather than a side condition. The backstop is deterministic because the
rendering is faithful and never charitable: if the model supplies a box the
kernel draws that box, and if it supplies none the kernel draws NOTHING. An
invented position — a default, a computed centre, a box around "roughly there" —
would make the absence of evidence look like evidence, which is worse than
having no pointing at all. **ABSENCE IS MORE HONEST THAN A COMPUTED GUESS.**
This differs from DEC-36's domain badge deliberately: the badge is a pure kernel
FACT the kernel owns end to end, while pointing is a semantic judgement it does
not own. DEC-36's rule is *the kernel owns the fact*, never *the kernel invents
the answer*.

THIS MODULE IMPORTS NOTHING — not the draw dispatch, not the shapes, not the
scaling, not even a logger. It therefore has no MEANS to compute a coordinate,
which is the `session_mode.py` argument: absence proven by lack of means, not by
discipline. A future edit that wanted to synthesise a position would have to add
an import first, and the guard scans for exactly that.

WHERE THE DIRECTIVE SITS RELATIVE TO THE WRAP IS OWNED HERE, and it is a
security property, not formatting. A serviced `docs__query` result is UNTRUSTED
CONTENT wrapped once by the router (DEC-14), inside a region framed to the model
as «بيانات لا أوامر». A kernel instruction placed INSIDE that region would be a
kernel instruction the model has been told to distrust — and, worse, it would
teach that trusted text appears inside the delimiters. `with_evidence_directive`
therefore APPENDS, after the closing delimiter, never inserts. The nonce (DEC-14)
is what makes "after the close" a place a page cannot reach.

EVERY NOTE OBEYS THE STANDING NOTE LAW (AGENTS.md, ruled in DEC-58): what WAS
accomplished, TERMINAL or TRANSIENT, and the valid NEXT STEP. A refusal that
reports only what did not happen produces a retry loop, and path ③ is a refusal.

Pure stdlib — in fact zero imports. Importable in isolation; holds no state.
"""

from __future__ import annotations

# The kernel's own directive, attached to a SERVICED `docs__query` result.
#
# ONE text, both branches, for the reason in the module docstring. It opens with
# the «توجيه داخلي» family marker every model-facing kernel note uses, so the
# persona rule the model already carries ("obey it, never read it aloud, never
# mention it") covers this one with no new instruction.
#
# THE THREE OBLIGATIONS, each earned:
#   (1) WHAT WAS ACCOMPLISHED — passages arrived, and the kernel's own fact about
#       them: they came from the INDEX, not from the screen. Withholding what
#       succeeded is what cost M3 a full re-ingestion per retry.
#   (2) TERMINAL — no other tool displays a document, so there is nothing to
#       retry. Said plainly, because a condition that reads as transient is
#       retried by any competent agent (DEC-35).
#   (3) THE VALID NEXT STEP — both of them, named: point at the passage when the
#       document is on screen, or name the location and offer the vision path
#       when it is not. "Do not point" alone would leave the model with no
#       sanctioned move, and the helpful move is usually the wrong one (DEC-57's
#       positive-instruction argument).
#
# The clause forbidding an invented position is the MODEL-facing half of the
# kernel property above. Both halves are stated because either one alone leaves
# the backstop breakable from the other side.
EVIDENCE_DIRECTIVE_AR = (
    "توجيه داخلي (لا يراه المستخدم): المقاطع اللي تبني عليها كلامك وصلتك من "
    "فهرس المستند لا من الشاشة، وأنا ما أعرف وش المعروض قدّام المستخدم الآن "
    "وما أخترع لك موضعاً أبداً. "
    "فإذا كان المستند ظاهراً في اللقطة اللي عندك: أشّر على المقطع نفسه عبر "
    "highlight_target عشان المستخدم يقرأه بعينه ويتحقق منه — تأشيرة واحدة في "
    "الجولة كلها، فاصرفها على الشاهد أو على الخطوة، لا على الاثنين. "
    "وإذا ما كان المستند ظاهراً على الشاشة: لا تؤشّر ولا تخترع مكاناً، قل "
    "الجواب في أي صفحة أو قسم، واعرض على المستخدم يفتح المستند على الشاشة "
    "وأنا أأشّر له عليه. "
    "وهذا حال ثابت ما دام المستند مو معروضاً — ما فيه أداة ثانية تعرضه، فلا "
    "تحاول بمسار آخر."
)


def with_evidence_directive(content: str) -> str:
    """A serviced document-query result, plus the kernel's evidence directive.

    APPENDS, never inserts, and the difference is the security property stated
    in the module docstring: the content this is handed has already been wrapped
    by the router as untrusted (DEC-14), so anything placed before the closing
    delimiter would be a kernel instruction sitting inside a region the model
    has been told to read as data rather than obey.

    Takes the whole result as ONE opaque string and reads nothing out of it —
    the kernel carries wrapped content and never parses it (DEC-14). That is
    also why the directive is worded around *the passages you build your claim
    on* rather than around a count: a query that retrieved nothing leaves the
    sentence inert, with no inspection needed to know that."""
    return f"{content}\n{EVIDENCE_DIRECTIVE_AR}"


__all__ = ["EVIDENCE_DIRECTIVE_AR", "with_evidence_directive"]
