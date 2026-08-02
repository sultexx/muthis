# tests/test_pass_servicing.py
"""
The DEC-73 extraction's equivalence proof, and the invariant it could have broken.

A BEHAVIOUR-IDENTICAL REFACTOR IS NOT A BYTE-IDENTICAL MOVE, so it cannot be
proven by `git diff` the way `records.py`, `transport.py` and `router_surfaces.py`
were. It is proven by the INVARIANT'S SHAPE instead — the `mount()` precedent:

  1. THE RECORD CARRIES EXACTLY WHAT THE TUPLE CARRIED. Constructed both ways,
     compared field by field. A field silently dropped or reordered during the
     extraction fails here and nowhere else, because every other test reads the
     fields by name and would never notice a missing one.
  2. THE ORDER IS UNCHANGED. The precondition is serviced BEFORE the read —
     `docs__query` depends on the index `docs__open` builds — so an extraction
     that reordered them would answer the query against nothing. That invariant
     already has an end-to-end test in `test_doc_servicing.py`, driven through
     the new path unchanged; here it is driven against THIS module directly, so
     a future edit to the loop is caught at its own door.

THE EMPTY RECORD IS PART OF THE CONTRACT. A pass that serviced nothing returns
`PassServiced()` rather than None, so no consumer branches on absence — the
`SessionTaint` discipline, where an optional-and-silently-absent seam is the
failure mode itself.
"""

from __future__ import annotations

import asyncio
import dataclasses

from muthis.cloud.protocol import ToolCall
from muthis.kernel.pass_servicing import PassServiced, service_pass_calls
from muthis.kernel.turn import TurnResult


class _Outcome:
    def __init__(self, text, taint=False, provenance="test"):
        self.result = type("R", (), {"text_ar": text})()
        self.taint = taint
        self.provenance = provenance


class _Router:
    """Records the ORDER it was asked in — the thing the extraction could break."""

    def __init__(self, taint=False):
        self.calls: list[str] = []
        self._taint = taint

    async def service(self, name, args):
        self.calls.append(name)
        return _Outcome(f"serviced:{name}", taint=self._taint)


class _Sandbox:
    def __init__(self):
        self.ran = []

    async def run(self, args):
        self.ran.append(args)
        return "ran"


def _call(name, tool_use_id):
    return ToolCall(name=name, args={}, tool_use_id=tool_use_id)


def _service(**kw):
    defaults = dict(router=_Router(), sandbox=None, result=TurnResult(),
                    precondition=None, read=None, run=None)
    defaults.update(kw)
    return asyncio.run(service_pass_calls(**defaults))


# ── 1. THE RECORD CARRIES EXACTLY WHAT THE TUPLE CARRIED ────────────────────

def test_the_record_holds_the_SAME_two_values_the_tuple_held():
    """Field-by-field, against the tuple this replaced. The old shape was
    `(read_results, run_result)` in that order, and both are still here."""
    router, sandbox = _Router(), _Sandbox()
    open_call, run_call = _call("docs__open", "d1"), _call("sandbox__run_code", "r1")

    serviced = _service(router=router, sandbox=sandbox,
                        precondition=open_call, run=run_call)

    # The tuple, as `consume()` used to build it, from the same inputs.
    old_read_results = [(open_call, "serviced:docs__open")]
    old_run_result = (run_call, "ran")

    assert list(serviced.read_results) == old_read_results
    assert serviced.run_result == old_run_result
    # ...and NOTHING ELSE is in the record, so a field cannot be added without a
    # deliberate edit to this assertion (the shape is the contract).
    assert [f.name for f in dataclasses.fields(PassServiced)] == [
        "read_results", "run_result"]


def test_a_pass_that_serviced_NOTHING_returns_the_empty_record_not_None():
    serviced = _service()

    assert isinstance(serviced, PassServiced)
    assert serviced.read_results == () and serviced.run_result is None


def test_the_record_is_FROZEN_so_a_consumer_cannot_edit_what_a_pass_serviced():
    serviced = _service()

    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        serviced.run_result = ("x", "y")        # type: ignore[misc]


# ── 2. THE ORDER IS THE INVARIANT ───────────────────────────────────────────

def test_the_PRECONDITION_is_serviced_BEFORE_the_read():
    """`docs__query` depends on the index `docs__open` builds. Serviced the other
    way round, the query answers against nothing — and it would look like a
    retrieval miss, which is the failure mode `doc_rag` is least able to see."""
    router = _Router()

    serviced = _service(router=router,
                        precondition=_call("docs__open", "d1"),
                        read=_call("docs__query", "d2"))

    assert router.calls == ["docs__open", "docs__query"]
    assert [c.tool_use_id for c, _ in serviced.read_results] == ["d1", "d2"]


def test_a_read_ALONE_is_still_serviced_when_there_is_no_precondition():
    """The positive control for the ordering test: without it, a loop that
    skipped the read entirely would still satisfy the assertion above."""
    router = _Router()

    serviced = _service(router=router, read=_call("read_local_file", "f1"))

    assert router.calls == ["read_local_file"]
    assert len(serviced.read_results) == 1


# ── 3. THE SIDE EFFECT THE EXTRACTION CARRIED WITH IT ───────────────────────

def test_taint_is_raised_on_the_TurnResult_exactly_as_before():
    """DEC-15's turn-level flag is set HERE, at the moment the provenance is
    known. An extraction that dropped it would leave a session looking clean
    while untrusted content flowed through it."""
    result = TurnResult()

    _service(router=_Router(taint=True), result=result,
             read=_call("web__fetch", "w1"))

    assert result.taint is True


def test_an_UNTAINTED_outcome_leaves_the_flag_alone():
    result = TurnResult()

    _service(router=_Router(taint=False), result=result,
             read=_call("read_local_file", "f1"))

    assert result.taint is False


def test_run_code_is_NOT_serviced_when_no_sandbox_is_composed():
    """`sandbox=None` means the tool is unavailable, never that it silently
    succeeded — the branch the extraction had to carry across intact."""
    serviced = _service(sandbox=None, run=_call("sandbox__run_code", "r1"))

    assert serviced.run_result is None
