"""
test_tool_envelope.py — the guard against a SILENTLY half-ported catalogue.

**THIS IS THE INVERSE OF DEC-11, AND THAT IS WHY IT IS A STRUCTURAL ASSERTION
RATHER THAN A ROUND TRIP.** DEC-11 was a LOUD failure: a dotted tool name
returned a live 400 that every offline test had passed, and the turn STOPPED —
the API was the guard. This provider will not do that. Measured live at DEC-88
①, each of these was ACCEPTED with no error at all:

  · `input_schema` present and `parameters` MISSING — the realistic half-port,
    where someone adds `type` and forgets the rename. The model is then handed a
    tool with NO DECLARED PARAMETERS and nothing anywhere says so.
  · `parameters` AND `input_schema` both present.
  · an outright nonsense key.
  · `strict` omitted although the SDK types it Required.

So there is no 400 to wait for and no exception to assert. **The only thing that
can notice is a test that compares the KEY SET EXACTLY** — which makes a missing
key and an extra key the same kind of failure, the one shape that catches a
half-port, because a half-port simultaneously drops `parameters` and keeps
`input_schema`.

EVERY ASSERTION RUNS OVER THE REAL ELEVEN-TOOL CATALOGUE, through the REAL
production mounts in production order (DEC-40, and `test_navigator_mount.py`'s
construction reused rather than re-typed). A hand-rolled two-tool list would
prove nothing about what production sends.

`VENDOR_ENVELOPE_KEYS` is IMPORTED, never re-typed here. A guard that spells out
its own copy of the contract passes forever after the contract changes.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from muthis.cloud.tool_envelope import (
    VENDOR_ENVELOPE_KEYS,
    VENDOR_STRICT,
    VENDOR_TOOL_TYPE,
    to_vendor_catalogue,
    to_vendor_envelope,
)
from muthis.composition import mount_doc_rag, mount_navigator, mount_web_research
from muthis.kernel.core_router import build_core_router
from muthis_plugins.doc_rag.plugin import DocRagPlugin
from muthis_plugins.navigator import NavigatorPlugin
from muthis_plugins.sandbox_exec import SandboxExecPlugin
from muthis_plugins.web_research.plugin import WebResearchPlugin

# The pattern DEC-11 was written from. Asserted again on the far side of the
# translation, because the translation touches the name field.
ANTHROPIC_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

# The byte-pinned catalogue, on disk — the one reference a process-global
# mutation cannot reach. See the no-mutation test for why that matters.
V7_SNAPSHOT = pathlib.Path(__file__).parent / "snapshots" / "look_tools_v7.json"


class _StubFetcher:
    async def fetch_readable(self, url):  # pragma: no cover — never called
        raise AssertionError("the envelope test must not fetch")


def _production_catalogue() -> list[dict]:
    """The eleven descriptors PRODUCTION shows the model, through the REAL mounts
    in production order: core four → sandbox → web → docs → navigator."""
    router = build_core_router(read_file=None)
    router.mount(SandboxExecPlugin(), namespace="sandbox", provenance="sandbox_exec")
    mount_web_research(router, WebResearchPlugin(), _StubFetcher())
    mount_doc_rag(router, DocRagPlugin())
    mount_navigator(router, NavigatorPlugin())
    return [descriptor.schema for descriptor in router.descriptors()]


# ═══ The positive control ════════════════════════════════════════════════════


def test_the_guard_is_looking_at_the_REAL_catalogue():
    """A CHECK WITH A CUTOFF MUST REPORT ITS ADMITTED COUNT (the DEC-50 standing
    rule). Every test below iterates the catalogue; an empty or truncated one
    would make all of them pass while examining NOTHING, which is
    indistinguishable from a healthy guard — and is exactly how the silent
    half-port gets through in the first place."""
    catalogue = _production_catalogue()
    assert len(catalogue) == 11, (
        f"the production catalogue is {len(catalogue)} tools, expected the v7 "
        "eleven — this guard's subject has moved and every assertion below is "
        "now measuring something else")
    assert {"highlight_target", "sandbox__run_code", "navigator__plan"} <= {
        tool["name"] for tool in catalogue}


# ═══ The envelope contract, asserted structurally ════════════════════════════


def test_every_translated_tool_has_EXACTLY_the_vendor_key_set():
    """THE CENTRAL GUARD. Exact equality, not a subset: `>=` would pass a
    catalogue carrying a leftover `input_schema` beside `parameters`, and `<=`
    would pass one missing the rename entirely. Both were measured ACCEPTED by
    the API, so this comparison is the only thing standing between a dropped
    field and a capability lost in silence for the whole process."""
    for tool in to_vendor_catalogue(_production_catalogue()):
        assert set(tool) == set(VENDOR_ENVELOPE_KEYS), (
            f"{tool.get('name')!r} translated to keys {sorted(tool)}, expected "
            f"exactly {sorted(VENDOR_ENVELOPE_KEYS)} — a missing key and an extra "
            "key are the SAME failure here, because this API reports neither")


def test_the_RENAME_happened_and_input_schema_is_GONE():
    """The half-port, named as its own test so a failure says which half broke.
    `input_schema` surviving into the request is the measured silent failure:
    accepted, ignored, and the tool arrives with no parameters."""
    for source, tool in zip(_production_catalogue(),
                            to_vendor_catalogue(_production_catalogue())):
        assert "input_schema" not in tool, (
            f"{tool['name']!r} still carries `input_schema` — the API ACCEPTS "
            "this and hands the model a tool with no declared parameters")
        assert tool["parameters"] == source["input_schema"], (
            f"{tool['name']!r} lost or altered its schema in translation")


def test_the_two_added_fields_carry_their_measured_values():
    """`type` is what the unmodified catalogue was REJECTED for
    (`Missing required parameter: 'tools[0].type'`), and `strict` is typed
    Required by the SDK while being accepted when absent — so neither may drift
    to a value nobody measured."""
    for tool in to_vendor_catalogue(_production_catalogue()):
        assert tool["type"] == VENDOR_TOOL_TYPE == "function"
        assert tool["strict"] is VENDOR_STRICT is False


def test_the_CONTENT_crosses_byte_identical_and_in_order():
    """The envelope is renamed; the catalogue is not re-authored. Name,
    description and order are what make a live result a statement about OUR
    catalogue rather than about the transform (the probe's own discipline)."""
    source = _production_catalogue()
    translated = to_vendor_catalogue(source)
    assert [t["name"] for t in translated] == [s["name"] for s in source]
    for original, tool in zip(source, translated):
        assert tool["name"] == original["name"]
        assert tool["description"] == original["description"]


def test_translation_NEVER_mutates_the_byte_pinned_catalogue():
    """`router.descriptors()` hands back the SAME dict objects on every call
    (DEC-59 Q3) and the plugin schemas are MODULE-LEVEL constants, so a write
    into one edits the model-visible catalogue for the whole PROCESS — the exact
    hazard `cache_control.py`'s copy discipline exists for. The schema is carried
    by REFERENCE here, which is safe only for as long as nothing writes.

    **THE REFERENCE IS THE SNAPSHOT ON DISK, AND THAT IS THE ENTIRE POINT.** The
    obvious form of this test — deepcopy the catalogue, translate, compare —
    SURVIVED the mutation that writes into the pinned schema, and it is worth
    naming why: the schemas are process-global, so an EARLIER test in this same
    file had already triggered the pollution, and the "before" snapshot faithfully
    captured the already-polluted state. The guard compared corruption against
    itself and reported success.

    A file on disk cannot be polluted by a test that ran first. That is what
    makes this assertion independent of execution order, and it is a fresh
    instance of the standing rule that a check able to pass without exercising
    its subject is not a check."""
    to_vendor_catalogue(_production_catalogue())
    # The canonical form is `test_navigator_mount.py`'s, letter for letter — two
    # guards comparing against one file must agree on how it is written.
    live = json.dumps(_production_catalogue(), ensure_ascii=False, indent=2) + "\n"
    assert live.encode("utf-8") == V7_SNAPSHOT.read_bytes(), (
        "the model-visible catalogue no longer matches look_tools_v7.json AFTER "
        "a translation — the translation wrote into a byte-pinned schema and "
        "changed what EVERY provider sees, for the rest of the process")


def test_translated_names_still_satisfy_the_DEC_11_pattern():
    """DEC-11's defect does not recur on this provider (`__` is legal there),
    but the translation touches the name field, and the catalogue is shared with
    a provider where the pattern IS enforced with a live 400."""
    for tool in to_vendor_catalogue(_production_catalogue()):
        assert ANTHROPIC_NAME_PATTERN.match(tool["name"]), tool["name"]


# ═══ A broken descriptor must fail LOUDLY ════════════════════════════════════


@pytest.mark.parametrize("missing", ["name", "description", "input_schema"])
def test_a_descriptor_missing_a_field_RAISES_rather_than_defaulting(missing):
    """The subscripts in `to_vendor_envelope` are deliberate. A `.get()` default
    would ship a nameless or parameterless tool that this API accepts without
    complaint — re-creating, inside our own code, the silence the module exists
    to close. Composition time is the right place to fail: before the loop
    opens, the same instant `assert_zone_invariant()` chooses."""
    broken = {k: v for k, v in _production_catalogue()[0].items() if k != missing}
    with pytest.raises(KeyError):
        to_vendor_envelope(broken)
