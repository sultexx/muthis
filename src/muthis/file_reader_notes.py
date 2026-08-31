# src/muthis/file_reader_notes.py
"""
The reader's MODEL-FACING Arabic surfaces — every sentence `read_local_file` can
return instead of file content.

Extracted VERBATIM from `file_reader.py` under the ≤300-line law (DEC-113, Phase
4A): a MOVE ONLY. That file stood at 280 and the symbol map took it to 312, so
the arrival became an extraction rather than a breach — the
`kernel/verification_notes.py` precedent, where the pin met its next arrival with
a number instead of a green suite. Nothing here was reworded at the move, and
`file_reader.py` re-exports every name, so no import site changed.

WHY THIS HALF AND NOT THE GATES. `file_reader.py` also holds the secret-name,
bare-name and binary refusals — SECURITY code, mutation-verified, and DEC-42's
discipline is that the stronger property stays byte-identical while the weaker
one is worked on. A message layer is the weaker half by construction: it decides
what a refusal SAYS, never whether it refuses. So the sentences move and the
guards do not.

AND THE SENTENCES ARE NOT DECORATION — DEC-35 IS THE PROOF. A refusal that
misreported its REASON turned a TERMINAL condition into a retryable one, the
agentic loop did exactly what it exists to do, and four provider calls and ~$0.10
bought no answer. What these strings say is load-bearing behaviour.
"""

from __future__ import annotations

# DEC-124: the note did not merely LACK terminality — it INVERTED it. The old
# text ended «واطلب القراءة من جديد» (*ask for the read again*), and its named
# next step, «تأكد من المسار الكامل», addresses someone who can inspect a
# filesystem — which the model cannot. So the only half the model could act on
# WAS the retry, and it retried: measured live 2026-08-30, three identical
# not-found reads in one turn, passes 1-3, with pass 4 empty.
#
# AND NOTHING BOUNDED IT. `read_local_file` has no per-turn budget — `read_call`
# is first-wins per PASS (`turn_pass.py`), with no `SandboxGate` equivalent — so
# only `MAX_AGENTIC_ITERATIONS` stopped the turn. The note is the whole brake.
#
# THIS IS DEC-58 RULING 3's LAW, AND ITS AUDIT NEVER REACHED THIS FILE: that
# sweep fixed `doc_rag`'s notes and its table holds the exact analogue one
# capability over — `DOC_READ_FAILED_AR`, *"did not say a retry with the same
# path gives the same error"*.
#
# THE THREE OBLIGATIONS, HONESTLY, and shaped on `FILE_IS_DOCUMENT_AR` below,
# which is DEC-35's fix and the one note in this file that already satisfies all
# three: (1) the STATE — nothing was read and nothing was opened; (2) TERMINAL
# FOR THIS PATH, said in those words, with the reason it cannot be retried away —
# the same path returns the same result; (3) a next step THE MODEL CAN TAKE —
# ask the user for the correct path, and the clause says WHY the model cannot
# settle it alone, so "check it yourself" is not left looking available.
FILE_NOT_FOUND_AR = (
    "ما لقيت الملف «{path}» — ما قرأت شي وما فتحت شي. وهذا المسار بالذات ما "
    "ينفع: أي محاولة ثانية بنفس المسار ترجع نفس النتيجة بالضبط، فلا تعيد "
    "القراءة به. بدل المحاولة: اسأل المستخدم عن المسار الصحيح، لأني ما أقدر "
    "أتصفّح جهازه لأتأكد من المسار بنفسي."
)
FILE_BLOCKED_AR = "هذا الملف من ملفات الأسرار (مفاتيح/بيانات اعتماد) وقراءته ممنوعة حمايةً للمستخدم."
FILE_TOO_LARGE_AR = "الملف أكبر من الحد المسموح للقراءة. اطلب من المستخدم يفتح الجزء المطلوب أو حدّد ملفاً أصغر."
FILE_NOT_TEXT_AR = "هذا ملف ثنائي (غير نصّي) وما أقدر أقرأه كنص."
# DEC-35, closed by the doc_rag milestone: the binary refusal NAMES THE FORMAT.
# Live evidence (2026-07-25): a PDF was refused correctly and nothing leaked, but
# the note the model read reported a RETRYABLE reason — so the model did the
# rational thing and retried four different paths until the agentic cap stopped the
# turn. Four provider calls, ~$0.10, no answer. A refusal that misreports its
# REASON turns a TERMINAL condition into a retryable one, and the agentic loop
# exists precisely to retry, so the cost compounds. Naming the format ends the
# attempt at the FIRST call, and the note routes to the vision path — the DEC-17
# robots-refusal pattern, where a block becomes a showcase.
DOCUMENT_FORMATS = {
    ".pdf": "PDF", ".docx": "DOCX", ".doc": "DOC", ".epub": "EPUB",
    ".odt": "ODT", ".rtf": "RTF", ".xlsx": "XLSX", ".xls": "XLS",
    ".pptx": "PPTX", ".ppt": "PPT", ".djvu": "DjVu",
}
FILE_IS_DOCUMENT_AR = (
    "هذا ملف {fmt}، وأداة قراءة النص عندي تقرأ الملفات النصية فقط فما تنفع معه. "
    "ما فيه مسار ثاني يقرأه كنص، فلا تحاول بمسار أو صيغة ثانية. افتح الملف على "
    "الشاشة وأنا أشرح لك منه وأشير على المكان اللي تسأل عنه."
)
# Staging-only (sandbox files[], DEC-13): the name must be BARE — no directory.
FILE_NAME_NOT_BARE_AR = "اسم الملف لازم يكون بدون مسار أو مجلّد — مرّر اسم ملف بسيط فقط."
# DEC-125: THE SAME INVERSION, ONE NOTE DOWN. «جرّب مرة ثانية» invited the retry
# and «تأكد من الصلاحيات» named a step only someone at the machine can take —
# `FILE_NOT_FOUND_AR`'s defect exactly, and DEC-58's `OPEN_FAILED_AR` shape: the
# catch-all for an unexpected exception, which "said none of the three".
#
# AND A SECOND DEFECT THE FIRST NOTE DID NOT HAVE — IT INVENTED A MECHANISM.
# This is the CATCH-ALL arm (`except Exception`), so the cause is by definition
# unknown, and «تأكد من الصلاحيات» asserted a specific one. A note that names a
# cause it does not have is the [[true-statement-false-mechanism]] shape: it
# sends the model, and through it the user, at the wrong thing — and it reads as
# diagnosis rather than as the guess it is.
#
# THE CONSTANT HAS TWO CALLERS, AND THE WORDING IS HONEST IN BOTH — WHICH IS WHY
# THE INVENTED CAUSE HAD TO GO RATHER THAN BE REPLACED WITH A BETTER ONE.
# `file_reader.py` returns it when a read ATTEMPT raised; `tool_result_pairing.py`
# returns it for a `read_local_file` block the kernel NEVER SERVICED. Those have
# different causes and only one shared truth — nothing came back — so the note
# states that, states that repeating it inside this turn changes nothing, and
# names a step the model can take. DEC-58 ruling 1 is the warning being obeyed
# here: «TWO notes, not one» — a note claiming what did not happen would be a
# fresh instance of this very defect in the opposite direction. Whether the two
# callers should eventually carry SEPARATE notes is flagged, not settled.
FILE_READ_ERROR_AR = (
    "صار خطأ وأنا أحاول أقرأ الملف — ما رجع لي منه شي. وإعادة نفس الطلب الحين "
    "ما تغيّر النتيجة، لأن ما فيه شي يتبدّل بين محاولة وأخرى في نفس الجولة. "
    "بدل التكرار: خبّر المستخدم إن القراءة فشلت واطلب منه يفتح الملف على الشاشة "
    "أو يعطيك مساراً ثانياً، لأني ما أقدر أتحقّق من السبب بنفسي."
)
FILE_READ_UNAVAILABLE_AR = "قراءة الملفات غير متاحة في هذا الوضع."
# A second read_local_file in the SAME pass — the same internal-directive
# family as the draw acks: answer from what you already have, explain now.
FILE_ALREADY_READ_AR = (
    "(توجيه داخلي من النظام — هذا النص ليس من المستخدم ولا يراه ولا يُقرأ "
    "بصوت عالٍ): قرأت ملفاً في هذه الجولة قبل قليل. لا تكرر القراءة — استخدم "
    "المحتوى اللي عندك وكمّل الشرح الآن."
)
TRUNCATION_NOTE_AR = (
    "\n(القراءة مقصوصة عند الحد الأقصى — اطلب read_local_file مرة ثانية مع "
    "start_line و end_line للجزء اللي يهمّك.)"
)


__all__ = [
    "DOCUMENT_FORMATS",
    "FILE_NOT_FOUND_AR", "FILE_BLOCKED_AR", "FILE_TOO_LARGE_AR",
    "FILE_NOT_TEXT_AR", "FILE_IS_DOCUMENT_AR", "FILE_NAME_NOT_BARE_AR",
    "FILE_READ_ERROR_AR", "FILE_READ_UNAVAILABLE_AR",
    "FILE_ALREADY_READ_AR", "TRUNCATION_NOTE_AR",
]
