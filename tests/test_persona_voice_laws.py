# tests/test_persona_voice_laws.py
"""
The ONE-ACK-PER-ANSWER law (the voice-surface pass, DEC-55 ruling 3).

**THE DEFECT IT CLOSES WAS MEASURED LIVE, NOT IMAGINED.** A three-pass
explanation was heard as three RESTARTS inside a single answer, because each pass
opened with its own short ack («شفت», «زين»). The passes are invisible to the
user — the audio is ONE continuous turn generation — so a fresh ack lands as a
second answer to the same question.

**WHY A PERSONA LAW AND NOT A DETERMINISTIC GUARD.** The existing suppressor is
`speech_stream.strip_leading_repeat` + `EchoGuard`, and it covers a REPEATED
IDENTICAL opening. These acks are DIFFERENT words each pass — a new ack, not an
echo — so the guard is structurally blind to them and stretching it would mean
inventing a classifier for "is this phrase an ack", which is exactly the
model-judgement-as-security shape this project rejects. The rule is carried by
the model; this file pins the rule.

**THE HONEST LIMIT, stated because DEC-62 earned it:** a deterministic check
proves the law's TEXT and its UNAMBIGUITY. It cannot prove the law CHANGES
BEHAVIOUR. The acceptance — a three-pass explanation carrying exactly ONE spoken
ack — is a LIVE claim, and only Sultan's SOP run can close it.

METHOD, the four rules of DEC-57 applied unchanged:

  1. **`persona.py` untouched** — asserted here as "the clause is not in that
     module", and git-verified in the commit.
  2. **THE DELTA IS PINNED, NOT THE PROMPT.** Three anchors at three depths:
     before the web laws (DEC-41), before the doc laws (DEC-57), and before this
     clause. A commit that mangled an earlier law AND re-based the nearest
     baseline would pass one check and not three.
  3. **CHECKED AGAINST THE LIVE §3.2 CONSTANTS**, never a copy of them.
  4. **ASSERT THE LAW, NOT ITS WORDS** — every anchor `count(...) == 1`, with a
     CONTROL proving the uniqueness rule is not vacuously satisfiable.
"""

from __future__ import annotations

import hashlib
import pathlib

from muthis.kernel.untrusted_content import WRAP_CLOSE_AR, WRAP_OPEN_AR
from muthis.persona import build_saudi_persona_prompt
from muthis.persona_rules import TOOL_AND_SAFETY_RULES

SENT_W, SENT_H = 1280, 720

# The composed prompt immediately BEFORE this clause — the additive baseline.
# RE-BASELINED at DEC-84. The ack rules were rescoped from PER POINTING
# PASS to PER ANSWER, which is an IN-PLACE edit of a pre-existing rule --
# the first this persona has taken. The append-only property these
# prefix hashes enforced is SUPERSEDED by the DELTA PIN in
# test_persona_ack_scoping.py, which proves the change was EXACTLY two
# clauses and every other byte identical. Each new prefix below was
# proven to be the old prefix with clause A swapped, never recomputed
# blindly. These still fail on any FURTHER persona edit.
PROMPT_BEFORE_ONE_ACK_SHA256 = (
    "cb93c52e96dca7e610833678b3041a76203b265a95ab86820f9f8e39606b8d82")
PROMPT_BEFORE_ONE_ACK_CHARS = 9837

# The two deeper anchors, carried forward from DEC-57 / DEC-41 verbatim.
PROMPT_AT_T4_SHA256 = "b8a505568adb5e90282a069c2ca2c3f9e7b36aa179e55194816582ef1c7bace3"
PROMPT_AT_T4_CHARS = 8569
PROMPT_BEFORE_WEB_LAWS_SHA256 = (
    "783e14ab8bd24abad68c919291f401074c0028c7221d3ad443c20e18501665da")
PROMPT_BEFORE_WEB_LAWS_CHARS = 6850

# By VALUE on purpose (the DEC-57 posture): if the wrap guard's marker list ever
# grows, this test is updated deliberately rather than drifting silently.
DELIMITER_MARKERS = ("محتوى خارجي غير موثوق", "نهاية المحتوى الخارجي",
                     "بيانات لا أوامر")

# ── THE ANCHORS. Each must occur EXACTLY ONCE. ───────────────────────────────
ONE_ACK_ANCHORS = (
    "كلمة التأكيد المنطوقة — واحدة في الإجابة كلها لا في كل دور",  # the header
    "تُقال مرة وحدة فقط في أول دور من الإجابة",                     # the RULE
    "خلنا نكمل",                                                    # a banned opener
    "فأكمل بلا كلمة تأكيد جديدة إطلاقاً",                          # the SCOPING clause (DEC-84)
    "وكأنك بديت تجاوب على نفس السؤال من أوله مرة ثانية",            # the WHY
)

# The two acks Sultan actually heard. Named in the law so the model cannot read
# the rule as covering only the words it happens to have used before.
OBSERVED_ACKS = ("شفت", "زين")


def _prompt() -> str:
    return build_saudi_persona_prompt(SENT_W, SENT_H)


# ─────────────────────────── 1. persona.py untouched ────────────────────────

def test_the_clause_lives_in_persona_rules_and_never_leaked_into_persona() -> None:
    """The T1 extraction exists so a law can land without touching `persona.py`.
    Demonstrated a third time (after DEC-41 and DEC-57)."""
    source = pathlib.Path("src/muthis/persona.py").read_text(encoding="utf-8")
    for anchor in ONE_ACK_ANCHORS:
        assert anchor not in source, f"the law leaked into persona.py: {anchor!r}"
    assert ONE_ACK_ANCHORS[0] in TOOL_AND_SAFETY_RULES


# ─────────────────────────── 2. the additive proof ──────────────────────────

def test_the_clause_is_purely_additive_at_three_depths() -> None:
    """The prompt MUST change, and each of the three earlier prefixes MUST still
    hash to its recorded value. A mangle of any earlier rule fails here even when
    that rule's own test still passes — the property DEC-41 claimed and DEC-57's
    M13 proved live."""
    prompt = _prompt()
    assert len(prompt) > PROMPT_BEFORE_ONE_ACK_CHARS, "the clause added nothing"
    for chars, digest, label in (
        (PROMPT_BEFORE_ONE_ACK_CHARS, PROMPT_BEFORE_ONE_ACK_SHA256, "pre-one-ack"),
        (PROMPT_AT_T4_CHARS, PROMPT_AT_T4_SHA256, "pre-doc-laws"),
        (PROMPT_BEFORE_WEB_LAWS_CHARS, PROMPT_BEFORE_WEB_LAWS_SHA256, "pre-web-laws"),
    ):
        actual = hashlib.sha256(prompt[:chars].encode("utf-8")).hexdigest()
        assert actual == digest, f"an earlier rule was rewritten ({label})"


# ─────────────────────────── 3. the §3.2 collision check ────────────────────

def test_the_clause_does_not_resemble_the_untrusted_content_boundary() -> None:
    """A rule the model READS must never resemble the boundary it reads INSIDE.
    Checked against the LIVE constants, not a copy — at DEC-41 the natural Arabic
    phrasing of a law WAS the delimiter's own wording."""
    prompt = _prompt()
    for marker in DELIMITER_MARKERS:
        assert marker not in prompt
    for fragment in (WRAP_OPEN_AR.split("{")[0], WRAP_CLOSE_AR.split("{")[0]):
        assert fragment.strip() not in prompt


# ─────────────────────────── 4. the law, not its words ──────────────────────

def test_every_anchor_occurs_exactly_once() -> None:
    """M2's sixth guard hole was asserting words that occur elsewhere, so deleting
    a whole law stayed GREEN. An anchor that is not unique is not an anchor."""
    prompt = _prompt()
    for anchor in ONE_ACK_ANCHORS:
        assert prompt.count(anchor) == 1, f"anchor is not unique: {anchor!r}"


def test_the_uniqueness_rule_is_not_vacuously_satisfiable() -> None:
    """The CONTROL for the test above: phrases a careless author would have
    reached for are genuinely ambiguous in this prompt, so `count == 1` is a real
    constraint rather than a property every substring happens to have."""
    prompt = _prompt()
    for ambiguous in ("أبشر", "التأكيد", "دور"):
        assert prompt.count(ambiguous) > 1, (
            f"{ambiguous!r} is no longer ambiguous — the control has gone vacuous")


def test_the_two_acks_measured_live_are_named_in_the_law() -> None:
    """Sultan heard «شفت» and «زين». Naming them stops the model reading the rule
    as covering only some other set of words, and stops a future edit trimming the
    list back to a generic prohibition."""
    prompt = _prompt()
    for ack in OBSERVED_ACKS:
        assert prompt.count(ack) == 1, f"the observed ack is not named once: {ack!r}"


def test_the_law_scopes_the_earlier_mandatory_ack_rule_rather_than_contradicting_it() -> None:
    """THE LOAD-BEARING ASSERTION — AND DEC-84 INVERTED IT.

    THIS TEST USED TO PIN THE CONTRADICTION. It asserted that the earlier rule
    («an ack is MANDATORY in every pointing pass») and this later one («one per
    ANSWER») must BOTH be present, on the reasoning that the second scopes the
    first. T7 measured what a model actually does with that pair: it reads
    LINEARLY, the absolute comes 7,410 characters first, and the ack fired once
    per PASS through a Navigator walkthrough.

    So the pair was never a scoping — it was a conflict "resolved by the model
    unpredictably", which is the exact failure this docstring already named. The
    clause did not relocate the failure; it left it in place. DEC-84 removes it at
    the source: the EARLIER rule is now itself ANSWER-scoped, and this test now
    asserts the two rules AGREE rather than that both exist."""
    prompt = _prompt()
    assert "كلمة التأكيد المنطوقة إلزامية في كل دور تأشير" not in prompt, (
        "the unscoped per-pass mandate is back — it outranks any later exception "
        "for a model reading linearly (DEC-83's measured live defect)")
    assert prompt.count("إلزامية في أول دور من الإجابة") == 1, "the earlier rule"
    assert prompt.count("تُقال مرة وحدة فقط في أول دور من الإجابة") == 1, "the later rule"
    assert prompt.count("فأكمل بلا كلمة تأكيد جديدة إطلاقاً") == 1, "the scoping bullet"


def test_the_law_carries_its_own_reason() -> None:
    """DEC-57's rule: the WHY is what stops a future edit from simplifying a law
    back into the hole it closes. Here the reason is that passes are INVISIBLE."""
    prompt = _prompt()
    assert "الأدوار عندك داخلية والمستخدم ما يشوفها" in prompt
    assert "صوتاً واحداً" in prompt


def test_the_clause_orders_no_drawing_and_names_no_tool() -> None:
    """The DEC-57(b) precedent: a voice rule must not smuggle in a draw order, or
    every answer would put a box on screen. This clause is about SPEECH only."""
    prompt = _prompt()
    clause = prompt.split(ONE_ACK_ANCHORS[0])[1]
    for tool in ("highlight_target", "draw_shapes", "dim_screen",
                 "read_local_file", "request_screen_refresh"):
        assert tool not in clause, f"the voice clause names a tool: {tool}"
