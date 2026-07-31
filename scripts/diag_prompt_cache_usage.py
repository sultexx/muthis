# scripts/diag_prompt_cache_usage.py
"""DIAG (V2 Phase 2 — prompt caching) — does `usage.input_tokens` INCLUDE or
EXCLUDE the cached portion? NEVER run in CI: it issues TWO BILLED calls.

WHY THIS SCRIPT EXISTS AT ALL, AND WHY IT IS COMMITTED RATHER THAN THROWN AWAY

The SDK documents `input_tokens` only as "the number of input tokens which were
used" and says nothing about whether the cached portion is included. The
asymmetry is itself evidence: `output_tokens_details` carries an EXPLICIT clause
("`output_tokens` remains the inclusive, authoritative total used for billing")
and no equivalent clause exists for `input_tokens` against the cache counters.

The DIRECTION of that silence decides whether Rule 10 keeps working:

  EXCLUDES -> the naive formula charges only fresh input; cache reads (0.1x) and
              writes (1.25x / 2x) are charged NOTHING. The ledger UNDER-reports
              and the sovereign ceiling is breached SILENTLY -- Rule 10 fails
              OPEN, which is strictly worse than stopping early.
  INCLUDES -> cached tokens are charged at full rate though billed at 0.1x. The
              ledger OVER-reports and sessions stop early -- Rule 10 fails closed.

MEASURED 2026-07-31 on claude-sonnet-4-6: it EXCLUDES, and it excludes the WRITE
as much as the read. Under-report 25x on a read, 301x on a write, and the write
is the FIRST turn of every session.

It is committed because pricing in `cloud/pricing.py` is built ON that direction.
Re-run it whenever vendor pricing moves, the SDK's Usage model changes, or the
model is re-pinned -- a silent flip of this answer would silently un-defend the
ceiling, and nothing else in the suite would notice.

METHOD -- and every part of it is load-bearing

  * DRIVEN THROUGH THE PRODUCTION READ SITE. claude_agent.py reads
    `event.message.usage` at `message_start` of a STREAM. A non-streaming
    `messages.create()` would settle the arithmetic while proving nothing about
    whether the counters are populated where the seam actually reads, so both
    calls stream and the message_start usage is what is printed (DEC-12: drive
    the real path, never an equivalent-looking one).
  * THE THIRD NUMBER IS FREE. `count_tokens` returns the cache-blind total, which
    turns a comparison into an IDENTITY: input_tokens + cache_read == total means
    EXCLUDES; input_tokens == total means INCLUDES.
  * THE PREFIX IS DETERMINISTIC AND WELL ABOVE THE MINIMUM. Sonnet 4.6 will not
    cache a prefix under 1024 tokens, and it does so SILENTLY
    (cache_creation_input_tokens: 0, no error). A run that never cached would
    otherwise look like a run that answered -- the DEC-50 failure mode -- so a
    zero cache read is reported as INCONCLUSIVE and exits non-zero rather than
    resolving a direction.

Run:  python scripts/diag_prompt_cache_usage.py
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from dotenv import load_dotenv

load_dotenv()  # Law 5.1: .env before any import that reads keys

from anthropic import AsyncAnthropic  # noqa: E402

MODEL = "claude-sonnet-4-6"  # what Mut'his actually runs (DEFAULT_MODEL)
MAX_TOKENS = 16              # the reply is irrelevant; only `usage` is measured

# Byte-stable filler. Any drift between call 1 and call 2 invalidates the prefix
# and the READ never happens, so this is built from one repeated literal rather
# than anything derived from the clock, the environment, or dict ordering.
_UNIT = (
    "Mut'his is an Arabic-first voice sidekick for Windows 11. It speaks and "
    "points at on-screen UI elements with a cyan rectangle overlay. It never "
    "clicks, types, presses hotkeys, or touches the clipboard. This sentence "
    "exists only to build a deterministic cacheable prefix for a measurement. "
)
BIG_PREFIX = _UNIT * 120  # ~7.9k tokens, far above the 1024-token minimum


def _request() -> dict:
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": [{
            "type": "text",
            "text": BIG_PREFIX,
            "cache_control": {"type": "ephemeral"},
        }],
        "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
    }


def _dump(usage) -> str:
    return json.dumps(usage.model_dump(exclude_none=False), ensure_ascii=False, indent=2)


async def _one_call(client: AsyncAnthropic, label: str) -> dict:
    """Stream one turn and capture usage AT message_start — the production site."""
    start_usage = None
    async with client.messages.stream(**_request()) as stream:
        async for event in stream:
            if event.type == "message_start":
                start_usage = event.message.usage
        final = await stream.get_final_message()

    print(f"\n=== {label} ===")
    print("usage AT message_start (what claude_agent.py reads):")
    print(_dump(start_usage))
    print("usage on the final message:")
    print(_dump(final.usage))
    return {
        "input_tokens": start_usage.input_tokens,
        "cache_creation": start_usage.cache_creation_input_tokens or 0,
        "cache_read": start_usage.cache_read_input_tokens or 0,
    }


async def main() -> int:
    client = AsyncAnthropic()

    counted = await client.messages.count_tokens(
        model=MODEL,
        system=_request()["system"],
        messages=_request()["messages"],
    )
    total = counted.input_tokens
    print(f"count_tokens (FREE, cache-blind) total prompt = {total} tokens")

    c1 = await _one_call(client, "CALL 1 — expect cache WRITE")
    # Call 1 has fully completed, so the entry is readable and call 2 is safe to
    # fire immediately (a cache entry becomes readable once the first response
    # has begun streaming — parallel calls would all miss).
    c2 = await _one_call(client, "CALL 2 — expect cache READ")
    await client.close()

    print("\n=== ARITHMETIC ===")
    print(f"count_tokens total prompt          = {total}")
    print(f"call 1 cache_creation_input_tokens = {c1['cache_creation']}")
    print(f"call 2 input_tokens                = {c2['input_tokens']}")
    print(f"call 2 cache_read_input_tokens     = {c2['cache_read']}")
    print(f"input_tokens + cache_read          = {c2['input_tokens'] + c2['cache_read']}")

    if c2["cache_read"] == 0:
        print("\nINCONCLUSIVE: no cache read happened — the prefix never cached.")
        print("Do NOT read a direction out of this run (the DEC-50 rule: a check")
        print("that examined nothing must never look like a check that passed).")
        return 2

    includes = abs(c2["input_tokens"] - total) <= 2
    excludes = abs((c2["input_tokens"] + c2["cache_read"]) - total) <= 2
    print("\n=== VERDICT ===")
    if excludes and not includes:
        print("input_tokens EXCLUDES the cached portion.")
        print("=> pricing input_tokens ALONE UNDER-reports; Rule 10 fails OPEN.")
        print("=> cloud/pricing.py MUST add the cached tokens back at their own")
        print("   rates. This is the direction the shipped pricing assumes.")
        return 0
    if includes and not excludes:
        print("input_tokens INCLUDES the cached portion.")
        print("=> THE SHIPPED PRICING IS NOW WRONG and double-counts the cache.")
        print("=> Treat as a DEFECT in cloud/pricing.py, not as a new baseline.")
        return 1
    print("AMBIGUOUS — neither identity holds. STOP and log; do not implement.")
    return 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
