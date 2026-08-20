# src/muthis/persona_laws_navigator.py
"""
The NAVIGATOR's AUTHORING laws — how to WRITE a walkthrough, as opposed to what
a capability may do with what it reads.

Extracted VERBATIM from `persona_laws.py` under the ≤300-line law (DEC-108 Gate
2C): a MOVE ONLY, taken because that file stood at 285/300 with fifteen lines
and its own pin says the next law needs an EXTRACTION before it needs a
sentence. The composed prompt is BYTE-IDENTICAL across the move, proven by hash
rather than asserted.

THE SEAM IS A FAMILY, NOT A LINE BUDGET. Every law left in `persona_laws.py`
arrived WITH A CAPABILITY and governs what the model may do with what that
capability returns — untrusted web text, a document it did not write, a citation
it must speak. These govern how the model AUTHORS a walkthrough: how to phrase a
step's expected result, when to verify it, and when to advance. They change when
the NAVIGATOR changes, which is a different schedule from the rest.

APPEND-ONLY, AND THE ORDER IS PRESERVED ACROSS THE SPLIT. `persona_laws.py`
composes `… + NAVIGATOR_LAWS` at the END, so every earlier law keeps its byte
offset and every additive prefix-hash proof in the persona tests still points at
the same bytes. A new navigator law goes at the BOTTOM of this file.
"""

from __future__ import annotations

NAVIGATOR_LAWS = (
    # ── HOW TO WRITE `expected_result` (DEC-107, Gate 1). The SCHEMA makes the
    # field unskippable; this law is the only place that says how to phrase it,
    # and the split is deliberate — two copies of one rule drift apart.
    #
    # IT GUIDES AND NEVER ENFORCES. The kernel checks that the field is present
    # and non-empty and NOTHING MORE (DEC-66): it cannot count the ends of a
    # sentence without reading it, and reading it is the law it must not break.
    # So an over-broad or two-ended result is ALLOWED by the contract and is
    # surfaced here and by measurement — a named residual, not a gap.
    #
    # ALL THREE CLAUSES ARE MEASURED, and clauses 1 and 3 come from the SAME
    # fixture with DIFFERENT mechanisms, which is why they are stated
    # separately rather than merged:
    #   1. RESULT, NOT ACTION — "round the top edges with a fillet", never "set
    #      the fillet radius to 5 mm". A step phrased around the CONTROL is
    #      genuinely SATISFIED mid-step (the radius IS set in the open dialog),
    #      which turns a designed trap into a true positive.
    #   2. ONE OBSERVABLE END — DEC-106's binding constraint, earned from an
    #      answer that was not an error: "Move X from Source to Destination"
    #      has two ends with DIFFERENT observability, departure provable and
    #      arrival not, and a three-outcome contract has no label for half.
    #   3. NO VALUE A FRAME CANNOT SETTLE — a committed fillet radius is not
    #      measurable from a screenshot, so naming it fails verification for a
    #      reason that has nothing to do with the step. NOT "no numbers": a
    #      cell's displayed contents ARE settleable, and this project's own
    #      category-3 fixture names 990 and 100 on purpose.
    "\n"
    "نتيجة كل خطوة — تكتبها مع الخطة قبل ما تشوف أي شي:\n"
    "- كل خطوة في navigator__plan تحمل نصّها ونتيجتها المتوقّعة. النتيجة هي وش "
    "بيشوفه المستخدم على الشاشة إذا خلّص الخطوة — صف المشهد اللي بيصير، لا "
    "الفعل اللي بيسويه: \"الملف صار داخل مجلد الوجهة\"، مو \"اسحب الملف "
    "للوجهة\".\n"
    "- طرف واحد ملحوظ لكل خطوة: اكتب \"الملف صار في الوجهة\" ولا تكتب أبداً "
    "\"انقل الملف من المصدر إلى الوجهة\" — الجملة اللي فيها طرفان يصير نصّها "
    "صحيحاً ونصفها الثاني ما يبان على الشاشة، وما لها تصنيف.\n"
    "- لا تذكر قيمة دقيقة ما تقدر اللقطة تحسمها: مقاس مضبوط في خانة، أو رقم "
    "داخل أمر تنفّذ ولا يظهر بعده. أمّا القيمة اللي تنكتب وتبان على الشاشة "
    "فاذكرها عادي.\n"
    "- اكتبها كلها وقت بناء الخطة قبل أي تحقّق، وما تعدّلها ولا تعيد صياغتها "
    "بعدها أبداً. لو غيّرتها بعد ما تطالع الشاشة فأنت تطابق النتيجة على اللي "
    "ظهر لك، والتحقّق يصير دائرة على نفسه.\n"
    "- وليه: بلا وصف مكتوب مقدّماً ما فيه شي تقارن الشاشة به، فتصير الشاشة هي "
    "السؤال والجواب في نفس الوقت."
)


__all__ = ["NAVIGATOR_LAWS"]
