# src/muthis/broker/net/http_status.py
"""
The hardened fetcher's HTTP-status rule (DEC-149 ⑤): WHICH responses are the
page, and the note every other one earns.

THE DEFECT THIS CLOSES. The fetcher never tested `status`. Any response with a
supported content type and extractable text came back `ok=True`, so a 403 block
page, a 404 or a 500 page reached the model under «نص الصفحة من <domain>:» as the
site's content; it was CACHED for the session as a success, so a second fetch of
that URL returned the failure without a request even after the site recovered;
and its domain went on the badge as a source read. Live at DEC-149 ③:
`[fetch] alnassr.sa status=403 bytes=6064 chars=460`. The only sign that the text
was a block page was the page's own wording — a careful model read it as a
block, and nothing guaranteed the next one would.

THE RULE: only a 2xx is the page (RFC 9110 §15.3). The fetcher applies it BEFORE
the content type, the extraction and the cache, so the three properties follow
from WHERE it sits rather than from three separate checks: a non-success reaches
the model as a note stating its status, never as content; it is never cached; and
being `ok=False` it never reaches the badge's one recording site — nothing was
read. Redirects never get here: the transport follows 301/302/303/307/308 itself.

THE NOTE CARRIES THE NOTE LAW'S THREE OBLIGATIONS (DEC-58, AGENTS.md): what
happened, whether a retry can help, and what the model can do instead. The retry
clause is the one that depends on the status, and it must be TRUE: a 4xx is the
site's answer to THIS link, so the same link gets the same answer; a 5xx, a 408
or a 429 is the site failing or throttling for now, so it may pass — but not
within this reply. One clause for both would be false for one of them.

AND ROBOTS.TXT (RFC 9309 §2.3.1.4): a 5xx there means its rules cannot be read,
and the crawler MUST assume complete disallow — so the page is never requested,
and `robots_unreachable_note` is what the model reads instead. The fetcher's
robots seam does the sorting; robots.py records the rest of the RFC's reading.

Imports nothing and logs nothing: the fetcher logs domain + status (DEC-20).
"""

from __future__ import annotations

# The non-success answers a retry can outlast besides the 5xx class: a request
# timeout (408 — RFC 9110 §15.5.9: the client MAY repeat the request) and a rate
# limit (429 — RFC 6585 §4). Every other 4xx — 401/403 a refusal, 404/410 a
# missing page — is the site's answer to this link, and it does not change.
TRANSIENT_CLIENT_STATUSES = frozenset({408, 429})

# The note, with the status stated and the retry clause chosen by status class.
# Addressed like the file reader's notes: first person for what was done, an
# imperative for the next move — and «بدل التكرار» names the move the retry
# would otherwise have been.
HTTP_STATUS_AR = (
    "ردّ الموقع برمز الحالة {status}، يعني ما سلّم الصفحة: اللي رجع منه رسالة "
    "رفض أو خطأ وليس محتوى الصفحة، فما قرأت منها شي. {retry} بدل التكرار: إن "
    "كان فيما عندك من نتائج سابقة ما يجيب، جاوب منه واذكر مصدره؛ وإلا خبّر "
    "المستخدم إن الموقع ما سلّم الصفحة، واقترح عليه يفتحها على شاشته وأنا أقرأ "
    "منها."
)
# A 4xx: terminal for this link.
RETRY_FUTILE_AR = (
    "وهذا رد الموقع على هذا الرابط بالذات، ونفس الرابط يرجع نفس الرد في كل "
    "مرة، فلا تفتحه مرة ثانية."
)
# A 5xx, 408 or 429: transient — what changes is time, and not within this reply.
RETRY_LATER_AR = (
    "وهذا عطل أو ضغط مؤقت عند الموقع قد يزول بعد مدة، لكن فتح نفس الرابط في "
    "هذا الرد يرجع غالباً نفس الرد، فلا تكرره الآن."
)


# A 5xx robots.txt: the page itself was never requested. The retry clause is
# RETRY_LATER_AR's — an outage is time's to change, not a retry's in this reply.
ROBOTS_UNREACHABLE_AR = (
    "ردّ الموقع على ملف قواعده للقراءة الآلية برمز الحالة {status}، والمعيار يمنع "
    "فتح صفحاته آلياً ما دامت هذه القواعد ما تنقرأ، فما فتحت الصفحة ولا قرأت منها "
    "شي. {retry} بدل التكرار: إن كان فيما عندك من نتائج سابقة ما يجيب، جاوب منه "
    "واذكر مصدره؛ وإلا خبّر المستخدم إن قواعد الموقع للقراءة الآلية ما انقرأت "
    "الحين، واقترح عليه يفتح الصفحة على شاشته وأنا أقرأ منها."
)


def is_success(status: int) -> bool:
    """True only for a 2xx — the one class whose body is the page."""
    return 200 <= status < 300


def is_transient(status: int) -> bool:
    """True when the failure belongs to the site's present state, not the link."""
    return status >= 500 or status in TRANSIENT_CLIENT_STATUSES


def status_note(status: int) -> str:
    """The note a non-success status earns: the status stated, nothing read, a
    retry clause true to the status class, and the move the model can make."""
    retry = RETRY_LATER_AR if is_transient(status) else RETRY_FUTILE_AR
    return HTTP_STATUS_AR.format(status=status, retry=retry)


def robots_unreachable_note(status: int) -> str:
    """The note a 5xx robots.txt earns (RFC 9309 §2.3.1.4): the status stated,
    the page never opened, and time — not a retry in this reply — as what can
    change it."""
    return ROBOTS_UNREACHABLE_AR.format(status=status, retry=RETRY_LATER_AR)


__all__ = [
    "HTTP_STATUS_AR", "RETRY_FUTILE_AR", "RETRY_LATER_AR", "ROBOTS_UNREACHABLE_AR",
    "TRANSIENT_CLIENT_STATUSES", "is_success", "is_transient", "robots_unreachable_note",
    "status_note",
]
