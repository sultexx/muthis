# src/muthis/broker/net/extract.py
"""
Readable extraction — the HTML→text reduction step of the hardened fetcher
(DEC-18, V2 Roadmap §3.1). Given an HTML body, produce readable prose (markup +
boilerplate stripped) via trafilatura, then cap it at ~4k tokens with an Arabic
truncation note. text/plain and JSON are already readable and never reach here.

Split out under the ≤300-line law (the DEC-23 discipline) so `fetcher.py` keeps
headroom for a T7 fix; `fetcher.py` imports + re-exports these names, so importers
are unaffected. This module isolates the ONE heavy third-party dependency
(trafilatura, which pulls lxml) — the codebase's lazy-heavy-lib convention.

SECURITY (DEC-18): extraction strips MARKUP, NOT textual injection. The DEC-14
wrapper at the router boundary is the injection guard — this is NOT a sanitizer.
It NEVER falls back to raw HTML (token-costly + injection-dense): a miss returns
None → a short Arabic note upstream, like every other failure (Law 11 / the
FileReader pattern). NEVER raises.

The urllib3-bypass guard (DEC-21-E) forbids this package from calling
trafilatura's network entry points — extraction uses ONLY `trafilatura.extract`.
"""

from __future__ import annotations

from typing import Optional

# The extract cap: ~4k tokens (Roadmap §3.1). A CHARACTER proxy (no tokenizer dep,
# no API round-trip), mirroring read_local_file's MAX_RETURN_CHARS which the
# codebase already frames as "≈ a few thousand tokens" at ~4 chars/token. This is
# DISTINCT from — and smaller than — the 2 MB raw-response cap (DEC-17); it bounds
# the context window the extract would otherwise blow.
MAX_EXTRACT_CHARS = 16_000

# Extraction produced nothing readable (a JS-only shell / no article). Degrade to
# the vision path — the SAME graceful move as robots/timeout — NEVER raw HTML.
EXTRACT_FAILED_AR = "ما قدرت أستخرج نصاً واضحاً من هذه الصفحة. افتحها على شاشتك وأنا أقرأ لك منها."
# Appended to over-cap content (the read_local_file TRUNCATION_NOTE_AR pattern):
# the remainder is reachable via the vision path (fetch has no range re-request).
EXTRACT_TRUNCATED_AR = (
    "\n\n(النص طويل ومقصوص عند الحد. إذا تبي بقية التفاصيل افتح الصفحة على شاشتك وأنا أكمل لك منها.)"
)


def extract_html(html: str) -> Optional[str]:
    """Blocking trafilatura extraction (run via asyncio.to_thread by the caller).
    Returns the page's READABLE text as plain prose (markup + boilerplate stripped)
    or None when there is no extractable content. `trafilatura` is lazy-imported
    here so importing the broker never pays for it. NEVER raises — any extractor
    surprise degrades to None, which the caller turns into a short Arabic note.

    NOTE (DEC-18): this strips MARKUP, NOT textual injection. The DEC-14 wrapper at
    the router boundary is the injection guard; extraction is not a sanitizer.

    HONEST LIMIT (recorded, DECISIONS 2026-07-25): trafilatura 2.1.0 sometimes
    emits a page's body TWICE on some (often short/synthetic) documents — no
    extract() option (fast / no_fallback / include_tables / deduplicate) suppresses
    it, and long realistic pages did NOT exhibit it in probing. It costs tokens but
    is bounded by cap_extract, and is neither a correctness nor a security defect
    (readable, boilerplate-stripped text is still returned). A post-filter risks
    collapsing legitimately-repeated prose, so it is DEFERRED to a T7 real-page
    measurement rather than guessed at here."""
    try:
        import trafilatura  # lazy: heavy (pulls lxml); only a web fetch pays for it
        return trafilatura.extract(
            html,
            include_comments=False,  # user comments = noise + an injection surface
            include_tables=True,     # documentation carries real content in tables
        )
    except Exception:  # noqa: BLE001 — extraction must never kill the turn (Law 11)
        return None


def cap_extract(text: str) -> tuple[str, bool]:
    """Cap readable text at MAX_EXTRACT_CHARS (~4k tokens, Roadmap §3.1), mirroring
    read_local_file's truncation contract: cut at a paragraph/word boundary and
    append the Arabic 'open it on your screen' note. Returns (content, truncated)."""
    if len(text) <= MAX_EXTRACT_CHARS:
        return text, False
    head = text[:MAX_EXTRACT_CHARS]
    cut = head.rsplit("\n", 1)[0]      # back off to a paragraph boundary (file_reader)
    if cut == head:                    # no newline in the window → a word boundary
        cut = head.rsplit(" ", 1)[0]
    return cut + EXTRACT_TRUNCATED_AR, True


__all__ = [
    "MAX_EXTRACT_CHARS", "EXTRACT_FAILED_AR", "EXTRACT_TRUNCATED_AR",
    "extract_html", "cap_extract",
]
