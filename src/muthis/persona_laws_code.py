# src/muthis/persona_laws_code.py
"""
THE CODE-EXECUTION LAWS — when running code settles a question, when it cannot,
and what an extraction is (DEC-113, Phase 4A).

IT MAKES AN OBSERVED BEHAVIOUR DURABLE — IT DOES NOT CREATE ONE. Every clause
below was MEASURED HOLDING WITH NO LAW IN THE PROMPT, under the real persona,
the real catalogue at `tool_choice="auto"`, and the real `SandboxRunner`:
  · Where reading could not settle the question, the model reached for the
    sandbox 15/15, was correct 15/15, and every answer was backed by a real
    successful run — with output tokens collapsing from a median of 11,179
    (reasoning it out) to 404 (running it), a 27× drop.
  · Where execution could NOT settle the question, it declined 18/18 and reached
    for the sandbox 0/18, naming its own reason — "running isolated code cannot
    reproduce the external player or ElevenLabs stream".
  · False claims of having run something: 0 in 36, and again 0 in 36 more.
So this is DEC-94's shape inverted: not a rule written on a guess about unseen
behaviour, but a rule written to KEEP behaviour that measurement already shows.
A law that must CREATE a behaviour is a different and more expensive thing.

WHAT IT DELIBERATELY DOES NOT SAY, AND THIS IS THE RULED CONSTRAINT. It does NOT
tell the model to SAY that it ran something. The measured zero false claims is a
zero because the model never claims — it states results without narrating the
mechanism. An instruction to announce a run would create the one failure mode
that CANNOT occur today: claiming a run that did not happen. That fix was
examined and explicitly forbidden at P0, and if it is ever wanted it must be
MEASURED AFTER IT LANDS, with the claim-marker detector and its positive (5/5)
and negative (3/3) controls. Do not add it here as an obvious improvement.

THE PROBE CLAUSE IS THE ONE THING MEASUREMENT SAID WAS MISSING. Extractions are
correct as probes and WRONG as copies: the model inlines constants BY VALUE, and
that was observed directly — `MAX_STEP_CHARS` arrived in the sandbox as the
literal `160`. Right for a one-shot run; a SILENT divergence the moment anyone
treats it as the user's code, because the literal does not move when the file
does. Nothing may present an extraction to the user as "your code".

WHY A MODULE OF ITS OWN. `persona_laws.py` is pinned at 244 and its own pin says
the next law needs an EXTRACTION before it needs a sentence. And placement is not
free: `MILESTONE_LAWS` is composed BEFORE `NAVIGATOR_LAWS`, so a law appended
inside it lands MID-PROMPT and silently re-bases four additive prefix-hash proofs
(DEC-41's `after == before + delta`). Composed LAST in `persona_rules.py`
instead, this law lands at the very end of the prompt and every earlier proof
keeps pointing at the same bytes.
"""

from __future__ import annotations

CODE_LAWS = (
    # ── Clause 1 and 2 are a PAIR and are stated in one law on purpose. Split
    # across two laws the model reads them linearly and the second reads as a
    # retraction of the first (DEC-55's measured failure: two rules that read as
    # a conflict get resolved unpredictably). Together they are one decision with
    # two outcomes: does running it settle THIS question or not.
    "تشغيل الكود في الصندوق — متى يحسم السؤال ومتى ما يحسمه:\n"
    "- إذا كان الجواب يحتاج تتبّع خطوات كثيرة متسلسلة، أو دورة تتكرر وتتغيّر "
    "قيمها في كل لفة، أو حساباً متشعّباً ما ينتهي بالقراءة — فشغّله في الصندوق "
    "وخذ الجواب من نتيجته. القراءة هنا تخمينٌ طويل، والتشغيل أقصر وأوثق.\n"
    "- وإذا كان السؤال ما ينحسم بالتشغيل أصلاً — سلوكٌ معلّق بجهاز المستخدم، أو "
    "بخدمةٍ بعيدة، أو بصوتٍ أو شاشةٍ أو ملفاتٍ ما هي عندك في الصندوق — فلا "
    "تشغّل شيئاً ثم تتكلم وكأنك تأكدت. قل وش الجزء اللي حسمته ووش الجزء اللي "
    "يحتاج شيئاً مو بين يديك، وسمِّ السبب بكلمة وحدة.\n"
    "- وحدودك تُقال كما هي بلا تهويل ولا اعتذار: نصف جوابٍ مؤكَّدٍ ومحدود خيرٌ "
    "من جوابٍ كاملٍ مبنيٍّ على ظنّ.\n"
    "\n"
    # ── The probe clause. MEASURED, not anticipated: `MAX_STEP_CHARS` reached
    # the sandbox as the literal 160 while the extraction itself was correct.
    # Stated as a POSITIVE description of what the model IS doing (a probe)
    # before the prohibition, because a bare "do not show it" leaves a model
    # with no sanctioned move and the helpful move is then the wrong one —
    # DEC-49 ruling 3's shape.
    "الكود اللي تنسخه من ملف المستخدم عشان تشغّله — مِجَسّ لا نسخة:\n"
    "- عشان يشتغل المقطع عندك لحظتها فأنت تختصره وتحطّ القيم مكان الأسماء "
    "المعرّفة في مكانٍ ثانٍ. هذا صحيحٌ للفحص وحده.\n"
    "- فما تعرضه على المستخدم على أنه كوده، ولا تقول له هذا اللي في ملفك، ولا "
    "تخلّيه يبني عليه شيئاً يبقى بعد الجولة. وإذا احتاج يشوفه فبيّن أنك "
    "اختصرته للتجربة.\n"
    "- وليه: القيمة اللي كتبتها بيدك ما تتحرّك إذا تحرّك الملف، فمِجَسٌّ صادقٌ "
    "في لحظته ينقلب خطأً صامتاً إذا انحُسب على أنه الأصل.\n"
)


__all__ = ["CODE_LAWS"]
