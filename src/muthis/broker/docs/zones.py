# src/muthis/broker/docs/zones.py
"""
THE ZONE DECISION (DEC-47) — which of three paths a document takes. Decided
HERE, in the broker, and never by a plugin.

WHY THE OWNER MATTERS MORE THAN THE ARITHMETIC. Zone 1 hands the model the WHOLE
document. A plugin that could choose its own zone could choose FULL INJECTION for
a hostile 200-page file — a plugin declaring how much of the user's context it is
entitled to spend. That is the same self-assertion DEC-15 refuses when it forbids
a plugin to declare its own taint, DEC-29 when it refuses a plugin-set
`is_error`, and DEC-34 when it refuses a plugin-declared cost. The recurring
principle is WHO OWNS THE FACT, and a document's size is a fact about the user's
machine, not about the tool that asked to read it. So the ingestion entry point a
plugin can reach takes a PATH and nothing else — no zone, no limit, no policy, no
override — and a signature scan asserts it, the way DEC-18's scan asserts the
search destination is configuration-only.

THE THREE ZONES
  1. estimated tokens <= `MUTHIS_DOC_INJECT_LIMIT` -> FULL INJECTION + prompt
     cache. Chunking, encoding and indexing are ALL bypassed (DEC-47) — the most
     common path is also the cheapest and the most accurate, because no retrieval
     step can beat handing the model the whole document.
  2. between the limit and the derived maximum -> index and retrieve.
  3. above the maximum -> a CLEAN REFUSAL, decided BEFORE any encoding runs.

THE DERIVED MAXIMUM IS MEASURED, NOT CHOSEN (DEC-47 / DEC-49 ruling 4):

    max_chunks = ingestion budget / per-chunk encode time
    max_tokens = max_chunks * mean tokens per chunk

Every input is a P0 output. The per-chunk figure is a BENCH measurement and T6
measured the operating one at more than double it — see `PER_CHUNK_ENCODE_MS`
below for the numbers, why the constant is deliberately not changed, and why the
startup log prints both.

THE INVARIANT, AND WHY IT IS A STARTUP ASSERTION RATHER THAN A COMMENT: the
derived maximum MUST EXCEED the injection limit, or zone 2 is EMPTY — every
document large enough to need an index is already too large to build one — and
the whole three-zone design is incoherent. P0 measured this inverting under the
rejected encoder (bge-m3 at a 60 s budget derives ~40,830 against a 50,000
limit), so the relation is real, not hypothetical. It was written down NOWHERE
before DEC-49, which is exactly how it would have broken silently after an
innocuous config change. A configuration that makes a whole zone unreachable is
not a degraded mode, it is an incoherent one, so this FAILS the process instead
of logging (the DEC-45 precedent for guards on silent-corruption paths).

Pure stdlib. No encoder, no tokenizer, no model — which is what makes the zone-1
and zone-3 bypasses STRUCTURAL: this module could not encode if it wanted to.
"""

from __future__ import annotations

import dataclasses
import enum
import logging
import os

from .token_estimate import TOKENS_PER_CHAR_CEILING, estimate_tokens

logger = logging.getLogger("muthis.broker.docs")

# ── The P0-measured inputs. Every one of these is a MEASUREMENT, and the file
#    that measured it is `docs/reports/phase2_m3_p0_rag_bench.md`. ────────────

# DEC-4's value with DEC-47's unit correction: TOKENS, not characters. A unitless
# 50000 read as characters would put the boundary several times too low, and wrong
# by a different factor in Arabic than in English.
DEFAULT_INJECT_LIMIT_TOKENS = 50_000

# The ingestion wall-clock budget. The P0 table derives the maximum at 60/120/180 s;
# 60 s is the row DEC-49 ruling 4 states the invariant against.
DEFAULT_INGESTION_BUDGET_SECONDS = 60.0

# Per-chunk encode time. 30.2 ms was measured at T2 through this repo's encoder
# path on a warm, isolated bench; P0's harness reported 30.6 ms for the same model
# on the same hardware, and the two agreeing is why the figure was trusted.
#
# T6 CORRECTION — THE BENCH FIGURE IS NOT THE OPERATING ONE. The first real live
# SOP measured 18.00 s to ingest a 267-chunk document: 67.4 ms per chunk, MORE
# THAN DOUBLE this constant, on a machine also running the overlay, the voice
# line and a live turn. So the derived maximum below is roughly HALF in
# production (~338,000 tokens rather than ~754,680).
#
# THE CONSTANT IS DELIBERATELY NOT CHANGED HERE. It feeds `max_tokens`, which is
# a ZONE BOUNDARY — moving it re-routes documents, and that is a design decision
# needing a ruling, not a reaction to one measurement. DEC-49 ruling 4's
# invariant holds either way and by a wide margin (338,000 against a 50,000
# injection limit), so nothing is broken. What IS fixed is the startup log, which
# used to print the bench-derived figure as though it were the operating one —
# the DEC-56 lesson landing in the one place an operator actually reads.
PER_CHUNK_ENCODE_MS = 30.2

# The live-measured figure, kept BESIDE the constant it qualifies so the two can
# never drift apart in a reader's head. Reported at startup; it derives nothing.
MEASURED_LIVE_PER_CHUNK_MS = 67.4

# The mean chunk the maximum is expressed in, from the P0 zone arithmetic.
MEAN_CHUNK_TOKENS = 380

# The characters-to-tokens estimate lives in `token_estimate.py` — a measured
# property of a corpus and a tokenizer, which changes for different reasons than
# the boundaries below. Its ratio is an upper bound ON PURPOSE; the argument for
# the direction of error is stated there, at the constant.

# Config that a typo can produce, read at the root.
ENV_INJECT_LIMIT = "MUTHIS_DOC_INJECT_LIMIT"
ENV_INGEST_BUDGET = "MUTHIS_DOC_INGEST_BUDGET_S"


class DocZone(enum.Enum):
    """The three paths of DEC-47. Named, so a log line and a test say the same word."""

    INJECT = "inject"          # zone 1 — the whole document, no index at all
    INDEX = "index"            # zone 2 — chunk, encode, retrieve
    REFUSE = "refuse"          # zone 3 — a clean refusal that offers a path


class ZoneConfigurationError(Exception):
    """The zone relation is incoherent — zone 2 would be EMPTY (DEC-49 ruling 4).

    Raised at STARTUP, never mid-turn: a configuration this broken must stop the
    process while an operator is still watching it, not surface as one strange
    document six turns later."""


@dataclasses.dataclass(frozen=True)
class ZoneDecision:
    """A zone, and the cutoffs it was decided against.

    THE CUTOFFS TRAVEL WITH THE DECISION (the standing rule from the P0 gate):
    every stage of this path filters, a filter can silently exclude its own
    subject, and a stage that reports success having examined nothing is the
    defect family this project has now met four times. So the decision states
    which limits it used and how many documents it admitted — and for a REFUSAL
    that count is zero, which is the honest answer rather than a pass."""

    zone: DocZone
    chars: int
    tokens: int
    inject_limit: int
    max_tokens: int
    exact: bool = False        # True when `tokens` was COUNTED, not estimated

    @property
    def admitted(self) -> int:
        return 0 if self.zone is DocZone.REFUSE else 1

    def describe(self) -> str:
        """One English log line: the zone, the cutoffs, the admitted count.

        NEVER the path and never a character of content (the privacy law)."""
        how = "counted" if self.exact else f"estimated@{TOKENS_PER_CHAR_CEILING:g}tok/char"
        return (f"[doc_rag] zone={self.zone.value} tokens={self.tokens} ({how}) "
                f"chars={self.chars} cutoffs(inject_limit={self.inject_limit}, "
                f"max_tokens={self.max_tokens}) admitted={self.admitted}")


@dataclasses.dataclass(frozen=True)
class ZonePolicy:
    """The two boundaries, and the measurements they are derived from.

    Built ONCE at the composition root and injected, the `HardenedFetcher` and
    search-provider shape: a policy rebuilt per document could differ per
    document, and the whole point of the startup invariant is that this pair is
    checked once, for the process."""

    inject_limit: int = DEFAULT_INJECT_LIMIT_TOKENS
    budget_seconds: float = DEFAULT_INGESTION_BUDGET_SECONDS
    per_chunk_ms: float = PER_CHUNK_ENCODE_MS
    mean_chunk_tokens: int = MEAN_CHUNK_TOKENS

    # -- the derived side ---------------------------------------------------
    @property
    def max_chunks(self) -> int:
        """How many chunks the budget pays for. FLOORED: a fraction of a chunk
        cannot be encoded, and rounding up would sell time the budget lacks."""
        if self.per_chunk_ms <= 0:
            return 0
        return int(self.budget_seconds * 1000.0 // self.per_chunk_ms)

    @property
    def max_tokens(self) -> int:
        """The ingestion maximum, in the unit the estimate speaks."""
        return self.max_chunks * self.mean_chunk_tokens

    # -- the decision -------------------------------------------------------
    def zone_for_tokens(self, tokens: int) -> DocZone:
        """The ONE place the two comparisons live. Both boundaries are INCLUSIVE
        of the lower zone: a document exactly AT the injection limit is injected,
        which is the reading that keeps the cheapest and most accurate path as
        wide as the configuration allows."""
        if tokens <= self.inject_limit:
            return DocZone.INJECT
        if tokens <= self.max_tokens:
            return DocZone.INDEX
        return DocZone.REFUSE

    def decide(self, chars: int) -> ZoneDecision:
        """THE UP-FRONT DECISION (DEC-47): estimated in tokens, before encoding.

        Called after extraction and before anything expensive, so a refusal costs
        seconds rather than the whole ingestion budget. Ingesting and THEN refusing
        would be worse than either option on its own — the user waits out the entire
        indexing budget in silence and is refused at the end of it, having paid the
        full cost for nothing. The order of operations IS the feature."""
        tokens = estimate_tokens(chars)
        return ZoneDecision(zone=self.zone_for_tokens(tokens), chars=chars,
                            tokens=tokens, inject_limit=self.inject_limit,
                            max_tokens=self.max_tokens)

    def exceeds_budget(self, n_chunks: int) -> bool:
        """THE SECOND GATE — exact, and still BEFORE any encoding.

        Chunking yields the true chunk count for free, and the encode cost is
        per CHUNK rather than per token, so this comparison is the real budget
        rather than a projection of it. It exists because the first gate is an
        estimate: an under-estimate that slipped a too-large document into zone 2
        would otherwise be discovered by running out of time, which is the failure
        DEC-47 forbids. Both gates refuse before a single vector is computed."""
        return n_chunks > self.max_chunks

    @classmethod
    def from_env(cls) -> "ZonePolicy":
        """Read the two knobs. Unparseable values WARN and fall back to default.

        The split is deliberate: a non-integer `MUTHIS_DOC_INJECT_LIMIT` is a
        TYPO, and a run-forever app does not die on a typo (the
        `MUTHIS_POINTER_ANIM_MS` precedent) — the default it falls back to is
        coherent. A parseable but INCOHERENT pair is a different thing entirely
        and `assert_zone_invariant` fails the process on it."""
        return cls(inject_limit=_env_number(ENV_INJECT_LIMIT,
                                           DEFAULT_INJECT_LIMIT_TOKENS, int),
                   budget_seconds=_env_number(ENV_INGEST_BUDGET,
                                              DEFAULT_INGESTION_BUDGET_SECONDS,
                                              float))


def _env_number(name: str, default, cast):
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return cast(raw)
    except ValueError:
        logger.warning("[doc_rag] %s=%r is not a number — using default %s",
                       name, raw, default)
        return default


def assert_zone_invariant(policy: ZonePolicy | None = None) -> ZonePolicy:
    """THE STARTUP ASSERTION (DEC-49 ruling 4). Returns the policy, or RAISES.

    `derived maximum > injection limit`, or zone 2 is empty and DEC-47's design
    is incoherent. Deliberately not a warning: an unreachable zone is not a
    degraded mode. The log line on the healthy path is as load-bearing as the
    raise, because it puts the derived numbers in the record of every run — the
    relation was written down nowhere before DEC-49, and a number nobody can see
    is a number nobody notices changing."""
    policy = policy or ZonePolicy.from_env()
    if policy.max_tokens <= policy.inject_limit:
        raise ZoneConfigurationError(
            f"zone 2 is EMPTY: derived maximum {policy.max_tokens} tokens "
            f"({policy.max_chunks} chunks at {policy.per_chunk_ms:g} ms) does not "
            f"exceed {ENV_INJECT_LIMIT}={policy.inject_limit}. Either raise "
            f"{ENV_INGEST_BUDGET} (now {policy.budget_seconds:g}s) or lower the "
            f"injection limit: the two are NOT independent knobs (DEC-49 ruling 4).")
    # ASCII ONLY in the message above, deliberately. This text reaches a Windows
    # console that is cp1256 here, at startup, BEFORE any stdout reconfigure has a
    # chance to matter in a traceback — an em dash would turn the one message an
    # operator needs into mojibake. The same cp1256 armor the MCP wire needed.
    # BOTH figures. Printing only the derived one states a maximum production does
    # not reproduce; printing only the live one would hide the boundary actually in
    # force. The operator needs to see the GAP, not a number swapped underneath them.
    live_max = int(policy.max_tokens * policy.per_chunk_ms / MEASURED_LIVE_PER_CHUNK_MS)
    logger.info("[doc_rag] zones: inject<=%d tokens, index<=%d tokens "
                "(%d chunks at %.1f ms/chunk BENCH within a %.0fs budget), refuse above",
                policy.inject_limit, policy.max_tokens, policy.max_chunks,
                policy.per_chunk_ms, policy.budget_seconds)
    logger.info("[doc_rag] zones: that %.1f ms/chunk is a BENCH figure; the live SOP "
                "measured %.1f, so the OPERATING maximum is nearer %d tokens. The "
                "invariant holds either way (%d > %d).",
                policy.per_chunk_ms, MEASURED_LIVE_PER_CHUNK_MS, live_max,
                live_max, policy.inject_limit)
    return policy


__all__ = [
    "DEFAULT_INGESTION_BUDGET_SECONDS", "DEFAULT_INJECT_LIMIT_TOKENS",
    "ENV_INGEST_BUDGET", "ENV_INJECT_LIMIT", "MEAN_CHUNK_TOKENS",
    "MEASURED_LIVE_PER_CHUNK_MS", "PER_CHUNK_ENCODE_MS",
    "TOKENS_PER_CHAR_CEILING", "DocZone",
    "ZoneConfigurationError", "ZoneDecision", "ZonePolicy",
    "assert_zone_invariant", "estimate_tokens",
]
