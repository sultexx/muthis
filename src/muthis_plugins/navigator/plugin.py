# src/muthis_plugins/navigator/plugin.py
"""NavigatorPlugin — the two mode verbs, DECLARED here and SERVICED by the
kernel (DEC-73's ruling, the `request_screen_refresh` pattern).

kernel_serviced: the state these verbs change is the KERNEL'S — the mode frame,
the plan, the step number. A plugin holding it would make "step 3 of 5" a
PLUGIN'S CLAIM, which is the whole thing DEC-65 exists to prevent. So this
package contributes two schemas and nothing else: no state, no transition, no
note. `execute` is unreachable in production and returns the same refusal every
declaration plugin returns."""

from __future__ import annotations

from typing import Any

from muthis_sdk import PluginContext, ToolDescriptor, ToolPlugin, ToolResult

from ..common import KERNEL_SERVICED_AR
from .schema import NAVIGATOR_PLAN_SCHEMA, NAVIGATOR_STEP_SCHEMA


class NavigatorPlugin(ToolPlugin):
    def descriptors(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="plan",
                schema=NAVIGATOR_PLAN_SCHEMA,
                read_only=True,
                kernel_serviced=True,
            ),
            ToolDescriptor(
                name="step",
                schema=NAVIGATOR_STEP_SCHEMA,
                read_only=True,
                kernel_serviced=True,
            ),
        ]

    async def execute(self, tool: str, args: dict[str, Any], ctx: PluginContext) -> ToolResult:
        return ToolResult(text_ar=KERNEL_SERVICED_AR, is_error=True)
