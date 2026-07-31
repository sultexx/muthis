"""
test_prompt_caching.py — the cache-aware accounting guard.

THE DEFECT THIS FILE EXISTS TO PREVENT, stated once so a future reader knows
what may not be relaxed:

  `usage.input_tokens` EXCLUDES the cached portion. MEASURED live 2026-07-31 on
  claude-sonnet-4-6 (scripts/diag_prompt_cache_usage.py): 13 + 7923 = 7936, the
  cache-blind total, on BOTH the write call and the read call. So a ledger that
  prices `input_tokens` alone UNDER-reports — 25x on a cache read and 301x on a
  cache write — and an under-reporting ledger does not stop a session that has
  already breached the sovereign ceiling. That is Rule 10 failing OPEN, which is
  strictly worse than stopping early.

  The cache WRITE is the worst case AND the first turn of every session: it costs
  1.25x MORE than not caching at all, while the naive formula reports 1/301st of
  it. The ledger would record its largest discount at the moment it paid its
  largest premium.

A separate guard covers the byte-pinned catalog: the breakpoint is written to a
request-time COPY, never into a mounted descriptor.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from muthis.cloud.cache_control import cacheable_system, cacheable_tools
from muthis.cloud.claude_agent import ClaudeAgent
from muthis.cloud.pricing import (
    CACHE_READ_MULTIPLIER,
    CACHE_WRITE_1H_MULTIPLIER,
    CACHE_WRITE_5M_MULTIPLIER,
    estimate_cost_usd,
    split_cache_creation,
)
from muthis.cloud.protocol import TurnComplete, UserInput

MODEL = "claude-sonnet-4-6"
IN_PRICE, OUT_PRICE = 3.00, 15.00

# The measured shape, reused so the numbers in the assertions are the numbers
# that came off the wire rather than invented ones.
MEASURED_REMAINDER = 13
MEASURED_CACHED = 7923
MEASURED_OUTPUT = 4


# ──────────────────────────────────────────────────────────────────────────
# Fake stream — a usage object whose cache fields the test controls
# ──────────────────────────────────────────────────────────────────────────


class _FakeBlock(SimpleNamespace):
    def model_dump(self, exclude_none=True):
        return dict(self.__dict__)


class _FakeStream:
    def __init__(self, events):
        self._events = events

    def __aiter__(self):
        self._iter = iter(self._events)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration

    async def get_final_message(self):
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[_FakeBlock(type="text", text="ok")],
        )


def _events(usage) -> list:
    return [
        SimpleNamespace(type="message_start",
                        message=SimpleNamespace(usage=usage)),
        SimpleNamespace(type="content_block_start",
                        content_block=SimpleNamespace(type="text")),
        SimpleNamespace(type="content_block_delta",
                        delta=SimpleNamespace(type="text_delta", text="ok")),
        SimpleNamespace(type="content_block_stop"),
        SimpleNamespace(type="message_delta",
                        delta=SimpleNamespace(stop_reason="end_turn"),
                        usage=SimpleNamespace(output_tokens=MEASURED_OUTPUT)),
        SimpleNamespace(type="message_stop"),
    ]


async def _run_turn(usage) -> TurnComplete:
    """Drive the REAL ClaudeAgent.run() over a stream carrying `usage`."""
    agent = ClaudeAgent(api_key="test-key", model=MODEL)

    @asynccontextmanager
    async def cm(*_args, **_kwargs):
        yield _FakeStream(_events(usage))

    with patch.object(agent._client.messages, "stream", cm):
        events = [ev async for ev in agent.run(
            user_input=UserInput(text="مرحبا"), screenshot=None, history=[])]
    completes = [e for e in events if isinstance(e, TurnComplete)]
    assert len(completes) == 1
    return completes[0]


def _usage(*, input_tokens, cache_read=None, cache_creation=None,
           five_m=None, one_h=None):
    """A usage namespace. Attributes are OMITTED when None so the object models
    a provider that does not report them at all, not one reporting zero."""
    fields = {"input_tokens": input_tokens}
    if cache_read is not None:
        fields["cache_read_input_tokens"] = cache_read
    if cache_creation is not None:
        fields["cache_creation_input_tokens"] = cache_creation
    if five_m is not None or one_h is not None:
        fields["cache_creation"] = SimpleNamespace(
            ephemeral_5m_input_tokens=five_m or 0,
            ephemeral_1h_input_tokens=one_h or 0)
    return SimpleNamespace(**fields)


# ──────────────────────────────────────────────────────────────────────────
# 1. THE acceptance test — a cache WRITE records the FULL billed cost
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_cache_write_turn_records_the_full_billed_cost_including_the_premium():
    """The one that matters. A cache-write turn must be priced on ALL the tokens
    it actually paid for — the 7923 written at 1.25x PLUS the 13-token uncached
    remainder — not on the remainder alone.

    If this ever fails by reporting ~$0.000099, the ledger has gone back to
    pricing `input_tokens` alone and Rule 10 is failing OPEN again."""
    done = await _run_turn(_usage(
        input_tokens=MEASURED_REMAINDER,
        cache_read=0,
        cache_creation=MEASURED_CACHED,
        five_m=MEASURED_CACHED, one_h=0))

    expected = ((MEASURED_REMAINDER + MEASURED_CACHED * CACHE_WRITE_5M_MULTIPLIER)
                * IN_PRICE + MEASURED_OUTPUT * OUT_PRICE) / 1_000_000
    assert done.cost_usd == pytest.approx(expected)

    # And it is NOT the remainder-only figure the naive formula produces.
    naive = (MEASURED_REMAINDER * IN_PRICE + MEASURED_OUTPUT * OUT_PRICE) / 1_000_000
    assert done.cost_usd > naive * 100, (
        "the write turn is priced like an uncached 13-token turn — the ledger "
        "is under-reporting by ~301x and the ceiling will breach silently")

    # The write really is MORE expensive than not caching at all (1.25x).
    uncached = ((MEASURED_REMAINDER + MEASURED_CACHED) * IN_PRICE
                + MEASURED_OUTPUT * OUT_PRICE) / 1_000_000
    assert done.cost_usd > uncached

    # The flat counters ride out for observability.
    assert done.cache_creation_input_tokens == MEASURED_CACHED
    assert done.cache_read_input_tokens == 0


@pytest.mark.asyncio
async def test_a_cache_read_turn_is_priced_at_the_read_multiplier():
    done = await _run_turn(_usage(
        input_tokens=MEASURED_REMAINDER,
        cache_read=MEASURED_CACHED,
        cache_creation=0))

    expected = ((MEASURED_REMAINDER + MEASURED_CACHED * CACHE_READ_MULTIPLIER)
                * IN_PRICE + MEASURED_OUTPUT * OUT_PRICE) / 1_000_000
    assert done.cost_usd == pytest.approx(expected)
    naive = (MEASURED_REMAINDER * IN_PRICE + MEASURED_OUTPUT * OUT_PRICE) / 1_000_000
    assert done.cost_usd > naive * 10
    assert done.cache_read_input_tokens == MEASURED_CACHED


# ──────────────────────────────────────────────────────────────────────────
# 2. The NESTED breakdown decides the multiplier — never the flat scalar
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_one_hour_write_is_priced_at_2x_not_at_the_five_minute_rate():
    """The flat scalar is identical for a 5m and a 1h write; only the nested
    object distinguishes them, and they bill at 1.25x and 2x. Pricing off the
    scalar would under-report a 1h write by a further 1.6x with NO signal."""
    done = await _run_turn(_usage(
        input_tokens=MEASURED_REMAINDER,
        cache_read=0,
        cache_creation=MEASURED_CACHED,
        five_m=0, one_h=MEASURED_CACHED))

    at_1h = ((MEASURED_REMAINDER + MEASURED_CACHED * CACHE_WRITE_1H_MULTIPLIER)
             * IN_PRICE + MEASURED_OUTPUT * OUT_PRICE) / 1_000_000
    at_5m = ((MEASURED_REMAINDER + MEASURED_CACHED * CACHE_WRITE_5M_MULTIPLIER)
             * IN_PRICE + MEASURED_OUTPUT * OUT_PRICE) / 1_000_000
    assert done.cost_usd == pytest.approx(at_1h)
    assert done.cost_usd > at_5m


def test_an_absent_breakdown_prices_at_the_HIGHER_multiplier_and_logs(caplog):
    """An unknown TTL must never resolve in the ledger's favour."""
    with caplog.at_level(logging.WARNING, logger="muthis.cloud.pricing"):
        five_m, one_h = split_cache_creation(1000, None)
    assert (five_m, one_h) == (0, 1000), "unknown TTL must be priced at 1h (2x)"
    assert "breakdown absent" in caplog.text


def test_buckets_that_do_not_reconcile_price_the_remainder_at_the_HIGHER_rate(caplog):
    """A future TTL bucket this code does not know about would otherwise vanish
    from pricing entirely. The unexplained remainder goes to 1h and is logged."""
    breakdown = SimpleNamespace(ephemeral_5m_input_tokens=400,
                                ephemeral_1h_input_tokens=100)
    with caplog.at_level(logging.WARNING, logger="muthis.cloud.pricing"):
        five_m, one_h = split_cache_creation(1000, breakdown)
    assert (five_m, one_h) == (400, 600)          # 500 unexplained -> 1h
    assert "account for" in caplog.text


def test_no_cache_activity_reduces_exactly_to_the_pre_caching_formula():
    """The DEC-34 degradation property, asserted directly on the arithmetic.
    (test_claude_agent.py::test_fake_session_event_sequence proves the same
    property end-to-end through an UNTOUCHED pre-existing assertion.)"""
    assert estimate_cost_usd(MODEL, 850, 64) == pytest.approx(
        (850 * IN_PRICE + 64 * OUT_PRICE) / 1_000_000)


@pytest.mark.asyncio
async def test_a_provider_that_does_not_cache_leaves_the_counters_None():
    done = await _run_turn(_usage(input_tokens=850))
    assert done.cache_read_input_tokens is None
    assert done.cache_creation_input_tokens is None
    assert done.cost_usd == pytest.approx(
        (850 * IN_PRICE + MEASURED_OUTPUT * OUT_PRICE) / 1_000_000)


# ──────────────────────────────────────────────────────────────────────────
# 3. The copy discipline — the byte-pinned catalog is never edited in place
# ──────────────────────────────────────────────────────────────────────────


def test_cacheable_tools_never_mutates_the_mounted_descriptors():
    """THE safety of the request-shaping step. router.descriptors() hands back
    the SAME dict objects every call, so an in-place write would change the
    model-visible catalog for the whole process and break the byte pin."""
    mounted = [{"name": "a", "input_schema": {}}, {"name": "b", "input_schema": {}}]
    before = json.dumps(mounted, sort_keys=True)

    shaped = cacheable_tools(mounted)

    assert json.dumps(mounted, sort_keys=True) == before, "the catalog was mutated"
    assert "cache_control" not in mounted[-1]
    assert shaped[-1]["cache_control"] == {"type": "ephemeral"}
    assert shaped[-1] is not mounted[-1], "the last tool must be a COPY"
    assert shaped[0] is mounted[0], "earlier tools are shared by reference"


def test_the_real_v4_catalog_survives_shaping_byte_identical():
    """The end-to-end version of the guard above, against the REAL production
    catalog rather than a hand-built pair — the same bytes test_doc_mount pins."""
    from muthis.composition import mount_doc_rag, mount_web_research
    from muthis.kernel.core_router import build_core_router
    from muthis_plugins.doc_rag.plugin import DocRagPlugin
    from muthis_plugins.sandbox_exec import SandboxExecPlugin
    from muthis_plugins.web_research.plugin import WebResearchPlugin

    class _StubFetcher:
        async def fetch_readable(self, url):  # pragma: no cover - never called
            raise AssertionError("the catalog test must not fetch")

    router = build_core_router(read_file=None)
    router.mount(SandboxExecPlugin(), namespace="sandbox", provenance="sandbox_exec")
    mount_web_research(router, WebResearchPlugin(), _StubFetcher())
    mount_doc_rag(router, DocRagPlugin())

    catalog = [d.schema for d in router.descriptors()]
    before = json.dumps(catalog, ensure_ascii=False, sort_keys=True)

    cacheable_tools(catalog)

    after = json.dumps([d.schema for d in router.descriptors()],
                       ensure_ascii=False, sort_keys=True)
    assert after == before, (
        "shaping the catalog for caching mutated the mounted descriptors — the "
        "byte-pinned model-visible catalog would drift from look_tools_v4.json")


def test_cacheable_system_is_the_block_form_carrying_the_breakpoint():
    """Only the block form accepts cache_control; a plain string cannot cache."""
    blocks = cacheable_system("النص")
    assert blocks == [{"type": "text", "text": "النص",
                       "cache_control": {"type": "ephemeral"}}]


def test_empty_tool_list_is_returned_untouched():
    assert cacheable_tools([]) == []


# ──────────────────────────────────────────────────────────────────────────
# 4. The wire — both breakpoints actually reach the SDK call
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_both_breakpoints_reach_the_sdk_and_the_tool_names_are_unchanged():
    agent = ClaudeAgent(api_key="test-key", model=MODEL)
    captured: dict = {}

    @asynccontextmanager
    async def cm(*_args, **kwargs):
        captured.update(kwargs)
        yield _FakeStream(_events(_usage(input_tokens=10)))

    with patch.object(agent._client.messages, "stream", cm):
        _ = [ev async for ev in agent.run(
            user_input=UserInput(text="مرحبا"), screenshot=None, history=[])]

    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert captured["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    # Only the LAST tool carries a breakpoint (max 4 per request; one is enough
    # for a prefix that ends at the catalog).
    assert all("cache_control" not in t for t in captured["tools"][:-1])
    # The model-visible surface is otherwise unchanged.
    assert {t["name"] for t in captured["tools"]} == {
        "highlight_target", "draw_shapes", "request_screen_refresh",
        "read_local_file"}
