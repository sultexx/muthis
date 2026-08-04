# src/muthis/broker/docs/notes.py
"""
The Arabic notes the ingestion path returns — every refusal TYPE-ACCURATE, and
every refusal offering a path.

THIS FILE IS DEC-35's CLOSURE, and DEC-35 is a lesson about signals rather than
gates. Live evidence, 2026-07-25: the user asked Mut'his to explain a PDF, the
binary gate refused it exactly as designed and leaked nothing — but the note the
model read said NOT FOUND. "Not found" is a RETRYABLE condition, so the model did
the rational thing and retried four different paths until the agentic cap stopped
the turn. Four provider calls, roughly $0.10, no answer. Every guard behaved
perfectly; the SIGNAL lied about its reason.

THE RULE IT PRODUCED: **a refusal that misreports its reason turns a TERMINAL
condition into a RETRYABLE one.** So the two failures that look alike from outside
get DIFFERENT notes here, because they are different conditions:

  · a SCANNED PDF has no text layer. Nothing this project has will ever read it —
    OCR is out of launch scope — so the note says so and CLOSES the attempt. This
    is the one place a note deliberately tells the model not to try again.
  · an UNSUPPORTED FORMAT (DOCX / EPUB) is a converter away. The note names the
    format, names what IS readable, and leaves the door open.

Collapsing them into one "cannot read this file" would recreate the exact defect
DEC-35 recorded, one level up.

EVERY REFUSAL OFFERS A PATH — the DEC-17 robots-refusal pattern, where a block
becomes a showcase. The three offers are: ask about a SPECIFIC SECTION, SPLIT the
file, or — the strongest — OPEN IT ON SCREEN and let Mut'his point at it, which
runs the LOOK-only vision path. The third is not a consolation prize: it routes
the user into the one capability that distinguishes this product from every
document-chat tool, so the largest document, the one the index cannot take, is
answered by the feature nothing else has.

NO NUMBERS THE USER DID NOT ASK FOR, AND NO PATHS. The notes name «المستند», never
a filesystem path (privacy: the model already knows what it asked for, and the log
surface must not learn it). Format notes name the SUFFIX, which is the type rather
than the file.

Arabic here, English in the logs — the language-split law. These strings are
model-facing tool_result text; Mut'his paraphrases them into speech, so they carry
no markdown, no lists and no formatting syntax (the persona's FORMATTING-SYNTAX
BAN: the output surface is TTS and a captions bar, never a renderer).
"""

from __future__ import annotations

# ── Zone 3: too large to index. The refusal DEC-47 designed. ─────────────────
# THE THREE OBLIGATIONS (the standing rule of 2026-07-30), each earned here:
#   1. WHAT WAS ACCOMPLISHED — the file WAS opened and its text read, and NOTHING
#      was indexed. Without this the model cannot tell a refusal from a crash, and
#      "ask about a section" reads as a fresh start rather than as the next step on
#      a document already open. WORDED TO BE TRUE AT BOTH CALL SITES: the up-front
#      estimate and the exact second gate. The second one has already chunked and
#      loaded the encoder, so this claims only what holds for both — read, sized,
#      not one vector computed. A note is not exempt from the accuracy it demands.
#   2. TERMINAL OR TRANSIENT — terminal FOR THIS FILE WHOLE, and transient for
#      everything else: re-sending the same file gets the same answer, so the note
#      says not to. This became load-bearing at DEC-72, which lowered the ceiling
#      and moved ~900-2,000-page documents into this note; a bigger refused band
#      means more chances for the retry loop DEC-35 measured at ~$0.10 a go.
#   3. THE VALID NEXT STEP — the three paths, strongest last so it is the one the
#      model most likely repeats. The size is stated because a refusal the user
#      cannot check is a refusal the user cannot trust.
DOC_TOO_LARGE_AR = (
    "فتحت المستند وقرأت نصه وحسبت حجمه: حوالي {tokens} توكن والحد عندي {limit} "
    "توكن، وفهرسته كاملة تتجاوز الوقت المتاح — فما فهرست منه شي، ووقفت قبل ما "
    "أبدأ. هذا الحد ثابت لهذا الملف كامل، فلا ترسله مرة أخرى كما هو لأن النتيجة "
    "بتكون نفسها. عندك ثلاث طرق تشتغل الآن: اسألني عن قسم محدد أو فصل معيّن وأنا "
    "أقرأه لك، أو قسّم الملف لملفات أصغر وافتح واحد منها، أو — وهذي أقواها — "
    "افتح الملف على الشاشة وأنا أشرح لك منه وأشير على السطر نفسه بينما تقرأ."
)

# ── The two PDF/format conditions DEC-35 requires to differ ──────────────────
# TERMINAL. The last sentence is the DEC-35 payload: without it, a competent agent
# retries, because retrying is what an agentic loop is for.
PDF_SCANNED_AR = (
    "هذا ملف PDF ممسوح ضوئيًا — صفحاته صور، وما فيه طبقة نص أقدر أقرأها. قراءة "
    "النص من الصور غير متوفرة عندي، فما فيه مسار ثاني يشتغل: لا تحاول تقرأه مرة "
    "أخرى ولا بصيغة ثانية. افتح الملف على الشاشة وأنا أشرح لك منه وأشير على "
    "المكان اللي تسأل عنه."
)

# RETRYABLE, but only after an ACTION — and the note names the action. Distinct
# from the scanned note on purpose: this file's type is the problem, not its
# content, and a converted copy works.
DOC_UNSUPPORTED_AR = (
    "صيغة «{suffix}» ما أقدر أفتحها. اللي أقدر أقرأه: ملفات PDF النصية وملفات "
    "Markdown وملفات النص العادية. حوّل الملف لواحدة من هذي وأنا أقرأه، أو افتحه "
    "على الشاشة وأنا أشرح لك منه مباشرة."
)

# ── The honest empties and failures ──────────────────────────────────────────
# A parser that returned nothing must NOT look like a parser that ran cleanly (the
# standing cutoff rule: zero admitted is a failure, never a pass).
DOC_EMPTY_AR = (
    "فتحت المستند لكن ما طلع منه نص أقدر أستخدمه. تأكد إن الملف فيه نص فعلاً، أو "
    "افتحه على الشاشة وأنا أشرح لك منه."
)

# LOUD degradation (DEC-44), and note what still works: zone 1 needs no encoder at
# all, so a smaller document is a real offer rather than a polite deflection.
DOC_ENCODER_UNAVAILABLE_AR = (
    "محرّك فهم المستندات غير متاح الآن، فما أقدر أفهرس مستنداً بهذا الحجم. "
    "المستندات الصغيرة أقرأها كاملة بدون فهرسة، وأي ملف تفتحه على الشاشة أشرحه "
    "لك مباشرة."
)

# The DEC-45 window guard fired. DEC-53 ruled the SPLITTER is what gets fixed when
# this happens, never the guard — so this note exists for the case the splitter
# genuinely cannot divide, and it says what the user can do meanwhile.
DOC_CHUNK_FAILED_AR = (
    "ما قدرت أقسّم المستند تقسيماً سليماً للفهرسة، ووقفت بدل ما أفهرسه ناقصاً "
    "وأعطيك إجابات من نصف مستند. اسألني عن قسم محدد، أو افتحه على الشاشة وأنا "
    "أشرح لك منه."
)

# The note law: an I/O error left NOTHING opened, and it is retryable only after
# the path or the permissions change — saying so stops a blind immediate retry.
DOC_READ_FAILED_AR = (
    "صار خطأ وأنا أفتح المستند، فما فُتح شي وما صار له فهرسة. إعادة المحاولة "
    "بنفس المسار بتعطي نفس الخطأ: تأكد من المسار والصلاحيات مع المستخدم، أو "
    "افتحه على الشاشة وأنا أشرح لك منه."
)


# The SAME failure, but with a cause we can NAME and an action that fixes it.
# Live evidence: the model sent a percent-encoded path (`.../My%20Documents/...`),
# nothing existed there, and it read the generic note above — which is true and
# useless, because "check the path" does not tell a model that `%20` is a space.
# The three obligations, each earned: what happened (BOTH forms tried, nothing
# opened, no index), that repeating THIS spelling is terminal, and the one action
# — ask the user for the path as the file explorer shows it.
DOC_PATH_URL_ENCODED_AR = (
    "ما قدرت أفتح المستند: المسار اللي وصلني مكتوب بترميز الروابط — فيه علامة "
    "٪ ومعها رقمان، مثل 20% بدل المسافة. جرّبته كما وصلني، ثم جرّبته بعد فك "
    "الترميز، وما فُتح شي في الحالتين وما صارت فهرسة ولا تغيّر شي. لا تعيد "
    "إرسال نفس المسار بنفس الصيغة، فالنتيجة بتكون نفسها: اطلب من المستخدم "
    "المسار كما يظهر له في مستكشف الملفات بمسافات عادية، أو خلّه يفتح الملف "
    "على الشاشة وأنا أشرح لك منه وأشير على المكان اللي تسأل عنه."
)


def read_failed(*, url_encoded: bool = False) -> str:
    """The open-failed refusal, NAMING the url-encoding when that is the cause.

    Two notes rather than one for DEC-35's reason exactly: a refusal that
    misreports its reason turns a fixable condition into a blind retry, and
    "check the path" and "the path is url-encoded, ask for it unencoded" are
    different instructions producing different next moves."""
    return DOC_PATH_URL_ENCODED_AR if url_encoded else DOC_READ_FAILED_AR


def too_large(tokens: int, limit: int) -> str:
    """The zone-3 refusal, carrying the two numbers that justify it.

    The size is given because a refusal the user cannot check is a refusal the
    user cannot trust — and because the model needs it to explain the ceiling in
    its own words rather than inventing one."""
    return DOC_TOO_LARGE_AR.format(tokens=tokens, limit=limit)


def unsupported(suffix: str) -> str:
    """The unsupported-format refusal, NAMING the format (DEC-35).

    A suffix-less file is described as such rather than as an empty quotation,
    which would read as a bug to the model and invite a retry."""
    return DOC_UNSUPPORTED_AR.format(suffix=suffix.strip() or "بدون امتداد")


__all__ = [
    "DOC_CHUNK_FAILED_AR", "DOC_EMPTY_AR", "DOC_ENCODER_UNAVAILABLE_AR",
    "DOC_PATH_URL_ENCODED_AR", "DOC_READ_FAILED_AR", "DOC_TOO_LARGE_AR",
    "DOC_UNSUPPORTED_AR", "PDF_SCANNED_AR", "read_failed", "too_large",
    "unsupported",
]
