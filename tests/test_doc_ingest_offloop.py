# tests/test_doc_ingest_offloop.py
"""
Zone-2 indexing runs OFF the event loop — a restored guarantee, not a feature.

**THE DEFECT WAS A KERNEL CONCURRENCY BUG WEARING SILENCE AS A DISGUISE.**
`ingest.py` called `_index` SYNCHRONOUSLY from an async function, so chunking, the
encoder load and encoding all ran on the loop thread and blocked it for the
measured ~20 s. The missing spoken announcement was the least of it: **the F9
barge-in reaches the kernel through `loop.call_soon_threadsafe`, so it was
scheduled onto a loop that could not run it.** A user pressing stop got nothing
for twenty seconds — against the ~100 ms interrupt that is the oldest guarantee in
the voice line — and a user who presses stop and sees nothing does not perceive
silence, they perceive a HANG.

It also explains why no announcement could ever have worked: the TTS reader task
lives on that same loop, so audio fed just before the block would not be HEARD
until after the silence it exists to explain.

DEC-64 ruling 3's MEASUREMENT stands (20.03 s cold vs 25.79 s warm, thermal
derating, the accumulating-structure hypothesis refuted). Its CAUSE was
misdiagnosed as *quiet* when it was *blocked*.

**WHAT IS PROVEN HERE, AND WHAT IS NOT.** These are deterministic proofs that the
encode leaves the loop thread and that the loop keeps running while it does — with
a POSITIVE CONTROL proving the probe can detect a blocked loop, because a
responsiveness test that cannot fail is worse than none (the DEC-50 cutoff rule).
What they CANNOT prove is the real-world figure: the production encode is native
code (`tokenizers` in Rust, `onnxruntime` in C++), and `to_thread` only frees the
loop while those libraries RELEASE THE GIL. They do; that is not verified here,
because it needs the pinned model and Sultan's corpus. **The live F9-during-
ingestion check is his.**
"""

from __future__ import annotations

import asyncio
import pathlib
import threading
import time

import numpy as np
import pytest

from muthis.broker.docs.blocks import Block, ExtractReport
from muthis.broker.docs.ingest import DocumentIngestor
from muthis.broker.docs.zones import DocZone, ZonePolicy

DOC = pathlib.Path("teaching/notes.md")

# Long enough to be unambiguous against scheduler noise, short enough that the
# suite does not notice. The assertions are ORDERING, never duration.
BLOCK_S = 0.40


class _SleepingEncoder:
    """A working zone-2 encoder that BLOCKS for a fixed span, recording WHERE and
    WHEN it ran. `time.sleep` is the right stand-in for the property under test:
    on the loop thread it stops the loop exactly as CPU work would."""

    def __init__(self, seconds: float = BLOCK_S) -> None:
        self._seconds = seconds
        self.thread_ident: int | None = None
        self.entered_at: float | None = None
        self.exited_at: float | None = None

    def load(self) -> None:
        pass

    def count_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    def encode_passages(self, texts):
        self.thread_ident = threading.current_thread().ident
        self.entered_at = time.perf_counter()
        time.sleep(self._seconds)
        self.exited_at = time.perf_counter()
        return np.ones((len(texts), 4), dtype=np.float32) / 2.0


def _blocks(chars: int, *, per_block: int = 500) -> list[Block]:
    word = "كلمة "
    body = (word * (per_block // len(word) + 1))[:per_block]
    count = max(1, chars // per_block)
    return [Block(text=body, page=1 + i // 4, para=i % 4) for i in range(count)]


def _zone2_ingestor(encoder: _SleepingEncoder) -> DocumentIngestor:
    """Past the injection limit and under the maximum — the same sizing the
    existing zone-2 positive test uses, so this drives the real INDEX branch."""
    blocks = _blocks(int(50_000 / 0.358) + 20_000)

    async def extract(path):
        return blocks, ExtractReport(source=path.suffix, blocks=len(blocks),
                                     pages_total=None, pages_with_text=None,
                                     chars=sum(len(b.text) for b in blocks))

    return DocumentIngestor(policy=ZonePolicy(), encoder_factory=lambda: encoder,
                            extract=extract)


async def _wait_until_encoding(encoder: _SleepingEncoder, *, timeout: float = 5.0) -> None:
    """Yield to the loop until the encode is IN FLIGHT. Bounded, so a regression
    fails by assertion rather than hanging the suite."""
    deadline = time.perf_counter() + timeout
    while encoder.entered_at is None and time.perf_counter() < deadline:
        await asyncio.sleep(0.005)


# ───────────────────────── the property, driven directly ────────────────────

@pytest.mark.asyncio
async def test_the_encode_does_not_run_on_the_event_loop_thread() -> None:
    """The crispest statement of the fix: thread IDENTITY, no timing involved."""
    loop_thread_ident = threading.current_thread().ident
    encoder = _SleepingEncoder(seconds=0.0)

    outcome = await _zone2_ingestor(encoder).ingest(DOC)

    assert outcome.zone is DocZone.INDEX and outcome.ok
    assert encoder.thread_ident is not None, "the encode never ran"
    assert encoder.thread_ident != loop_thread_ident, (
        "the encode ran on the event-loop thread — the loop is blocked again")


@pytest.mark.asyncio
async def test_the_loop_stays_responsive_during_a_zone_2_ingestion() -> None:
    """THE ACCEPTANCE: a coroutine scheduled during the ingestion runs WHILE it is
    in progress. Asserted as an ORDERING — the probe's timestamp falls strictly
    between the encode's entry and exit — so it does not depend on any duration."""
    encoder = _SleepingEncoder()
    task = asyncio.create_task(_zone2_ingestor(encoder).ingest(DOC))
    try:
        await _wait_until_encoding(encoder)
        assert encoder.entered_at is not None, "the encode never started"
        probe_at = time.perf_counter()          # a coroutine running mid-ingestion
        assert encoder.exited_at is None, "the encode had already finished"
        outcome = await task
    finally:
        if not task.done():
            task.cancel()

    assert outcome.zone is DocZone.INDEX and outcome.ok
    assert encoder.entered_at < probe_at < encoder.exited_at, (
        "the probe did not run DURING the encode — the loop was blocked")


@pytest.mark.asyncio
async def test_the_responsiveness_probe_can_actually_detect_a_blocked_loop() -> None:
    """THE POSITIVE CONTROL. The test above must be able to FAIL, or it passes for
    free and this file certifies nothing — the defect family this project has now
    met repeatedly (DEC-50's cutoff rule, DEC-64 ruling 1). Here the same probe is
    driven against work deliberately left ON the loop, and it must NOT interleave."""
    stamps: dict[str, float] = {}

    async def blocking_on_the_loop() -> None:
        stamps["enter"] = time.perf_counter()
        time.sleep(BLOCK_S)                     # deliberately NOT off-loop
        stamps["exit"] = time.perf_counter()

    task = asyncio.create_task(blocking_on_the_loop())
    deadline = time.perf_counter() + 5.0
    while "enter" not in stamps and time.perf_counter() < deadline:
        await asyncio.sleep(0.005)
    probe_at = time.perf_counter()
    await task

    assert "exit" in stamps
    assert not (stamps["enter"] < probe_at < stamps["exit"]), (
        "the probe interleaved with loop-blocking work — it cannot discriminate, "
        "so the responsiveness test above proves nothing")


@pytest.mark.asyncio
async def test_a_cancelled_ingestion_returns_promptly_instead_of_waiting() -> None:
    """THE F9 PROPERTY, at the layer this file owns. A barge-in cancels the turn;
    before the fix the cancellation could not even be DELIVERED until the encode
    finished. Now the await is cancelled promptly while the worker finishes and its
    index is discarded — wasted work, and the correct trade."""
    encoder = _SleepingEncoder()
    task = asyncio.create_task(_zone2_ingestor(encoder).ingest(DOC))
    await _wait_until_encoding(encoder)
    assert encoder.entered_at is not None and encoder.exited_at is None

    task.cancel()
    started = time.perf_counter()
    with pytest.raises(asyncio.CancelledError):
        await task
    elapsed = time.perf_counter() - started

    assert elapsed < BLOCK_S / 2, (
        f"cancellation waited {elapsed:.3f}s for the encode — F9 is still blocked")


# ───────────────────────── nothing else changed ─────────────────────────────

@pytest.mark.asyncio
async def test_the_outcome_is_unchanged_by_the_offload() -> None:
    """A restored guarantee must not be a behaviour change. Same zone, same
    chunking, same index — the offload moves WHERE the work runs and nothing else."""
    encoder = _SleepingEncoder(seconds=0.0)

    outcome = await _zone2_ingestor(encoder).ingest(DOC)

    assert outcome.zone is DocZone.INDEX and outcome.ok
    assert outcome.note_ar is None
    assert outcome.index is not None and len(outcome.index) > 0
    assert outcome.chunks is not None and outcome.chunks.chunks == len(outcome.index)


@pytest.mark.asyncio
async def test_extraction_is_off_loop_too__the_sibling_this_fix_follows(monkeypatch) -> None:
    """CLOSING A REAL GAP, found by a SURVIVING MUTATION rather than by review.

    Moving `extract_blocks_async` back on-loop SURVIVED the first mutation run of
    this file. The mechanism was MEASURED, not guessed: every test here injects a
    fake `extract` coroutine, so the real function is never called. But the
    standing rule requires more than a mechanism — it requires a CONTROL showing
    the property is genuinely tested SOMEWHERE, and a sweep found **nothing
    anywhere asserting extraction runs off the loop.**

    So the survivor was not "unobservable"; it was UNGUARDED. That matters
    precisely here: `ingest.py`'s new comment cites this call as the precedent it
    follows, and a 228-page parse measured ~2.6 s at P0 — enough to stall the
    audio loop on its own. A precedent whose own property nothing checks is a
    precedent that can quietly stop being true.

    The idiom is `test_screen_capture.py::test_capture_offloads_blocking_work_to_thread`."""
    from muthis.broker.docs import extract as extract_mod

    loop_thread_ident = threading.current_thread().ident
    seen: dict[str, int | None] = {}

    def fake_extract_blocks(path, *, gap=None):
        seen["thread"] = threading.current_thread().ident
        return [], ExtractReport(source=".md", blocks=0, pages_total=None,
                                 pages_with_text=None, chars=0)

    monkeypatch.setattr(extract_mod, "extract_blocks", fake_extract_blocks)

    await extract_mod.extract_blocks_async(DOC)

    assert seen.get("thread") is not None, "extraction never ran"
    assert seen["thread"] != loop_thread_ident, (
        "extraction ran on the event-loop thread — a 228-page parse would stall "
        "the loop that also drives audio")


@pytest.mark.asyncio
async def test_the_bypassed_zones_still_never_touch_the_encoder() -> None:
    """The offload must not weaken the structural bypass `test_doc_ingest.py`
    pins: a zone-1 document still never CONSTRUCTS an encoder, and `to_thread`
    must not have hoisted the factory out of the INDEX branch."""
    def exploding_factory():
        raise AssertionError("a bypassed zone constructed the encoder")

    small = _blocks(2_000)

    async def extract(path):
        return small, ExtractReport(source=path.suffix, blocks=len(small),
                                    pages_total=None, pages_with_text=None,
                                    chars=sum(len(b.text) for b in small))

    outcome = await DocumentIngestor(policy=ZonePolicy(),
                                     encoder_factory=exploding_factory,
                                     extract=extract).ingest(DOC)

    assert outcome.zone is DocZone.INJECT and outcome.ok
