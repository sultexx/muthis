# tests/test_doc_zones.py
"""
The three size zones and the startup invariant (V2 Phase 2 M3, T3 — DEC-47/DEC-49).

WHAT THIS FILE DEFENDS THAT NOTHING ELSE CAN. The zone relation
(`derived maximum > injection limit`) was written down NOWHERE before DEC-49, and
P0 measured it INVERTING under the rejected encoder — bge-m3 at a 60 s budget
derives ~40,660 tokens against a 50,000 limit, which empties zone 2 entirely.
Nothing at runtime would report that: every document would take one of two paths,
both would look healthy, and the retrieval feature would simply not exist. So the
invariant is DRIVEN here with the real measured numbers that break it, never
merely asserted true for the config that happens to ship.

THE CORPUS ROUTING IS DRIVEN BY MEASURED DIMENSIONS, NOT BY THE CORPUS. The P0
corpus is Sultan's private files and never enters this repository, its logs, or
any artifact. What enters is the measurement: three character counts and three
token counts from the P0 report's own tables. Routing those through the real
estimator and the real policy checks exactly what a re-read of the files would
check — the zone each document lands in — without a byte of them being here.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib

import pytest

from muthis.broker.docs.token_estimate import (
    MEASURED_RATIOS, TOKENS_PER_CHAR_CEILING, estimate_tokens,
)
from muthis.broker.docs.zones import (
    DEFAULT_INJECT_LIMIT_TOKENS, ENV_INGEST_BUDGET, ENV_INJECT_LIMIT,
    MEAN_CHUNK_TOKENS, PER_CHUNK_ENCODE_MS, SUPERSEDED_BENCH_PER_CHUNK_MS,
    DocZone, ZoneConfigurationError, ZoneDecision, ZonePolicy,
    assert_zone_invariant,
)

# The P0 corpus, as MEASURED DIMENSIONS (report §5 and §7). chars -> the zone the
# P0 gate placed the document in. Two of three never touch the index, which is
# DEC-47's build-order argument in data.
P0_CORPUS = (
    ("doc C (md, 69% ar)", 2_788, 909, DocZone.INJECT),
    ("doc B (66pp pdf, 97% ar)", 31_350, 9_945, DocZone.INJECT),
    ("doc A (228pp pdf, 44% ar)", 384_288, 103_187, DocZone.INDEX),
)

# The rejected encoder's MEASURED per-chunk time (P0 §6). This is the number that
# makes the invariant fail, and it is a measurement rather than a synthetic value.
BGE_M3_PER_CHUNK_MS = 558.4


# ---------------------------------------------------------------------------
# The derived maximum is COMPUTED from measurements
# ---------------------------------------------------------------------------

def test_the_maximum_is_derived_from_the_measured_encode_time():
    policy = ZonePolicy()

    # floor(60_000 ms / 67.4 ms) = 890 chunks, x 380 tokens = 338_200.
    assert policy.max_chunks == int(60_000 // PER_CHUNK_ENCODE_MS) == 890
    assert policy.max_tokens == policy.max_chunks * MEAN_CHUNK_TOKENS == 338_200


def test_the_chunk_count_is_FLOORED_because_a_partial_chunk_cannot_be_encoded():
    # 100 chunks' worth of budget plus a sliver buys 100 chunks, never 101.
    # Derived from the constant rather than a literal, so this stays a test of the
    # FLOOR and never quietly becomes a second copy of the encode time.
    per = PER_CHUNK_ENCODE_MS
    policy = ZonePolicy(budget_seconds=(100 * per + per / 2) / 1000.0, per_chunk_ms=per)

    assert policy.max_chunks == 100


# ---------------------------------------------------------------------------
# THE CEILING'S PROVENANCE — DEC-72, and the defect it closed
# ---------------------------------------------------------------------------

def test_the_ceiling_is_derived_from_the_PRODUCTION_figure_not_the_BENCH_one():
    """DEC-72. The bench figure derived a ceiling that ACCEPTED documents the
    budget could not COMPLETE: 754,680 tokens is ~134 s of encoding against a 60 s
    budget, so the capability it protected was admitted by wrong arithmetic.

    THE DISCRIMINATING ASSERTION is the second one. "The maximum is 338,200" is
    satisfiable by any constant that happens to produce it; what must not come back
    is the BENCH figure driving a zone boundary — which is exactly the edit a future
    reader makes after finding the P0 bench report and seeing a faster number."""
    policy = ZonePolicy()

    assert policy.per_chunk_ms == PER_CHUNK_ENCODE_MS == 67.4
    assert PER_CHUNK_ENCODE_MS != SUPERSEDED_BENCH_PER_CHUNK_MS
    # The superseded figure DERIVES NOTHING: it is not the default of any field.
    defaults = {f.name: f.default for f in dataclasses.fields(ZonePolicy)}
    assert SUPERSEDED_BENCH_PER_CHUNK_MS not in defaults.values()


def test_the_ceiling_in_force_is_one_the_BUDGET_CAN_ACTUALLY_COMPLETE():
    """The property the old constant violated, stated as arithmetic rather than as
    a number — so it holds for any future re-derivation too.

    A maximum that cannot be encoded inside the budget is not a capability, it is
    an acceptance that ends in an overrun (DEC-47: estimate the refusal UP FRONT)."""
    policy = ZonePolicy()

    encode_ms = policy.max_chunks * policy.per_chunk_ms

    assert encode_ms <= policy.budget_seconds * 1000.0
    # And the SUPERSEDED figure fails it, which is what made it a defect: driving
    # the ceiling at 30.2 buys 1,986 chunks that then cost 67.4 ms each.
    bench = dataclasses.replace(policy, per_chunk_ms=SUPERSEDED_BENCH_PER_CHUNK_MS)
    assert bench.max_chunks * PER_CHUNK_ENCODE_MS > policy.budget_seconds * 1000.0


def test_the_CAPABILITY_REDUCTION_is_driven_rather_than_only_recorded():
    """Sultan's ruling required the reduction be recorded EXPLICITLY. Recording it
    in prose leaves nothing that fails if it is reverted, so it is driven here.

    The affected band is 338,200-754,680 tokens — roughly 900 to 2,000 pages. A
    document there used to INDEX and now REFUSES. The band's lower neighbour still
    indexes and zone 1 is untouched, so this is not satisfied by a policy that
    refuses everything."""
    policy = ZonePolicy()
    bench_max = dataclasses.replace(
        policy, per_chunk_ms=SUPERSEDED_BENCH_PER_CHUNK_MS).max_tokens

    assert (policy.max_tokens, bench_max) == (338_200, 754_680)
    # The whole band moved INDEX -> REFUSE...
    for tokens in (338_201, 500_000, bench_max):
        assert policy.zone_for_tokens(tokens) is DocZone.REFUSE
    # ...and nothing below it moved: zone 2 and zone 1 are exactly as they were.
    assert policy.zone_for_tokens(338_200) is DocZone.INDEX
    assert policy.zone_for_tokens(50_000) is DocZone.INJECT
    assert policy.inject_limit == DEFAULT_INJECT_LIMIT_TOKENS == 50_000


def test_a_nonsensical_encode_time_derives_ZERO_rather_than_dividing_by_zero():
    assert ZonePolicy(per_chunk_ms=0.0).max_chunks == 0
    # ...and zero chunks cannot exceed the injection limit, so the invariant
    # catches it through the SAME comparison rather than needing its own branch.
    with pytest.raises(ZoneConfigurationError):
        assert_zone_invariant(ZonePolicy(per_chunk_ms=0.0))


# ---------------------------------------------------------------------------
# THE STARTUP INVARIANT — driven broken, not asserted true
# ---------------------------------------------------------------------------

def test_the_shipped_configuration_satisfies_the_invariant(caplog):
    with caplog.at_level("INFO", logger="muthis.broker.docs"):
        policy = assert_zone_invariant(ZonePolicy())

    assert policy.max_tokens > policy.inject_limit
    # The healthy path LOGS the derived numbers, which is half the point: a
    # relation nobody can see is a relation nobody notices changing (DEC-49).
    assert "338200" in caplog.text and "50000" in caplog.text


def test_the_startup_log_states_the_ceilings_PROVENANCE_and_the_figure_it_replaced(
        caplog):
    """DEC-72's log half. The old second line reported the GAP between a
    bench-derived boundary and the operating figure; that gap is closed, so the line
    now has to earn its place by reporting something else — WHERE the number came
    from, and what the superseded one would have admitted.

    The superseded figure is reported by its CONSEQUENCE (754,680 tokens), not by
    itself: "30.2 ms" tells an operator nothing about what was wrong."""
    with caplog.at_level("INFO", logger="muthis.broker.docs"):
        assert_zone_invariant(ZonePolicy())

    assert "PRODUCTION measurement" in caplog.text
    assert "754680" in caplog.text          # the superseded consequence, named
    assert f"{SUPERSEDED_BENCH_PER_CHUNK_MS:g} ms bench" in caplog.text
    # The re-derivation rule reaches the operator, not just the source comment.
    assert "production run" in caplog.text


def test_the_REJECTED_encoders_measured_time_EMPTIES_zone_2_and_FAILS_STARTUP():
    """The configuration P0 actually measured inverting, driven directly.

    bge-m3 at 558.4 ms/chunk and a 60 s budget derives ~40,660 tokens — BELOW the
    50,000 injection limit. Every document big enough to need an index is already
    too big to build one, so DEC-47's middle zone does not exist."""
    broken = ZonePolicy(per_chunk_ms=BGE_M3_PER_CHUNK_MS)

    assert broken.max_tokens < broken.inject_limit          # the inversion is real
    with pytest.raises(ZoneConfigurationError) as caught:
        assert_zone_invariant(broken)

    message = str(caught.value)
    assert "zone 2 is EMPTY" in message
    # The message must name BOTH knobs, because the fix is a relation between them
    # and naming only one sends an operator to tune the wrong number.
    assert ENV_INJECT_LIMIT in message and ENV_INGEST_BUDGET in message
    assert "40660" in message and "50000" in message


def test_the_invariant_also_fails_when_the_BUDGET_is_what_broke():
    # Same relation, broken from the other side: the shipped encoder, a 2 s budget.
    with pytest.raises(ZoneConfigurationError):
        assert_zone_invariant(ZonePolicy(budget_seconds=2.0))


def test_an_EQUAL_maximum_still_fails_because_zone_2_would_be_a_single_point():
    # max == limit leaves a band of width zero. "Exceeds" means exceeds.
    equal = ZonePolicy(inject_limit=338_200)

    assert equal.max_tokens == equal.inject_limit
    with pytest.raises(ZoneConfigurationError):
        assert_zone_invariant(equal)


def test_the_failure_message_is_ASCII_so_a_cp1256_console_can_show_it():
    """This machine's console is cp1256 and this message appears at startup, in a
    traceback, before anything has reconfigured stdout. An em dash would turn the
    one message an operator needs into mojibake — the same wire armor the MCP
    layer needed on this host."""
    with pytest.raises(ZoneConfigurationError) as caught:
        assert_zone_invariant(ZonePolicy(budget_seconds=1.0))

    str(caught.value).encode("ascii")          # raises if a non-ASCII char slipped in


# ---------------------------------------------------------------------------
# THE STARTUP CALL SITE — a production call whose deletion would be invisible
# ---------------------------------------------------------------------------

def _main_function() -> ast.FunctionDef:
    tree = ast.parse(pathlib.Path("src/muthis/main.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    raise AssertionError("main() not found in main.py")


def test_main_CALLS_the_invariant_before_the_event_loop_opens():
    """DEC-40's lesson, applied before it can bite: five of six mutations survived
    there because every test built its own router, so DELETING the production
    mount call stayed green. A startup check is the same shape — nothing else in
    the suite would notice its absence, so this asserts the call site itself."""
    body = _main_function().body
    called_at = [i for i, stmt in enumerate(body)
                 if any(isinstance(n, ast.Call) and getattr(n.func, "id", "") ==
                        "assert_zone_invariant" for n in ast.walk(stmt))]
    ran_loop_at = [i for i, stmt in enumerate(body)
                   if any(isinstance(n, ast.Call) and
                          getattr(n.func, "attr", "") == "run" for n in ast.walk(stmt))]

    assert called_at, "main() must call assert_zone_invariant at startup (DEC-49)"
    # ORDER is the property: a check after the loop opens is a check the first
    # document would beat to the punch.
    assert min(called_at) < min(ran_loop_at)


# ---------------------------------------------------------------------------
# The two boundaries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tokens,expected", [
    (0, DocZone.INJECT),
    (49_999, DocZone.INJECT),
    (50_000, DocZone.INJECT),          # AT the limit is injected — inclusive
    (50_001, DocZone.INDEX),
    (338_200, DocZone.INDEX),          # AT the maximum is still indexable
    (338_201, DocZone.REFUSE),
])
def test_each_boundary_is_inclusive_of_the_CHEAPER_zone(tokens, expected):
    assert ZonePolicy().zone_for_tokens(tokens) is expected


def test_the_two_boundaries_are_DIFFERENT_numbers_and_ordered():
    """Not two independent assertions that a mutation could satisfy by collapsing
    both onto one value — the INEQUALITY is what is asserted."""
    policy = ZonePolicy()

    assert policy.inject_limit < policy.max_tokens
    assert policy.zone_for_tokens(policy.inject_limit + 1) is DocZone.INDEX
    assert policy.zone_for_tokens(policy.max_tokens + 1) is DocZone.REFUSE


# ---------------------------------------------------------------------------
# THE ESTIMATE — an upper bound, on purpose
# ---------------------------------------------------------------------------

def test_the_ratio_is_the_HIGHEST_p0_measured_and_STRICTLY_above_the_rest():
    """The trap this closes: 0.317 (pure Arabic) is also "a measured ratio" and
    also upper-bounds most of the corpus, so a mutation swapping the ceiling for
    it would look defensible. Asserting the ceiling is the MAXIMUM, and strictly
    above the runner-up, is what makes that mutation fail."""
    assert TOKENS_PER_CHAR_CEILING == max(MEASURED_RATIOS)
    assert TOKENS_PER_CHAR_CEILING > sorted(MEASURED_RATIOS)[-2]


@pytest.mark.parametrize("ratio", MEASURED_RATIOS)
def test_the_estimate_never_UNDER_states_a_document_at_any_measured_ratio(ratio):
    """Under-estimation is the harmful direction (it admits a document that then
    exceeds the ingestion budget), so the bound must hold for every text P0 saw."""
    chars = 100_000

    assert estimate_tokens(chars) >= chars * ratio


def test_the_estimate_is_an_upper_bound_on_every_p0_corpus_document():
    for name, chars, true_tokens, _zone in P0_CORPUS:
        assert estimate_tokens(chars) >= true_tokens, name


def test_an_empty_document_estimates_zero_rather_than_going_negative():
    assert estimate_tokens(0) == 0
    assert estimate_tokens(-5) == 0


# ---------------------------------------------------------------------------
# THE REAL CORPUS, routed by its measured dimensions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,chars,true_tokens,expected", P0_CORPUS)
def test_every_p0_corpus_document_routes_to_the_zone_the_gate_measured(
        name, chars, true_tokens, expected):
    """Routed from CHARACTERS through the real estimator, and compared against the
    zone the P0 report assigned from the TRUE token count. The estimate is allowed
    to be generous; it is not allowed to change the answer."""
    policy = ZonePolicy()
    decision = policy.decide(chars)

    assert decision.zone is expected, f"{name}: {decision.describe()}"
    assert policy.zone_for_tokens(true_tokens) is expected, f"{name}: true count"


def test_two_of_the_three_corpus_documents_never_touch_the_index():
    """DEC-47's build-order argument, stated as a number: zone 1 is the COMMON
    path. If this ever drops to zero the ordering premise is gone and the
    milestone's whole shape should be re-argued rather than quietly rebalanced."""
    zones = [ZonePolicy().decide(chars).zone for _n, chars, _t, _z in P0_CORPUS]

    assert zones.count(DocZone.INJECT) == 2


def test_a_document_far_above_the_maximum_is_refused():
    decision = ZonePolicy().decide(3_000_000)

    assert decision.zone is DocZone.REFUSE
    assert decision.admitted == 0        # zero admitted is a FAILURE, not a pass


# ---------------------------------------------------------------------------
# The SECOND gate is counted in CHUNKS, the unit the budget is spent in
# ---------------------------------------------------------------------------

def test_the_exact_gate_counts_CHUNKS_not_tokens():
    policy = ZonePolicy()

    assert not policy.exceeds_budget(policy.max_chunks)
    assert policy.exceeds_budget(policy.max_chunks + 1)


# ---------------------------------------------------------------------------
# The decision reports its cutoffs (the standing rule)
# ---------------------------------------------------------------------------

def test_a_decision_states_both_cutoffs_and_its_admitted_count():
    line = ZonePolicy().decide(2_788).describe()

    assert "inject_limit=50000" in line and "max_tokens=338200" in line
    assert "admitted=1" in line
    assert f"{TOKENS_PER_CHAR_CEILING:g}tok/char" in line     # HOW it was sized


def test_an_exact_decision_says_counted_rather_than_estimated():
    exact = ZoneDecision(zone=DocZone.REFUSE, chars=1, tokens=9, inject_limit=1,
                         max_tokens=2, exact=True)

    assert "counted" in exact.describe() and "estimated" not in exact.describe()
    assert exact.admitted == 0


def test_a_decision_CANNOT_carry_a_path_because_it_has_no_field_for_one():
    """Structural, not textual: the `FetchedDomains` precedent, which proved it
    could not leak a domain by having nothing to leak it from. A decision holds
    counts and cutoffs, so no future `describe()` can start logging the user's
    filesystem — there is nothing there to log."""
    fields = {f.name for f in dataclasses.fields(ZoneDecision)}

    assert not fields & {"path", "name", "file", "source", "text", "blocks"}
    assert fields == {"zone", "chars", "tokens", "inject_limit", "max_tokens",
                      "exact"}
    line = ZonePolicy().decide(31_350).describe()
    assert "\\" not in line and ".pdf" not in line       # nor by accident


# ---------------------------------------------------------------------------
# Config: a TYPO is not a broken relation
# ---------------------------------------------------------------------------

def test_a_typo_warns_and_falls_back_rather_than_killing_a_forever_app(
        monkeypatch, caplog):
    monkeypatch.setenv(ENV_INJECT_LIMIT, "fifty thousand")

    with caplog.at_level("WARNING", logger="muthis.broker.docs"):
        policy = ZonePolicy.from_env()

    assert policy.inject_limit == DEFAULT_INJECT_LIMIT_TOKENS
    assert ENV_INJECT_LIMIT in caplog.text
    # ...and the default it fell back to is COHERENT, so startup still passes.
    assert_zone_invariant(policy)


def test_a_real_value_is_honoured_from_the_environment(monkeypatch):
    monkeypatch.setenv(ENV_INJECT_LIMIT, "12345")
    monkeypatch.setenv(ENV_INGEST_BUDGET, "90")

    policy = ZonePolicy.from_env()

    assert policy.inject_limit == 12_345 and policy.budget_seconds == 90.0


def test_an_empty_value_is_treated_as_unset(monkeypatch):
    monkeypatch.setenv(ENV_INJECT_LIMIT, "   ")

    assert ZonePolicy.from_env().inject_limit == DEFAULT_INJECT_LIMIT_TOKENS
