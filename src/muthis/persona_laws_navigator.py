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
    "\n"
    "\n"
    # ── WHEN TO VERIFY AND WHEN TO MOVE (DEC-108 Gate 2C). THE KERNEL MUST NOT
    # ENFORCE THIS ORDER — Sultan's ruling — because an ordering rule between two
    # verbs is a semantic judgement about turn shape, and `pass_servicing.py` is
    # pinned as holding no ordering state at all. So it is carried by the model,
    # which is exactly the division DEC-66 draws everywhere else.
    #
    # THE FAILURE MODE IS ONE WASTED PASS INSIDE THE CAP OF 4, NOT A DEFECT, and
    # that is why guidance is sufficient here where a structure was required for
    # the evidence: first-wins already answers the second call with a note that
    # claims nothing and asks for a retry, so a model that ignores this loses a
    # pass and nothing else.
    #
    # IT ALSO SAYS WHAT THE KERNEL DOES WITH A PROOF, because the model cannot
    # otherwise know that a proven step advances BY ITSELF — and a model that
    # asked for the advance it had already earned would spend its pass on a
    # refusal at the plan's edge.
    "التحقّق والتقدّم — حركة واحدة في كل خطوة تفكير:\n"
    "- أخدم حركة مسار واحدة فقط في كل خطوة تفكير، فلا تطلب التحقّق والانتقال "
    "معاً في نفس الرسالة؛ الثانية ما تُنفَّذ وتضيع عليك خطوة بلا فائدة.\n"
    "- وإذا أثبتّ نتيجة الخطوة فأنا أقدّم المسار بنفسي — لا تطلب مني الانتقال "
    "بعدها، فالتقدّم صار.\n"
    "- وإذا احتجت حركة أخرى — رجوع، أو قفزة، أو إنهاء — فاطلبها في الخطوة "
    "التالية وحدها."
    "\n"
    "\n"
    # ── HOW TO JUDGE (DEC-100's conservative instruction, DEC-105's boundary).
    # THIS LAW IS THE ONE EVERY MEASURED NUMBER IN THIS SERIES WAS OBTAINED
    # WITH, AND IT SHIPPED LAST. DEC-100 measured a NEUTRAL instruction failing
    # T₁ at 43.3% — seventeen false advances in thirty — and this rule taking it
    # to 100% with T₂ and T₃ UNMOVED: the failure was REMOVED, not relocated,
    # and reasoning tokens fell 17 → 2, so the rule is free. It lived in the
    # probe's `INSTRUCTION` until now, which meant the build carried the machine
    # and not the judgement it was measured with.
    #
    # AND IT REFUTED A CEILING ARGUMENT ON THE SAME FRAME, which is why the
    # wording is copied in its measured terms rather than paraphrased: the same
    # pixels, asked neutrally, gave "the body visibly has rounded top edges" ten
    # times out of ten, and asked THIS way gave "the rounded geometry is only a
    # live preview and the operation has not been confirmed" ten times out of
    # ten. The model could always SEE the dialog; what was missing was the rule.
    #
    # THE LAST CLAUSE IS DEC-105's BOUNDARY, AND IT IS NOT A FLOURISH. Excel's
    # cell-edit case failed 10/10 at confidence 99 with the model applying the
    # earlier rule CORRECTLY — it looked for a disqualifier, found none, and
    # concluded settled, which is what "no dialog is visible" instructs. So the
    # rule was STRUCTURALLY INCOMPLETE rather than badly worded, and this clause
    # is what fills it: absence of evidence against is not evidence for.
    #
    # WHAT IT DOES NOT CLAIM: it cannot make an unrendered state visible. DEC-105
    # ruled that boundary — the automatic path covers mid-steps whose unsettled
    # state is ACTUALLY DRAWN — and no phrasing moves it. A step whose app never
    # draws its own unsettled state stays outside, and the honest outcome there
    # is "not proven", which this law's last clause is what produces.
    "الحكم على نتيجة الخطوة — متى تقول إنها تحقّقت:\n"
    "- لا تعتبرها تحقّقت إلا إذا كان البرنامج في حالة مستقرّة والنتيجة مثبَّتة "
    "فعلاً، لا قيد التنفيذ.\n"
    "- والمعاينة ليست نتيجة: كثير من البرامج ترسم الشكل النهائي على اللوحة قبل "
    "أن تُؤكَّد العملية، فاللي تشوفه حينها معاينة حيّة لا نتيجة.\n"
    "- وإذا كانت هناك نافذة أو لوحة مفتوحة تنتظر تأكيداً — ما انضغط فيها "
    "«موافق» ولا «Enter» — فالحالة ما استقرّت، مهما بدا على اللوحة خلفها.\n"
    # THE WORDING HERE AVOIDS «شفت» DELIBERATELY, and a LIVE GUARD is what
    # found it: DEC-84's ack law pins that word at `count(...) == 1` because it
    # was MEASURED live, and the natural phrasing of this clause reproduced it.
    # Fixed in the LAW and never in the guard — Gate 1's precedent, twice now.
    "- وغياب المانع الظاهر لا يثبت الاستقرار: لو ما بان لك شيء يمنع، فهذا ليس "
    "دليلاً على أن الخطوة انتهت — بعض البرامج ما ترسم حالتها المؤقّتة أصلاً. "
    "قل إنها ما ثبتت، ولا تصنع يقيناً من غياب دليل مضادّ.\n"
    "- وليه: التحقّق أن ترى النتيجة نفسها، لا أن تستنتجها من مجرى العمل."
)


__all__ = ["NAVIGATOR_LAWS"]
