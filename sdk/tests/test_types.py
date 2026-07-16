# sdk/tests/test_types.py
"""muthis-sdk value types: the closed capability enum + contract defaults."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from muthis_sdk import (
    CAPABILITIES,
    PluginContext,
    ServiceOutcome,
    ToolDescriptor,
    ToolPlugin,
    ToolResult,
)


def test_capability_enum_is_closed_and_look_only():
    """The golden rule §1.1: input-control capabilities DO NOT EXIST."""
    assert "perceive.files.read" in CAPABILITIES
    assert "sandbox.execute" in CAPABILITIES
    for forbidden in ("input.mouse", "input.keyboard", "clipboard.write"):
        assert forbidden not in CAPABILITIES
    with pytest.raises(AttributeError):
        CAPABILITIES.add("input.mouse")  # frozenset: no mutation path at all


def test_descriptor_defaults_and_immutability():
    d = ToolDescriptor(name="read_local_file", schema={"name": "read_local_file"})
    assert d.read_only is True
    assert d.kernel_serviced is False
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.name = "other"  # type: ignore[misc]


def test_service_outcome_phase1_fields_default_inert():
    out = ServiceOutcome(result=ToolResult(text_ar="تم"), provenance="core:file_read")
    assert out.taint is False and out.cost_usd is None and out.extras == {}


def test_tool_plugin_contract_round_trip():
    """A minimal ToolPlugin subclass satisfies the ABC and returns ToolResult."""

    class Echo(ToolPlugin):
        def descriptors(self):
            return [ToolDescriptor(name="echo", schema={"name": "echo"})]

        async def execute(self, tool, args, ctx):
            assert isinstance(ctx, PluginContext)
            return ToolResult(text_ar=f"صدى: {args.get('x', '')}")

    result = asyncio.run(Echo().execute("echo", {"x": "1"}, PluginContext()))
    assert isinstance(result, ToolResult) and result.is_error is False
