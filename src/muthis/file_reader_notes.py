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

FILE_NOT_FOUND_AR = "ما لقيت الملف «{path}». تأكد من المسار الكامل واطلب القراءة من جديد."
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
FILE_READ_ERROR_AR = "صار خطأ أثناء قراءة الملف، جرّب مرة ثانية أو تأكد من الصلاحيات."
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
