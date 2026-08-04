# src/muthis/kernel/ack_scope.py
"""
The spoken ack's SCOPE, as one sentence with one home.

WHAT THIS CLOSES, and it is worth stating precisely because the code did not
break: **the Navigator EXPOSED a directive-coverage gap that was previously
closed by COINCIDENCE.** That is DEC-13's posture one layer up — a property held
by circumstance rather than by construction.

THE COINCIDENCE, MEASURED (T7 runs 1-3, DEC-83). The directive that actually
forbids a repeated ack — the one naming «أبشر» and «بدون أي مقدمة أو تأكيد» —
rides the DRAW pairing (`highlight_gate.py`). Before Phase 3 the first pass of an
answer ACKED AND DREW, so that directive arrived immediately and the only pass
after it was the forced-text explain. **The Navigator inserts an ack-eligible
pass BEFORE any draw**: `test_advance_WITHOUT_pointing_leaves_the_gate_unflipped`
asserts `calls[1][1] == "auto"`, so pass 2 is another tool-capable pass — and
every navigator and mode directive was SILENT on acks. The measured live result
was an ack per PASS inside one answer: «سم، شوف أول خطوة!أبشر، شوف شريط البحث!».

WHY IT MATTERED HERE MORE THAN ANYWHERE BEFORE: the Navigator explains step by
step across several passes, so the defect fires **per STEP** rather than per
answer — in the milestone's flagship feature.

THE SCOPE IS PER **ANSWER**, NEVER PER TOOL FAMILY — Sultan's ruling, and the
phrasing is deliberate. A rule written per family ("after a navigator verb, do
not ack") would have to be RE-EARNED by every future capability that opens a new
pass gap, which is exactly how this gap arrived. Written per ANSWER, a capability
inherits it by existing: **the ack belongs to the FIRST pass of an answer, and
every later pass continues directly — whatever tools it calls.**

ONE SENTENCE, ONE COPY. Six directives carry it (four navigator surfaces, two
mode-frame lines) and they read it from here, so "the two wordings drifted" is
not a state that exists — the `NAMESPACE_SEP` discipline applied to a law rather
than to a name.

DELIBERATELY NOT A PROHIBITION. «Never ack» would be wrong on the mode-frame
line, which rides the turn's FIRST user message: forbidding an ack there would
kill the mandatory opening ack that masks the pass-2 round-trip (v7.1 Fix E — a
silent pass 1 is banned, and a measured chars=0 ack left the gap unmasked). The
positive form is correct at BOTH positions, which is why one sentence can serve
them.

Imports NOTHING — so it cannot cycle, and it cannot grow a dependency that would
make it something other than a sentence. Pure stdlib; importable in isolation.
"""

from __future__ import annotations

# The law, in the model's own language. Carried by every directive that can be
# followed by another pass of the SAME answer.
#
# It never contradicts the mandatory opening ack: it says WHERE that ack belongs
# (the answer's first pass) rather than forbidding one, and «مهما كانت الأدوات
# اللي يستدعيها» is the clause that makes it tool-agnostic — the half that stops
# the next capability from re-opening this gap.
ACK_SCOPE_AR = (
    "كلمة التأكيد المنطوقة واحدة في الإجابة كلها وتكون في أول دور منها، وكل "
    "دور بعده في نفس الإجابة يبدأ بالمعلومة مباشرة بلا كلمة تأكيد جديدة مهما "
    "كانت الأدوات اللي يستدعيها"
)

__all__ = ["ACK_SCOPE_AR"]
