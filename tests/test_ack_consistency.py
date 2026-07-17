"""
test_ack_consistency.py — the two draw-tool ACK surfaces must be PARALLEL.

Phase B-2 pins the cross-tool consistency the persona relies on: the
highlight_target ACK and the draw_shapes ACK must both be user-invisible
INTERNAL directives that COMMAND an immediate explanation — never a
"success"/"done" status report (the framing that used to collapse the
forced-text pass 2 into a bare "أبشر / تم" acknowledgement). Both must open the
same way, order the explanation to start with the information from the first
word, and forbid the same filler leads by name.

Pure stdlib import (highlight_gate imports only dataclasses/typing) — no SDK, no
network, fully deterministic.

Run:  set PYTHONPATH=src && python -m pytest tests/test_ack_consistency.py -q
"""

from __future__ import annotations

from muthis.kernel.highlight_gate import HIGHLIGHT_ACK_TEXT_AR, SHAPES_ACK_TEXT_AR

# The two ACKs the gate hands back for the FIRST draw of a turn (highlight_target
# and draw_shapes) — they must be consistent, so they are tested together.
BOTH_ACKS = (HIGHLIGHT_ACK_TEXT_AR, SHAPES_ACK_TEXT_AR)

# Each ACK opens by naming itself a user-invisible directive (never spoken)…
INTERNAL_DIRECTIVE = "توجيه داخلي (لا يراه المستخدم)"
# …then COMMANDS the explanation now, immediately…
EXPLAIN_NOW = "الآن قدّم شرحك مباشرةً"
# …starting with the information from the first word.
START_WITH_INFO = "ابدأ بالمعلومة من أول كلمة"

# The filler leads BOTH ACKs must forbid by name — so pass 2 never collapses to a
# bare acknowledgement. "أبشر"/"تم" are the shared ones; each tool also forbids its
# own verb ("أشرت لك" / "رسمت لك").
SHARED_FORBIDDEN_FILLER = ["أبشر", "تم"]


def test_both_acks_are_internal_explain_now_directives():
    # Consistency (1): both ACKs are user-invisible steering that ORDERS an
    # immediate explanation starting with the info — not a completion report.
    for ack in BOTH_ACKS:
        assert INTERNAL_DIRECTIVE in ack, "ACK is not framed as a user-invisible directive"
        assert EXPLAIN_NOW in ack, "ACK does not command an immediate explanation"
        assert START_WITH_INFO in ack, "ACK does not order starting with the info"


def test_both_acks_forbid_success_filler():
    # Consistency (2): neither ACK reads as "success/done" — each NAMES the filler
    # leads it forbids, so no bare "أبشر / تم" ack can survive as the whole reply.
    for ack in BOTH_ACKS:
        for filler in SHARED_FORBIDDEN_FILLER:
            assert filler in ack, f"ACK must name the forbidden filler {filler!r}"
        # And it must not carry an explicit success word ("بنجاح") that reads as
        # task-done — the regression that produced a bare ack in the first place.
        assert "بنجاح" not in ack, "ACK reads as a success report, not a directive"
